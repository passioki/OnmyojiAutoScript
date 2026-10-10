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

## 3. 步3 · 前端队列 —— ✅ **已完成**

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 3.1 | **四类分区** | ✅ | `queue_panel.dart` `build()`：分类 0 `_statusBlock`（正在运行）→ 分类 1/2 可拖列表（`可跑 N · 未到窗口 N`）→ 只读明细（待执行/等待中）→ 分类 3 **只给指引不罗列** |
| 3.2 | **权威在后端**（前端不推导）| ✅ | 控制器 `isQueued`/`isAutoQueue`/`queuedTasks`/`enabledNotQueuedTasks` 全部读 `/overview` 的 `queued`/`auto_queue` |
| 3.3 | **【添加任务】走后端候选端点** | ✅ | 选择器改调 `fetchAddCandidates()` → `GET /{script}/queue/candidates`；**删掉**前端自己的 `allTasks` 过滤（守卫断言 `widget.controller.allTasks` **不得出现**）|
| 3.4 | 空态给**原因与出路** | ✅ | 文案说明"只列已启用的次数任务；定时类会自动进队列；次数任务要先在任务列表启用" |
| 3.5 | **移除 = 弹窗 + 后端停用 + 提示** | ✅ | `_confirmAndRemove()`：`AlertDialog`（按 `auto_queue` 给不同说明）→ `c.removeFromQueue()` → `Get.snackbar` |
| 3.6 | **第 3 类不堆在队列下面** | ✅ | **删除** `_unqueuedRow`（26 行）与"未编排（共 N 个）"标题；改为一句指引 + 「去添加」按钮 |
| 3.7 | 测试 + 全量 | ✅ | 前端 **79 passed**（75 + 4 新守卫）；后端 **1481 passed**；release 构建通过 |

### 测试守卫（新增 4 个）

* 四类分区的**权威字段**（`queued` / `auto_queue` 必须从后端读）
* 第 3 类**不堆在队列下面**（`_unqueuedRow` 与"未编排（共" 必须已消失）
* 控件测试：**队列只渲染 `queued` 的任务**（第 3 类不出现，但有指引）
* 移除必须**确认弹窗 + 后端停用 + 提示**

★ 顺带发现并修正：假控制器/假数据**必须覆盖新方法**（`queuedTasks` 等），
否则队列渲染成空，测试报 `Found 0 widgets` —— 很容易误判成"面板坏了"。
已在假控制器里写明这个坑。

---

## 4. 步4 · 调度机制统一（**手术级**）

### 4-A · 硬编码时段搬进 `meta.py` —— ✅ **已完成**

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 4A.1 | `TaskSpec` 加 `window` 字段（**支持单段与多段**）| ✅ | `task_catalog.py`；`windows_effective` / `window_describe` / `in_window()` / `next_opening()`。实测 `TaskSpec` 字段 = `[...,'auto_queue','window','list_pos']` |
| 4A.2 | 精确采集代码事实（不猜）| ✅ | 逐文件读过 `AbyssShadows:104-105,202-213` / `DemonRetreat:33,42-45` / `Dokan:65-69` / `Hunt:51-101` / `GuildBanquet:121-139` / `MysteryShop:24-25` / `Secret:286` / `Restart:45-56,64` |
| 4A.3 | 7 个任务落 window | ✅ | `AbyssShadows` 周五六日 19:00-19:15 · `DemonRetreat` 周六 19:00-20:00 · `Dokan` 周一~周四 19:00-20:00 · `Hunt` **两段**（周一~周四 06:00 起 / 周五~周日 17:00 起）· `MysteryShop` 周三+周六 · `Secret` 周一 08:00 起 · `GuildBanquet` 每天 18:00-22:00 |
| 4A.4 | 守卫测试 | ✅ | 新增 `tests/module/config/test_task_window.py`（**17 个全过**）：字段存在、单段、**多段**、`next_opening` 取最早、无 window 即不限、7 个任务的时段与代码事实逐条比对、`AbyssShadows` 恰好周五六日、`Dokan` 不含周末 |
| 4A.5 | 全量测试 | ✅ | 后端 **1498 passed**（1481 + 17）；前端 **79 passed** |

### ★ 4-A 期间我自己发现并改正的**两个错误**

**错误一: 差点把用户可调的时刻写死在 `meta.py`。**
`AbyssShadows` 有三个用户可调的 `custom_run_time_friday/saturday/sunday`,
`DemonRetreat` 有 `custom_run_time`。若 meta 写死 19:00, 会**覆盖**用户设的
18:30 之类 —— 擅自改变行为。→ meta 只放**游戏机制**（哪几天）+ 默认时段;
运行时用任务配置的时刻收窄/移动它（见 4-A 后续）。

**错误二: 差点用 `AvailabilityWindow` **错误地**表达"排除"。**
`Restart` 的需求是"**避开**周三 06:00-08:00 维护"。我第一版写成两段
`00:00-06:00` + `08:00-23:59` —— 但**第二段在任何一天都成立**, 于是窗口
等于"全天开放", 是**假迁移**。`AvailabilityWindow` 只能表达"允许",
不能表达"排除"。→ `Restart` **不放进 meta**（它的"维护期顺延"留在代码里,
那本来就是"运行中任务被延后", 不是"任务什么时候开放"）。
已加守卫测试 `test_restart_has_no_window` 钉住这个判断。

### 4-B · 运行时的**用户配置覆盖** —— ⚠ **刻意不做**（记录原因）

**我第一版做了, 然后自己退掉了。** 记录在此以免后人重蹈:

第一版写了 `_configured_start_times()`, 拿任务的 `custom_run_time_friday` /
`kirin_time` / `banquet_day_1_start_time` 等配置字段去**收窄/移动** meta 的窗口。
实测立刻出问题:

```
AbyssShadows 的 meta 窗口 = 周五六日 19:00-19:15
配置里 custom_run_time_* = 19:30
-> 收窄后变成 19:30-19:45
-> 输入 19:05（**本来在 meta 窗口内**）被推到 19:30 起
-> 更糟: 连"周五 19:05 已在窗口内"也被改掉了
```

**根因**: "`custom_run_time_friday` 到底指什么" —— 是游戏开始时刻、还是应用该去跑的
时刻、还是"提前多久开始准备"? **从代码里看不出唯一答案**（不同任务用法不同）。
拿它移动窗口就是**在猜**, 而猜错会**静默改变调度行为**。

按纪律（§10.10: 不猜、不静默降级）: **不做**这件事。
作为替代, 把 meta 的窗口**放宽**到足以容纳用户配置的常见取值
（`AbyssShadows` 19:00-19:15 → **19:00-20:00**, 见该 `meta.py` 的注释）。

★ 守卫测试 `test_no_configured_override_guessing` 钉住这个判断。

### 4-C · `next_run` 对齐 `next_opening()` —— ✅ **已完成**

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 4C.1 | `task_delay()` 算出 `next_run` 后**对齐窗口** | ✅ | `Config._align_to_window()`；`task_delay` 里紧接 `run = min(run)` 调用 |
| 4C.2 | `Config.task_window()` 提供生效窗口 | ✅ | 只读 `meta.py` 的 `spec.windows_effective`（**单一来源**）|
| 4C.3 | 窗口内**不变** | ✅ | 实测 `AbyssShadows` 周五 19:05 / 19:30 / 19:45 **全部不变** |
| 4C.4 | 窗口外**推到下一次开放** | ✅ | 周一 19:05 → 周五 19:00；周一 19:30（DemonRetreat）→ 周六；周五 19:30（Dokan）→ **下周一 10-12**；周二 09:00（Secret）→ 下周一 08:00 |
| 4C.5 | 无窗口任务**行为不变** | ✅ | `Delegation` 原样返回 |
| 4C.6 | **绝不往前推** | ✅ | 守卫测试遍历 5 个任务 × 7 天 × 7 个时刻, 断言 `got >= when` |
| 4C.7 | 守卫测试 | ✅ | `test_task_window.py` **25 passed**（17 → 25, 新增 8 个对齐测试）|
| 4C.8 | 全量测试 | ✅ | 后端 **1506 passed**（1498 + 8）；前端 **79 passed** |

★ `AbyssShadows` 的窗口放宽为 **19:00-20:00** 是**刻意留余量**: 保证用户可配的
  19:30 落在窗口内, 否则合法时刻会被推走（就是上面那个 bug）。余量**不会**让任务
  在 19:15 后真的能跑 —— 游戏关门了就进不去, 任务自己失败返回。

### 4-D · `next_available()` 接进调度 —— ✅ **已完成**

**这是把新模型真正"接线"的一步。** 此前 `resource.py`(364 行) 与
`scheduler_core.py`(291 行) 早就写好、47 个单测, 但**从没被调度器调用** ——
在 `config.py`/`script.py` 里搜 `next_available|Resource|RunState` 得到 **0 处**。

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 4D.1 | `task_delay()` **优先**用 `Resource` 排期 | ✅ | 新增 `Config._next_run_from_resource()`；`task_delay` 里 `if success: planned = self._next_run_from_resource(...)`，`planned is None` 时回退旧 interval |
| 4D.2 | 状态从 `start_time` 做锚点（不新建存储）| ✅ | `RunState(refill_anchor=start_time)`；与旧 `next_run = start_time + interval` **同一锚点**, 所以行为可对齐 |
| 4D.3 | `interval` 类**行为对齐** | ✅ | 实测 `DemonEncounter` 12:00→13:00（+1h）· `SoulsTidy`/`Duel` 12:00→15:00（+3h）· `WantedQuests` 12:00→13:30（+1.5h）—— **与旧 interval 完全一致** |
| 4D.4 | `slots` 类**修正白跑** | ✅ | `GoldYoukai`/`ExperienceYoukai`/`Tako` 12:00 → **次日 00:00**（按 `slots='0,12'` 的真实机制）, 而非旧的"加 3 小时" |
| 4D.5 | `none+period` / `window` 类**不**用（防热循环）| ✅ | `_next_run_from_resource` 对 `refill not in ('interval','slots')` 返回 `None` —— 周期类的"下次运行"由完成记忆在周期边界决定; 若用 `next_available`（它在"现在可行"时返回 `now`）会**热循环** |
| 4D.6 | 失败仍用 `failure_interval` | ✅ | 退避重试是**独立概念**, 与资源补充无关（台账 7.6「次数与冷却解耦」）|
| 4D.7 | 守卫测试 | ✅ | `test_task_window.py` **30 passed**（25 → 30, 新增 5 个接线测试, 含**反向守卫**: `config.py` 里必须真的出现 `next_available`/`RunState`/`TC.get_spec`）|
| 4D.8 | 全量测试 | ✅ | 后端 **1511 passed**（1506 + 5）；前端 **79 passed** |

### ★ 顺带修掉一个**跨午夜的测试 flake**（既有缺陷）

第一次跑全量时 `test_function_window.py` 有 **2 个失败**, 复跑又全过。查明是
**测试自身的时间依赖**（不是我的改动引起的）:

```
测试在 23:59:5x 执行 datetime.now().weekday()  -> 周五(4)
实际断言 in_window() 时已过午夜               -> 周六(5)
weekday 5 不在 days=(4,) 里 -> **假失败**
```

上一版作者已把窗口改成 00:00-23:59 想避开时间依赖, 但**漏了"取 now 与断言
之间"也可能跨午夜**。已修: 把同一个 `now` **显式传给 `in_window(now)`**,
`test_garbage_days_falls_back` 改用**固定时刻**（2026-10-05 正午）断言。

★ 该测试的注释里原本就写着"曾在 23:06 失败" —— 说明这个问题**反复出现过**,
只是每次都被当成偶发忽略。已把根因写进注释。

### 4-E · 删旧配置面 —— ✅ **已完成（"隐藏"而非"删字段", 原因见下）**

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 4E.1 | 内部字段显式标记 | ✅ | `Scheduler` 12 个字段打 `json_schema_extra={'internal': True}`；`charge_*` 12 个（3 任务 × 4）同样标记 |
| 4E.2 | `merge_value` 跳过内部字段 | ✅ | `config_model.py` 与既有 `0xABCDEF` 排除同一处 |
| 4E.3 | **用户配置面 16 → 4** | ✅ | 实测 `Orochi` 的 `scheduler` 组只剩 `enable` / `priority` / `target` / `expected_minutes` |
| 4E.4 | `charge_*` 从界面隐藏 | ✅ | 实测 `GoldYoukai` 的 `gold_youkai` 组 **0 个字段**（全是 charge）|
| 4E.5 | 守卫测试 | ✅ | 新增 `tests/module/config/test_user_config_surface.py` **16 passed** |
| 4E.6 | 全量测试 | ✅ | 后端 **1527 passed**（1519 + 8 → 16）；前端 **79 passed** |

#### ★ 为什么是"隐藏字段"而不是"删字段"

`task_delay()` 要把算出来的 `next_run` **落盘**（重启后才知道下次什么时候跑）；
`_skip_by_period()` 要读 `period` / `reset_at`。**删了会崩。**
所以正确做法是: 字段留在模型里（内部用）, 但**不再出现在界面上**。

#### ★★ 4-E 期间我自己犯的**两个错误**（都留了守卫）

**错误一: 自动标记做过头, 误伤用户配置。**
第一版我用正则给"含 charge 的整行 `Field(...)`"加 `internal`,
结果把同组的 **`user_status`（队伍状态, 用户必须能配）** 也标上了
→ `test_team_modes` 里 `assert 'user_status' in names` **3 个任务全失败**。
→ 已改为**精确只标那 4 个 `charge_*` 字段名**; 加守卫
`test_user_status_NOT_hidden`。

**错误二: 参数插到了 `Field(...)` 的括号之外。**
第二版把 `json_schema_extra` 追加到**行尾**, 而那行已经是
`charge_enable: ... = Field(...),` —— 变成 `Field(...), json_schema_extra={...}`
（括号外多出关键字参数）→ **SyntaxError**, **36 个测试失败, 模块都 import 不了**。
→ 正确做法: 正则定位 `Field\((.*)\)` 并把参数插到**闭合括号之前**;
加守卫 `test_charge_config_files_compile` 与
`test_marking_inserts_inside_field_parens`。

#### 未完成的部分（如实记录）

`charge_*` **字段本身还在**（只是隐藏）。要真正删除, 必须先把任务代码里
**61 处** `con.charge_*` 读取改用 `Resource.recharge` —— 那属于 **4-F** 的范畴,
且需要先核实"任务自己的存量簿记"与 `Resource` 的语义是否等价
（**不能猜**, 见 4-B 的教训）。台账标 ⬜, 不虚报。

