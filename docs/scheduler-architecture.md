# OAS 调度架构设计（原子化 · 集合论）

> 本文是**设计的唯一权威**。实现与本文不一致时，以本文为准；
> 若要改设计，先改本文，再改代码。
>
> 起因（用户 2026-10-10 第四轮裁定）：
> * "这个排序问题请**从架构上专门设计一款调度**，参考**原子化、集合类**理念，
>   包括数据的**增删改查、分类及互相的联动**。"
> * "**窗口是唯一排期依据**"
> * "不是 window slots，而是**设置多个 window**！slots 不是已经废弃了吗，
>   请**通读代码、设计文档并更新记忆**！**前后端要同步改**！"
> * "拖动只在同类别内生效**是在选了定时优先或者固定任务优先时**，
>   如果选了列表自定义，那么**全都可以拖动次序**。
>   也就是三个选项：**定时任务优先、固定任务优先、自定义**"
> * "给 `run_list` **加类别分段**"
> * "去除旧的充能存量说法。现在靠 window 的**多次设置**完全可以做到正常运行。"
> * "连 `charge_*` 字段和**存量逻辑一起删**"

---

## 0. 核心命题（三句话）

1. **窗口是唯一排期依据** —— 一个任务**能不能现在跑**，只由它的**窗口集合**决定。
2. **队列顺序是唯一执行顺序依据** —— 谁先跑，只由 `run_list`（分段后的）**顺序**决定。
3. **"跑几次"由两件事表达** —— 任务内的**次数**（一轮打几场）与队列里的**重复条目**（跑几轮）。

★ 这三句合起来排除了所有"任务内自排期"（`custom_next_run`）、
"按间隔轮询"（`success_interval`）、"按存量补充"（`charge_*`）等历史机制。

---

## 1. 实体层（原子）

一切数据都拆成**有身份、可独立增删改**的**原子实体**。

### 1.1 `Window` —— 一段开放时段（原子）

```python
@dataclass(frozen=True)
class Window:
    id: str                  # ★ 稳定身份（不是位置）—— 见 §1.5
    enabled: bool = True
    period: WindowPeriod     # DAILY / WEEKLY / MONTHLY
    start: time              # 起（时:分）
    end: time                # 止（时:分）—— 可跨午夜（end < start）
    days: tuple = ()         # period=WEEKLY 时的周几（0=周一）；空 = 由 days_from_config 决定
    days_of_month: tuple = ()# period=MONTHLY 时的几号；空 = 整月
    days_from_config: tuple = ()   # 运行时从**任务配置**读星期（见 §1.4）
    times_from_config: tuple = ()  # 运行时从**任务配置**读时刻
```

**语义（不变量）**
* `W1` 一个任务的**可跑集合** = **其所有 `enabled` 窗口的并集**（逐段取或）。
* `W2` **两端同周期** —— `period` 只一份，`start`/`end` 共用（用户裁定 (B)）。
* `W3` 窗口**只回答"可不可以"**，**不回答"几次"**。
  "一天跑两次" = **两个窗口**（不是 `window_slots`，**已废弃**）。
* `W4` `days` / `days_of_month` 为空 + `period` 有值 -> 由 `period` **推导**
  （DAILY=全周、WEEKLY=全周、MONTHLY=1..31）。
  三种都"空"且无动态项 -> `enabled=False`（不限时段）。

### 1.2 `QueueEntry` —— 一条队列条目（原子）

```python
@dataclass
class QueueEntry:
    entry_id: str            # ★ C: `20261010T143005-RealmRaid`（可拆可合并，同秒重复加序号）
    kind: EntryKind          # TASK / REST
    task: str = ''           # kind=TASK
    minutes: int = 0         # kind=REST
    group: str = ''          # ★ 新增: 类别分段（'timed' / 'fixed'）—— 见 §2
```

**语义（不变量）**
* `E1` **同一任务可以有多条**（用户用重复条目表达"重复跑整个任务"）。
* `E2` `entry_id` **唯一**且**稳定**（拖拽不改变它）。
* `E3` 状态（完成记忆）**按 `entry_id` 记**，不是按任务 —— 所以重复条目**各跑一次**。
* `E4` `group` 决定它属于哪一段；**由任务类别推导**，用户拖拽**不改变**它。

### 1.3 `Task` —— 任务（原子）

任务的**类别**由 `meta.py` 声明，但**最终类别**跟随 `period`（用户裁定）：

```
category_effective =
    TIMED  且 period_effective == NONE  ->  FIXED     # "不限"就不是定时任务
    其它                                 ->  声明的 category
```

**类别全集**：`FIXED` · `TOPPA` · `LIMITED` · `TIMED`
（★ `CHARGE` **删除** —— 用户裁定"去除旧的充能存量说法"）

