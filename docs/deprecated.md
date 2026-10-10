# 废弃清单（**唯一权威**）

> **状态**：**废弃清单**（唯一）
> **最后按代码核对**：2026-10-10 @ `0c5e9819` + **S7 工作区改动**
> （S7 = 「调度优先级三模式」整簇删除, 见 §3.2）
> **冲突时以**：本文为准（关于"某东西还在不在"）
>
> ## 这份文件解决什么
>
> 重构删掉的东西很多, 而**别的文档还在**把它们当**现行功能**描述 ——
> 后面接手的人会照着**已删除的字段/端点/模块**去写代码。
>
> ★ 所以这里做**唯一一份**清单: **一条一行, 写清"删了什么 / 为什么 / 谁取代它 /
>   在哪一步删的"**。其它文档提到已删内容时, 一律指向本文。
>
> ## 怎么用
>
> * 要确认"某个字段/端点/模块**还在不在**" -> **查这里**
> * 发现别处文档提到一个**不存在**的东西 -> 在本文加一行, 并改那边
> * `tests/test_docs_no_dead_refs.py` 会**自动**校验文档里提到的 `.py` 路径
>   是否真的存在（**白名单允许本文与 `archive/`**）

---

## 1. 「充能 / 存量」机制（S5 全部删除）

用户裁定：

> "**去除旧的充能存量说法。现在靠 window 的多次设置完全可以做到正常运行。**"
> "**连 `charge_*` 字段和存量逻辑一起删**"
> "**去掉组队协同，去掉存量次数。组队协同应该是单独模块啊，不应该放在金币妖怪里。**"

| 删除的东西 | 类型 | 取代它的 | 台账 |
|---|---|---|---|
| `class Recharge` | 类（`module/config/resource.py`）| **窗口**（`windows` 列表）| §40 |
| `class Resource` | 类（同上）| 同上 | §40 |
| `TaskSpec.resource` | 字段 | `TaskSpec.period`（**独立字段**）| §36 |
| `TaskMeta.has_charge` / `charge_max` / `charge_slots` / `charge_consume` | 字段 | 无（"跑几次"由**重复条目**表达）| §41 |
| `Category.CHARGE` | 枚举值 | `Category.TIMED`（3 个任务改判）| §41 |
| `Scheduler.build_window()` | 方法（49 行, **一调就崩**）| `Function._build_windows()` | §49 |
| `task_state.get_charges` / `consume_charge` / `next_charge_time` / `parse_slots` / `_slot_*` / `_decode_charges_v2` / `peer_charges` / `_normalize` | 函数 | **窗口** | §39 |
| `task_state.summarize()` 的 `charges` 键 | 返回字段 | 无 | §39 |
| `module/config/scheduler_core.py` | **整个模块**（346 行, 死代码）| 无 | §40 |
| `module/config/team_coordinator.py` | **整个模块**（213 行）| ★ 用户要求"应该是**单独模块**" —— 待重新设计 | §39 |
| `dev_tools/gen_resource_specs.py` | 脚本 | 直接在各任务 `meta.py` 写 `period=` | §43 |
| `dev_tools/migrate_state_to_resource.py` | 脚本 | 无（迁移目标已不存在）| §43 |
| `dev_tools/compare_scheduler.py` | 脚本 | 无 | §40 |
| `tests/.../test_task_charges.py` | 测试 | `test_charge_system_removed.py`（**反向守卫**）| §38 |
| `tests/.../test_team_coordinator.py` | 测试 | 无 | §39 |
| `tests/.../test_scheduler_core.py` · `test_availability.py` | 测试 | 无 | §40 |
| `/overview` 的 `charges` | API 字段 | 无 | §42 |
| `/overview` 的 `resource_describe` | API 字段（**53/53 恒为 `''`**）| 无 | §42 |
| `/report` 的 `charges` | API 字段 | 无 | §42 |
| 前端 `charges` / `resource_describe` 读取 | 前端代码 | 无 | §42 |

★ **代码里 `charge` 残留 = 0 行**（从 75 文件 / 319 行清到 0）。
★ ⚠ **数据残留**: `config/template.json` 仍可能有 `charge_*` 键 ——
  pydantic `extra='ignore'` 会在**下次 save 时**静默丢弃它们。

---

## 2. 单值窗口（S3 删除）

用户裁定：

> "不是 window slots, 而是**设置多个 window**！slots 不是已经废弃了吗"
> "**一天跑两次 = 两个窗口**"

