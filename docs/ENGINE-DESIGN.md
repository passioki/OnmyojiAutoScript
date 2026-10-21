# OAS 新引擎设计稿（ENGINE-DESIGN）—— **A（全重写）· Rust 双端**

> ★★★ **[10-15] 用户裁定（逐字）**：
> > "**可以改run的逻辑，咱们做干净开发，之前的任务可以在任务构建功能成熟后再重新构建。
> >   你甚至可以判断是否需要在现有基础开发，还是重新写。毕竟这个软件本质是通过
> >   OCR识别/模拟器键鼠接口调用/任务流程编辑/任务调度等功能模块协同实现的，
> >   一个最小的软件引擎，代码量应该不算大。咱们甚至可以从开发一款OCR识别点击编辑的
> >   角度出发，最好兼顾跨平台，如安卓等。**"
> > 路线选择："**A+ Rust 双端**"
>
> ★ **本文性质**：★ **设计稿**（★ 不含生产代码）。★ 审完再开工。
> ★ **旧仓库（`backend`/`frontend`）定位**：★ **冻结为"资产 + 游戏知识源"**，不再长新任务。

---

## 0. ★★ 一句话定义

> ★★ **OAS = 一个"手机/模拟器自动化引擎" + 一个"识别—编排—调试 编辑器"。**
> ★ **任务 = 数据**（`flow.json` + 素材），★ **不是代码**。

★ 依据（实测）：★ 现有 56 个任务共 **16,192 行** `script_task.py`，其中 **33/56 可由 3 组骨架表达**、
**9 个组队任务近乎逐行复制** ⇒ ★ 这些行是**内容**，不是引擎；★ 而引擎核心估 **5,000~8,000 行**。
★ **1,926 张 PNG + 2,539 处 ROI** 是**可移植的真实资产**（与引擎无关）。

---

## 1. ★★★ 目标 / 非目标

### 目标（P0~P4 全部达成才算完成）

| # | 目标 | 判据（可核查） |
|---|---|---|
| **G1** | ★ **引擎 = 6 个模块**，核心只依赖 2 个端口接口（`ScreenSource` / `InputSink`）| ★ 编译时无平台 `cfg` 泄漏进 core；★ core crate 不依赖 win32/android |
| **G2** | ★ **任务 = 声明式 `flow.json`**（受控指令集 + 解析式表达式，**无 eval**）| ★ 新建一个任务**零 Rust/零 Python**；★ 引用不存在的素材 ⇒ **保存时**报错 |
| **G3** | ★ **一次编写、双端运行**：同一份 `flow.json` + 素材在 **PC 与 Android** 都能跑 | ★ 同一 flow 两端跑通；★ DSL/素材/协议**零分支** |
| **G4** | ★★ **离线可验证**（录制回放）| ★ 录一轮 → 离线重放 ⇒ 动作序列一致；★ 改坏一处 ⇒ 回放**必红** |
| **G5** | ★ **调度可解释**（单一 `TaskUnit` + 单一状态机 + 单一存储）| ★ 39 个周期任务逐条"已完成/未完成 + 原因"可查；★ 卡住/预算耗尽**记失败** |
| **G6** | ★ **每一步可观测**（结构化日志：步骤/参数/结果/耗时）| ★ 任取一次失败 ⇒ ≤3 次点击定位到"第几步/哪张图/分数" |

### ★ 非目标（★ 本期明确不做，防"地基越做越大"）

* ★ 不移植旧的 56 个任务代码（★ 只迁移**素材**与**知识**；任务用编辑器重建）
* ★ 不做资源账本/优先级最优排程（P5 之后）
* ★ 不做多设备/多账号池
* ★ 不碰旧仓库的配置格式（★ 旧配置只作为"知识源"，不兼容）

---

## 2. ★★★ 总体架构

```
┌───────────────────────────── UI 层（Flutter，双端复用）─────────────────────────────┐
│  编辑器：截帧 · 框选 ROI · OCR/模板试识别 · 指令面板 · 流程编排 · 立即运行 · 日志/回放  │
└───────────────────────────────▲──────────────────────────────────────────────────────┘
                                │ ★ 进程内 FFI（flutter_rust_bridge）—— 双端零协议开销
┌───────────────────────────────┴──────────────────────────────────────────────────────┐
│                              oas-core（Rust，与 OS 无关）                              │
│  flow/ 指令集 + 解释器 + 表达式解析 + 预算/硬超时/重试      ← ★ 任务就是这里的输入     │
│  schedule/ TaskUnit + 状态机 + 单一状态存储 + 账本            ← ★ "完美调度"           │
│  perceive/ 模板匹配(NCC) + OCR(ONNX) + 页面识别              ← ★ 只吃帧，不碰设备       │
│  obs/ 结构化日志 + 录制/回放                                   ← ★ 验证与知识采集      │
│  ── 仅依赖两个 trait ──                                                                 │
│      trait ScreenSource { fn grab(&mut self) -> Frame; }                               │
│      trait InputSink    { fn click(..); swipe(..); key(..); text(..); drag(..); }      │
└──────────────▲───────────────────────────────────────────────▲───────────────────────┘
               │                                               │
   ┌───────────┴────────────┐                      ┌───────────┴────────────┐
   │ oas-adapter-pc         │                      │ oas-adapter-android    │
   │ capture: nemu_ipc /    │                      │ capture: MediaProjection│
   │          scrcpy / adb  │                      │ input:   Accessibility  │
   │ input:   minitouch /   │                      │          （手势注入）    │
   │          uiautomator2  │                      │ （JNI/NDK，可 adb-WiFi） │
   └────────────────────────┘                      └────────────────────────┘
```

