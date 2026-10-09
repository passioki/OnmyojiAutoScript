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
| 6 | **Restart** | ⬜ | 3 处（L50/53/56）—— 领体力时刻（12:00/20:00）, 可能保留 |
| 7 | **MemoryScrolls** | ⬜ | 1 处（L63）—— 给**别的任务**（Exploration）排期, 语义特殊 |
| — | 其余（Dokan / MysteryShop / Secret / Tako / DemonEncounter / GuildActivityMonitor / AreaBoss …）| ⬜ | 用 `weekday()` 但**不**调 `custom_next_run`（选 boss/选区域等正当用途）, 需逐个确认 |

**剩余 `custom_next_run` / `days_until` 实测: 10 行** —— 台账标 ⬜/⛔, 不虚报。

★ `BaseTask.custom_next_run()` **暂时不能删** —— 上面几个任务还在调它。

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