### 4-F · 删任务内硬编码时段 —— 🔄 **进行中**（2/16 任务已清理）

**原则: 逐任务核实语义后再删, 不批量盲删。** 每个任务都要先证明"新逻辑与旧逻辑等价"。

| # | 任务 | 状态 | 等价性证据 |
|---|---|---|---|
| 1 | **DemonRetreat** | ✅ | 删 20 行 `weekday()` 判断 + 3 处 `custom_next_run` → `set_next_run(success=True)`。<br>**实测 4/4 场景等价**: 周一/周三/周日 → 本周六 19:00; 周六成功 → 下周六 19:00 |
| 2 | **AbyssShadows** | ✅ | 删 `today not in [4,5,6]` 判断 + 4 处 `custom_next_run` → `set_next_run(success=True)`。<br>**实测 3/3 等价**: 周五→周六 · 周六→周日 · **周日→下周五** |
| 3 | **Hunt** | ✅ | 删 `check_datetime` 里的"太早/太晚"分支（20 行）+ `plan_tomorrow_hunt` + `con_time` + 未用的 `time` import。<br>**关键洞察**: 窗口 23:00 结束 -> 23:00 后**不会被派发** -> 原来 `>23:00` 分支是**死代码**。<br>实测窗口对齐: 周一 22:30 跑完 +3h = 周二 01:30 → **对齐到周二 06:00** |
| 4 | **RyouToppa** | ⛔ **阻塞（需你决策）** | 只有 2 处, 但它**没有 window**（`window=None`, `auto_queue=False` 的次数任务）。<br>`_align_to_window` 对无 window 的任务**原样返回** -> 删掉 `custom_next_run` 后, `next_ryoutoppa_time`（默认 7:00, **用户可配**）这个"次日几点跑"的意图**会丢失**。<br>**这需要"给 RyouToppa 新增 window"这个行为决策, 不是安全重构** —— 不擅自做。 |
| 5 | **GuildBanquet** | ⬜ | 3 处（L133/136/139），宴会日由用户配置（`banquet_day_1/_2`）, 需单独核实 |
| 6 | **Restart** | ⬜ | 3 处（L50/53/56）—— 领体力时刻（12:00/20:00）。<br>⚠ 用的是 `Time(12, 0)`（大写 `Time`）, 不是标准 `time`, 需单独看 |
| 7 | **MemoryScrolls** | ⬜ | 1 处（L63）—— 给**别的任务**（Exploration）排期, 语义特殊 |
| — | 其余（Dokan / MysteryShop / Secret / Tako / DemonEncounter / GuildActivityMonitor / AreaBoss …）| ✅ | **实测 0 处** —— 它们用 `weekday()` 只是选 boss/选区域, 属正当用途 |

**剩余 `custom_next_run` 真实代码: 9~10 处**（4 个任务）—— 台账标 ⬜, 不虚报。

★ **计数口径的不确定性（如实说明）**: `Restart` 的 3 处在两种统计口径下**时有时无** ——
  我的"剥 docstring"逻辑对那个文件不稳（它有多段三引号, 贪婪/非贪婪匹配都会错乱）。
  **我不假装精确**: 准确数在 **9~10 处**之间。
  要精确计数请用: `grep -n 'custom_next_run' tasks/Restart/script_task.py` 然后**人工看**是否在注释里。

★ `BaseTask.custom_next_run()` **暂时不能删** —— 4 个任务还在调它。


删它必须先清完这些调用点（属于本步的剩余工作）。

★ 守卫测试: 新增 `tests/tasks/test_no_hardcoded_windows.py`（**8 passed**）
* 清理过的文件里**不得**再出现 `custom_next_run` / `days_until`
* **不得**用 `weekday()` 决定"能不能跑"（`weekday()` 与 `raise TaskEnd` 同段即判失败）
* `DemonRetreat` 的 window 必须是"仅周六"
* 直接比对**旧算法 vs 新算法**的结果（等价性回归）

★ 期间踩到一个坑: 测试文件在 `tests/tasks/`, **比其他测试浅一层**,
`REPO` 应是 `parents[2]` 而不是 `parents[3]` —— 写成 3 会得到
`D:\OAS-dev` 并报 `FileNotFoundError`。已在注释里标明。

#### ★ 为什么删掉任务里的判断是**安全**的

`custom_next_run(task, custom_time, delta)` 的实现就是
`set_next_run(target=(now + delta).replace(hour=..., minute=...))`。
而 `set_next_run` 会在算完后由 `_align_to_window()`（4-C）**把结果纠正到窗口内**。
所以"手工算到周六"与"让它走 `success_interval` 再由窗口对齐"**结果相同**
—— 这是逐个任务实测过的, 不是推测。

### 4-G · 测试重写 · ⬜ 待做

---

## 5. 步5 · 文档按事实修正 —— ✅ **已完成**

| # | 子项 | 状态 | 证据 |
|---|---|---|---|
| 5.1 | 台账 **10.7** 改为真实状态 | ✅ | 7.1 改为"已达成（方式: 从界面隐藏, 非从模型删除）"并附证据；7.3 改 **⬜ 未做（虚报）**；7.5 改 **🔄 部分（曾虚报）**；7.7 改为"16 → 4"并附实测。加了一段引用 SESSION-LEDGER 的说明 |
| 5.2 | 台账 **10.9** 改为真实状态 | ✅ | 9.2 改"✅ 已接线"并说明"曾经默认全关且不参与 `next_run` 计算"；9.3 **修订表述**（时段来源从"全部由用户配置"改成"任务 `meta.py`"，并说明实测 `window_enable` 全为 False）；9.5 改 **⚠ 类已实现无调用者**；9.6 改 **⬜ 未落进 meta.py** |
| 5.3 | 台账 **10.10** 补录纪律 | ✅ | 新增 10.4「不许未完成却标记完成」· 10.5「不猜语义」· 10.6「删掉 ≠ 合并」· 10.7「剥注释再断言」· 10.8「单一数据源」|
| 5.4 | 新增 **§2.1 三套机制 → 一套** | ✅ | 用可复现的 grep 命令作证据，说明机制 ①②③ 并存、危害、以及 4-A/4-C/4-D/4-E/4-F 的收敛过程 |
| 5.5 | 新增 **§12 本会话决策** | ✅ | 翻译（6 条）/ 执行队列（6 条）/ 汇报纪律（3 条）|
| 5.6 | 新增 **§13 进行中的工作** | ✅ | 4-F 逐任务状态（含 3 个 ⛔ 阻塞及原因）+ 6 项其它未完成，**全部标 ⬜/⛔, 不标 ✅** |
| 5.7 | `ui-api-mapping.md` 同步 | ✅ | §7 已在步3/4 更新；本轮补 `queued`/`auto_queue` 与"用户配置面 4 个字段" |

★ 校验: 5 个关键章节锚点全部存在（`## 2.1 ★★` / `## 12. 本会话` / `## 13. 进行中的工作` / `### 10.4` / `### 10.7`）。
`architecture.md` 由 47359 → **52612 字符**（1807 行）。

---

## 6. 最终验收

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| 6.1 | 后端全量 pytest | ⬜ | — |
| 6.2 | 前端全量 flutter test | ⬜ | — |
| 6.3 | 两个仓库干净 + 已推送 | ⬜ | — |
| 6.4 | 逐条对账本文件所有 ✅ 的证据可复现 | ⬜ | — |
| 6.5 | 文档与代码一致性复核（重点：台账不再虚报） | ⬜ | — |

---

# 7. 最终结算（★ 逐条对照目标, 诚实标注）

对照最初的目标逐条结算。**每一项都指到证据; 未达成的写清原因, 不粉饰。**

| 目标 | 子项 | 结算 | 证据 / 原因 |
|---|---|---|---|
| **①** | 翻译全量修复 | ✅ | 后端表 973 → **1091** 条; 前端改为**拉取**（原来每次启动丢 344 条）; `trOrRecord` 记录未命中; 枚举值也翻（60 个）。守卫 `test_i18n_full_coverage.py`（10 个）|
| **①** | 单一数据源 | ✅ | `GET /home/chinese_translate`（1191 条权威）; `PUT` 改**增量合并** |
| **①** | 未命中兜底告警 | ✅ | `POST /home/missing_translate` → `log/missing_translate.txt` |
| **①** | 剩余英文日志 | ✅ | `costume_base.py` 实测无英文开头 |
| **②** | `auto_queue` 到 `meta.py` | ✅ | 54 个**显式**落值（40 自动 / 14 手动）; 与 `countable` **零矛盾** |
| **②** | 四类分区 | ✅ | `/overview` 给 `queued` + `auto_queue`; 前端按后端字段分 |
| **②** | 添加任务过滤 | ✅ | `GET /queue/candidates`（后端规则, 前端不重复实现）|
| **②** | 移除 = 停用 | ✅ | `POST /queue/remove` 做 `sch.enable = False` |
| **②** | 队列自动补齐 | ✅ | `build_queue()`; 用户编排**保持顺序在前**, 自动任务**追加在后**, **不回写配置** |
| **②** | 正在运行第 0 行不可拖 | ✅ | `_statusBlock` 只读 |
| **③** | 前端队列 tab | ✅ | `[调度] [执行队列]`; 右侧日志宽度可拖 + 持久记忆 |
| **④** | `Resource`/`RunState`/`next_available` 接进调度 | ✅ | `Config._next_run_from_resource()`; 守卫 `TestResourceWiring` |
| **④** | `next_run` 对齐 window | ✅ | `Config._align_to_window()`; 实测 17:00/18:00/22:00 不变, 23:00 → 次日 17:00 |
| **④** | `success_interval`/`next_run` **配置面**删除 | ⚠ **界面已删, 模型保留** | 界面 16 → **4** 个字段; 字段留在模型里（`task_delay` 要落盘 `next_run`、`_skip_by_period` 要读 `period`/`reset_at`）—— 删了会崩。守卫 `test_user_config_surface.py`（22 个）|
| **④** | `failure_interval` → `retry_interval` | ✅ | 带 `validation_alias`（读旧名）+ 不设 `serialization_alias`（写新名 → **旧配置自然迁移**）; 实测 `kekkai_activation` 的 10 小时覆盖**保住** |
| **④** | `charge_*` **配置面**删除 | ⚠ **界面已删, 模型保留** | 3 任务 × 4 字段已标记 `internal`（实测 `gold_youkai` 组 0 字段）。**真正删除未做** —— 任务用 `task_state.get_charges(..., max_charges=con.charge_max, slots=con.charge_slots)` **显式传参**, 删字段须先证明与 `Resource.recharge` **状态存储一致**, 否则"还剩几次"会算错。**证据不足, 不冒险** |
| **④** | 删 42 处任务内硬编码时段 | ⚠ **部分** | **3 个任务已清理且有等价性实测**（DemonRetreat / AbyssShadows / Hunt）; 时段已搬进 **8 个任务**的 `meta.py`。剩余 **9~10 处**（4 任务）|
| **④** | **彻底删除** `custom_next_run` | ⛔ **决策: 不删** | 它与"开放时段"是**两个概念**（允许 vs 希望几点）。4 个调用点全是"用户配置的时刻"（`banquet_day_*` / `next_ryoutoppa_time` / 领体力时刻 / 跨任务排期）, 无法用固定 window 声明。**硬合并会丢表达能力**。详见 §13.1 |
| **⑤** | 文档按事实修正 | ✅ | 台账 10.7 的 7.1/7.3/7.5/7.7、10.9 的 9.2/9.3/9.5/9.6 全部改为实测状态; 新增 §2.1 / §12 / §13; 10.10 补 5 条纪律; `ui-api-mapping.md` 补 §8 |

## 7.1 ★ 明确**未做**的项（不虚报）

| 项 | 原因 |
|---|---|
| `charge_*` 字段**真正删除** | 需先证明任务存量簿记 ≡ `Resource.recharge`（**不猜**）|
| `ObservedWindow` **自学习接线** | 类已实现但无调用者; 要接需"记录每次成功时刻"的钩子, 属**新功能** |
| `next_run` 完全**纯函数化**（不再落盘） | 需要状态存储改造 |
| 4-G **测试重写**（200-300 个） | 前置项（4-F）未全部完成 |
| `custom_next_run` 删除 | **决策保留**（见上）|

## 7.2 ★ 本会话的**元收获**（比具体改动更重要）

1. **发现并修正了"文档虚报"这一系统性问题** —— 台账标 ✅ 而代码里没做的事有 **8 条**。
   建立了 `SESSION-LEDGER.md` 作为唯一事实来源, 规则是"**每个 ✅ 必须附可复现证据**"。
2. **"静默降级"是本项目的主要缺陷模式**, 本会话修了 4 处:
   * GetX `.tr` 未命中**静默返回 key** → 113 个翻译缺口长期无人发现
   * `hasattr(TC, 'get_by_key')` 恒 False → "添加任务候选"**永远为空**
   * 前端 `PUT` 翻译**整份覆盖**后端 → 每次启动**静默丢 344 条**
   * pydantic `extra='ignore'` → 改字段名会让**用户配置静默失效**
3. **"删掉" ≠ "合并"**、**"不猜语义"** 已写进 §10.10 纪律 —— 都是本会话踩坑换来的。

---

# 8. ★★ 用户新澄清的设计（2026-10-10 第二轮）★★

## 8.1 window 的完整设计（比原理解宽）

**所有定时任务都有 window** —— 不存在"没有 window 的任务"：

| 周期 | window |
|---|---|
| **每天** | 每天 **00:00–24:00**（即整天）|
| **每周** | **周一 00:00 – 周日 24:00** |
| **每月** | 当月 **1 日 00:00 – 月末 24:00** |
| **具体活动** | 如逢魔之时 = **每天 17:00–23:00** |

★ 推论: `window=None` **不是**"不限时段"的意思, 而是**"这个任务的 window 还没被声明"**
—— 是**缺失**, 需要补齐。这修正了我此前的理解（我把 `None` 当"不限时段"）。

★ 用户同时发现: **很多定时任务没有开放 window 和周期的设置**（见 §8.3 审计）。

## 8.2 调度模型（用户明确）

```
队列顺序 = 唯一的调度依据（不再看 interval 谁先到点）

调度器: 从队列**按顺序**取第一个「到点 且 在窗口内」的任务
        跑完它 -> 接着取下一个
```

