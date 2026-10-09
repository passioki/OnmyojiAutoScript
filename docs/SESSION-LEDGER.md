# 会话进度台账（**唯一事实来源**）

> ★★ **最高纪律：不许出现"未完成却标记完成"** ★★
>
> 本文件是本次改造的**唯一事实来源**。规则：
>
> 1. **每一项都必须带"验证证据"** —— 一条可复现的命令 + 它的实际输出，
>    或一个具体文件的行号。**没有证据不许标 ✅。**
> 2. **状态只有三种**：
>    * `⬜ 未开始`
>    * `🔄 进行中`
>    * `✅ 已完成（附证据）`
>    **不存在"大概做了""应该可以"这种状态。**
> 3. **每完成一步**都要：
>    ① 重新读一遍 `architecture.md` 与相关代码，**核对文档说的是否还是事实**；
>    ② 跑全量测试（后端 `pytest` + 前端 `flutter test`）；
>    ③ 把结果写进本文件；
>    ④ 向用户汇报。
> 4. **发现文档与代码不一致时**，先改**文档**（因为文档是给人看的），
>    或者先改**代码**（如果文档描述的是目标状态）—— 但**必须在本文件里
>    明确记录哪一个是错的**，不能含糊过去。
>
> **背景（为什么要有这条纪律）**：本次彻查发现
> `docs/architecture.md` 决策台账 **10.7** 把 7.1 / 7.5 / 7.7 标成 ✅，
> 但代码里 `success_interval` / `charge_*` / `next_run` **仍在配置面且仍在执行**，
> `Resource` / `RunState` / `next_available()` **从没接进调度**。
> 即"**文档说做完了、代码里没做、还留着两套机制**"。
> 这条纪律就是为了不再发生这种事。

---

## 0. 起点基线（改动前的实测事实）

| 项 | 实测值 | 证据 |
|---|---|---|
| 后端测试 | `1453 passed, 1 skipped, 4 subtests` | `pytest tests -q --ignore=tests/tasks/Component/GeneralBattle/test_battle_wait.py` |
| 前端测试 | `75 passed` | `flutter test`（OASX） |
| 后端测试文件 | 20 个在 `tests/module/config/` | — |
| 任务总数 | 54（`module/config/task_catalog_data.json`） | `TC._load()` |
| 次数任务（`countable`）| 14 个 | 同上 |
| 自动进队列候选 | 40 个 | 同上 |

### 0.1 发现的三套机制（**这是要收敛的核心问题**）

| # | 机制 | 位置 | **实测状态** | 证据 |
|---|---|---|---|---|
| ① | `success_interval` / `failure_interval` / `next_run` / `charge_*` / `window_*` | `tasks/Component/config_scheduler.py` | ✅ **正在执行** | `config.py` L885-893 算出 `next_run`；L288-294 用 `in_window()` 拦 pending |
| ② | 任务代码里的硬编码星期/时刻 | `tasks/*/script_task.py` **42 处** | ✅ **正在执行** | `DemonRetreat/script_task.py` L31-49；`AbyssShadows` L104-213；`Dokan` L66/144 等 |
| ③ | `Resource` / `Recharge` / `RunState` / `next_available()` | `module/config/{resource,scheduler_core,availability}.py` | ❌ **从没接进调度** | 在 `config.py`/`script.py`/`config_model.py`/`task_state.py` 搜 `next_available\|Resource\|RunState\|scheduler_core` → **0 处** |

### 0.2 文档虚报清单（**必须修正**）

| 台账条目 | 文档声称 | **实测事实** | 判定 |
|---|---|---|---|
| 10.7 / 7.1 | 删字段 `success_interval`/`charge_*`/`next_run` 不再是配置项 — ✅ | 仍在配置面、仍在执行 | **❌ 虚报** |
| 10.7 / 7.5 | 核心抽象只有 `Resource` + `RunState` — ✅ | 没接进调度 | **❌ 虚报** |
| 10.7 / 7.7 | 用户配置面 10 → 3 个字段 — ✅ | `Scheduler` 仍暴露 16 个字段 | **❌ 虚报** |
| 10.7 / 7.3 | `failure_interval` → `retry_interval` — ✅ | 字段名仍叫 `failure_interval` | **❌ 虚报** |
| 10.7 / 7.4 | 删除 `scheduler_v2` 开关 — ✅ | 三个文件里搜 `scheduler_v2` → **0 处** | ✅ **属实**（唯一一条属实的）|
| 10.7 / 7.6 | 「次数」与「冷却」解耦 — ✅ | 搜 `retry_interval` → **0 处**（字段仍叫 `failure_interval`）| **❌ 虚报** |
| 10.9 / 9.2 | 新增 `AvailabilityWindow` — ✅ 已实现 | 类已实现，但**默认全关**，且**不参与 `next_run` 计算** | **⚠ 部分**（"已实现"只对类本身成立） |
| 10.9 / 9.5 | 自学习 `ObservedWindow` — ✅ 已实现 | 类已实现，**无调用者** | **⚠ 部分** |

