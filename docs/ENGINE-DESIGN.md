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

## 10. ★★★ 输入 / 截屏通道矩阵（★ 用户提问后新增）

> ★★ **用户原话**：
> > "**对于安卓自动化检测，我记得有一种是通过系统注入实现，可以不用无障碍服务，是否有这样的。**"
>
> ★ **答：有，而且不止一种。** ★ 这直接决定 `InputSink` 不能只做一种实现，必须是**可插拔后端 + 能力协商**。

### 10.1 ★ 输入后端（★ 按"是否需要无障碍"分类）

| # | 后端 | 实现位置 | 依赖 | 延迟/精度 | ★ 无障碍? |
|---|---|---|---|---|---|
| **A** | ★★ **模拟器自身接口**（nemu_ipc / 窗口消息）| **PC 侧** | 模拟器 | ★ 最好（毫秒级、多点）| ★ ✗ 且 **Android 侧看不到注入痕迹** |
| **B** | **adb `input`**（tap/swipe/text/keyevent）| PC → adb → Android InputManager | adb 调试 | ★ 差（★ 每次拉起进程 ~100-300ms）| ★ ✗ |
| **C** | ★ **minitouch / `sendevent`**（写 `/dev/input/event*`）| 设备内 native 二进制 + socket | shell（或 root） | ★ 好（低延迟、多点/压力）| ★ ✗ |
| **D** | ★ **scrcpy-server**（内部 `InputManager.injectInputEvent`）| 设备内 java(`app_process`) + adb | shell | ★ 好 | ★ ✗（走隐藏 API，不是无障碍）|
| **E** | ★★ **系统注入 / root**（Xposed / Frida / Magisk 模块 / 系统签名 app 持 `INJECT_EVENTS`）| 设备内 | ★ **root / 定制 ROM / 系统签名** | ★ 最好，可无 adb 常驻 | ★ ✗ —— ★★ **这就是你记的"系统注入"** |
| **F** | UiAutomation（uiautomator2 / atx-agent）| 设备内 | shell | ★ 中 | ⚠ ★ **底层就是 AccessibilityManager** ⇒ ★ **属于无障碍路线，不是你要的** |

### 10.2 ★ 截屏后端（同理）

| # | 后端 | 依赖 | 备注 |
|---|---|---|---|
| **a** | ★ 模拟器 IPC 帧（nemu_ipc / 共享内存）| 模拟器 | ★ PC 首选，最快 |
| **b** | adb `exec-out screencap -p` | adb | ★ 通用但慢（~100ms+）|
| **c** | scrcpy 视频流 | adb | ★ 最快之一（H.264 解码）|
| **d** | Android `MediaProjection` | 用户授权一次 | ★ 原生 App 用；★ 授权弹窗需处理 |
| **e** | root framebuffer（`/dev/graphics/fb0`）| root | ★ 兜底 |

### 10.3 ★ 引擎设计结论（★ 落到代码结构）

```rust
/// ★ 不是"一个 InputSink"，而是"后端集合 + 能力协商"
pub trait InputSink {
    fn caps(&self) -> InputCaps;      // 多点? 压力? 文本? 按键? 延迟?
    fn click(&mut self, p: Point) -> Result<()>;
    fn swipe(&mut self, from: Point, to: Point, ms: u32) -> Result<()>;
    fn drag(&mut self, from: Point, to: Point, ms: u32) -> Result<()>;
    fn key(&mut self, key: Key) -> Result<()>;
    fn text(&mut self, s: &str) -> Result<()>;
}
/// ★ 启动时按"优先级 + 可用性"探测并选择；★ 后端可在 UI 里显式指定
pub enum InputBackend { EmulatorIpc, AdbInput, Minitouch, Scrcpy, RootSystem, UiAutomation }
```

* ★★ **`flow.json` 里不写"用哪个后端"** —— ★ 后端是**部署配置**，不是任务逻辑
  ⇒ ★ 同一份 flow 在 PC/模拟器/真机都能跑（★ 满足 G3）。
* ★ **探测顺序（建议）**：★ `EmulatorIpc` → `Scrcpy` → `Minitouch` → `AdbInput` → `RootSystem` → `UiAutomation`（★ 最后才用无障碍）。
* ★ **UI 必须能显示"当前用的是哪个后端 + 它的能力"**（★ 排查问题时第一句话就是这个）。

### 10.4 ★ 风险因子（★ 实现前必须评估，不是"绕过指南"）

★ 不同后端在**可观测性**上不同，风险因子包括（★ 仅列出，供选型时权衡）：