| # | 规则 |
|---|---|
| 1 | **队列 = 全部启用任务**（定时自动进 + 次数手动加）, 按用户拖的顺序 |
| 2 | **A: 间隔完全废弃** —— 用户原话"a 完全废弃, b 和 c 的假设似乎并不存在" |
| 3 | **B: 不在窗口 = 不能运行** —— 变灰, 放进「未到开放时间」; 不卡住队列 |
| 4 | **「待执行」与「执行顺序」合并成一套可拖列表**（不再两套）|
| 5 | **「等待中」改名为「未到开放时间」**（显式意义）|
| 6 | **不用括号解释, 一律改为悬停提示** |
| 7 | 窗口生效位置必须移到 `Function`（见 §8.4 —— 此前是**死代码**）|

## 8.3 ★ 审计: 54 个任务的 window / 周期现状

| category | 数量 | 有 `TaskSpec.window` |
|---|---|---|
| CHARGE | 3 | **0** |
| FIXED | 13 | **0** |
| LIMITED | 8 | **0** |
| TIMED | 28 | **8** |
| TOPPA | 2 | **0** |
| **合计** | **54** | **8** |

→ **46 个任务缺 window**（按 §8.1, 这是"缺失"而非"不限时段"）。

★ 另有 8 个 `LIMITED` 任务的 `Resource.recharge.kind == 'window'`
（`ActivityShikigami` / `BudokaiTournament` / `DyeTrials` / `FloatParade` /
`FrogBoss` / `KittyShop` / `MetaDemon` / `Quiz`）—— 它们的"活动期"**也没填**。

## 8.4 ★★ 修正我自己的虚报: **窗口是死代码** ★★

我在 §13.2 / 交付说明里把"逢魔时段落进 `meta.py`"标了 ✅。**实测证明它没生效**:

```
2026-10-10 07:36 实测:
  TaskSpec.window (meta.py)     : DemonEncounter = 每天 17:00-23:00   ← 我加的
  Function.window (调度器用的)   : 不限时段                            ← 真正的判断依据
  DemonEncounter.in_window(now) : True      ← 07:36 本该 False!
  pending = 27 个   waiting = 0 个
```

**根因**: `Function._build_window()` 从 `scheduler.window_enable` 构建
—— 而那个字段**全 54 个任务都是 `False`**。`Function` **完全不读** `meta.py`
（`config.py` 里搜 `get_spec` 只命中 `task_window` / `_align_to_window`）。

**并且** `_align_to_window` **只在 `task_delay()`（任务结束时）被调用** ——
对"从没跑过 / `next_run` 是旧值"的任务, `update_scheduler()` 里**没有任何窗口过滤**,
所以它们**不管在不在窗口内都直接进 pending**。

❌ 我此前的 ✅ 是**错的**。已在本节改正, 标为 **🔄 未生效（死代码）**。

## 8.5 ★ C 项审计结果（用户要求逐个确认）

扫 `tasks/*/script_task.py` 的排期调用, 区分"**interval 式**"与"**真实日期时间式**":

| 任务 | interval 式 | 真实日期式 | 结论 |
|---|---|---|---|
| **GuildBanquet** | 3 | 1 | ⚠ **两者都有** —— interval 部分要移植 |
| **Hunt** | 1 | 0 | ⛔ **interval 式 → 移植后删除** |
| **MemoryScrolls** | 1 | 0 | ⛔ **interval 式 → 移植后删除** |
| **RyouToppa** | 2 | 0 | ⛔ **interval 式 → 移植后删除** |

★ 其余任务（`DemonEncounter` / `Dokan` / `Duel` / `FindJade` / `KekkaiActivation` /
`MysteryShop` / `Secret` / `Tako` / `TrueOrochi` / `WantedQuests` /
`ActivityShikigami` / `BudokaiTournament` / `CollectiveMissions` /
`ExperienceYoukai` / `GoldYoukai` / `FrogBoss` / `GuildActivityMonitor` /
`KekkaiUtilize` / `Nian` / `Orochi` …）**用的是 `set_next_run(target=...)`**
—— **真实日期时间式, 属正当用途**, 不是要删的 `custom_next_run`。

**新结论（修正我上一轮的判断）**: 需要"移植后删除"的只有 **4 个任务**,
其中 `Hunt` / `RyouToppa` / `MemoryScrolls` 是**纯 interval 式**（应删）,
`GuildBanquet` 是混合（保留真实日期部分）。

★ 用户对此的论证（我接受）:
> "在设置了 window 的情况下, 执行顺序都是按照队列依次执行的,
>  谁会希望一个任务在几点之后再开始而不是早早地完成呢? 这意味着效率变低。
>  我们设计重构的初衷就是为了消除这种低效率设计。"

→ 上一轮我"保留 `custom_next_run`"的决定**基于错误的模型**（以为 interval 仍决定调度）。
**撤回该决定。**

---

# 9. 本轮（F1/F2）进度 —— ★ 区分"已做"与"未接线"

## 9.1 F1 · 让 `Function.window` 真的读 `meta.py` —— ✅ 已生效（有实测）

| 项 | 状态 | 证据 |
|---|---|---|
| `Function._build_window` 优先读 `TaskSpec.window` | ✅ | `module/config/config.py` |
| 多段窗口的并集表达 | ⚠ **有损** | `Hunt` 显示"每天 06:00-23:00", **丢了下午段**（应"周一~周四 06:00-23:00 与 周五~周日 17:00-23:00"）。布尔判断足够, 但 **`next_opening` 会不准** —— 仍待 F1b |
| 实测窗口生效 | ✅ | 07:50 实测: `DemonEncounter` 每天 17:00-23:00 / `in_window=False`; `pending=25 waiting=2`（修复前 27/0）|
| 我此前的虚报已改正 | ✅ | §8.4 |

## 9.2 F2 · 周期推导默认窗口 —— 🔄 **基础设施已完成, 但`TaskSpec` 尚未接线**

| 子项 | 状态 | 说明 |
|---|---|---|
| `Period` 加 `MONTHLY` | ✅ | `module/config/resource.py`; `TaskPeriod` 同步 |
| `AvailabilityWindow` 加 `days_of_month` | ✅ | 空元组 = 不限（**不是**"都不允许"）|
| `window_for_period(period, start, end)` | ✅ | DAILY/WEEKLY/MONTHLY -> 窗口; `NONE` -> `None` |
| `describe()` 支持每月 | ✅ | "每月 00:00-23:59" / "每月 1-15 日 …" / "每月 16-月末 日 …" |
| **修一个真 bug**: `is_unrestricted` 漏判时刻 | ✅ | 原来只判 `len(days)==7` -> `AvailabilityWindow(True, 17:00, 23:00)` 被**误判成"不限"**（明明只开放 6 小时）。守卫 `test_is_unrestricted_accounts_for_month` |
| 措辞修正 | ✅ | `describe()` 对未声明的窗口返回 **"未声明开放时段"**（原"不限时段"会**掩盖缺失** —— 用户要求"所有定时都有 window"）|
| **`TaskSpec.windows_effective` 回退到周期推导** | ✅ **已接线** | 取值顺序: ①`meta.py` 显式 `window` ②`window_for_period(period)` ③都没有 -> `enabled=False`。新增 `period_effective` / `declared_window` 两个属性 |
| **46 个任务补显式 window** | ✅ **已补 18 个（其余 28 个由周期推导）** | 见 §9.5 |

★ **不算完成**: F2 只是把"能推导"这个能力做好了, **调度器还看不到**。
按纪律标 🔄, 不标 ✅。

## 9.3 剩余工作（按依赖）

| 步 | 内容 | 状态 |
|---|---|---|
| **F1b** | 多段窗口在 `Function` 里不再用有损并集 | ⬜ |
| **F2b** | `TaskSpec.windows_effective` 回退到 `window_for_period`（接线上文的能力）| ⬜ |
| **F2c** | 46 个任务补显式 window + **校验脚本**（没写就报错, 让缺失可见）| ⬜ |
| **F3** | **队列顺序成为唯一调度依据**, `interval` 完全废弃 | ⬜ **核心** |
| **F4** | 删 `custom_next_run`（4 个任务移植; `MemoryScrolls` 需用户定）| ⬜ |
| **F5** | 移除语义: 定时 -> 停用; 次数 -> 回【添加任务】池 | ⬜ |
| **F6** | 前端: 待执行+执行顺序**合并一套可拖**; 「未到开放时间」; 括号改悬停 | ⬜ |
| **F7** | 测试重写 | ⬜ |

## 9.4 仍需用户确认（未阻塞, 但影响后续）

1. **`MemoryScrolls` 的跨任务排期**（`custom_next_run(task='Exploration', ...)`）——
   删掉后 `Exploration` 靠自己队列位置决定; 触发条件是**游戏状态**, 窗口表达不了
2. **46 个任务补 window 的方式** —— 每任务显式写 vs 周期推导 + 校验脚本
3. **`Period.MONTHLY` 已加**（实测原本只有 none/daily/weekly）

---

# 9.5 F2b / F2c 完成（本轮）—— ★ 含口径澄清

## 结果（实测）

```
任务总数 54
  显式声明 window    26   （原 8 + 本轮补 18）
  由周期推导         28
  **缺失**            0   ← 用户要求"所有的定时都有着 window 属性"
```

`python dev_tools/check_windows.py` -> **exit 0**（此前 exit 1, 报 18 个缺失）。

## ★ 诚实说明: 本轮补的 18 个是"整天窗口", **行为零变化**

补的窗口是 `AvailabilityWindow(True, time(0,0), time(23,59))` ——
`contains()` 恒 `True`, 与补之前的 `AvailabilityWindow()`（`enabled=False`,
也恒 `True`）**在行为上完全等价**。

**所以这一步是"纯声明"**: 把"没写"变成"写了", 让**缺失可见**
（`check_windows.py` 能核对）, 但**不改变任何既有行为**。

★ **仍然要做的**: `AreaBoss` / `Duel` / `WeeklyTrifles` / `TalismanPass` /
`KekkaiUtilize` / `GoldYoukai` / `ExperienceYoukai` / `Tako` 等有**真实游戏时段**
的玩法, 需要按机制**收窄** —— 那是**行为变更**, 必须逐个核实（§10.5 不猜语义）。
已登记, 未做。

## `Function.window` 的优先级（本轮确立）

| 顺序 | 来源 | 说明 |
|---|---|---|
| ① | `TaskSpec.window`（`meta.py`）| **游戏机制, 权威** |
| ② | `scheduler.window_*`（配置项）| 回退（旧机制遗留, 4-E 已从界面移除）|
| ③ | `AvailabilityWindow()` | 都没有 -> `enabled=False` |

★ 因为①优先, **测试用真实任务名注入 `scheduler.window_*` 不再生效**
（54 个任务全都有 meta 了）。已改用 `monkeypatch` 屏蔽 `TC.get_spec`
来测②这条回退路径 —— 见 `test_function_window.py`:
`TestMetaWindowPriority`（①）/ `TestSchedulerConfigFallback`（②）。

★ 踩过的坑: 想用"合成任务名"走②, 但 `ConfigModel.type()` 对未知任务名抛
`KeyError` —— **合成名走不通**, 必须用 monkeypatch。

## 守卫测试（新增 17 个）

`tests/module/config/test_every_task_has_window.py`:
* **一个都不能缺窗口**（含缺失任务的明确报错信息）
* 每个任务必须落在"显式声明"或"周期推导"之一
* `dev_tools/check_windows.py` 必须 exit 0（同一份审计, 命令行/CI 可用）
* 推导出的窗口**不该限制任何时刻**（否则会改变既有行为）
* 8 个显式活动窗口的内容逐个钉住（逢魔 17:00 / 狭间暗域 周五六日 19:00 …）

---

# 10. F5 · 「移出队列」分两类 —— ✅ 已完成（用户修正了我的错误）

## 10.1 用户修正

我此前把"移出队列"写成**无条件停用**（`sch.enable = False`）。用户明确纠正:

> "执行队列中移除后自动停用只针对定时任务, 固定任务移除后应该返回添加任务的池子里。"

## 10.2 修正后的规则

| 任务类型 | `auto_queue` | 移除后 |
|---|---|---|
| **定时任务** | `True` | 出队列 **且 `enable=false`** |
| **固定/次数任务** | `False` | **只出队列**, `enable` 保持 -> 回到【添加任务】池子 |

**为什么定时任务必须停用**: 自动进队列的任务只要 `enable=true` 就会被
`Config.build_queue()` **重新补进队列** —— 只从 `run_list` 删掉是**无效操作**。

**为什么次数任务不能停用**: 它们不在自动补齐范围内, 出队列后不会被补回来。
若也停用, 用户想再跑就得先回任务列表启用 —— 多余步骤。

## 10.3 实测证据

```
GoldYoukai: auto_queue=True  enable=False
    msg: 已把「GoldYoukai」移出队列并停用。它启用后会自动回到队列。
RealmRaid:  auto_queue=False enable=True
    msg: 已把「RealmRaid」移出队列。它仍在【添加任务】里, 可随时加回。
```

守卫: `tests/module/server/test_queue_removal_semantics.py`（**5 个**）
* 定时任务 -> `enable=False`（内存 + **磁盘**都查）
* 次数任务 -> `enable=True`
* 次数任务移出后**出现在候选端点里**（端到端）
* 定时任务移出后（已停用）**不在**候选里
* 提示文案分两类

★ 踩过的坑: 断言"磁盘上的 `enable`"时**不能用 `mm.config_cache()` 再读** ——
  它可能返回**缓存实例**, 而端点在内部用的是**另一个** `Config` 对象。
  实测: 端点返回 `enable=False`、磁盘文件也是 `false`,
  但测试持有的 `cfg.model` 仍是旧值 -> **假失败**。改为直接读 JSON 文件。

## 10.4 前端同步（OASX）

`queue_panel.dart` / `task_list_controller.dart` 的确认弹窗、按钮文案、tooltip
都改成**分两类**（`Text(auto ? '移出并停用' : '移出队列')`）。
`flutter analyze` 无问题; `flutter test` 79 passed。

## 10.5 ★ OASX 推送**权限不足**（非代码问题）

```
remote: Permission to runhey/OASX.git denied to passioki.
fatal: unable to access 'https://github.com/runhey/OASX/': 403
```

`git ls-remote --heads origin` 只有 `refs/heads/master` 与 `refs/heads/page`
—— **远端根本没有 `oas-tasks-ui` 分支**, 且当前账号对该仓库**无写权限**。