---

## 1. 步1 · 翻译全量修复 —— ✅ **已完成**

**目标**：任务设置页不再有英文；翻译有单一数据源；未命中可发现。

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 1.1 | 统计缺哪些 key | ✅ | 前端 `i18n_cn.dart` 746 条 / 后端 `zh-CN.json` 973 条；**两边都没有 = 113** |
| 1.2 | 补 113 个缺 key 的中文 | ✅ | 后端 `zh-CN.json` **973 → 1090**（实际新增 **117** 条，含 11 条从后端搬到前端 + 多处顺带补齐）；自检输出 **"两边仍缺: 0 个"** |
| 1.3 | **单一数据源**：前端改为**拉**后端 | ✅ | 新增 `GET /home/chinese_translate`（`home_router.py:123`，实测返回 **1191** 条）<br>新增 `LocaleService.loadFromBackend()`（`locale_service.dart:79`）<br>`ctrl_nav.onInit` 已删除 `putChineseTranslate()` 调用 |
| 1.4 | **修"互相覆盖"循环**（本轮新发现的更严重问题）| ✅ | `PUT /home/chinese_translate` 从**整份覆盖**改为**增量合并**（`home_router.py:83`）；保留 `PUT /home/chinese_translate/replace` 给确需整份替换的场景；<br>新增 `POST /home/missing_translate`（`home_router.py:146`）落 `log/missing_translate.txt` |
| 1.5 | 未命中兜底 + 告警 | ✅ | `LocaleService.missingKeys`（`locale_service.dart:63`）+ `trOrRecord()`（`:111`）+ `reportMissing()`；`args_view.dart` 的 `title`/`description`/枚举选项**全部改走** `_t()` → `trOrRecord` |
| 1.6 | `costume_base.py` 剩余 4 条英文日志 | ✅ | 实测该文件 `logger.info` **已无英文开头**（替换 5 条）|
| 1.7 | 回归守卫测试 | ✅ | 新增 `tests/module/config/test_i18n_full_coverage.py`（**10 个测试全过**）：<br>· 全部英文字段 key 后端必须覆盖<br>· 译文里必须真有中文（防英文占位）<br>· PUT 必须增量合并（防回退成整份覆盖）<br>· 前端必须拉取而非推送<br>· 必须记录未命中 key |
| 1.8 | 全量测试 | ✅ | 后端 **1463 passed, 1 skipped**（原 1453 + 10 新守卫）；前端 **75 passed** |

### ★ 步1 期间新发现的**更严重**问题（已修）

原以为"只是缺 113 个 key"。实际查出一条**互相覆盖的循环**：

```
OASX 启动 (ctrl_nav.onInit)
  ├─ PUT /home/chinese_translate   把前端 746 条 **整份覆盖**后端 1090 条
  ├─ GET /home/additional_translate 读的是**另一个文件** assets/i18n/zh-CN.json (152 条)
  └─ 写进本地缓存 → 下次启动合并
```

**实测损失：每次启动丢 344 条翻译。**
→ 这就是"翻译永远补不齐"的**真正根因**。若只补 key 而不改方向，
本次新补的 117 条会在下次启动时被覆盖掉。

**已改为**：后端权威、前端只读、PUT 增量合并。

---

## 2. 步2 · auto_queue 与执行队列（后端）—— ✅ **已完成**

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 2.1 | `TaskSpec` 加 `auto_queue`（可覆盖）+ `auto_queue_effective` 属性 | ✅ | `task_catalog.py:161-181` 字段；`:189+` 属性。实测 `TaskSpec` 字段 = `['task','name_zh','category','resource','requires','note','auto_queue','list_pos']` |
| 2.2 | 54 个 `meta.py` 落**显式**值 | ✅ | 实测 `显式写了 auto_queue 的: 54`；`auto_queue=True: 40` / `False: 14`；**与 `countable` 矛盾的任务: 0** |
| 2.3 | `/overview` 加 `queued` + `auto_queue` | ✅ | `schema_router.py` 每任务字段块；实测 18 个启用任务 → 队列 15 个 / 第3类 3 个（RealmRaid/RyouToppa/Hyakkiyakou，**全是次数任务**）|
| 2.4 | **队列自动补齐**（auto 追加在已编排之后）| ✅ | `config.build_queue()`（`config.py:510`）。实测：用户 4 条编排**在最前且保持顺序**，12 个自动任务**追加在后** |
| 2.5 | **接进调度**（否则补齐只是摆设）| ✅ | `update_scheduler` 改用 `self.build_queue()`（`config.py:306` 附近）。守卫测试 `test_scheduler_uses_build_queue` |
| 2.6 | **移除 = 停用** | ✅ | 新增 `POST /{script}/queue/remove`：删 `run_list` 条目 + `sch.enable = False` + 中文提示。守卫测试断言 `sch.enable = False` 必须在 |
| 2.7 | **添加候选** = `enable && !auto_queue && !queued` | ✅ | 新增 `GET /{script}/queue/candidates`。实测候选 = `{RealmRaid, RyouToppa, Hyakkiyakou}`；自动任务与未启用任务**都不在** |
| 2.8 | 测试 + 全量 | ✅ | 新增 `tests/module/config/test_execution_queue.py`（**18 个全过**）；后端 **1481 passed**（1463 + 18）；前端 **75 passed** |