| 因子 | 会被谁看到 |
|---|---|
| 无障碍服务已启用 | ★ 系统设置 / 部分应用会读 `enabled_accessibility_services` |
| adb 调试已开启 / adb 常驻 | ★ `ADB_ENABLED` 等系统设置 |
| 注入事件来自"虚拟设备" | ★ 事件对象上的 `deviceId` / `source` 等属性 |
| 设备已 root / 装框架 | ★ root 检测、完整性检测 |
| 截屏方式 | ★ `MediaProjection` 授权会留痕 |

★ **工程结论**：★ **PC + 模拟器（后端 A/a）在可观测面上最干净、也最快** ⇒ ★
**P0~P3 全部走模拟器**；★ **真机 Android（P4）再在这几个后端里按你的设备条件选**。

---

## 11. ★★ 开放问题 —— ★★ [10-15] 用户已全部裁定（存档）

| # | 问题 | ★★ 用户裁定（逐字/要点） | 落地动作 |
|---|---|---|---|
| **1** | 新仓库位置 | ★ "**1先本地、后推**" | ★ 本地建 `<WORKSPACE>/oas-core`（`git init`），★ 稳定后再推 GitHub |
| **2** | Rust 工具链 | ★ "**2你装**" | ★ 我装：`rustup` + `stable-x86_64-pc-windows-msvc`（★ 依赖已装的 VS 2022 BuildTools）· ★ **本机原本没有 cargo/rustc**（实测 False/False）|
| **3** | 编辑器是否复用 OASX | ★ "**3新写**" | ★ 新起精简 Flutter App；★ 旧 `frontend` 不再演进 |
| **4** | 旧仓库处置 | ★ "**4好的**" | ★ `backend`/`frontend` **只读冻结**（★ 保留 git 历史 + `docs/flows/*.md` 作为需求文档）|
| **5** | P0 样板设备 | ★ "**5账号已备好，现在运行着的就是**" | ★ P0 直接对**当前运行中的设备**做录制（★ 不必等账号、也不必用旧截图做种子）|
| **6** | ★ 输入通道（新增）| ★ 用户问"有没有不用无障碍的系统注入" | ★ 有（见 **§10**）：★ PC 模拟器走后端 **A**（最干净）；★ 真机可选 **D scrcpy / C minitouch / E root 系统注入**；★ `UiAutomation` 才是无障碍路线 ⇒ 默认不用 |

★ **剩余待确认（不阻塞 P0）**：
1. ★ **GitHub 仓库名**（推的时候需要）：建议 `oas-core`。★ **[10-15] 用户已确认："1好的"** ⇒ 仓库名 = **`oas-core`**。
2. ★ **编辑器技术栈** ⇒ ★★ **[10-15] 已定案：Tauri v2 + 静态 HTML/JS**（见 **§12**）。
3. ★ **P0 先录哪个任务**：★ **[10-15] 用户"3你看着办"** ⇒ ★ **`Tako`（石距）** —— 单轮直线、无主循环。

---

## 12. ★★★ 编辑器技术栈（★ [10-15] 用户："我其实零经验，看哪种更好用就用哪种吧，你介绍下"）

### 12.1 ★ 本机实测约束（★ 选型必须先看这个）

| 项 | 实测 | 影响 |
|---|---|---|
| ★ `node` / `npm` / `pnpm` / `npx` | ★ **全部缺失** | ★ 任何需要 Node 的方案都要**额外装一条工具链** |
| ★ **WebView2** | ★ **已存在**（`C:\Program Files (x86)\Microsoft\EdgeWebView\Application`）| ★ Tauri **开箱可用** |
| ★ Rust | ★ **已装**（`cargo/rustc 1.99.1` · MSVC）| ★ 引擎侧就绪 |
| ★ Flutter 3.27.1 | ★ 已装（`D:\flutter3271`）| ★ 但旧 `OASX` 被冻结，无复用价值 |
| 磁盘 | D 45.5 GB · E 26.2 GB | ★ 充裕 |

### 12.2 ★ 候选对比

| 方案 | 额外依赖 | 与 Rust 集成 | UI 表达力（ROI/截图/日志）| Android 路线 | 结论 |
|---|---|---|---|---|---|
| ★★ **Tauri v2 + 静态 HTML/JS** | ★ **零**（WebView2 已有）| ★★ **Tauri command 就是 Rust 函数**，★ **零 FFI 代码生成** | ★★ web canvas 最强 | ★ v2 官方支持（需 Android SDK/NDK）| ✅ **选它** |
| Tauri v2 + React/Vite | ★ 需 Node | ★★ 同上 | ★★ 同上 + 组件生态 | ★ 同上 | ⏸ 以后想升级再加构建链 |
| Flutter + flutter_rust_bridge | ★ Flutter 已有 | ⚠ 需 **代码生成 + 每平台 FFI 构建** | ★ 中上（CustomPaint）| ★★ 最成熟 | ⏸ 备选 |
| egui / eframe | ★ 零 | ★★ 纯 Rust | ★ 中（UI 朴素，★ **中文 IME 弱**）| ★ 可用但小众 | ⏸ 只适合内部调试工具 |
| Electron | ★ 需 Node + 体积大 | ⚠ 需 sidecar/stdio | ★★ | ⚠ 弱 | ❌ 否决 |