→ OASX 的改动**已提交在本地** (`oas-tasks-ui`), 但**推不上去**。
  这不是重试能解决的（重试 20 次全 403）。**需要用户处理仓库权限**。

## 10.6 ★ 发现一处**真实设计张力**（未解决, 记录）

`GuildBanquet` 的 `custom_next_run` 用 **`banquet_day_1` / `banquet_day_2`**
（**用户配置的周几**）决定下次哪天跑:

```python
if today < self.banquet_day_1:
    self.custom_next_run(..., time_delta=self.banquet_day_1 - today)
elif self.banquet_day_1 <= today < self.banquet_day_2:
    self.custom_next_run(..., time_delta=self.banquet_day_2 - today)
...
```

而 `AvailabilityWindow.days` 是**冻结的**（`frozen=True` dataclass, 声明时固定）
—— **无法表示"用户可变的两个星期几"**。

**这是真实张力, 不是遗漏**: 要删它的 `custom_next_run`, 必须先让窗口能表达
"周几来自用户配置"。三个选项:

| 选项 | 说明 |
|---|---|
| (a) 把宴会日**收窄**为固定值 | **改变用户语义**（用户就白配了）|
| (b) 给 `AvailabilityWindow` 加 **"动态 days"**（运行时从配置读）| 让"冻结"的窗口变成可变, 影响面大 |
| (c) **保留** `custom_next_run` 给这一个任务 | 与"彻底删除"目标冲突 |

**未做决定, 已记录**。同类还有 `RyouToppa`（`next_ryoutoppa_time`）、
`Restart`（领体力 12:00/20:00）、`MemoryScrolls`（跨任务给 Exploration 排期）。

---

# 11. F3 · 队列顺序成为唯一调度依据 —— ✅ 已完成（实测）

## 11.1 用户的设计（原话）

> "待执行里为什么不能和执行顺序一样拖动呢, 他俩应该并在一起啊, 而等待中还没到点的却没有一个"
> "定时任务的拖动代表执行顺序发生了变化。完成上一个任务就会接着完成下一个。
>  正在运行 a, 执行顺序 bcd, 待执行 efg, 我把 g 拖到 bgcd, 这样运行完 B 就会运行 g。"
> "现有的不能拖动是不是意味着当前任务调度还是按照 interval 间隔时间来完成任务的,
>  而非设计要求中的排序依次完成?"

**用户的判断是对的** —— 此前确实不是"按队列依次执行"。

## 11.2 查明**两个**根因

### 根因 1: 队列顺序被 `timed_sort_key` 完全覆盖

`TaskScheduler.schedule(LIST, ...)` **确实**按队列位置排好了,
但紧接着 `_order_by_timed_priority()` 用 `timed_sort_key`
（到点程度 / 窗口快关 / 耗时短）**把整个列表重排**。

**实测**（2026-10-10）:

| 队列位置 | 任务 | 实际派发位置 |
|---|---|---|
| 1 | `Delegation` | **第 4** |
| 9 | `ExperienceYoukai` | **第 1** |

### 根因 2: **队列外的任务也在跑**

```
queue   = 18 个
pending = 25 个      ← 多出 9 个
```

多出的 9 个（`EternitySea` / `Exploration` / `Orochi` / `FallenSun` /
`GoryouRealm` / `Hyakkiyakou` / `RealmRaid` / `RyouToppa` / `Sougenbi`）
都是 `auto_queue=False` 的**次数任务** —— 用户**没把它们加进队列**,
它们却在跑。这与"队列是唯一调度依据"直接矛盾。

### 根因 3（顺带发现）: `server_update` **覆盖**了窗口对齐

`task_delay()` 里原本是:

```
next_run = self._align_to_window(task, next_run)   ← 对齐
if server: ...                                      ← 又覆盖!
```

`server_update` 默认 `09:00` -> 走 `else` 分支 ->
`next_run = parse_tomorrow_server(...)` -> **直接变成"明天的 09:00"**,
**完全无视窗口** —— 对齐**白做**。

已把 `_align_to_window` 移到**最后**, 让"落在窗口内"成为不可被覆盖的终态。

## 11.3 修法

| 改动 | 说明 |
|---|---|
| `Config._is_list_rule(rule)` | **新增**。判断是否 `LIST` 规则 |
| `Config._order_by_queue(pending)` | **新增**。按队列顺序排 + **剔除队列外任务** |
| `LIST` 分支走 `_order_by_queue` | 队列顺序**就是**执行顺序, 队列外的**不跑** |
| 其它规则保留 `_order_by_timed_priority` | `FILTER`/`FIFO`/`PRIORITY` 本来就是"按机制排" |
| `_align_to_window` 移到 `server_update` **之后** | 修上面根因 3 |
| 「运行一次」`_order_by_manual_run` **保留** | 它是用户的**显式即时指令**, 不是"按机制插队" |

## 11.4 ★ 实测证据

```
★ pending == 队列剔除(waiting) 后的保序子序列: True

队列顺序即执行顺序:
   1. Delegation          待执行
   2. KekkaiUtilize       待执行
   3. AreaBoss            待执行
   4. BondlingFairyland   待执行
   5. AbyssShadows        未到开放时间      ← 窗口 周五六日 19:00-20:00
   6. DailyTrifles        待执行
   7. DemonEncounter      未到开放时间      ← 窗口 每天 17:00-23:00
   8. Duel                待执行
   9. ExperienceYoukai    待执行
  10. GoldYoukai          待执行
  ...

pending 25 → 16（队列外的 9 个不再跑）
```

★ 这正是用户要的: **队列顺序 = 执行顺序**;
**不在窗口的变灰进「未到开放时间」**（§8.2 的规则 B）。

## 11.5 ★ 踩过一个**静默失效**的坑

```python
# ❌ 永远为 False —— 改动静默失效（派发顺序一点没变, 也不报错）
if str(_rule).lower() not in ('schedule_rule.list', 'list'):

# 实际: str(ScheduleRule.LIST) == 'ScheduleRule.LIST'  (不是 'List')
```

已改用 `_is_list_rule()`（枚举取 `.value`, 字符串直接比）,
并加守卫 `test_str_of_enum_is_not_the_value` 把这个坑**钉住**。

## 11.6 `interval` 的残留（如实）

**顺序上已经不影响** —— 队列顺序是唯一依据（§11.4 实测）。

但 `task_delay()` 里**仍有回退分支**（L1315-1316）:

```
if success:
    interval = scheduler.success_interval
else:
    interval = scheduler.retry_interval     ← 失败退避, 保留（台账 7.6）
```

它只在 `_next_run_from_resource()` 返回 `None` 时生效（即
`Resource.recharge.kind` 不是 `interval`/`slots` 的任务）。

★ 失败路径的 `retry_interval` **要保留** —— 退避重试是独立概念（与资源补充无关）。
★ `success_interval` 的**彻底删除**还未做（见 §13.2）。

## 11.7 守卫测试（新增 8 个）

`tests/module/config/test_queue_is_authority.py`:
* **核心不变量**: `pending` 是队列剔除 `waiting` 后的**保序子序列**
* 队列外的任务**不该**进 `pending`
* `pending` **不能**是 `timed_sort_key` 排出来的顺序（反回归）
* `_is_list_rule` 对 4 种规则 + 3 种字符串写法都正确
* **钉住坑**: `str(ScheduleRule.LIST) == 'ScheduleRule.LIST'`

---

# 12. ★★ 窗口的**准确数据模型**（用户 2026-10-10 澄清）★★

## 12.1 术语纠正

**OAS 只有一个 window 概念: 任务可执行窗口。**
（我此前用过"会话窗口"的说法 —— **那是错的, 不是会话窗口**。）

## 12.2 用户给出的准确结构

```
窗口开始
  下拉选择：每天、每周、每月
  下拉选择：时:分 / 周几:时:分 / 几号:时:分
窗口结束
  下拉选择：每天、每周、每月
  下拉选择：时:分 / 周几:时:分 / 几号:时:分
```

即 **两端各自带一个周期**:

| 端 | 周期 | 取值形式 |
|---|---|---|
| **窗口开始** | 每天 | `时:分` |
| | 每周 | `周几 时:分` |
| | 每月 | `几号 时:分` |
| **窗口结束** | 每天 | `时:分` |
| | 每周 | `周几 时:分` |
| | 每月 | `几号 时:分` |

★ 这比我实现的 `AvailabilityWindow(enabled, start, end, days)` **表达能力更强**:
* 我的是"**每天**的 [start, end) 时段 + 限定星期" —— 一个窗口只覆盖同一天内
* 用户要的是**两端可以跨越不同的周期单位**（如"每月 1 号 00:00 → 月末 24:00"
  就是 start=每月1号00:00, end=每月末24:00）

## 12.3 用户对"用户可改"的要求

> "缺 window 用 period 推导, 记得要符合前端设计意义
>  （**用户可以选择每天, 然后把时间改为 17-23 点**）, 后端也要符合这个逻辑"

→ **`window_start` / `window_end` 必须是用户可见可改的**。

★ 我此前（4-E）把它们当"内部字段"**隐藏了 —— 那是错的**, 已在本轮修正:
现在 `window_enable` / `window_start` / `window_end` / `window_days` / `period`
**全部用户可见**（用户配置面 4 → 9 个字段）。

优先级: **用户配置的 window > `meta.py` 声明的游戏机制**（取并集, 见
`Function._build_window`）。

## 12.4 其它澄清

| 项 | 用户原话 | 影响 |
|---|---|---|
| `Period.MONTHLY` | "period.monthly作为预留的嘛, 可以下拉选择每月, 确保**后端有这个功能**, 前端才能出现" | 后端已加（本会话 F2）; **前端下拉还需确认** |
| `custom_next_run` | "用户配置时刻/周几怎么处理, 这**相当于多 window**" | → 应当**移植成多窗口**（与 (b) 选项一致）|
| `success_interval` | "如果没有用到那么就删掉" | 待核实后删 |
| `MemoryScrolls` | "**只做停止用途, 不做排期**" | 删掉它给 `Exploration` 排期的那行 |
| 仓库 | "https://github.com/passioki/OASX 可以推送" | 见 §13.2 |

## 12.5 ★ 新增需求: 任务完成汇报 tab

> "这顺便发现了一个可以添加的显式汇报屏幕功能 —— 添加一个**任务完成汇报 tab**,
>  现在的日志属于原始日志, 应该**转移到单独界面**, 用来 debug,
>  当前日志位置替换为**任务完成汇报**的 tab, 只会报完成了哪些、
>  **出错任务标注**等等其它可以作为简报的内容"

→ 这是一个**新功能**（不在原目标里）, 已登记为后续工作（见 §13.3）。

---

# 13. F6 完成情况 + 剩余工作

## 13.1 F6 已完成（前端的"合并"部分）

| 项 | 状态 | 说明 |
|---|---|---|
| 「执行顺序」与「待执行」**合并成一套可拖列表** | ✅ | 只有一个 `ReorderableListView`, 渲染 `c.queuedTaskRows` |
| 「等待中」改名「**未到开放时间**」 | ✅ | 不在窗口的**变灰**（`disabledColor`）|
| **显示自动补齐的定时任务** | ✅ | ★ 顺带修掉用户报的 bug: 此前只渲染 `entries`（`run_list`）, 而**自动补齐的任务不在里面** -> 启用了金币妖怪/经验妖怪/狭间暗域**界面上看不到** |
| 「休息」条目仍可拖 | ✅ | 它也在 `run_list` 里 |
| `window_*` / `period` 用户可见可改 | ✅ | 修正 4-E 的过度隐藏 |
| 译文补齐 | ✅ | `window_*_help` / `period_help`（1096 条）|

新增: `queuedTaskRows`（有效队列）· `reorderQueue`（统一重排）。

★ 删掉了不再使用的 `_listBlock`（只读观察窗）。

## 13.2 ★ OASX 推送: **基础设施问题**（未解决）

已按用户给的地址改了 remote:

```
origin -> https://github.com/passioki/OASX.git
```

**权限 OK 了**（不再 403）, 但推送失败:

```
remote: fatal: did not receive expected object 92f63f57826c125b7e13103348513fcdcb9809a5
error: remote unpack failed: index-pack failed
```

**排查记录**（都试过）:

| 检查 | 结果 |
|---|---|
| `git fsck` | **干净**, 无损坏 |
| 仓库大小 | 仅 2.61 MiB（很小）|
| `92f63f57` 是否存在 | **本地不存在**（`git cat-file` 报 bad object）|
| 远端状态 | **空仓库**（`ls-remote` 无任何分支）|
| `push --dry-run` | **成功**（"* [new branch]"）|
| 大缓冲 / `core.compression=0` / `pack.threads=1` / `protocol.version=2` | 全部仍失败 |
| 重试 6 次 | 全部失败 |

**本地提交是完好的**（`oas-tasks-ui` @ `2fca0c3`）。这是**推送侧的问题**,
需要用户在 GitHub 侧检查（仓库是否异常 / 换 SSH 或 token / 或换个仓库）。

## 13.3 剩余工作（未做, 按优先级）

| # | 项 | 来源 | 状态 |
|---|---|---|---|
| 1 | **窗口数据模型重构**: 两端各带周期（每天/每周/每月 + 相应取值）| §12.2 | ⬜ **核心** |
| 2 | `MemoryScrolls` 删掉给 `Exploration` 排期那行 | 用户 | ⬜ |
| 3 | `custom_next_run` **移植成多窗口** | 用户（"相当于多 window"）| ⬜ |
| 4 | `success_interval` 核实未用后**删除** | 用户 | ⬜ |
| 5 | 前端 `period` 下拉**确认有"每月"** | 用户 | ⬜ |
| 6 | **任务完成汇报 tab**（日志移到单独 debug 界面）| 用户（新需求）| ⬜ |
| 7 | `Function` 多段窗口不再用有损并集 | F1b | ⬜ |
| 8 | 测试重写 | F7 | ⬜ |

---

# 14. ★★ OASX 推送 —— **已解决**（2026-10-10）★★

## 14.1 根因

**原仓库的历史里有坏对象** `92f63f57826c125b7e13103348513fcdcb9809a5`
（`git cat-file` 报 bad object, 本地不存在）—— 只要推**任何含该历史的 ref**
都会被服务端拒绝:

```
remote: fatal: did not receive expected object 92f63f57...
error: remote unpack failed: index-pack failed
```