| 删除的字段 | 取代它的 | 台账 |
|---|---|---|
| `window_enable` | `windows[].enabled` | §33 |
| `window_period` | `windows[].period`（★ 两端**共用**）| §33 |
| `window_start` / `window_end` | `windows[].start` / `.end` | §33 |
| `window_days` | `windows[].days` | §33 |
| `window_dom` | `windows[].days_of_month` | §33 |
| **`window_slots`** | ★ **`windows` 列表本身** —— "一天两次" = **两个窗口** | §33 |
| `/schema` 的 `window_fields` | `GET/PUT/POST/PUT{id}/DELETE{id} /{s}/tasks/{task}/windows` | §49 |
| ~~`_SLOT_SPAN_MINUTES`~~ | ★★ **本条是误判, 已撤销**（第二轮复核）: `module/config/config.py:37` **仍定义**它、`:288` **在活路径里使用**（`resolve_windows()`）—— **保留** | §33 |

★ **前端从来没有过单值窗口的表单**（`lib/views/args/` 原无窗口 UI）——
  多窗口编辑器 `window_editor.dart` 是 S4 新写的。

---

## 3. 排序设置的三代演化（**S7 之后只剩 `run_list` 顺序**）

### 3.1 第一代（S6 之前）: 两个**语义重叠**的字段

用户裁定（S6 依据）:

> "拖动只在同类别内生效是在选了**定时优先**或者**固定任务优先**时, 如果选了
>  **列表自定义**, 那么全都可以拖动次序。你理解下, 也就是
> **三个选项: 定时任务优先、固定任务优先、自定义**"

| 废弃的 | S6 时被谁取代 | ★ S7 之后 |
|---|---|---|
| `schedule_rule`（4 路: `Filter`/`FIFO`/`Priority`/`List`）| `priority_mode`（3 路）| ★ **两个都已删** -> 执行顺序 = `run_list` 顺序 |
| `timed_priority`（2 路: `timed`/`list`）| 同上 | ★ **两个都已删** |
| `Config._order_by_timed_priority()`（74 行, 死代码）| `Config._segment_queue()`（队列层排段）| ★ 后者在 S7 **改名**为 `Config._tag_and_place_rest()`（**只打段名 + 挪 rest, 不排段**）|
| **`TaskScheduler.schedule()` 的调用** | `Config._order_by_queue()`（**队列是唯一顺序权威**）| ★ **仍然有效** —— 唯一没被 S7 推翻的一条 |
| 前端「优先级依据」四选一下拉 | 前端「调度优先级」三模式下拉 | ★ **两个下拉都已删** -> 换成两个**按钮**（见 §3.2）|

★ `schedule_rule` / `timed_priority` 两个**配置字段仍在**（旧配置里可能有,
  直接删会崩）, 但已标 `json_schema_extra={'internal': True}`（界面不显示）;
  `ScheduleRule` / `TimedPriority` **枚举仍在** —— 只为**读旧值**与测试。
★ **它们不再影响行为**。

### 3.2 ★★★ 第二代（S6）: `priority_mode` 三模式 —— **S7 整簇删除** ★★★

用户裁定（**这是本轮删除的唯一依据**, 原话）:

> "我觉得……这个**固定任务优先和定时任务优先以及不能跨类别拖动太蠢了**。
>  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和定时任务优先
>  **直接作为一个快捷排序**就好, 而不是定义一些没有意义的**不能跨类别拖动**
>  以及**单独的调度优先级**。"

**为什么删**（逐句对应原话）:

1. "**不能跨类别拖动太蠢了**" -> **拖动约束**（前端判据 + 后端校验）**全删**。
2. "**单独的调度优先级**…没有意义" -> `priority_mode` 这个**常驻状态**删掉。
3. "**直接作为一个快捷排序**" -> 换成**一次性动作** `PUT /{script}/queue/sort`。
4. "**自由拖动/改变执行顺序**" -> **执行顺序 = `run_list` 的顺序本身**。