### 12.3 ★★ 定案与理由

> ★★ **编辑器 = Tauri v2 + 静态 HTML/JS（不引 Node/npm）**

1. ★★ **引擎本来就是 Rust** ⇒ ★ Tauri 的 command **直接就是 Rust 函数**，★ **省掉整整一层 FFI 代码生成**
   （对比 Flutter 需要 `flutter_rust_bridge` codegen + 每平台构建配置）。
2. ★★ **UI 是 web** ⇒ ★ **框选 ROI / 缩放平移 / 日志面板 / 指令表格** 都是 canvas+DOM 的强项，
   ★ 而且 ★ **未来 Android 可以把同一份静态 UI 原样包进 WebView** ⇒ ★ **UI 资产跨端不重写**。
3. ★★ **依赖最少**：★ 本机 **只有 Rust + WebView2**，★ **不需要 Node / 不需要 Flutter 桌面构建**。

### 12.4 ★ 风险与回退

* ⚠ ★ **Tauri v2 的 Android 支持较新** ⇒ ★ P4 才需要（且要装 Android SDK/NDK）。
  ★ **回退路径**：★ UI 是纯静态 web ⇒ ★ 最坏情况用"极简 Android WebView 壳 + Rust 引擎经 JNI"包装，★ **UI 不用重写**。
* ⚠ ★ 无框架 ⇒ 手写 DOM 略啰嗦 ⇒ ★ 若后期真需要组件生态，★ **加 Vite/React 只是构建链变化，架构不变**。

---

## 13. ★★ P0 进度（★ 已开工）

| 步 | 内容 | 状态 | 证据 |
|---|---|---|---|
| **P0-1** | ★ 本地 `oas-core` 仓库 + cargo workspace + `oas-types`（数据契约）| ✅ **已完成** | ★ `cargo build` 通过 · `cargo test` **2 passed** · ★ 首次提交 **`7588c96`**（`git init -b main`，本地先行）|
|  | ★★ **`Exit`（8 类）→ `Outcome`（3 态）唯一映射**（★ 已落地：`Exhausted ≠ Done`，★ 直接堵死旧的 `except TaskEnd: return True`）| ✅ | `crates/oas-types/src/lib.rs` |
|  | ★ `Expire`（Session/Daily/Weekly/Monthly/Never）—— ★ **周期/临时统一的第一块砖** | ✅ | 同上 |
|  | ★ `ScreenSource` / `InputSink` 两个端口 trait（★ core 唯一允许的平台边界）| ✅ | 同上 |
|  | ★ **依赖红线**：`oas-types` **零依赖**（无 winapi/JNI/opencv）| ✅ | `Cargo.toml` |
| **P0-2** | ★ 纯 Rust NCC 模板匹配（`crates/oas-perceive`）| ✅ **已完成（正确性）/ ⚠ 性能待优化** | ★★ **等价性已验证**：`cargo test --release` ⇒ **`equivalence OK: 4 cases match OpenCV within 1e-4`**（★ 分数差 <1e-4、★ 最佳位置**完全一致**）—— ★ 参照值由 `tools/refgen_cv2.py` 用 **cv2 4.7.0 `TM_CCOEFF_NORMED`** 生成（synthetic 4 例：exact / noisy / absent / crop）<br>★ 实现方式：**精确整数形式**（无浮点舍入）+ **积分图**（窗口 `ΣI/ΣI²` O(1)）+ 行内 `i32` 累加<br>★★ **修掉一个自己引入的性能 bug**：最初**每个模板都重建一次全帧积分图** ⇒ 12.00ms/模板；★ 改为 **`Matcher` 每帧建一次、所有模板复用** ⇒ **3.72ms/模板**（50 模板 186ms）<br>⚠ **与 OpenCV 仍有差距**：★ cv2 同工作量 **0.29ms/模板**（50 模板 14.3ms）⇒ Rust 约 **12.8×** 慢 ⇒ ★ **P0-2b：AVX2（x86）/ NEON（ARM）SIMD 点积 + 粗到精搜索** |
| **P0-2b** | ★ SIMD / 粗到精优化（目标：≤1ms/模板）| ⬜ 下一步 | ★ 判据：50 模板 ≤50ms（即 ≤1ms/模板）；★ **优化后等价性测试必须仍然通过** |
| **P0-3** | ★ 录制回放 | ⬜ 下一步 | 判据：动作序列逐条一致 |
| **P0-3a** | ★ **`oas-adapter-pc`**：`AdbCapture`（`exec-out screencap -p` + **纯 Rust `png` 解码**）+ `AdbInput`（`input tap/swipe/keyevent`）+ 设备枚举**去重** | ✅ **已完成** | ★★ **真机实测（`cargo run -p oasd -- probe`）**：★ `device: serial=127.0.0.1:16384 unique=android_id:657eef8300229911` · ★ **`of 1 deduped endpoint(s)`**（★ 两个 adb 入口正确合并成 1 台）· ★ `captured frame: 1280x720 rgba_bytes=3686400` · ★ 回写 PNG 与 adb 直采一致 · ★ 单元测试 **2 passed** |
| **P0-4** | ★ PC adapter（模拟器 IPC 截图+点击）| ✅ **已完成**（★ 用 adb 通道，见 §14.5） | ★ 判据满足：★ 对当前运行设备**真点一次**且**可逆复原**（`tap(1183,192)` → 分组2 高亮，`tap(1183,124)` → 复原，与基线差 0.39%）|