★ **关键决定（★ 决定 Android 能不能做）**：
1. ★★ **core 不依赖 OpenCV、不依赖 Tesseract** —— ★ 模板匹配**纯 Rust 实现 NCC**（可移植、无 native 构建地狱）；
   ★ OCR 用 **ONNX Runtime（`ort` crate）** + RapidOCR 小模型（★ Android 有官方 mobile runtime）。
2. ★★ **UI 与引擎走进程内 FFI**（`flutter_rust_bridge`）⇒ ★ **Android 上就是"一个 Flutter App + Rust 库"**，不必起服务。
   ★ PC 侧另加一个瘦 `oasd`（headless CLI/daemon）供无人值守用。
3. ★ **协议（若需要跨进程）**：★ JSON over localhost WS；★ Android 默认不用（FFI）。

---

## 3. ★★★ DSL 规格（★ 最重要的"语言无关资产"）

### 3.1 文件位置与形态

```
tasks/<Name>/flow.json      ← ★ 一个任务的逻辑（= SPEC §1.17 NL5 的落点）
assets/<Name>.json          ← ★ 素材表（由编辑器生成，★ 不许手改）
meta.json                   ← ★ 调度元数据 = TaskUnit 声明（见 §5）
```

`flow.json`：
```json
{
  "schema_version": 1,
  "name": "Tako",
  "steps": [
    {"id": 1, "op": "wait_until", "args": {"cond": "appear('I_UI_BACK_RED')", "timeout_s": 20}},
    {"id": 2, "op": "if", "args": {"cond": "ocr('O_NUMBER') == 0"}, "then": [3], "else": [4]},
    {"id": 3, "op": "log", "args": {"level": "warn", "text": "没票了（本轮结束）"}},
    {"id": 4, "op": "loop", "args": {"n": "O_TARGET"}, "body": [5, 6]},
    {"id": 5, "op": "click", "args": {"sel": "I_FIRE"}, "on_error": "retry(3)"},
    {"id": 6, "op": "wait_battle_end", "args": {"hard_timeout_s": 180}}
  ]
}
```

### 3.2 ★ 指令集（初版 = SPEC §1.17 NL1，收紧为"可解释执行"）

| 类 | 指令 | 说明 |
|---|---|---|
| 流程 | `if/elif/else` · `loop(n)` · `while(cond)` · `break` · `continue` · `call(subflow)` | ★ 全部**结构化**，无 `goto` |
| 等待 | `wait(s)` · `wait_until(cond, timeout_s)` · `wait_battle_end(hard_timeout_s)` | ★★ **`timeout_s` 必填或取全局默认**（★ 治"无界等待"）|
| 识别 | `appear(sel)` · `detect(sel)` · `ocr(sel)` · `ocr_digit(sel)` · `ocr_counter(sel)` · `page()` | ★ 统一返回**结构化结果**（★ 不许"静默 0"）|
| 动作 | `click(sel)` · `long_click` · `swipe(sel_or_dir)` · `drag` · `key(key)` · `input_text` | ★ 全走 `InputSink` |
| 调试 | `log(level, text)` · `screenshot(tag)` | ★ **每条指令自动留痕**（步骤号/耗时/结果）|
| 出口 | `finish(exit)` | ★ `exit ∈ 8 类具名出口`（SPEC §1.19 C6）|

### 3.3 ★ 表达式（★ 解析式，**不用 eval**）

* ★ 支持：`appear('X')` · `ocr('X')` · `ocr_digit('X')` · `page() == 'battle'` · 数字/字符串字面量 · `+ - * / %` · `== != < <= > >=` · `and/or/not` · 括号。
* ★ **不支持**：赋值、函数定义、属性访问、任意函数调用 ⇒ ★ 从语法层就**不可能执行任意代码**。
* ★ 实现：Pratt parser（Rust，约 300~500 行）+ 类型检查（bool/number/string）。
* ★ **表达式里的素材名必须是本任务 `assets` 里的 id** ⇒ ★ 保存时校验（G2 判据）。

