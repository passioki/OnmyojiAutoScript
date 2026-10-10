# 废弃清单（**唯一权威**）

> **状态**：**废弃清单**（唯一）
> **最后按代码核对**：2026-10-10 @ `1da97b9e`
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
| `_SLOT_SPAN_MINUTES`（`config.py` 那份）| —— | §33 |

★ **前端从来没有过单值窗口的表单**（`lib/views/args/` 原无窗口 UI）——
  多窗口编辑器 `window_editor.dart` 是 S4 新写的。

---

## 3. 两个重叠的排序设置（S6 合并为一个）

用户裁定：

> "拖动只在同类别内生效是在选了**定时优先**或者**固定任务优先**时, 如果选了
>  **列表自定义**, 那么全都可以拖动次序。你理解下, 也就是
> **三个选项: 定时任务优先、固定任务优先、自定义**"

| 废弃的 | 取代它的 |
|---|---|
| `schedule_rule`（4 路: `Filter`/`FIFO`/`Priority`/`List`）| ★ `priority_mode`（3 路）|
| `timed_priority`（2 路: `timed`/`list`）| ★ 同上 |
| `Config._order_by_timed_priority()`（74 行, 死代码）| `Config._segment_queue()`（**队列层**排段）|
| **`TaskScheduler.schedule()` 的调用** | `Config._order_by_queue()`（**队列是唯一顺序权威**）|
| 前端「优先级依据」四选一下拉 | 前端「调度优先级」三模式下拉 |

★ `ScheduleRule` / `TimedPriority` **枚举仍在**、`TaskScheduler` **类仍在**
  —— 只为**读旧配置**与测试; ★ **它们不再影响行为**。
★ `schedule_rule` / `timed_priority` 两个**配置字段仍在**（旧配置里可能有,
  直接删会崩）, 但已标 `json_schema_extra={'internal': True}`（界面不显示）。
★ `priority_mode_explicit` 是**迁移标记**: `True` = 用户已在新界面表过态 ->
  **永不覆盖**。不用它的话, 自定义键会被 pydantic `extra='ignore'` 丢掉 ->
  **每次启动都覆盖用户设置**。

---

## 4. 其它

| 删除的东西 | 为什么 | 取代它的 | 台账 |
|---|---|---|---|
| `success_interval`（模型字段）| 与窗口语义重叠 | **窗口** | §26 |
| `custom_next_run()` 的**调用点**（9 处）| 任务不该自己排期 | **窗口** | §26 |
| `Config.name_to_function()` | **一调就崩**（`Function({})` 缺参）| 无（0 调用）| §49 |
| `tests/.../test_battle_wait.py` 的 21 个测试 | 断言基于**旧 API**（`per_battle` 曾是 `dict`）| ★ **待按当前状态机重写**（现在**无保护**）| §49 |
| `docs/task-list-prototype.html` | 过时原型（含 `charge` 类别、"存量"列）| 见 `ui-api-mapping.md` | — |
| `docs/oasx-task-list-ui.patch` | git patch（1.7 万行, 含全部旧模型）| 无（不该在 `docs/`）| — |
| `docs/team-coordination.md` | 引用了已删的 `team_coordinator.py` | ★ 待重新设计为**独立模块** | §39 |

★ **`TaskMeta.success_interval` 与配置 JSON 里的 `success_interval` 是
  「有意保留」**（读旧值用）, 见 `tests/test_success_interval_removed.py`。

---

## 5. ★ 反向守卫（"这些东西**不得**再出现"）

| 守卫 | 位置 |
|---|---|
| `Category.CHARGE` / `Recharge` / `Resource` **不存在**; `Period` **必须存在** | `tests/module/config/test_charge_system_removed.py` |
| `team_coordinator.py` / `scheduler_core.py` **不存在** | 同上 |
| `/overview` **不得**有 `charges` / `resource_describe` | 同上 |
| `RunEntry.to_dict()` **永不**序列化 `group`（派生值） | `tests/module/config/test_priority_mode.py` |
| `/schema` **不得**有 `window_fields` | `tests/module/server/test_schema_router.py` |
| 单值 `window_*` 字段**不存在** | `tests/module/config/test_multi_window_storage.py` |
| `_order_by_timed_priority` **不存在** | `tests/module/config/test_queue_no_leak_all_rules.py` |
| 调度路径**不得**再调 `TaskScheduler.schedule()` | `tests/module/config/test_execution_queue.py` |
| 文档里的 `.py` 路径**必须存在** | `tests/test_docs_no_dead_refs.py` |