| 删除的东西 | 类型 / 原位置 |
|---|---|
| `PriorityMode` 枚举（`timed_first` / `fixed_first` / `custom`）| 枚举（`tasks/Script/config_optimization.py`）|
| `Optimization.priority_mode` / `priority_mode_explicit` | 模型字段（同上）|
| `Config.priority_mode()` | 方法（`module/config/config.py`）|
| `Config._order_by_priority_mode()` | 方法（同上, 本就是**生产 0 调用**的死代码）|
| `Config.migrate_priority_mode_once()` | 方法（同上, 原来在 `Config.__init__` 里调）|
| `Config._segment_queue(rl)` | 方法（同上）-> ★ **改名** `Config._tag_and_place_rest(rl)` |
| `Config.resegment_run_list()` | 方法（同上）-> ★ **改名** `Config.sort_run_list(by)` |
| `_check_drag_allowed()` / `drag_blocked` | 函数 + 返回键（`module/server/schema_router.py`）|
| `_current_priority_mode()` | 函数（同上）|
| `GET` / `PUT /{script_name}/priority_mode` | **两个端点**（同上）|
| `/schema` 的 `global_fields.priority_mode` | 契约字段（同上）|
| `/schema` 的 `global_fields.drag_within_group_only` | 契约字段（同上, 给前端判"能不能跨类别拖"）|
| 前端「调度优先级」下拉 + `priorityMode` / `dragWithinGroupOnly` / `setPriorityMode` / `dragRejection` | 前端代码（`OASX-src/lib/...`）|
| `tests/module/config/test_drag_constraint.py`（115 行）| **整个文件已删** |
| `tests/module/config/test_drag_rest_position.py`（78 行）| **整个文件已删** |
| `tests/module/config/test_priority_mode.py`（169 行）| **整个文件已删** |
| `tests/module/config/test_priority_mode_migration.py`（124 行）| **整个文件已删** |

★ **取代它的**（现行唯一权威）:

* **执行顺序 = `run_list` 的顺序本身** —— 没有任何"模式"能改变它。
* 「定时排前面 / 固定排前面」= **一次性动作** `Config.sort_run_list(by)`
  （`by ∈ 'timed'` / `'fixed'`, **会写盘**）; 端点
  `PUT /{script_name}/queue/sort`, body `{"by": "timed"|"fixed"}`。
  ★ **点一次排一次, 不留状态** —— 排完之后用户**可以随意再拖**（跨类别也行）。
* ★ **唯一硬约束**: 「休息」（`rest`）条目**恒排最后** —— 由
  `Config.place_rest_last(rl)` **归一化**（挪到最后）, **不是拒绝**。
  用户确认: "**任意拖，但「休息」条目仍强制排最后**"。
* `/schema` 的 `global_fields` 现在**只有 4 个键**:
  `enable_fixed` / `enable_timed` / `rest_interleave` / `when_task_queue_empty`。
* 新增测试:
  * `tests/module/config/test_queue_sort.py`（21 条 —— 幂等 / 类内稳定 / 写盘 / 非法输入 / **端点契约**）
  * `tests/module/config/test_segment_of.py`（3 条）
  * `tests/module/server/test_drag_is_free.py`（**11 条** —— **反向守卫**: 跨类别拖动必须被接受、
    `rest` 是**挪位不是拒绝**、生产代码里**不得**再有 `drag_blocked` / `priority_mode`）
  * `tests/module/config/test_pending_subsequence.py`（**4 条** —— `pending` 是队列的保序子序列,
    `queue` 顺序 = `run_list` 顺序, **调度期间没有任何东西重排 `pending`**）
* ★ `RunEntry.group` 的"**永不落盘**"守卫**已从** `test_priority_mode.py`
  **搬到** `tests/module/config/test_run_list.py`（`TestRunEntryGroup`）。

⚠ **如实记录的残留**:

* ★ `_check_drag_allowed()` **已整函数删除**（不是空壳）——
  `module/server/schema_router.py` 里只留一段"为什么删"的注释。
  ★ 刻意**不留**"恒返回放行"的空壳: 那种空壳未来被接回某个分支时
  会**静默恒放行**, 变成"看起来在校验、其实没有"的假守卫。
* ⚠ **生产代码里仍有过时的注释/文档串**（不影响行为, 但会误导）:
  `schema_router.py:167-168` 仍写"模式从 `global_fields` 的 `priority_mode` 读"
  （那个键已删）; `:490` 仍提 `_check_drag_allowed` 的判定;
  `tasks/Script/config_optimization.py:159` 仍写"请用上面的 `priority_mode`"。
  ★ 本轮**只改 `docs/`**, 未动这些注释。
* 老配置里遗留的 `priority_mode` / `priority_mode_explicit` 键: `Optimization`
  不再声明它们 -> pydantic 加载时**静默忽略多余键** -> 下次 `save()` 时从磁盘上
  **自然消失**。**不需要写清理迁移**。

---

## 4. 其它