### 3.4 ★ 失败语义（★ 治"卡住记成功"）

* ★ 每条指令可带 `on_error`：`retry(n, backoff)` / `skip` / `abort` / `goto(step)`（★ 默认 `abort`）。
* ★★ **执行结束必须先算出一个 `Outcome`**（`Done` / `Failed` / `Exhausted` / `Skipped`…），
  ★ **只有 `Done` 进"已完成"**；★ `Exhausted`（预算/硬超时耗尽）★ **必须记失败**（★ 不许再"`except TaskEnd: return True`"）。
* ★ 全局**预算**：`TaskBudget { max_wall_s, max_steps, max_clicks }` ⇒ ★ 超限 ⇒ `Outcome::Exhausted`。

---

## 4. ★★ 素材格式（★ 可移植资产）

```json
{
  "schema_version": 1,
  "design_resolution": [1280, 720],
  "items": [
    {"id": "I_UI_BACK_RED", "kind": "template",
     "file": "images/I_UI_BACK_RED.png", "roi": [10, 20, 60, 60],
     "threshold": 0.85, "rev": 3},
    {"id": "O_NUMBER", "kind": "ocr_counter", "roi": [900, 30, 120, 30], "rev": 1}
  ]
}
```

* ★ **坐标体系写死 `design_resolution`**，★ 运行时**按实际帧比例缩放**（★ 治"只认 1280×720"的硬约束）。
* ★ 每个素材带 `rev`（修订号）⇒ ★ 改图后**能报"哪张图变了"**。
* ★★ **迁移来源**：★ 旧 `dev_tools/assets_extract.py` **本来就产出 JSON**（`tasks/<Name>/**/*.json` → `assets.py`）
  ⇒ ★ **素材迁移几乎是免费的**：★ 把旧 JSON 转成新格式 + 拷 PNG。
* ★ 阈值**分级可配**（`strict/normal/loose`），★ 不再散落 0.55~0.9。

---

## 5. ★★★ 调度模型（★ 统一 `TaskUnit`，旧双布局**不迁移**）

```rust
struct TaskUnit {
    task: String,                 // 任务名
    expire: Expire,               // Session | Daily | Weekly | Monthly | Never | At(ts)
    window: Option<Window>,       // 时段（可跨天）
    enqueue: Enqueue,             // Auto | Manual
    quota: Quota,                 // Counter{target} | Resource{kind,per_run} | None
    exit_map: ExitMap,            // Exit -> Outcome
}
```

### 5.1 ★ 状态机（★ `Outcome → 状态` 唯一映射）

```
 Idle ──(到点/资源够/窗口内)──▶ Ready ──(调度)──▶ Running
   ▲                                                │
   │                          ┌─────────────────────┤
   │                          ▼                     ▼
   │                    Done(计入完成)          Failed/Exhausted(★不计完成, 进冷却)
   │                          │                     │
   └────(过期: expire 判据)────┴─────────────────────┘
```

### 5.2 ★ 单一存储（★ 只有一套布局，无迁移桥）

```json
{
  "schema_version": 1,
  "units": {
    "<unit_key>": {"state": "done|failed|ready|running", "runs": 12, "target": 30,
                   "period_key": "2026-10-21", "outcome": "Done",
                   "updated_at": "…", "reason": "没票了"}
  },
  "loop": {"session_start": 1759…, "rounds": 3}
}
```
* ★★ `unit_key = entry_id or task`（两级），★ **只有一份**；★ 旧的两套布局**不迁移**（★ 干净开发）。
* ★ `schema_version` 从第 1 天就有；★ 升级时**一次迁移 + 报告逐字段 diff**。

---

## 6. ★★ 录制回放（★ P0 必须，因为它是"验证 + 知识采集"双重工具）

```json
{"schema_version": 1, "meta": {"task": "Tako", "started_at": "…", "design_resolution": [1280,720]},
 "frames": [{"i": 0, "ts": 0, "file": "frames/0000.png", "sha256": "…"}],
 "events": [{"i": 0, "step": 1, "op": "appear", "sel": "I_UI_BACK_RED", "score": 0.93, "result": "hit"}]}
```
* ★ **录**：每帧 + 每次识别结果 + 每个动作（★ 可与真机并行，开销可控）。
* ★ **放**：`ScreenSource::Replay` 用帧答 `grab()`；★ 断言**动作序列与事件序列一致**。
* ★★ **知识采集**：★ 录真机一轮 ⇒ ★ 自动生成 `flow.json` **草稿**（★ 把 56 个任务从"重写"降为"录+修"）。
* ★ 存储：★ `_replay/` **不进 git**（★ 大文件）；★ 只提交"断言帧 + 事件"用于回归。