### ★ 步2 期间发现的**第 3 个真 bug**（静默降级）

两处（`build_overview` 与新增的候选端点）写着：

```python
meta = TC.get_by_key(key) if hasattr(TC, 'get_by_key') else None
```

**`TC.get_by_key` 根本不存在** → `hasattr` 恒为 `False` → `meta` **永远是 `None`**。

* `build_overview` 下面有回退（还原任务名再 `TC.get`），所以**没暴露**
* 候选端点**没有回退** → **候选永远为空**（第一次实测就是 `set()`）

这正是本项目反复踩到的"**静默降级**"模式：加个 `hasattr` 守卫看起来"很稳"，
实际把逻辑错误藏起来了。已改为统一的 `_meta_of_key(key)`（内部用
`TC.get()`，它本身已支持下划线/全小写容错），并在函数文档里写明来龙去脉。

★ 值得一提的是：这个 bug 与步1 的"`.tr` 未命中静默返回 key"是**同一类问题** ——
**静默降级让错误不可见**。所以两处都补了"让缺口可见"的机制。

---

## 3. 步3 · 前端队列

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 3.1 | 四类分区（正在运行第0行不可拖 / 可跑 / 未到窗口灰 / 未编排） | ⬜ | — |
| 3.2 | 添加任务过滤 + 空态提示 | ⬜ | — |
| 3.3 | 移除弹窗确认 + 提示 | ⬜ | — |
| 3.4 | 测试 + 全量 | ⬜ | — |

---

## 4. 步4 · 调度机制统一（**手术级**）

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 4.1 | `AvailabilityWindow` 接进 `next_run` 计算（`next_opening()` 对齐） | ⬜ | — |
| 4.2 | `next_available()` 接进调度，取代 `next_run` 推进 | ⬜ | — |
| 4.3 | 删 `Scheduler.success_interval` / `charge_*` / `next_run` 配置面 | ⬜ | — |
| 4.4 | `failure_interval` → `retry_interval` | ⬜ | — |
| 4.5 | 删 42 处任务内硬编码时段，搬进 `meta.py` | ⬜ | — |
| 4.6 | 删 `BaseTask.custom_next_run()` | ⬜ | — |
| 4.7 | `_skip_by_period` / `_record_task_success` 并入 `RunState` | ⬜ | — |
| 4.8 | 迁移桥梁 `Resource.from_legacy()` 保留（读旧配置） | ⬜ | — |
| 4.9 | 测试重写 + 全量 | ⬜ | — |

---

## 5. 步5 · 文档按事实修正

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 5.1 | 台账 7.1 / 7.3 / 7.5 / 7.7 改为真实状态 | ⬜ | — |
| 5.2 | §3 标注实现进度（哪些接了、哪些没接） | ⬜ | — |
| 5.3 | 新增本轮决策（分类 / 队列 / auto_queue / 时段 / 单一机制） | ⬜ | — |
| 5.4 | 新增"三套机制 → 一套"的说明 + 本次收敛记录 | ⬜ | — |
| 5.5 | `ui-api-mapping.md` 同步 | ⬜ | — |
| 5.6 | 把"不许虚报完成"纪律写进文档 | ⬜ | — |

---

## 6. 最终验收

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| 6.1 | 后端全量 pytest | ⬜ | — |
| 6.2 | 前端全量 flutter test | ⬜ | — |
| 6.3 | 两个仓库干净 + 已推送 | ⬜ | — |
| 6.4 | 逐条对账本文件所有 ✅ 的证据可复现 | ⬜ | — |
| 6.5 | 文档与代码一致性复核（重点：台账不再虚报） | ⬜ | — |