| 删除的东西 | 为什么 | 取代它的 | 台账 |
|---|---|---|---|
| `success_interval`（模型字段）| 与窗口语义重叠 | **窗口** | §26 |
| `custom_next_run()` 的**调用点**（9 处）| 任务不该自己排期 | **窗口** | §26 |
| `Config.name_to_function()` | **一调就崩**（`Function({})` 缺参）| 无（0 调用）| §49 |
| `tests/.../test_battle_wait.py` 的 21 个测试 | 断言基于**旧 API**（`per_battle` 曾是 `dict`）| ★ **已重写为 27 个真测试**（§53.2）| §49 / §53 |
| `docs/task-list-prototype.html` | ★ **计划删**（文件**仍在**, 34KB）—— 过时原型（含 `charge` 类别、"存量"列）| 见 `ui-api-mapping.md` | — |
| `docs/oasx-task-list-ui.patch` | ★ **计划删**（文件**仍在**, 724KB）—— git patch（1.7 万行, 含全部旧模型）| 无（不该在 `docs/`）| — |
| `docs/team-coordination.md` | ★ **计划删/重写**（文件**仍在**, 20KB）—— 引用了已删的 `team_coordinator.py` | ★ 待重新设计为**独立模块** | §39 |
| `RunState` / `next_available()` | ★（第二轮补录）随 `scheduler_core.py` 一起删 | **窗口** | §40 |
| `module/config/scheduler_core.py` | ★（第二轮补录）**整个模块** 346 行, 死代码 | 无 | §40 |
| `module/config/team_coordinator.py` | ★（第二轮补录）**整个模块** 213 行 | ★ 待重新设计为**独立模块** | §39 |
| 前端 `resetToDefault()` | ★（第二轮补录）**会清空 `run_list`** 的危险死代码 | 无（0 调用）| §53 |
| 前端 `timedPriority` / `timedPriorityChoices` / `setTimedPriority` | ★（第二轮补录）读**已废弃**的 `global_fields.timed_priority`（后端已不返回）| ★ `priorityMode*`（S6）—— **它也在 S7 被删**, 现为两个**排序按钮**（`sortQueueBy`）| §53 / §61 |
| 前端 `scriptRunning` / `isTaskEntry` / `overviewRowOf` | ★（第二轮补录）只读、0 调用 | `taskRowOf` / 直读 `ScriptService` | §53 |

★ **`TaskMeta.success_interval` 与配置 JSON 里的 `success_interval` 是
  「有意保留」**（读旧值用）, 见 `tests/module/config/test_success_interval_removed.py`。

---

## 5. ★ 反向守卫（"这些东西**不得**再出现"）

| 守卫 | 位置 |
|---|---|
| `Category.CHARGE` / `Recharge` / `Resource` **不存在**; `Period` **必须存在** | `tests/module/config/test_charge_system_removed.py` |
| `team_coordinator.py` / `scheduler_core.py` **不存在** | 同上 |
| `/overview` **不得**有 `charges` / `resource_describe` | 同上 |
| `RunEntry.to_dict()` **永不**序列化 `group`（派生值） | `tests/module/config/test_run_list.py`（★ S7 从**已删除**的 `tests/module/config/test_priority_mode.py` **搬过来**）|
| `/schema` **不得**有 `window_fields` | `tests/module/server/test_schema_router.py` |
| 单值 `window_*` 字段**不存在** | `tests/module/config/test_multi_window_storage.py` |
| `_order_by_timed_priority` **不存在** | `tests/module/config/test_queue_no_leak_all_rules.py` |
| 调度路径**不得**再调 `TaskScheduler.schedule()` | `tests/module/config/test_execution_queue.py` |
| ★ `Optimization` **不得**再有 `priority_mode` / `priority_mode_explicit`; `put_priority_mode` / `get_priority_mode` **不存在** | `tests/module/config/test_queue_sort.py`（`TestSortEndpointContract`）|
| ★ `GET`/`PUT /{script}/priority_mode` **不存在**; 排序只走 `PUT /{script}/queue/sort` | 同上 |
| ★★ **跨类别拖动必须被接受**（不得被拒）; 生产代码里**不得**出现 `drag_blocked` / `priority_mode`; `_check_drag_allowed` **不得**存在 | `tests/module/server/test_drag_is_free.py` |
| ★ `pending` 是队列的**保序子序列**, 调度期间**不得**重排它 | `tests/module/config/test_pending_subsequence.py` |
| 文档里的 `.py` 路径**必须存在** | `tests/test_docs_no_dead_refs.py` |