**不是**权限问题（换 `passioki/OASX` 后不再 403）、**不是**仓库大小（仅 2.61 MiB）、
**不是** `git fsck` 能查出的损坏（fsck 干净）。

## 14.2 解法（用户建议的方法, 稍作调整）

用户建议:
```
git remote add origin https://github.com/passioki/OASX.git
git branch -M main
git push -u origin main
```

★ 直接这么做**仍然失败** —— 因为 `oas-tasks-ui` 的历史里就带着那个坏对象。

**真正有效**的做法是**绕开坏历史**:

```bash
git archive HEAD -o OASX.zip          # 导出当前树的完整内容
# 解压到新目录 -> git init -> commit -> push
```

结果:
```
* [new branch]      main -> main
远端: 052b281db43bc110fb3d00d4213b2d2f6f732e0e  refs/heads/main
```

## 14.3 ★ 代价（必须说清）

推上去的 `main` 是**单个提交**（"OASX: 调度/队列 UI 重构（F1-F6）"）,
**不是**逐步的 23 个提交 —— 坏对象在历史里, 完整历史推不上去。

* **本地** `D:\OAS-dev\OASX-src` 保留**完整历史**（`oas-tasks-ui` / `main` /
  `oas-tasks-ui-backup` 都指向同一提交 `2fca0c3`）
* **远端** `passioki/OASX` 只有最终状态

★ 若需要逐步历史, 得先修原仓库的对象（`git fetch --refetch` 或从
  `runhey/OASX` 重新 clone 再把改动 rebase 过去）。

## 14.4 顺带修掉的一个**真问题**

`period` 是**下拉**, 界面显示的是**选项值**（`daily`/`weekly`/`monthly`）
而不是 `_help`。而 i18n 守卫原本只扫带 `_help` 后缀的**字段 key** ——
**漏了枚举选项值**, 于是下拉里会赤裸裸显示英文。

已补 4 条译文（`none`/`daily`/`weekly`/`monthly` -> 不限/每天/每周/每月）,
并加守卫。**`period` 下拉现在会正确显示"每月"**。

★ 这也回答了用户 #5 的疑问: **后端已有 `monthly`, 前端下拉由
  `enumEnum` 动态生成**, 所以只要后端有, 前端就会出现
  （新增守卫 `test_monthly_is_offered_by_backend` 钉住）。

---

# 15. 本轮（#2 / #5）完成情况

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| 2 | `MemoryScrolls` **只做停止用途** —— 删掉替 `Exploration` 排期那行 | ✅ | `custom_next_run` 全库 10 → **9** 处; 编译通过; 守卫 3 个 |
| 5 | 前端 `period` 下拉**有"每月"** | ✅ | 后端 `enumEnum=['none','daily','weekly','monthly']`; 选项值译文已补; 守卫 2 个 |
| — | `window_*` 用户可见可改 | ✅ | 见 §12.3; 用户配置面 4 → 9 |
| — | **OASX 推送** | ✅ **已解决** | 见 §14 |

守卫: `tests/module/config/test_window_ui_contract.py`（**10 个**）
* `period` 选项值必须有**中文**译文
* 后端 `period` 的 `enumEnum` 必须含 `monthly`（前端下拉才会出现）
* `period` / `window_*` 必须**用户可见**（不是 internal）
* `/schema` 的 `scheduler` 组里必须能看到窗口字段
* `MemoryScrolls` 不得有 `custom_next_run`、不得替别的任务排期、仍应 `raise TaskEnd`

★ 踩过: 直接查 `model_json_schema()['properties']['period']['enum']` 得到 `[]`
  —— 因为 `period` 是 **`$ref`**, `enum` 在 **`$defs`** 里。
  改用端到端的 `/schema` 输出（`enumEnum` 已展开好）。

---

# 16. #4 · 核实 `success_interval` 是否可删 —— ⛔ **仍在使用, 不能直接删**

## 16.1 用户要求

> "success_interval 如果没有用到那么就删掉"

**「如果没有用到」** —— 所以我先核实。**结论: 还在用。**

## 16.2 核实结果（逐处, 2026-10-10）

全库 **54 处**出现（含注释/文档/测试）; 其中**真正执行的代码**是:

| 位置 | 用途 | 能否直接删 |
|---|---|---|
| `tasks/DailyTrifles/script_task.py:58` | `next_run = now + self.config.daily_trifles.scheduler.success_interval` | ⛔ **不能** —— 任务直接读它算下次运行 |
| `tasks/TrueOrochi/script_task.py:207` | `next_run = now + self.config.true_orochi.scheduler.success_interval` | ⛔ **不能** |
| `module/config/config.py:1315` | `task_delay()` 的**回退分支**（`_next_run_from_resource()` 返回 `None` 时）| ⛔ **不能** —— 有任务走到这条路 |
| `tasks/*/config.py`（7 个任务）| 覆盖 `success_interval`（`FloatParade` 3 天 · `Secret` 7 天 · `KekkaiUtilize`/`TalismanPass` 6 小时 …）| ⚠ 配置面, 删字段会连带 |
| `module/config/resource.py:336` | `Resource.from_legacy(success_interval=...)` 迁移桥 | ⚠ 迁移用, 保留 |
| 其余约 35 处 | 注释 / 文档字符串 / 测试断言 | 非代码 |

## 16.3 正确顺序（先移植, 再删）

1. **移植** `DailyTrifles` / `TrueOrochi` 的 `now + success_interval`
   -> 改为靠**自己的窗口**（§8.1 的模型: 所有定时任务都有 window）
2. **删掉** `task_delay()` 的回退分支（L1315-1316）—— 但**必须保留**
   `retry_interval`（失败退避是**独立概念**, 台账 7.6; 用户没要求删它）
3. **删字段** `Scheduler.success_interval` + 7 个任务的覆盖 + 相关迁移
4. 更新测试断言

★ **我没有直接删** —— 那会**破坏 3 处正在执行的代码**。
  按纪律（§10.5 不猜语义 / 不冒险）, 标 ⬜ 并附上确切的依赖清单。

## 16.4 与用户"间隔完全废弃"的关系

用户 A 选项 = "间隔完全废弃"。**当前状态**:

* ✅ **顺序上已废弃** —— 队列顺序是唯一调度依据（§11 实测）
* ⛔ **字段还在被读** —— 上面 3 处（本节的清单）
* ✅ `period` / `window` 已成为**新的**节奏表达（§8.1 / §12）

所以"完全废弃"还差**这 3 处移植**。已登记为 #4 的后续。

---

# 17. #4 移植 · 步骤 1 完成（任务侧的 2 处已清理）

## 17.1 做了什么

| 位置 | 原来 | 现在 |
|---|---|---|
| `DailyTrifles/script_task.py:58` | `next_run = now + self.config.daily_trifles.scheduler.success_interval` | `next_run = self.config.next_run_after('DailyTrifles', after=now)` |
| `TrueOrochi/script_task.py:207` | `next_run = now + self.config.true_orochi.scheduler.success_interval` | `next_run = self.config.next_run_after('TrueOrochi', after=now)` |

★ 新增 `Config.next_run_after(task_key, after=None)` —— 用**任务的窗口**精确算
"下次允许运行的时刻", 取代"加一个用户配置的间隔"这种**近似**。
实测:

```
DailyTrifles     after=2026-10-10 12:00 -> 2026-10-11 00:00
TrueOrochi       after=2026-10-10 12:00 -> 2026-10-11 00:00
DemonEncounter   after=2026-10-10 12:00 -> 2026-10-10 17:00   ← 窗口 17:00-23:00
DemonEncounter   after=2026-10-10 18:00 -> 2026-10-11 17:00   ← 已过窗口
```

两者都是"跨月/跨周就重置计数"的用途 —— 现在由**窗口**决定, 不再依赖 interval。

★ `TrueOrochi` 的失败分支**保留** `retry_interval`（退避重试是独立概念, 台账 7.6）。

## 17.2 ★★ 重大发现: **22/27 个启用任务仍在走 interval 回退** ★★

实测（`_next_run_from_resource` 的返回）:

```
能算出（用 Resource）:  5 个
**回退到 interval**  : 22 个
    AbyssShadows(daily) · BondlingFairyland(daily) · EternitySea(daily)
    FallenSun(daily) · GoryouRealm(daily) · Orochi(daily) · Sougenbi(daily)
    TrueOrochi(weekly)
    AreaBoss(none) · DailyTrifles(none) · DemonEncounter(none) ·
    ExperienceYoukai(none) · GoldYoukai(none) · KekkaiUtilize(none) ·
    MysteryShop(none) · RealmRaid(none) · RichMan(none) · RyouToppa(none) ·
    SoulsTidy(none) · TalismanPass(none) · WantedQuests(none)
```

**根因**: `_next_run_from_resource()` 对 `refill not in ('interval', 'slots')`
**返回 `None`** —— 于是 `period=daily` / `weekly` 的任务
（`Orochi` / `FallenSun` / `Sougenbi` / `TrueOrochi` …）**本该用周期算, 却退回 interval**。

**这与用户的设计冲突**:

> "缺 window 用 period 推导 … 后端也要符合这个逻辑"

用户要求 `period`（每天/每周/每月）成为**节奏的唯一表达**。
而当前 `period` 在**排期路径上完全没被使用**（只用于推导窗口的"描述"）。

## 17.3 下一步（#4 剩余）

1. 让 `_next_run_from_resource()`（或它的替代）**用 `period` 算**:
   * `period=daily`  -> 下次运行 = **当天的下一个周期边界**（或次日 0 点）
   * `period=weekly` -> 下周一 0 点
   * `period=monthly`-> 下月 1 日 0 点
2. 那之后, `task_delay()` 的 `interval` 回退分支（`config.py:1367`）
   才真正可以**删掉** —— 因为**没有任务**会走到它
3. 最后删字段 `Scheduler.success_interval` + 7 个任务的覆盖 + 迁移桥

★ **现在不能删**: 22/27 个任务仍依赖那条回退。按纪律标 ⬜, 附确切数字。

---

# 18. #6 · 任务完成汇报 —— 🔄 后端已完成, 前端 UI **未做**

## 18.1 用户需求

> "这顺便发现了一个可以添加的显式汇报屏幕功能 —— 添加一个**任务完成汇报 tab**,
>  现在的日志属于原始日志, 应该**转移到单独界面**, 用来 debug,
>  当前日志位置替换为**任务完成汇报**的 tab, 只会报完成了哪些、
>  **出错任务标注**等等其它可以作为简报的内容"

## 18.2 ✅ 已完成: 后端汇报

**新增 `module/config/report.py`** —— 纯数据聚合（无 FastAPI 依赖, 可单独单测）。

★ **不新增任何状态存储** —— 复用现有三份文件:

| 来源 | 回答什么 |
|---|---|
| `run_record`（`log/.run_record.json`）| 跑了**几次**、花了**多久** |
| `task_state`（`log/.task_state.json`）| **本周期完成**了哪些、充能还剩几次 |
| `failure_state`（`log/.failure_state.json`）| **失败**计数 + 冷却到什么时候 |

**新增端点** `GET /{script}/report`（`schema_router.py`）。

### 实测输出（真实数据）

```
summary: {"total": 18, "completed": 0, "failed": 1, "in_cooldown": 0,
          "total_runs": 30, "total_minutes": 47.9}
tasks:   18 个
    地域鬼王      runs=3   546s  marks=[]
    每日琐事      runs=0    40s  marks=[]
    式神委派      runs=0    28s  marks=[]
    逢魔之时      runs=2   405s  marks=['failed']      ← 出错标注
    斗技         runs=0    57s  marks=[]
    经验妖怪      runs=1    93s  marks=[]
    金币妖怪      runs=1   124s  marks=[]
errors:  1 条
    [failed] 逢魔之时：失败 1 次
```

### 「出错标注」的四种级别

| mark | 含义 |
|---|---|
| `cooldown` | 冷却中（还要等 N 分钟）—— **最严重, 排最前** |
| `failed` | 有失败计数 |
| `short` | 运行 < 20 秒就结束（可能没做成事）|
| `completed` | 本周期已完成 |

## 18.3 ✅ 已完成: 前端 API 客户端

`lib/api/api_client.dart` 加 `getTaskReport(scriptName)`（`flutter analyze` 无问题）。

## 18.4 ⬜ **未做**: 前端汇报 tab 的界面

用户要求的是:
1. **把现有日志位置替换成「任务完成汇报」tab**
2. **日志本身转移到单独界面**（供 debug）

**这两条都还没做** —— 需要:
* 新增一个汇报视图（渲染 `getTaskReport` 的 summary/tasks/errors）
* 把现有日志视图移到单独的 debug 入口
* 在 `task_list_view.dart` 里换 tab

★ 按纪律标 **⬜**, 不标 ✅。

## 18.5 守卫测试（16 个）

`tests/module/config/test_task_report.py`:
* 顶层结构 / `at` 是时间戳 / `summary` 键齐 / 任务行键齐
* **出错任务必须带 mark 且进 `errors`**
* `marks` 只能是已知四种（防拼错）
* 中文名（简报给人看, 不能是 `demonencounter`）
* `summary` 的计数与 `tasks` **逐项自洽**
* **数据源坏掉不崩**（monkeypatch 让 `run_record` 抛异常）
* 端点可用

## 18.6 OASX 推送（本轮又推成功一次）

因为完整历史仍带坏对象（§14.1）, 每次推送都要走
`git archive` + 新建仓库 + `push -f`:

```
+ 052b281...d47d6c4 main -> main (forced update)
```

★ 代价同 §14.3: 远端是**单个提交**, 本地保留完整历史。

---

# 19. #6b · 前端汇报 tab + 日志独立窗口 —— ✅ 已完成

## 19.1 按用户原话逐条落地

| 用户要求 | 实现 |
|---|---|
| "添加一个**任务完成汇报 tab**" | `TabBar` 加第三个 tab **「任务汇报」**（`length: 3`）|
| "现在的日志属于原始日志, 应该**转移到单独界面**, 用来 debug" | 新增 `_showRunLogs()` —— 点标题栏的 📄 图标打开**独立对话框**显示 `LogWidget` |
| "**当前日志位置替换为**任务完成汇报的 tab" | 宽屏右半栏、窄屏底部 —— 原来的 `LogWidget` 位置**全部**换成 `TaskReportPanel` |
| "只会报完成了哪些、**出错任务标注**" | 见下 |

## 19.2 新增 `lib/views/tasks/task_report_panel.dart`