### 1.4 动态窗口（窗口**引用配置**）

用户裁定："`AvailabilityWindow` 支持动态 days（运行时从配置读）"、
"窗口仍然是唯一排期依据，这个 B 并不冲突"。

`days_from_config` / `times_from_config` 存的是**相对任务**的点分路径，
`Config.resolve_windows()` 运行时读成实际值，与静态值**取并集**。

★ 路径**相对任务**（`guild_banquet_time.day_1`），因为 `_build_windows()` 只拿到
  **任务级**数据。**踩过**：写成绝对路径 -> 永远解析失败（静默）。

### 1.5 「身份，不是位置」原则（原子化的关键）

| 实体 | 身份 | 位置 |
|---|---|---|
| 窗口 | `Window.id` | 列表下标（**可变**） |
| 队列条目 | `entry_id` | 队列位置（**可变**，用户拖） |

★ **一切"增删改"引用身份，不引用位置**。
**踩过的坑**：按**任务名**删队列条目 -> 同名多条**一删全删**（用户报告的 ⑨）。

---

## 2. 集合层（分类与分段）

### 2.1 任务的**两个集合**

| 集合 | 定义 | 谁在这里 |
|---|---|---|
| **`queue`（执行队列）** | `queued_commands()` = `run_list` 的任务 **∪** **已启用**的 `auto_queue` 任务 | 只有这里的任务会跑 |
| **`pool`（候选池）** | 已启用、`auto_queue=False`、且**不在** `queue` 里 | 用户可【添加任务】加进队列 |

★ **不变量 `S1`**：`pending ⊆ queue`（**队列是唯一调度依据**）。
★ **不变量 `S2`**：`pending == queue` 剔除 `waiting` 后的**保序子序列**。

**踩过的坑（本轮修复）**：`schedule_rule=Filter` 时
`_order_by_timed_priority()` **只排序、不剔除** -> 队列外 8 个任务照样跑。
**修**：**任何**规则下都先 `_order_by_queue()` 过滤。

### 2.2 `run_list` 的**类别分段**

`run_list` 存的是 `QueueEntry` 的**有序列表**，每条带 `group`：

```
run_list = [
  {entry_id:..., task:'Delegation',      group:'timed'},
  {entry_id:..., task:'RealmRaid',       group:'fixed'},
  {entry_id:..., task:'RealmRaid',       group:'fixed'},   # 重复条目
  {entry_id:..., task:'AreaBoss',        group:'fixed'},
  ...
]
```

**不变量 `S3`**：`group` **由任务类别推导**，与用户拖拽**无关**：
* `category_effective in (TIMED, LIMITED)` -> `'timed'`
* `category_effective in (FIXED, TOPPA)` -> `'fixed'`

**不变量 `S4`**：**段内的相对顺序**由用户拖拽决定；**段的先后**由**优先模式**决定
（§3），**不由列表物理顺序**决定。

★ 这样"拖动只在同类别内生效"就有了数据依据（段内）。

### 2.3 优先级**模式**（用户裁定：三个）

```python
class PriorityMode(str, Enum):
    TIMED_FIRST = 'timed_first'   # 定时任务优先
    FIXED_FIRST = 'fixed_first'   # 固定任务优先
    CUSTOM      = 'custom'        # 自定义（列表自定义）
```

★ **取代**现有的两个重叠字段（`schedule_rule` 的四选一 + `timed_priority` 的二选一）。
**踩过的坑**：两者语义重叠 -> 界面上"选了定时优先却没用"
（后端只在 `schedule_rule == List` 时读 `timed_priority`）。

---

## 3. 排序层（偏序与算法）

### 3.1 偏序定义

给定 `queue` 的条目集合 `Q`，模式 `M`，类别 `g(e) ∈ {timed, fixed}`：

**`M = CUSTOM`**
```
order = 用户拖的**全局顺序**        # 段不起作用
```

**`M = TIMED_FIRST`**
```
order = [e ∈ Q, g(e)=timed] 按**段内用户顺序**   ⧺
        [e ∈ Q, g(e)=fixed] 按**段内用户顺序**
```
即：**定时类全排在固定类之前**；两类**各自**保持用户拖的顺序。

**`M = FIXED_FIRST`**
```
order = [e ∈ Q, g(e)=fixed] 按段内顺序  ⧺  [e ∈ Q, g(e)=timed] 按段内顺序
```

### 3.2 ★ "窗口期内定时任务全完成后才轮到固定"

`TIMED_FIRST` 的**完整语义**（用户原话）不是"排前面"就完了，而是：