---

## 7. ★ 工程结构（Rust workspace）

```
oas-core/                 ← ★ 与 OS 无关（不允许出现 win32/android 依赖）
  crates/
    oas-types/    (数据契约：Frame/TaskUnit/Outcome/Flow/Asset…)
    oas-perceive/ (NCC 模板匹配 + ort OCR + 页面识别)
    oas-flow/     (指令集 + 解释器 + 表达式 parser)
    oas-schedule/ (状态机 + 单一存储 + 账本/早报)
    oas-obs/      (结构化日志 + 录制回放)
    oas-core/     (组装 + 两个 trait 定义)
  adapters/
    oas-adapter-pc/      (nemu_ipc/scrcpy/adb + minitouch/uiautomator2)
    oas-adapter-android/ (MediaProjection + Accessibility, JNI)
  apps/
    oasd/         (PC headless daemon：HTTP/WS)
    oas-ffi/      (flutter_rust_bridge 绑定)
  editor/         (Flutter：PC + Android 共用)
```

★ **依赖红线**：★ `oas-core` **不许**依赖 `opencv` / `tesseract` / `winapi` / JNI；
★ 跨端差异**只允许**出现在 `adapters/*`。

---

## 8. ★★ 分期与判据

| 期 | 交付 | ★ 验收判据 |
|---|---|---|
| **P0** | ★ Rust workspace 骨架 + 两个 trait + **纯 Rust NCC** + `oas-obs` 录制回放 + PC `capture/input` | ★ 录一段真机 → 离线重放，★ 动作序列一致；★ NCC 在 1280×720 上 **单帧 ≤50ms**（50 个模板）|
| **P1** | ★ **编辑器 MVP** + `Tako` 样板（真素材）| ★ 界面里框选→试识别→生成指令→拼 10 步→**立即运行**→看步骤日志；★ 零代码 |
| **P2** | ★ **调度内核**（TaskUnit/状态机/单一存储/早报）| ★ 39 周期任务逐条状态可查；★ 卡住⇒失败+冷却；★ 重启不重打 |
| **P3** | ★ 迁移 **10 个高频任务**（御魂/觉醒/探索/突破/斗技/寮30/结界/逢魔/退治/花合战）| ★ 每个 = 1 份 flow + 1 份 assets；★ 与旧版差异**用回放逐条对比** |
| **P4** | ★ **Android 引擎**（同 DSL/素材/UI）| ★ 同一 `flow.json` 在 Android 跑通 |

---

## 9. ★★ 风险与对策

| # | 风险 | 对策 |
|---|---|---|
| 1 | ★★ **游戏知识迁移**（16k 行里的隐性知识）| ★ **P0 的录制→生成 flow 草稿**；★ 旧 `docs/flows/*.md` 是**天然需求文档** |
| 2 | ★ Rust + ONNX 的 Android 交叉编译 | ★ **不引 OpenCV**（纯 Rust NCC）；★ `ort` 用官方 mobile 预编译；★ Adapter 隔离 |
| 3 | ★ Android **反自动化识别**（无障碍服务特征）| ★ P4 才做；★ 先把 PC 版做扎实；★ 保留 adb-WiFi 作为备选通道 |
| 4 | ★ 双端行为不一致 | ★ **DSL/素材/协议零分支**；★ 回放断言在两端都跑 |
| 5 | ★ 一次性重写导致"长期不能用" | ★ 旧仓库**冻结但可用**（回退路径）；★ P3 每迁一个任务就多一个可用任务 |
| 6 | ★ 设计过度 | ★ 本文**只覆盖 P0/P1 的接口**；★ P5+（资源账本/多账号）**不写** |

---

## 10. ★★ 开放问题（需用户裁定）

1. ★★ **新仓库位置**：★ 建议 `<WORKSPACE>/oas-core`（新 git 仓库）⇒ ★ 需要你建 GitHub 仓库（或先本地建、后推）。
2. ★ **Rust 工具链**：★ 本机需装 `rustup` + VS Build Tools（★ 已装 VS 2022）⇒ ★ 我可自查安装。
3. ★ **Flutter 复用**：★ 编辑器沿用现有 `OASX`（Flutter 3.27.1）还是新起一个精简 App？
   ★ 建议：★ **新起精简 App**（★ 旧前端 1.9k 行 UI 与旧后端 schema 深度耦合）。
4. ★ **旧仓库的处置**：★ 建议 ★ `backend` **只读冻结**（不再提交新功能），★ 保留其 git 历史与 `docs/flows/*.md` 作为知识源。
5. ★ **P0 的样板设备**：★ 用本机 MuMu（`127.0.0.1:16384`）还是等你准备好账号？（★ 回放可用**旧截图**做种子，不必等账号）