**汇总行**: 任务数 · 已完成 · 有失败 · 冷却中 · 总运行 · 总耗时

**「需要注意」区**（出错标注）三级:

| 级别 | 图标 | 悬停说明 |
|---|---|---|
| `cooldown` | ⏳ | 失败后进入冷却，冷却结束前不会再派发这个任务 |
| `failed` | ⚠ | 该任务有失败记录 |
| `short` | ⏱ | 运行时间很短就结束，可能进去看了一眼就退了 |

**各任务明细**: 中文名 · 跑了几次 · 耗时 · 标签（已完成 / 冷却 N 分 / 失败 N 次 / 短运行 / 还剩 N 次）

★ **所有说明都走 `Tooltip`** —— 落实用户第 ⑤ 条"括号式说明改为悬停提示"。
★ 数据**全部来自后端 `GET /{script}/report`**，前端**不自己推导**。

## 19.3 测试更新（前端）

旧测试 `统一控制台: **两个 tab** + 日志常驻` 断言的正是本轮**故意改掉**的东西 ——
已改写为 `三个 tab（调度 / 执行队列 / 任务汇报）+ 日志移到独立窗口`, 并加**反向守卫**:

```dart
expect(body.contains('LogWidget('), isFalse,
    reason: '日志**不该**再常驻在 build 里 —— 它已移到独立窗口');
```

★ 那句守卫生效了: 我改完主分支后**忘记改窄屏分支**（还留着 `logs`），
  `flutter analyze` 抓到了 `logs` 未定义。

## 19.4 验证

| 项 | 结果 |
|---|---|
| 后端 pytest | **1615 passed, 2 skipped** |
| 前端 flutter test | **79 passed** |
| `flutter analyze` | No issues |
| OASX 提交 | `5fe3e8f`（本地）· 远端 `main` = **`d35b09e`** |

★ OASX 推送仍走 `git archive` + 新建仓库 + `push -f`（坏历史仍在, §14.1）。

---

# 20. ★★ 用户最终裁定（2026-10-10 第三轮）★★

## 20.1 窗口语义 = **(B) 两端必须同周期**

用户原话:

> "窗口语义：**(B) 两端必须同周期**"

即:
* 窗口开始 = **每天** + `时:分`   -> 窗口结束也必须是 **每天** + `时:分`
* 窗口开始 = **每周** + `周几 时:分` -> 结束也必须 **每周**
* 窗口开始 = **每月** + `几号 时:分` -> 结束也必须 **每月**

★ 我此前倾向 (A)（跨周期区间）, **用户选的是 (B)** —— 已按 (B) 修正理解。

## 20.2 ★★ 排期依据 = **整体任务开放窗口**（不是 period, 也不是 interval）★★

用户原话:

> "排期应该是用具体的 **window** 来算, **period 只是 window 的一个粗粒度**,
>  下边还有具体的时间区间如几点到几点呢。
>  应该用**整体的任务开放窗口 window** 来计算"

**这同时回答了我一直问的 ②** —— 我之前问"`period` 是否决定一天跑几次",
**答案是: 不是**。层次是:

```
period（每天 / 每周 / 每月）      ← 窗口的**粗粒度**
    └── window 的**具体时间区间**  ← 几点到几点（排期**用它算**）
```

所以:
* **排期** -> 用 **window**（`_align_to_window` / `next_opening`）
* **`period`** -> 只表达粗粒度（并给出窗口的默认跨度）
* **interval** -> **完全不用**（与用户第 ② 条 A 选项一致）

## 20.3 对实现的要求

| 项 | 现状 | 应改为 |
|---|---|---|
| `task_delay()` 成功路径 | 优先 `Resource`, **否则退回 `success_interval`** | **用 window 算**（不再有 interval 回退）|
| `_next_run_from_resource()` | 对 22/27 个任务返回 `None` -> 回退 interval（§17.2）| 让 **window** 兜底（不是 interval）|
| `success_interval` 字段 | 仍被回退分支读 | **可删**（回退分支消失后）|

---

# 21. 用户裁定: 窗口/周期**只管"能不能跑"**, 不管"跑几次"

## 21.1 用户原话（2026-10-10 第三轮）

> "**窗口和 period 都不决定一天跑几次**, 他们只能说是**这个时间可以跑**"
>
> "跑几次需要**用户自己设置跑几次**, 应该在**次数**里体现啊。
>  另外现在的任务执行里**添加任务应该设置为可以重复添加相同的任务**,
>  这样就**变相实现了多次跑任务**"

## 21.2 职责划分（最终）

| 概念 | 回答什么 | 载体 |
|---|---|---|
| **window** | 这个时间**可不可以**跑 | `TaskSpec.window` / 用户窗口字段 |
| **period** | window 的**粗粒度**（每天/每周/每月）| `Scheduler.period` |
| **次数**（`target`）| 用户想跑**几次** | `Scheduler.target` |
| **重复条目** | 同一任务在队列里**出现多次** | `run_list` 的多条 task 条目 |

★ **排期仍然只用 window**（§20.2）—— 窗口/周期/次数**都不**产生
  "一天跑几次"的语义。

## 21.3 已查明: **重复添加任务**有三个障碍（未做）

### 障碍 1: 候选端点把"已在队列"的过滤掉了

候选规则是 `enable && !auto_queue && !queued`。任务一旦加入, `queued` 为 true
-> **从候选里消失** -> **无法再加第二次**。

**修法**: 候选端点**不再排除 `queued`**（重复添加是允许且有意义的）,
只排除 `!enable` 与 `auto_queue`。

### 障碍 2: `build_queue()` / `task_order()` 都会去重

* `build_queue()` 用 `existing = {task}` 去重（**自动补齐**去重是对的）
* `run_list.task_order()` 是"去重保首" -> **重复条目的第二条拿不到队列位置**

**修法**: `list_order` 的 `explicit` 映射要从"任务名 -> 一个下标"改为
"任务名 -> **该任务所有条目的下标**"（或直接按**条目**排）。

### 障碍 3（更根本）: 派发状态是**按任务**存的, 不是按条目

`Scheduler.next_run` 在**任务**上; `task_state` 也是按 `config + task` 记的
（`get_charges` / `is_completed_in_period` —— 已实测确认）。

所以同一任务的两条重复条目**无法各自追踪"这条跑过没有"** ——
第一条跑完会把任务的 `next_run` 推到下次窗口开放, 第二条**拿不到独立状态**。

**要真正实现"重复条目各自跑一次", 需要按条目追踪**（给条目一个 id,
`task_state` 的键从 `task` 变成 `entry_id`）。这是**中等规模的状态模型改造**。

★ **没有擅自做** —— 它对 `task_state` / `scheduler_core` / 队列都是结构性的,
  且会改变现有"按任务记完成"的语义（影响 `is_completed_in_period`）。
  **已登记, 等用户确认。**

## 21.4 本轮已完成的两项

### ✅ #7 `Function` 支持**精确多段窗口**

实测: `Hunt` 周五 10:00 从"**误判在窗口内**"改为**正确的不在窗口内**。

```
Hunt 段数: 2
   周一周二周三周四 06:00-23:00
   周五周六周日 17:00-23:00
周五 10:00 -> in_window=False   ← 修复前是 True（有损并集的 bug）
周五 18:00 -> in_window=True
周一 10:00 -> in_window=True
```

守卫: `tests/module/config/test_multi_segment_window.py`（**12 个**）。

### ✅ 排期改为**由窗口算**（§20.2 的裁定落地）

`Config.next_run_after(task_key, after, strict=)`:

| `strict` | 语义 | 用途 |
|---|---|---|
| `True` | **总是**返回"下一次窗口开放" | **排期** |
| `False` | 在窗口内 -> 返回**本窗口结束** | 周期边界判断 |

`task_delay()` 成功路径已改为**窗口兜底** —— **不再退回 `success_interval`**。

实测:

```
strict=True（排期）:
  DemonEncounter 18:00 -> 10-11 17:00   已过窗口 -> 明天
  DemonEncounter 12:00 -> 10-10 17:00   还没到窗口 -> 今天
  Orochi         12:00 -> 10-11 00:00   整天窗口
  Hunt 周五 10:00      -> 10-09 17:00   多段生效（推到下午）

strict=False（周期判断）:
  DailyTrifles   12:00 -> 10-10 23:59   本窗口结束
```

★ 这让 §17.2 的"22/27 个任务走 interval 回退"**不再成立** —— 现在**全部由窗口决定**。

## 21.5 ★ 我犯的一个错误（已修）

我写的 `test_no_task_loses_segments` 用了 `TC.get(...).windows_effective`
—— 但 `TC.get()` 返回 **`TaskMeta`**, 而 `windows_effective` 在 **`TaskSpec`** 上。
必须用 `TC.get_spec(...)`。（`AttributeError` -> 已修）

---

# 22. A / B 完成: **允许重复添加同一任务**

## 22.1 用户裁定

> "现在的任务执行里**添加任务应该设置为可以重复添加相同的任务**,
>  这样就**变相实现了多次跑任务**"

## 22.2 ✅ A: 候选端点**不再排除** `queued`

| | 规则 |
|---|---|
| 改前 | `enable && !auto_queue && !queued` |
| **改后** | `enable && !auto_queue` |

任务加入队列后 `queued=true` -> 改前会**从候选消失** -> 无法加第二次。

★ 仍然排除 `auto_queue`（自动补齐的): 它们由 `build_queue()` 补齐,
  手动重复也没用（补齐按任务名去重）。

**实测**: 候选里出现了已在队列的 `BondlingFairyland` —— 可以再次添加。

## 22.3 ✅ B: `list_order` **按条目**建位置

`TaskScheduler.list_order` 原来用 `run_list.task_order()` ——
它是"**去重保首**"的, 于是重复条目的第二条**拿不到自己的队列位置**。

改为**遍历 `run_list.entries`**, 取每个任务的**最早**出现位置, 并记录
出现次数（重复时打日志）。

**实测** —— 编排 `[Delegation, RealmRaid, RealmRaid, AreaBoss]`:

```
调度结果: ['Delegation', 'RealmRaid', 'AreaBoss']
★ 一致: True
```

关键差别: `AreaBoss` 的位置现在是 **3**（旧行为因去重会算成 2）——
排序结果相同, 但**位置语义**正确了, 后续插入/拖拽才准。

## 22.4 ★ 障碍 3 仍未解决（见 §21.3）

派发状态是**按任务**存的（`Scheduler.next_run` / `task_state`）——
`TaskScheduler.schedule` 返回的是 `Function` 列表（**按任务**),
一个任务只有一个 `Function` 对象。

所以"同一任务的两条重复条目"**在排序层面只能映射到同一个位置**。
要真正让它们**各跑一次**, 需要**按条目追踪状态**
（给条目一个 id, `task_state` 的键从 `task` 变成 `entry_id`）。

★ **待用户确认** —— 这是中等规模的状态模型改造, 会改变现有
  "按任务记完成"的语义（影响 `is_completed_in_period`）。

## 22.5 守卫测试（6 个）

`tests/module/config/test_duplicate_queue_entries.py`:
* 候选源码里**不该**再有 `if command in queued`
* 端到端: 已在队列的次数任务**仍应**出现在候选里
* `list_order` 用**条目**位置（`AreaBoss` 位置 = 3）
* `RunList` 本身必须允许重复条目
* `task_order()`（旧字段）**仍**去重 —— 那是它的既有契约
* **反向守卫**: `list_order` 不该再用 `task_order()`

## 22.6 ★ 我又踩了一次"规则变了没同步测试"

`test_candidates_live`（我上一轮写的"按规则自己算一遍"）在规则改动后
**假失败** —— 因为它的 `expected` 里还排除 `queued`。

已同步更新（并显式注释"规则改了, 原算法已失效"）。
★ 教训: **同一规则在测试里重算一遍**会随规则漂移 —— 但它的价值
  （交叉验证）大于维护成本, 所以保留, 只是必须在规则变更时同步。

---

# 23. ★★ C 与 D 的裁定（用户 2026-10-10 第四轮）★★

## 23.1 ★ D 的答案: **次数**与**重复添加**是**两个机制**

用户原话:

> "**D, 两个机制**, 次数是**单一任务里设置战斗跑几次**,
>  重复添加是**重复跑整个任务**。
>  **a 50次, a50次**: 50 次是**次数**, 但是 a50次**重复添加了一次**。"

| 机制 | 含义 | 是否参与**排期** |
|---|---|---|
| **次数**（`Scheduler.target`）| **单一任务内**战斗跑几次 | ❌ **不参与** |
| **重复添加**（`run_list` 多条同任务条目）| **重复跑整个任务** | ✅ **它就是排期** |

**例子**: `a 50次, a 50次` = 队列里有 **2 条 a** -> 跑 **2 轮**, 每轮 **50 场**。

★ 纠正我之前的错误假设: 我曾以为"次数"是排期依据之一。
  **它完全与排期无关** —— 它只是"这一轮里战斗打几场"。

## 23.2 ★ C 的设计: `entry_id = 当前时间 + task`

用户原话:

> "**entry_id 用当前时间 + task 来实现**, 这样可以**分拆也可以合并**,
>  任务量上会不会就变得很小。"

### 格式

```
entry_id = f"{added_at:%Y%m%dT%H%M%S}-{task}"
例: 20261010T143005-RealmRaid
```

| 好处 | 说明 |
|---|---|
| **可拆** | 去掉时间戳前缀就得到 `task` |
| **可合并** | 同一个 `task` 的多条条目可以按需求合并显示/统计 |
| **稳定** | 条目身份不随队列顺序变化（拖拽不改变 id）|
| **可读** | 界面上显示成 `2026-10-10 14:30 · 个人突破` |

### ★ 为什么"任务量会变得很小"—— 用户这个担心是**对的**

* 状态键从 `config + task` 变成 `config + entry_id` -> **键的数量 = 队列条目数**
  （而不是任务数的倍数）→ 状态文件**更小**
* 但要为**每条条目**存 `period_key`, 所以条目多时线性增长
  （这是**必要的** —— 不按条目记就无法"各跑一次"）

### ★★ 实现上的**真正难点**（必须先解决, 否则做了也没用）

`TaskScheduler.schedule()` 返回的是 **`Function` 列表（按任务）** ——
一个任务只有**一个** `Function` 对象。所以**条目身份在调度层就丢了**。

调用链（已实测确认）:

```
Config._skip_by_period(task_key)                  <- 门槛
    └─ is_completed_in_period(config_name, task_key, period, reset_at)
                                    ^^^^^^^^  按**任务**查
Config._record_task_success(task_key)             <- 记录
    └─ record_success(config_name, task_key, ...)
                                  ^^^^^^^^  按**任务**写
```

**要做按条目追踪, 必须:**

1. `RunList` 的 `RunEntry` 加 `entry_id` 字段（`from_dict`/`to_dict` 保留它）
2. `_order_by_queue` / `list_order` 不再返回"任务 -> 位置"的映射, 而是
   **保留条目**（`pending` 要能区分"这是 a 的第 1 条还是第 2 条"）
3. `_skip_by_period` / `_record_task_success` 改成按 **entry_id** 读写
4. `task_state.is_completed_in_period` / `record_success` 的键改成 entry_id
   （**向后兼容**: 旧数据里是 `task`, 读不到就当"没完成" —— 已有这种兜底）

★ 第 2 步是**结构性**的（`Function` 是**按任务**的对象, 无法表达"两条同任务")。
  可能的做法: `pending` 从 `list[Function]` 改成 `list[(Function, entry_id)]`,
  或者让 `Function` 多一个 `entry_id` 属性（轻量, 但要小心复用同一个对象）。

★ **我没有擅自做** —— 它改动 `scheduler.py` / `run_list.py` / `task_state.py` /
  `config.py` 四处, 且会让 `_skip_by_period` 的语义从"按任务"变"按条目"。
  **已登记, 需要用户确认后实施。**

## 23.3 本轮已做: 前端【添加任务】允许重复

`_TaskPickerDialog` 现在:

* **不再隐藏**已在队列的任务
* 标注 **`已在队列 ×N`**, Tooltip 说明"再点一次会再加一条 ——
  同一任务排多条, 就是让它多跑几次"
* 每行带 ➕ 图标（明确可加）

★ 修了两个错误: 在 `_TaskPickerDialogState` 里误用 `c`（那是
  `_QueuePanelState` 的 getter, 应为 `widget.controller`）;
  并删掉已无用的 `_monitorRow`。

---

# 24. #1 窗口字段模型 + ⑥ 的**如实结论**

## 24.1 ✅ #1 完成: 窗口字段模型（按用户裁定的 **(B)**）

新增两个字段（`tasks/Component/config_scheduler.py`）:

| 字段 | 含义 |
|---|---|
| `window_period` | **每天 / 每周 / 每月**（枚举 `WindowPeriod`）|
| `window_dom` | `每月` 时的**几号**（1-31）|

★ **两端共用**一个 `window_period` —— 落实用户裁定的 **(B) 两端必须同周期**。

`_build_windows()` 现在按 `window_period` 决定用哪组值:
* `daily`   -> 用 `window_start` / `window_end`
* `weekly`  -> 再加 `window_days`（周几）
* `monthly` -> 再加 `window_dom`（几号）

### ★★ 同时修正一个**设计错误**: 用户配置应当**优先** ★★

**实测（修正前）**:
```
用户把窗口改成 17:00-23:00  ->  Function.window = 每天 00:00-23:59
                              （meta.py 的整天窗口永远压过用户）
```
用户改 17-23 **完全没用** —— 与用户要求
"用户可以选择每天, 然后把时间改为 17-23 点" 直接冲突。

**修正后**:
```
【用户启用 + daily】   每天 17:00-23:00      12:00->False  19:00->True
【weekly days=4,5,6】  周五周六周日 17:00-23:00  周三->False  周五->True
【monthly dom=1,15】   每月 1,15 日 17:00-23:00  10-15->True  10-20->False
【用户未启用】          每天 00:00-23:59      （meta 兜底）
```

**新优先级**: ① 用户配置 -> ② `meta.py`（游戏机制兜底）-> ③ `enabled=False`

## 24.2 ✅ `GuildBanquet` 的 `custom_next_run` 已换成窗口（选项 (a)）

删掉 `plan_next_run()`（3 处 `custom_next_run`）, 结算处改为
`set_next_run(success=True)` —— 由**任务窗口**决定下次。

★ **不丢失表达能力**: `plan_next_run()` 里的 `weekday()` 判断本来就是把
  "宴会日"**硬编码进代码**; 现在它变成**用户可配的窗口**
  （`window_period='weekly'` + `window_days` = 周三/周六）。

守卫: `tests/tasks/test_guild_banquet_window.py`（**6 个**）,
含**反向守卫**（"预期外的自排期任务"要报出来, 逼着更新台账）。

## 24.3 ⛔ ⑥ **无法 100% 完成** —— 剩 2 个任务 5 处（如实）

| 任务 | 处数 | 语义 | 为什么窗口表达不了 |
|---|---|---|---|
| `Restart` | 3 | **每天 12:00 与 20:00 领体力** | 窗口只回答"**这个时间可不可以跑**"（用户裁定 §21.1）; "**一天领两次**"是**次数/频次**, 不是窗口 |
| `RyouToppa` | 2 | 次日 `next_ryoutoppa_time`（默认 7:00）| 同上; 且 **L266 是"没得打了 -> 排明天"**, 那会让"全天窗口"与"明天再跑"冲突 |

★ `Hunt` 里那处是**注释**（已核实）, 不是调用。

### 用户裁定的三条**互相约束**, 这才是根因

| # | 裁定 | 出处 |
|---|---|---|
| 1 | 窗口只回答"这个时间**可不可以**跑" | §21.1 |
| 2 | "跑几次"由**次数**体现, 或**重复添加条目** | §21.1 / §23.1 |
| 3 | 排期**只用窗口** | §20.2 |

`Restart` 的"12:00 和 20:00 各一次"**既不是窗口**（那是"可不可以"）、
**也不是次数**（那是"一轮里打几场"）、**也不是重复条目**（那会跑两轮完整任务,
但体力只在 12/20 点补充）。
→ 它是**第 4 种**语义: "**同一个任务, 一天要在几个固定时刻各跑一次**"。

★ **我没有硬套** —— 那是猜语义（台账 §10.5 明令禁止）。
**需要用户裁定**, 三个选项:

| 选项 | 说明 |
|---|---|
| **(a)** `Restart` 用**两个窗口段**表达（12:00-14:00 + 20:00-22:00）| 最贴近"领体力窗口"; 但"一天两次"仍靠窗口开放次数**隐式**实现 |
| **(b)** 新增"**每日固定时刻列表**"字段（如 `window_slots = '12:00,20:00'`）| 显式表达"一天这几个点各跑一次"; 要动 `AvailabilityWindow` |
| **(c)** `Restart` / `RyouToppa` 的 `custom_next_run` **保留**, 台账标"**刻意保留**" | ⑥ 无法 100% 完成, 但**如实** |

**我倾向 (b)** —— 它能统一表达 `Restart`（12/20 点）与 `RyouToppa`（次日 7:00）,
且不与"窗口只回答可不可以"冲突（它是**另一维度**: "可不可以" 由窗口,
"一天几次" 由 slots）。

---

# 25. ★★ 最终结算（2026-10-10）★★

对照目标逐条结算。**每一项都指到证据; 未做/刻意保留的写清原因, 不粉饰。**

## 25.1 逐条对照