```
阶段 1: 只跑 timed 类里**当前在窗口内**的条目
        （不在窗口的 -> waiting, 不阻塞阶段 1 的其它任务）
阶段 2: 当阶段 1 **再无可跑**（全部完成 / 全部不在窗口）时, 才跑 fixed 类
```

★ 实现上**不需要状态机**：由于 §3.1 的偏序已把 timed 放前，且
`Config.in_window()` 把不在窗口的踢进 `waiting`，
**`pending` 天然就是"阶段 1 的可跑项"**；fixed 条目在其后，
只有 timed 全部进 `waiting`/完成时才会被选中。

★ **反例（必须避免）**：fixed 条目**不能**因为"timed 在等窗口"而被提前跑。
由于 `waiting` 里的条目**不占 pending 位**，`pending[0]` 会是
"下一个可跑的 timed"；**只有当 timed 集合可跑项为空时**，
`pending[0]` 才会是 fixed —— **这是自动成立的**，无需额外逻辑。

### 3.3 拖动约束（用户裁定）

| 模式 | 拖动 |
|---|---|
| `TIMED_FIRST` / `FIXED_FIRST` | ★ **只能在同一段内**重排（跨段拖动被拒绝） |
| `CUSTOM` | ★ **完全自由**（跨段也可） |

**实现**：`reorderQueue(oldIndex, newIndex, mode)`：
* `CUSTOM` -> 按全局下标重排
* 其它 -> 若 `g(拖动项) != g(落点项)` -> **拒绝**（返回失败 + 界面提示"只能在同类任务内调整顺序"）

### 3.4 ★ 删除"重排函数"

现有 `_order_by_timed_priority()`（按 `timed_sort_key` 重排）**必须删除**：
它会让 `pending` **不再是队列的保序子序列**（= 用户拖的顺序失效）。

**类别偏序**由 §3.1 的**分段拼接**表达，**不再**由一个排序函数偷偷重排。

---

## 4. 不变量总表（实现必须全部满足）

| ID | 不变量 | 守卫测试 |
|---|---|---|
| `W1` | 可跑集合 = 所有 `enabled` 窗口的并集 | `test_multi_segment_window` |
| `W2` | 窗口两端**同周期** | `test_window_ui_contract` |
| `W3` | 窗口**不**表达"几次" | 本条（设计约束） |
| `E1` | 同一任务可有**多条**条目 | `test_duplicate_queue_entries` |
| `E2` | `entry_id` 唯一且拖拽不改变 | `test_entry_id` |
| `E3` | 完成状态**按条目**记 | `test_entry_scoped_state` |
| `E4` | `group` 由类别推导, 拖拽不改变 | **待建**（S6） |
| `S1` | `pending ⊆ queue` | `test_queue_no_leak_all_rules` |
| `S2` | `pending` 是"queue 剔除 waiting"的**保序子序列** | `test_queue_is_authority` |
| `S3` | `group` 由 `category_effective` 推导 | **待建**（S6） |
| `S4` | 段内顺序 = 用户拖拽；段先后 = 模式 | **待建**（S6） |
| `Z1` | 僵尸任务（缺 `meta.py`）**不在**配置里 | `test_zombie_nodes` |
| `Z2` | 僵尸清理**不碰** `EXTRA_GLOBAL` 等必需节点 | `test_zombie_nodes` |

---

## 5. CRUD 契约（前后端各自的端点）

### 5.1 窗口（`windows`）

| 操作 | 端点 | 说明 |
|---|---|---|
| 查 | `GET /{script}/tasks/{task}/windows` | 返回 `[{id, enabled, period, start, end, days, days_of_month}]` |
| 增 | `POST /{script}/tasks/{task}/windows` | body = 一个 window；后端生成 `id` |
| 改 | `PUT /{script}/tasks/{task}/windows/{id}` | **按 id**, 不按下标 |
| 删 | `DELETE /{script}/tasks/{task}/windows/{id}` | **按 id** |
| 整单替换 | `PUT /{script}/tasks/{task}/windows` | 拖拽/批量编辑用（可选） |

★ **按 id**，不按下标（§1.5）。

### 5.2 队列（`run_list`）

| 操作 | 端点 | 说明 |
|---|---|---|
| 查 | `GET /{script}/run_list` | 含 `entry_id` / `group` |
| 加任务 | `POST /{script}/queue/add` | body `{task}`；**允许重复**（⑧） |
| 加休息 | `POST /{script}/queue/add` | body `{kind:'rest', minutes}` |
| 移出 | `POST /{script}/queue/remove` | body `{task, entry_id?}`；**带 id 只删一条**（⑨） |
| 重排 | `PUT /{script}/queue/reorder` | body `{from_index, to_index}`；**受模式约束**（§3.3） |
| 清空 | `POST /{script}/queue/clear` | 清 `run_list` + 停用 `auto_queue` 任务（⑦） |
| 候选 | `GET /{script}/queue/candidates` | 已启用、`auto_queue=False`（**不排除已在队列的**，⑧） |