---

## 14. ★★★ 预设 / 御魂 切换（★ OCR）· 与测试约定

> ★★★ **用户原话（第一版）**：
> > "**后边真机实测，如果要换预设和御魂的话，那么用默认分组-通用阵容，
> >   这个作为之后的所有测试内容的预设和御魂**"
>
> ★★★ **[10-15] 用户随即更正（逐字 · ★ 本节以这三条为准）**：
> > ★ "**R1只是用作测试方便，如果是实机,事实上需要玩家自己修改。**"
> > ★ "**R4失效，因为现在是全新开发，之前的暂停只是记录个台账，现在理清了，如果要OCR，那么就OCR**"
> > ★ "**R5要建模板，因为战斗类的任务基本都需要换预设和御魂。**"

### 14.1 ★★ 现行口径

| # | 项 | ★ 口径 |
|---|---|---|
| **R1** | ★ 「默认分组 - 通用阵容」的定位 | ★★ **只是【测试时】的方便约定**；★★ **不是产品要求** —— ★ **实机上玩家必须能自己改**（★ 预设/御魂 由玩家配置决定）|
| **R2** | ★ **产品必须支持** | ★★ 新引擎提供"**按名字**切换预设 / 御魂"（★ 玩家写名字，**不写数字**）★ 用 **OCR 识字 + 列表查找** |
| **R3** | ★ 战斗类任务 | ★★ 用户："**战斗类的任务基本都需要换预设和御魂**" ⇒ ★ **切预设/切御魂 = 战斗任务的必备步骤** |
| **R4** | ★ 素材 | ★★ **要建"预设/御魂选择界面"的模板**（★ 入口 / 列表项 / 滚动区 / 确认）|
| **R5** | ★★ **失败语义（★ 与旧引擎相反）** | ★ 旧引擎"**跳过切换、继续跑**"（默认 `-1,-1`）⇒ ★★ **新引擎必须"切成功才继续"**：★ 找不到 ⇒ 滚动重试 N 次 ⇒ 仍失败 ⇒ ★ **中止本次、记失败** —— ★ 因为**用错阵容打副本 = 白烧体力**，静默跳过更糟 |

### 14.2 ★★ 语义层设计（★ 复用，不许每个任务复制）

```rust
// oas-core / schedule 之外的语义模块：oas-semantic（或 flow 的内置步骤）
pub trait PresetOps {
    fn switch_preset(&mut self, name: &str) -> Result<()>;   // 队伍预设（按名字，OCR）
    fn switch_soul(&mut self, group: &str, team: &str) -> Result<()>; // 御魂组/队伍（按名字，OCR）
}
```

★ 二者都建立在**一个通用原语**上（★ 这是本节最重要的可复用能力）：

```rust
/// 在**可滚动列表**里按**文字**找到某项并点击（找不到就滚动，滚到底仍没有 => Err）
fn find_text_in_list(&mut self, text: &str, scroll: ScrollPolicy) -> Result<Point>;
```

★ `ScrollPolicy { max_scrolls, step_px, settle_ms }` —— ★ **必须有上限**（★ 治"列表滚不到就卡死"）。

### 14.3 ★ 素材清单（★ P1 起逐步建）