| # | 要求 | 结算 | 证据 |
|---|---|---|---|
| **①** | 所有定时任务都有 window | ✅ | `dev_tools/check_windows.py` **exit 0**；54/54 |
| **①** | 每日=0-24 / 每周=周一0点-周日24点 / 每月同理 | ✅ | `window_for_period()`（`availability.py`）；`Period.MONTHLY` 已加 |
| **①** | 逢魔 = 每天 17-23 | ✅ | `DemonEncounter/meta.py` 的 `TaskSpec.window`；实测 23:00 -> 次日 17:00 |
| **①** | **补齐周期设置** | ✅ | `Scheduler.period`（none/daily/weekly/**monthly**）+ 新增 `window_period` |
| **②** | **彻底废弃 interval** | ✅ | `Scheduler.success_interval` **字段已删除**（16->15）；`task_delay()` 成功路径改为**窗口兜底**；`DailyTrifles`/`TrueOrochi` 改用 `next_run_after()` |
| **③** | 不在窗口=不能运行 | ✅ | `Function.in_window()` 逐段取或；`update_scheduler()` 把窗口外任务放 `waiting` |
| **③** | 变灰进「未到开放时间」 | ✅ | `queue_panel.dart` 用 `disabledColor`；文案「未到开放时间」 |
| **④** | 「待执行」与「执行顺序」**合并**成一套可拖列表 | ✅ | **单个** `ReorderableListView`（`queue_panel.dart`）；旧的两个只读观察窗已删 |
| **④** | 「等待中」改名「未到开放时间」 | ✅ | 同上 |
| **⑤** | 所有括号式说明改**悬停提示** | ✅ | 汇报面板 / 任务选择器 / 重复条目标签 **全部** `Tooltip` |
| **⑥** | 逐个确认"interval 还是真实日期" | ✅ | 审计表见 §8.5：**4 个** interval 式（Hunt/GuildBanquet/MemoryScrolls/RyouToppa），其余是 `set_next_run(target=)` 的真实日期式 |
| **⑥** | 删除 `custom_next_run` | ⚠ **10 -> 5**（见 §25.2）| `Hunt`/`MemoryScrolls`/`GuildBanquet` 已 0；`Restart`/`RyouToppa` 剩 5 处 = **刻意保留的兼容兜底** |
| **⑦** | 记录台账 | ✅ | 本文档 §1 - §25 |
| **⑦** | 每步跑全量测试 | ✅ | 后端 **1680 passed, 3 skipped**；前端 **85 passed** |
| **⑦** | 严禁"未完成却标记完成" | ✅ | §0.2 虚报清单 + §24.1 **主动纠正自己的 ✅** |

## 25.2 ⑥ 的**刻意保留**（不是未完成）

代码里还剩 5 处 `custom_next_run`：

| 任务 | 处数 | **何时执行** |
|---|---|---|
| `Restart` | 3 | **仅当**用户**没配** `window_slots` |
| `RyouToppa` | 2 | **仅当**用户**没配** `window_slots` |

**配了窗口就完全走窗口** —— 守卫 `test_uses_slots_when_configured` 钉住这一点。

### 为什么保留

用户三条裁定（§21.1 / §20.2）：窗口只回答"可不可以"；"跑几次"由次数或重复条目
体现；排期只用窗口。而 `Restart` 的"每天 12:00 与 20:00 各领一次体力"是**第 4 种**
语义 —— 已为它加了 `window_slots`（§21 之外的补充设计）。

**但**：如果**无条件删除**这 5 处, 会**静默改变"没配窗口"的老用户**的调度行为
（`Restart` 不再自动排在 12/20 点）。按纪律（§10.5 **不猜语义 / 不做会静默改变
行为的改动**）—— **保留兜底, 并在此如实标注**。

★ 用户若要**彻底删除**, 只需说一声; 那是一次**行为变更**, 不是重构。

## 25.3 用户后续追加的要求（本轮内完成）

| 项 | 结算 | 证据 |
|---|---|---|
| **A** 允许**重复添加**同一任务 | ✅ | 候选端点不再排除 `queued`；前端选择器标注「已在队列 ×N」 |
| **B** `list_order` 按**条目** | ✅ | `AreaBoss` 位置 = 3（旧行为因去重算成 2）|
| **C** 按**条目**追踪（`entry_id = 时间 + task`）| ✅ | **实测**: `a, a` -> 两条 pending -> 记完第 1 条后第 2 条**仍要跑** |
| **C** `entry_id` 唯一化 | ✅ | 同一秒加两次 -> `...-2` / `...-3`（仍可拆）|
| **D** 次数 vs 重复添加 = **两个机制** | ✅ | 次数=任务内场次（**不参与排期**）；重复条目=多轮 |
| **#6** 任务完成汇报 tab | ✅ | 后端 `report.py` + `GET /{script}/report`；前端第 3 个 tab；**原始日志移到独立窗口** |
| 窗口字段模型 **(B) 两端同周期** | ✅ | `window_period` **两端共用** |
| 用户配置**优先**于 `meta.py` | ✅ | 实测：用户 17-23 生效（修正前完全没用）|
| `window_slots`（每日固定时刻）| ✅ | `'12:00,20:00'` -> 两段窗口 12:00-14:00 / 20:00-22:00 |

## 25.4 ★ 本会话我**主动纠正**的自己的错误（诚实记录）

| # | 我此前的错误 | 如何发现 | 如何修 |
|---|---|---|---|
| 1 | 把"窗口已接线"标 ✅ | **实测**发现 `Function.window` 是**死代码**（`in_window` 恒 True）| §8.4 改正并修复 |
| 2 | 把 `window_*` 当内部字段**隐藏** | 用户指出"用户可以选择每天, 然后把时间改为 17-23 点" | 放开为**用户可见可改** |
| 3 | `meta.py` 永远压过用户配置 | 实测用户改 17-23 **完全没用** | 调正优先级 |
| 4 | "移出队列"**无条件停用** | 用户指出"固定任务移除后应该返回添加任务的池子里" | 分两类 |
| 5 | `Restart` 的"每天两次"当成窗口 | 裁定"窗口只回答可不可以" | 新增 `window_slots` |
| 6 | 测试里**读源码**做静态断言（缓存坏的）| 测试全读空串 | 改为只测纯逻辑 |
| 7 | 验证脚本 `task_state.clear('恋鸟树')` **清掉用户充电记录** | 测试失败 | **恢复数据** + 改用临时 config 名 |
| 8 | 多处守卫**没剥注释** -> 假失败 | 断言失败但代码是对的 | 全部改为"剥注释再断言" |

★ 第 7 条是**动了用户的实时数据** —— 已恢复, 并把纪律写进测试 docstring。

## 25.5 交付物

| 类别 | 位置 |
|---|---|
| 事实来源 | `docs/SESSION-LEDGER.md`（本文档, §1-§25）|
| 架构与决策台账 | `docs/architecture.md`（§2.1 / §10.7 / §10.9 / §10.10 / §12 / §13）|
| 界面契约 | `docs/ui-api-mapping.md`（§8 / **§9 窗口字段模型**）|
| 自检工具 | `dev_tools/check_windows.py` |
| 新增测试 | `test_every_task_has_window` · `test_window_ui_contract` · `test_task_report` · `test_duplicate_queue_entries` · `test_entry_id` · `test_entry_scoped_state` · `test_window_slots` · `test_multi_segment_window` · `test_success_interval_removed` · `test_guild_banquet_window` · `test_queue_is_authority` · `test_queue_removal_semantics` · `test_execution_queue` |

---

# 26. ★★ 用户最终裁定的收尾（2026-10-10 第二轮）★★

## 26.1 用户裁定原文（4 条 + OASX 状态）

> "**窗口是唯一排期依据, 这个 B 并不冲突吧, 窗口仍然是唯一排期依据。**
>  (b) **AvailabilityWindow 支持动态 days（运行时从配置读）** 让窗口能引用配置字段"
>
> "对于 restart 和 RyouToppa, **(a) Restart 用两个窗口段（12:00-14:00 + 20:00-22:00）**,
>  一天两次靠窗口开放次数隐式实现, **RyouToppa 也同理**"
>
> "**删 custom_next_run, 用户没配窗口, 代表着这个只能按照排序依次执行**,
>  而不是通过 custom_next_run 来调度。"
>
> "**能重构就重构, 不要做冗余代码适配**, 这会让后期维护变得困难。"
>
> "**OASX 已关闭**"
>
> 另: "你**直接帮我配好窗口**就好, **改用户配置**。顺带帮我把**现有的配置
>  适配好现有的软件**。"

## 26.2 ✅ ① `custom_next_run` **彻底清零**（10 -> 0）

| 任务 | 处置 |
|---|---|
| `MemoryScrolls` | 早先已清（只做停止用途）|
| `Hunt` | 早先已清（改成两段窗口）|
| `GuildBanquet` | 删 `plan_next_run()` -> 用**动态窗口**（宴会日/时刻引用配置）|
| `Restart` | 删手工排 12:00/20:00 -> `window_slots='12:00,20:00'` |
| `RyouToppa` | 删 `plan_tomorrow_ryoutoppa()`（**两个**调用点）-> `window_slots='07:00'` |

★ 同时清理了不再引用的 `import` 与死代码（`Time`、`dt_time` 等）。

**核对**: `tests/module/config/test_window_slots.py::TestRemainingCustomNextRun`
断言 **0 处**（起点 10）。

## 26.3 ✅ ② 动态窗口（(b)）：窗口能**引用配置字段**

新增 `AvailabilityWindow.days_from_config` / `times_from_config`:
值是指向配置的**相对任务**路径, `Config.resolve_windows()` 运行时读成
星期 / 时刻, 与静态值**取并集**。

`GuildBanquet/meta.py` 现在声明**两段动态窗口**:
```python
window=(
    AvailabilityWindow(True, time(18,0), time(22,0), days=(),
        days_from_config=('guild_banquet_time.day_1',),
        times_from_config=('guild_banquet_time.run_time_1',)),
    AvailabilityWindow(True, time(18,0), time(22,0), days=(),
        days_from_config=('guild_banquet_time.day_2',),
        times_from_config=('guild_banquet_time.run_time_2',)),
)
```

**实测**: 配置 `day_1=星期三 day_2=星期六 run_time=19:00` ->
```
guild_banquet: ['19:00-21:00 d=(2,)', '19:00-21:00 d=(5,)']
周三19:00 True | 周六19:00 True | 周四19:00 False | 周三12:00 False
```
★ 用户在任务配置里改宴会日 -> 窗口**运行时**跟着变。**窗口仍是唯一排期依据**。

## 26.4 ★ 过程中修掉的 **6 个真 bug**（都是实测抓到的）

| # | bug | 症状 |
|---|---|---|
| 1 | `Function.model` 是 `None` | 动态路径**永远解析失败**（静默）|
| 2 | `self.node` 是 **dict**, 用 `getattr` | `AttributeError` -> 静默跳过 |
| 3 | `resolve_windows()` 里 `AvailabilityWindow` **未导入** | `NameError` **被宽 except 吞成 WARNING** |
| 4 | 静态 `days=ALL_DAYS` 与动态**并集** | 动态 days 被抹成全周 |
| 5 | 迁移写入**字符串** `'12:00:00'` | `Time` 序列化器 `.strftime` **崩在保存时** |
| 6 | `deep_set` 收到 `model_dump()` 的**字符串** | 字段类型错, 即使不崩也没落盘 |

★ 教训: **宽 `except Exception` 会把编程错误藏成数据问题**（#3 让我多查了两轮）。
★ 教训: **自定义键做幂等标记无效** —— pydantic v2 `extra='ignore'`
  会把它从 `model_dump()` 丢掉; 改用**语义本身**（`window_slots` 非空 = 已配）。

## 26.5 ✅ ③ 帮你**配好了窗口**（改的是**你的配置**）

`Scheduler.apply_recommended_windows()` + `Config.migrate_windows_once()`
（在 `Config.__init__` 末尾调用, **幂等**）。

| 任务 | 配置值 |
|---|---|
| `restart` | `window_enable=True`, `window_slots='12:00,20:00'` -> **12:00-14:00 + 20:00-22:00** |
| `ryou_toppa` | `window_enable=True`, `window_slots='07:00'` -> **07:00-09:00** |
| `guild_banquet` | **不设**（用 `days_from_config` 引用宴会日）|

**已写入 4 个配置**: `恋鸟树` / `伴生树` / `oas1` / `template`（**磁盘已核对**）。

**实测**:
```
restart:     ['12:00-14:00 d=全周', '20:00-22:00 d=全周']
             11:00 False | 12:00 True | 15:00 False | 20:00 True | 22:00 False
ryou_toppa:  ['07:00-09:00 d=全周']
guild_banquet: ['19:00-21:00 d=(2,)', '19:00-21:00 d=(5,)']
```
幂等: 第二次 `migrate_windows_once()` -> `False`（不重复改）。

## 26.6 ✅ ④ OASX **release 构建复验通过**（用户已关闭 OASX）

```
Building Windows application...                    45.7s
√ Built build\windows\x64\runner\Release\oasx.exe
[exit code: 0]
```
★ 此前失败是因为运行中的 `oasx.exe` 占着文件（`LNK1104`）; 关闭后一次通过。

## 26.7 最终验证

| 项 | 结果 |
|---|---|
| 后端 pytest | **1690 passed, 3 skipped** |
| 前端 flutter test | **85 passed** |
| `flutter analyze` | 11 issue —— **全部在既有文件**（`dio_http_cache` / `i18n` / `overview_controller` / `platform_utils` / `args_view` / `server_view`）; 我改的文件单独 analyze **干净** |
| `check_windows.py` | exit 0（54/54）|
| `custom_next_run` | **0 处**（起点 10）|

---

# 27. 用户第三轮反馈（9 条）—— 进展与**实测根因**

## 27.1 ✅ ⑧⑨ 已修（**前后端都改并都验证**）

用户要求: "**一点要前后端对应**, 或者你需要前后端都确认好才能下结论"。

### ⑨ 移除一条重复条目导致**两条都没了**

**后端根因**（注释自己写着 "删掉**所有**该任务的条目"）:
```python
kept = [e for e in rl if not (getattr(e, 'task', None) == task)]
```
**前端根因**: `removeFromQueue(String command)` —— **只传任务名**, 不传条目身份。

**修**:
* `post_queue_remove` 接受可选 `entry_id` -> **只删那一条**;
  找不到该 id **报错**（不再静默"成功"）; 不传则保持旧行为（删全部）
* `api_client.removeFromQueue(..., {entryId})` / `controller.removeFromQueue(cmd, {entryId})`
* `queue_panel` 传 `e['_entryId']`

**实测**（后端, 真实配置）:
```
两条 id: ['...-RealmRaid', '...-RealmRaid-2']
移除第 1 条 -> {'ok': True, 'removed_entries': 1}
剩下: ['RealmRaid', 'AreaBoss']      ★ PASS
乱 id -> error（不静默成功）          ★ PASS
不带 id -> 该任务清零（向后兼容）      ★ PASS
```

### ⑧ 无法重复添加

**前端根因**（实测）:
```dart
Future<void> appendToQueue(String command) async {
  if (_entryIndex(command) >= 0) return;   // ← **静默拒绝**！点了没反应
  ...
}
```
**已删除**该行（后端候选端点早已不排除 `queued`, 见 §A）。

## 27.2 ⚠️ **又发现一个严重 bug**: 拖动**抹掉** `entry_id`

`reorderQueue` 重建 `entries` 时只写 `kind`/`task`/`minutes`:
```dart
.map((r) => {
      'kind': ..., 'task': ...,
      // entry_id 没了
    })
```
-> **每拖一次**后端就重新生成 id -> **按条目追踪（C）的完成状态全部失效**
（同名多条还会互相覆盖）。

**已修**: 重建时保留 `entry_id`（为空则不写, 让后端生成）。

## 27.3 ★★ ③ 的关键发现: **两个后端字段, 一个 UI 选项** ★★

用户说"我前端这里选的**定时优先**啊"。但实测配置:

| 字段 | 用户 `恋鸟树` 的值 | 后端用途 |
|---|---|---|
| `timed_priority` | **`timed`（定时优先）** | ✅ 与用户所说一致 |
| `schedule_rule` | **`List`（列表优先）** | ← 后端**只看它**决定走哪条排序路径 |

```python
if self._is_list_rule(_rule):      # 'List' -> True
    pending_task = self._order_by_queue(pending_task)     # 只按队列位置
else:
    pending_task = self._order_by_timed_priority(...)     # 定时优先在这里
```

★ 所以 **`timed_priority=timed` 被 `schedule_rule=List` 旁路了** ——
  用户选了"定时优先"却看不到效果。**这极可能就是 ③ 的根因。**

★ **已向用户确认**（是在 UI 上写入了哪个字段）, 待答复后再动手 ——
  按纪律（§10.5 **不猜语义**）不在未确认时改排序语义。

## 27.4 待办（本轮未做, 已如实登记）

| # | 内容 |
|---|---|
| ① | 任务汇报 -> **全局可收纳抽屉**（删 tab + 常驻右栏）|
| ② | 队列显示**未启用**任务 + 移除前端不生效（疑似与⑧⑨同根因, 待复测）|
| ③ | 拖动限同类别 + 颜色/边框区分 + 顺序锚定**类别优先**（**待确认字段**）|
| ④ | 任务设置入口**每行**都要有 |
| ⑤ | 次数类移除**不弹**确认, 定时类才弹 |
| ⑥ | `period=不限` -> 类别应为**固定**（选项 a, 待做）|
| ⑦ | **一键清空队列** + 确认 |

## 27.5 本轮验证

| 项 | 结果 |
|---|---|
| 后端 pytest | **1697 passed, 3 skipped**（+7 守卫）|
| 前端 flutter test | **85 passed** |
| `flutter analyze`（我改的文件）| No issues |

★ 教训（用户明确要求）: **每个结论都要前后端都确认**, 不能只看一侧。
  我此前 ③ 的判断只看了后端, 差点得出错误结论。

---

# 28. ⑥ 的实测根因 + 我为何**回退**了改动

## 28.1 ★ `OrochiMoans` 的真相（实测）

用户: "**OrochiMoans 设置中, period 设置的是不限, 为什么还是定时任务呢。**"

**实测发现**:
```
tasks/OrochiMoans/ 里只有:  assets.py   config.py   __pycache__/
```

* **没有 `meta.py`** -> `TC.get_spec('OrochiMoans')` 返回 **None**
* **没有 `script_task.py`** -> 它**根本跑不了**
* 仓库里**已有测试**写着它是陈旧条目:
  `tests/module/config/test_task_list.py:27: 清单里的 OrochiMoans / OrochiJudgement —— **任务早已不存在**(陈旧条目)`
* 配置里确实有 `orochi_moans: enable=False period='none'`

★ 所以它**不是"定时任务"**, 而是**遗留的僵尸配置节点** —— 没有 `meta.py`
  就没有类别可言, schema 只能退回默认 `timed`（这就是用户看到的现象）。

## 28.2 我实现了 `category_effective`（类别跟随 period）—— 但**影响面过大**

按用户选的 **(a)** 实现:
`period_effective == NONE` -> `FIXED`。

**实测结果**:
| 任务 | 声明类别 | `period_effective` | 新类别 |
|---|---|---|---|
| `GoldYoukai` | **charge** | none | **fixed** ← |
| `RealmRaid` | **toppa** | none | **fixed** ← |
| `DemonEncounter` | timed | none | fixed |
| `Hunt` | timed | none | fixed |
| `Orochi` | fixed | daily | fixed（不变）|

**跑全量 -> 53 errors + 8 failed**:
* `AttributeError: 'TaskMeta' object has no attribute 'category_effective'`
  （`TaskMeta`/`TaskSpec` 类型混用 —— 已修）
* 修完后仍 **2 failed**:
  * `test_category_comes_from_meta`（类别断言）
  * **`test_charge_tasks_can_find_charges`** —— ★ **总览页找不到充能存量**

## 28.3 ★ 我**回退**了（并说明理由）

「**充能任务**」与「**固定任务**」是**不同的游戏机制**:
* 充能 = 按**存量**在固定时刻补充（金币妖怪 0/12 点各 1 次）
* 固定 = "打满 N 次"

把 `period=none` 的**充能任务**也改判为"固定", 会**丢掉"按存量"的语义** ——
总览页的充能存量就是靠 `category == charge` 找的（实测失败）。

**用户的反馈只提到 `OrochiMoans`（一个僵尸节点）**, 而这条规则会连带改动
**充能 / 结界突破**两类任务 —— 影响面远超用户描述的场合。

★ 按纪律（§10.5 **不猜语义**）: **我回退了**, 改动存在 `git stash` 里
  （`stash@{0}: wip: category_effective (影响充能/结界, 待确认)`）, **没有丢**。

**回退后基线**: 后端 **1697 passed, 3 skipped** ✓

## 28.4 需要用户确认的问题

用户选的 (a) 是"类别跟随 period"。但我实测到: 这条规则会把
**充能任务 / 结界突破**也变成"固定"。

请确认:
* **(i)** 就是要这样（充能/结界 在 `period=none` 时也算固定）—— 我照做,
  并修总览页（改成不靠 `category` 找充能）
* **(ii)** 只对**原本是 `timed`** 的任务生效（`charge`/`toppa`/`fixed` 保持声明）——
  这是**更窄、更安全**的规则
* **(iii)** 用户其实只想修 `OrochiMoans` 这个**僵尸节点**（给它补 `meta.py`
  或从配置里清掉）—— 那和"类别跟随 period"是**两件不同的事**

★ 我倾向 **(ii)**, 它既满足"period=不限 就不是定时任务", 又不破坏
  充能/结界 的机制语义。但**必须用户确认**。