### 5.3 模式

| 操作 | 端点 |
|---|---|
| 查 | `GET /{script}/priority_mode` |
| 改 | `PUT /{script}/priority_mode` body `{mode}` |

---

## 6. 联动矩阵（★ 一处定义，全局一致）

| ↓ 模式 \ 影响 → | 队列顺序 | 拖动约束 | 渲染分段 | 谁先跑 |
|---|---|---|---|---|
| `TIMED_FIRST` | timed 段在前 | **仅段内** | 两段（有色条/标签区分） | timed 可跑项全空后才是 fixed |
| `FIXED_FIRST` | fixed 段在前 | **仅段内** | 两段 | fixed 可跑项全空后才是 timed |
| `CUSTOM` | 全局用户顺序 | **自由** | 仍**标注**类别（色条/标签），但**不分段排** | 严格按用户顺序 |

★ **单一数据源**：模式只存**一处**（`priority_mode`），
**后端**用它算 `pending` 顺序，**前端**用它决定**拖动约束 + 是否分段排**。
**前端不重新推导调度规则**。

---

## 7. 前后端职责边界

| 关注点 | 权威 | 前端可否推导 |
|---|---|---|
| 任务类别 | **后端** `category_effective` | ❌ 只显示 |
| 窗口生效（`in_window`） | **后端** `Config.resolve_windows()` | ❌ 只显示 |
| `pending` / `waiting` 顺序 | **后端** `update_scheduler()` | ❌ 只显示 |
| 拖动是否允许 | **后端**（模式 + 段） | ⚠️ 前端可**预检**（避免无谓请求），但**以后端判定为准** |
| 段/类别的**颜色与标签** | 前端 | ✅ 纯展示 |

★ **原则**：**任何"这个任务现在能不能跑 / 先后顺序"的判断都在后端**。
前端只做**展示**与**交互预检**。

---

## 8. 迁移与废弃清单

| 项 | 处置 | 步骤 |
|---|---|---|
| `window_slots` | ★ **删除**（字段 + `_SLOT_SPAN_MINUTES` + 迁移里的写法） | S3 |
| `window_start` / `window_end` / `window_days` / `window_dom` / `window_period` | ★ **删除**，换成 `windows: list[Window]` | S3 |
| `charge_*` 字段 + 存量逻辑（71 文件 / 327 行） | ★ **删除** | S5 |
| `Category.CHARGE` | ★ **删除** | S5 |
| `_order_by_timed_priority()` | ★ **删除**（§3.4） | S6 |
| `schedule_rule`（四选一） | ★ **合并**进 `priority_mode` | S6 |
| `timed_priority`（二选一） | ★ **合并**进 `priority_mode` | S6 |
| `custom_next_run` | 已清零（§26） | ✅ 已完成 |
| `success_interval` | 已删除（§20） | ✅ 已完成 |

**迁移原则**：
1. **旧配置要能升上来**（用 `validation_alias` 或一次性迁移）
2. **迁移必须幂等**（不能每次启动都覆盖用户的新设置）
3. **不在实时配置上做有副作用的测试**（踩过两次）

---

## 9. 落地顺序（每步一个可验收的大步）

| 步 | 内容 | 前后端 |
|---|---|---|
| **S1** | 僵尸节点清理 + 队列泄漏修复 | ✅ **已完成**（§32） |
| **S2** | 本文档（设计） | ✅ |
| **S3** | `windows: list` 结构化 + 迁移 + **废弃 `window_slots`** | 前后端 |
| **S4** | 前端**窗口列表编辑器**（增/删/改） | 前端 |
| **S5** | **删除充能存量**（`charge_*` + `CHARGE` 类别 + 总览列） | 前后端 |
| **S6** | `priority_mode` 三模式 + `run_list` **类别分段** + 拖动约束 | 前后端 |

---

## 10. 术语表

| 术语 | 含义 |
|---|---|
| **窗口 `Window`** | 一段"可以跑"的时间区间（原子实体，有 id） |
| **队列 `queue`** | 实际会跑的任务集合 = `run_list` ∪ 已启用的 `auto_queue` |
| **候选池 `pool`** | 可被加入队列的（已启用、非自动、不在队列） |
| **段 `group`** | 队列里按类别分出的两段：`timed` / `fixed` |
| **优先模式 `priority_mode`** | 定时优先 / 固定优先 / 自定义 |
| **条目 `QueueEntry`** | 队列里的一条（有 `entry_id`，可重复） |
| **僵尸任务** | 有 `config.py` 但缺 `meta.py` 的遗留任务 |