| 素材 | 用途 |
|---|---|
| 预设入口按钮（庭院/准备界面）| 打开预设列表 |
| 预设列表容器（用于 OCR 的 ROI）| OCR 识字定位 |
| 「默认分组」分组头 / 「通用阵容」项 | 测试约定用；★ 产品里是玩家自定义名字 |
| 御魂组/队伍选择入口 + 列表 | 同上 |
| 确认/应用按钮 | 切完确认 |
| 滚动区域 | `find_text_in_list` 的滚动锚点 |

### 14.4 ★ 验收（★ 用回放，不需要反复真机）

1. ★ **录一次真机**（默认分组-通用阵容）
2. ★ 用编辑器把"切预设/切御魂"拼成 **sub-flow**
3. ★ **回放断言**：★ 找到的列表项文本 == 目标名字；★ 点击坐标落在该项 ROI 内；★ 滚动次数 ≤ `max_scrolls`
4. ★ **失败路径**：★ 把目标名字改成不存在的 ⇒ ★ 必须**先滚动到上限再报错**（★ 不许静默跳过）

### 14.5 ★★★ 首次真机探测实测（[10-15] · P0-4 · ★ 证据落盘 `_verify/p0_live/`）

| 项 | ★ 实测 | 说明 |
|---|---|---|
| 设备 | MuMu · ★ **`ro.product.model = V2284A`**（★ 这是**机型**，**不是** serial！）| ★ `ro.serialno` / `ro.boot.serialno` 在 MuMu 上**都是空** ⇒ ★★ **不能拿它们做唯一键** |
| ★★ **去重键（实测修正）** | ★ `127.0.0.1:16384` 与 `emulator-5554` **是同一台**：★ `android_id` 都是 **`657eef8300229911`** · `boot_id` 都是 `24f8007e-…` · `wlan0 MAC` 都是 `08:2e:9b:c3:a4:ab` | ★★ **正确去重顺序**：★ ① `settings get secure android_id` ② `wlan0 MAC` ③ `boot_id` ④ adb serial · ★ **绝不能用 `ro.product.model`**（同型号多台会误合并）|
| 包名 / 前台 | **`com.netease.onmyoji`** · `mCurrentFocus=…/Client` | ★ 可作为"游戏在不在前台"的判据 |
| ★ **截图尺寸** | ★★ **1280×720（横向）** | ★ `wm size` 报 **`Physical size: 720x1280`（竖）** ⇒ ★★ **引擎必须按【截图实际尺寸】，绝不能信 `wm size`**（旋转差）|
| 当前界面 | ★ **式神录 → 队伍预设** | ★ 右侧 **「默认分组」高亮**；★ 中间 **「通用阵容」已选中** ✓ 与用户说法一致 |
| ★ 预设 UI 结构 | ★ 右侧分组列（默认分组/分组2…分组8/管理分组）· 中间预设列表 · 顶部预设名输入框 · 底部「新建预设队伍」 | ★ 建模板时的锚点 |
| ★★ **实测坐标**（1280×720） | ★ 「默认分组」**(1183,124)** · 「分组2」**(1183,192)** · 「分组3」≈(1183,262)（★ 行距 ≈70）· 「新建预设队伍」≈(780,378) · 右侧列 x≈**1183** | ★ 供"切预设"实机验证用（★ 但**产品逻辑要 OCR 按名字**，坐标只作兜底）|
| ★★ **输入通道验证（用户选 B）** | ★ `adb shell input tap 1183 192` ⇒ ★ 「分组2」高亮 + 中间变为「新建预设队伍」⇒ ★ 像素变化 **10.83%**；★ 再 `tap 1183 124` ⇒ ★ 回到「默认分组」⇒ ★ 与基线差 **0.39%** | ★ ✅ **cap/act 通道打通且可逆** |
| ★★ **关键发现（影响回放设计）** | ★ 两次截图的**残差 0.39% 来自动态元素**（活动横幅、聊天栏 `[楚枫] [照片]` 会变）| ★★ **回放断言绝不能比"像素完全相等"** ⇒ ★ 必须比 **事件序列/动作序列**（★ 设计稿 §6 已如此规定，此处得到实测印证）|

★ **由此给 P0-3/P0-4 的具体要求（已定）**：
1. ★ `ScreenSource` **返回实际帧尺寸**（★ 不信 `wm size`）；
2. ★ 设备枚举要**去重**（同 serial 多入口只算一台）；
3. ★ 回放断言 = **动作序列 + 识别结果**（★ 不比像素）；
4. ★ 动态区域（横幅/聊天）在模板 ROI 里**要避开**。
