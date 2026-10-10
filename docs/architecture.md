# OAS 架构与调度系统

> **状态**：**已降级为「指针 + 非调度域内容」**（★ 2026-10-10）
> **最后按代码核对**：2026-10-10 @ `1da97b9e`（**仅头部与 §0**；正文 §3 / §5.4 /
> §11 / §13 **未逐个校对, 已知过时**）
> **冲突时以**：`docs/scheduler-architecture.md` 为准（**调度域唯一权威**是它）
>
> ## ★★ 读之前先看这三行 ★★
>
> * **调度问题**（窗口 / 队列 / 优先级 / 排期 / 类别）-> 一律看
>   [`scheduler-architecture.md`](scheduler-architecture.md)
> * **端点与字段**（前后端契约）-> 看 [`ui-api-mapping.md`](ui-api-mapping.md)
> * **"某个东西还在不在"** -> 看 [`deprecated.md`](deprecated.md)（唯一废弃清单）
>
> ### 本文**已过时**的部分（不要照做）
>
> ★★ **行号已于第二轮复审修正**（原来写错, 且**恰好排除**了点名的符号）★★
>
> | 节 | 行范围 | 问题 |
> |---|---|---|
> | **§3** | `149-357` | 整节讲**已删除**的 `Recharge` / `Resource` / `RunState` / `next_available()` / `TaskSpec.resource`, 还给了源码。★ 原头部写 `:204-305` —— 那只覆盖 §3.0/§3.1, **恰好漏掉** §3.2-§3.4 那三个点名符号 |
> | **§2.1**（编号与 `:81` 的 §2 **重复**）| `1674-1728` | 里面的 `TaskSpec.resource`（`:1722`）与 `scheduler_core.next_available()`（`:1724`）**已删除** |
> | **§4.1 / §4.2 / §4.3** | `372-410` | `spec.resource` / `next_available(spec.resource, …)` / `team_coordinator.py` **均已删除** |
> | **§5.4.1** | — | 把 `timed_priority` 当**现行**字段（已并入 `priority_mode`）; ★ **`priority_mode` 本身也已在 S7 删除**（见 `deprecated.md` §3.2）|
> | **§5.4.1 / §10.3** | `755-787` / `1598-1608` | 仍讲「优先级三模式 / 调度优先级下拉」—— ★ **S7 已整簇删除**; 现行做法是 `PUT /{script}/queue/sort` 的**一次性动作**（★ 行号已按**改后**核对）|
> | **§5.7 / §7.6 / §10.7** | `1007` / `1378` / `1626`,`1629` | 仍提 `_order_by_timed_priority()`【**已删除**】 / `charge` 任务【**已删除**】 / `resource`【**已删除**】 |
> | **§11 / §13** | `1824` / `1764` | 编号错位; ★ **§13.1(`:1805`) 的方向是反的** —— 它把**已删除**的 `Resource`/`next_available` 写成"`✅ 接进调度`"（不是"已完成写成待办", 而是**已删除写成已完成**）|
> | **附录** | `1850-1884` | 列了**已删除**的 `scheduler_core.py` / `gen_resource_specs.py` / `test_availability.py`（已打删除线）。★ 原头部写 `:1813-1819` —— 那是 §13.2 的表 |
> | **`:1731`** | — | 仍称台账为"**唯一事实来源**" —— ★ 台账 `:3` 已**降级**为历史记录, 这句**自相矛盾** |
>
> ### 本文**仍有效**的部分
>
> 平台能力（§7.4）· 调研方法论（§8）· 历史 bug 根因（那些"为什么当初这么做"的记录）
> —— 这些与本次调度重构**无关**, 仍然可信。
>
> 更新：2026-10-08（原文）；2026-10-10（本轮降级）
> 读者：后续维护者（包括未来的我）

本文档**曾是** OAS 架构与调度系统的单一入口。合并自此前分散的多份设计稿：
`scheduler-redesign.md`（旧版）、`task-list-design.md`、
`architecture-evolvability.md`、`adding-new-activity.md`、`decision-log.md`。

**为什么要有这份文档**：此前的设计过程暴露出一个真实问题 —— 同一个概念
（"多久跑一次"）在代码里有四个载体（`success_interval`【已删】 / `charge_slots`【已删】 /
`charge_max`【已删】 / `next_run`），而设计知识又散在五份文档里。**概念要收敛，文档也要收敛。**

★ **2026-10-10 追加**：这次收敛**做过头了** —— 三个文档同时自称"唯一权威",
  于是**同一知识又有两处定义**, 又漂移。现已分层（见文件头）。

---

## 0. 目录

> ★ **调度器的正式设计在 [docs/scheduler-architecture.md](scheduler-architecture.md)** —— 原子化 / 集合 /
>   ~~三优先模式~~【**已删除**】—— ★ **S7 之后: 执行顺序 ≡ `run_list`, 拖动永远自由,
>   排序是 `PUT /{script}/queue/sort` 的一次性动作** /
>   CRUD 契约 / 联动矩阵 / 不变量总表。**与本文冲突时以它为准。**

| 节 | 内容 |
|---|---|
| [1](#1-设计原则) | 设计原则 |
| [2](#2-现状问题) | 现状问题（已实测） |
| [3](#3-核心抽象) | 核心抽象：Resource + RunState + AvailabilityWindow |
| [4](#4-调度器) | 调度器 |
| [5](#5-任务列表) | 任务列表（调度器的一种模式） |
| [6](#6-运行控制) | 运行控制：暂停 / 休息 / 延后 |
| [7](#7-可演进性) | 可演进性：新增任务 / 维护 / 前后端 / 跨平台 |
| [8](#8-游戏机制数据从哪来) | **游戏机制数据从哪来（调研方法论）** |
| [9](#9-路线图) | 路线图 |
| [10](#10-决策台账) | 决策台账 |
| [11](#11-已修复的-bug) | 已修复的 bug |

---

## 1. 设计原则

三条，按优先级。**任何设计有疑问时，回到这三条。**

| # | 原则 | 反例（改造前的现状） |
|---|---|---|
| 1 | **一个概念只用一个词表达** | "多久跑一次"同时有 `success_interval`【已删】、`charge_slots`【已删】、`charge_max`【已删】、`next_run` |
| 2 | **知识只存在一处** | 金币妖怪"0/12 点补 2 次"散在 3 个配置字段 + 代码里 |
| 3 | **用户只看到他该管的** | 54 个任务暴露 `charge_max`/`charge_slots`/`success_interval`【三者**均已删**】, 用户只想改"打几次" |

**推论（重要）**：不为"兼容旧配置"保留双轨、兼容层或 feature flag。
旧配置用**一次性迁移脚本**转换，**脚本用完即删**。留在仓库里就是永久技术债。

---

## 2. 现状问题

### 2.1 调度器（改造前）

```python
# module/config/config.py get_next()
for task in all_tasks:
    if not enable:              continue
    if _skip_by_period():       waiting.append()
    elif next_run < now:        pending.append()      # ← 就绪判据只有 next_run
    else:                       waiting.append()
pending = TaskScheduler.schedule(rule, pending)        # Filter/FIFO/Priority

# task_delay()
interval = scheduler.success_interval if success else scheduler.failure_interval
run.append(start_time + interval)     # ← 一个标量决定一切
```

**三个根本问题**：

| # | 问题 | 后果 |
|---|---|---|
| 1 | `next_run` **同时承担**"冷却结束"与"资源可用" | 无法表达"容量 2、0/12 点各补 1" |
| 2 | 资源模型是**一个标量间隔** | 充能类只能靠 `charge_*` **另一套代码旁路**，两套并存 |
| 3 | 没有"可用窗口"概念 | 限时活动只能靠把 `next_run` 推远来**假装不存在** |

★ **最关键**：旧代码把"次数"当作冷却时间实现（打 50 次 → 隔 1 天）。
但"目标次数"本来就是**单次运行内的循环上限**，与冷却无关。**这两件事必须拆开。**

### 2.2 字段命名不统一（实测）

```
FallenSun/Orochi/...        limit_count
Exploration                 minions_cnt
Hyakkiyakou                 hya_limit_count   (脚本里映射成 limit_count)
RealmRaid                   number_attack     (脚本里映射成 limit_count)
WantedQuests                **硬编码 30**     (用户改不了, 是 bug)
```

### 2.3 任务注册中心化

`module/config/config_model.py` **硬编码 57 行 import + 56 行字段**。

加一个游戏活动要动 **5 处**，其中 3 处是中心化硬编码：

| # | 位置 | 漏改后果 |
|---|---|---|
| 1-3 | `tasks/<New>/` config / script_task / assets | — |
| 4 | **`config_model.py`** | **任务加载不了** |
| 5 | **i18n（OAS xml + OASX 两个 dart）** | 界面显示英文 key |

### 2.4 i18n 漂移已经真实发生

```
OAS  zh_CN.xml:171    FallenSun → 日轮之城     ← 错(已修), 且重复 2 次
     zh-CN.json       FallenSun → 日轮之陨     ← 对
OASX i18n_cn.dart     FallenSun → 日轮之陨     ← 权威
```

**同一任务名三份手写副本，其中一份已写错。** 靠手写同步，漂移是必然。

### 2.5 「完成记忆」从未生效（本次改造引入的 bug）

`period` 完成记忆已实现，但**所有任务的 `period` 默认都是 `none`**，
因此它一次都没生效过。真实周期实际由 `success_interval` 控制。

---

## 3. 核心抽象

> ★★ **本节（§3）整体已过时** —— 讲的是**已删除**的"存量/充能"机制 ★★
>
> | 本文提到的 | 现状 |
> |---|---|
> | `Resource`（`:232`）| ★ **已删**（S5, 见 [`deprecated.md`](deprecated.md)）|
> | `Recharge`（`:234`）| ★ **已删** |
> | `RunState`（`:293`）| ★ **已删**（随 `scheduler_core.py`）|
> | `next_available()`（`:305`）| ★ **已删** |
> | `TaskSpec.resource`（`:323`）| ★ **已删** -> 改成**独立字段** `TaskSpec.period` |
>
> ★ **取代它们的是**：**窗口**（`Scheduler.windows: List[TaskWindow]`）。
>   "一天跑几次"由**多个窗口** + 队列里的**重复条目**表达。
>
> ★ 本节**保留**只因为它是"**当时为什么这么设计**"的记录（踩过的坑：
>   "同一个概念有四个载体"）。**不要照它写代码。**
>
> 现行设计 -> [`scheduler-architecture.md`](scheduler-architecture.md)

**只有三个概念。**

```
Resource            资源     —— 任务"能跑几次"的来源   （静态规则）
AvailabilityWindow  开放时段 —— 任务"什么时候允许跑"   （静态规则, 硬约束）
RunState            运行态   —— 它"现在能不能跑"        （动态）
```

`next_run` / `success_interval` / `charge_*` 全部消失 —— 它们都是这些概念的
**不完整实现**。

### 3.0 ★ AvailabilityWindow —— 一个此前完全缺失的概念

**阴阳师很多玩法不是随时能做**，而是有固定开放时段。而 OAS 此前**没有这个概念**，
用户只能用一个迂回办法绕过：

> 把 `success_interval` 设得很短（如 1 小时），让任务**频繁醒来碰运气** ——
> 因为软件无法保证"在开放时段内一定会打开该任务"。

这带来两个后果：

| 后果 | 说明 |
|---|---|
| **字段语义被污染** | `success_interval` 里混进了**用户意图**（轮询节奏），不再是游戏机制。任何拿它当游戏知识读的逻辑都会出错 |
| **白跑一趟** | 不在时段内时，任务进界面、发现做不了、退出 —— 浪费时间，还可能干扰游戏状态 |

```python
# 复现该问题(用户实际配置)
demon_encounter.success_interval = "00 01:00:00"   # ← 这是"用户为了不错过而每小时轮询"
# 真实的游戏机制是: 逢魔之时 每天 17:00-23:00   ← 这条信息配置里完全没有
```

**新模型把两者彻底分开**：

| 概念 | 来源 | 性质 | 例 |
|---|---|---|---|
| `AvailabilityWindow` | **游戏机制** | **硬约束**：不在时段内一律不跑 | 逢魔 17:00–23:00 |
| `interval` | **用户配置** | **软约束**：我想多快轮询 | 每小时醒一次 |
| `slots` | **游戏机制** | 固定时刻补充额度 | 金币妖怪 0/12 点 |
| `period` | **游戏机制** | 周期回满额度 | 每天打 50 次 |

三者可以**共存**：

```python
Resource(
    capacity=1,
    interval=(0, 1, 0),                                 # 用户轮询节奏(软)
    window=AvailabilityWindow(True, time(17), time(23)),  # 游戏开放时段(硬)
    period=Period.DAILY,
)
```

**设计约束（用户明确要求）**：

| # | 要求 | 落实 |
|---|---|---|
| 1 | **不写死任何时段** | 时段全部来自用户配置；`AvailabilityWindow` 的默认值是 `enabled=False`（不限时段），因此新字段**不改变既有行为** |
| 2 | **全部开放出来** | `start` / `end` / `days` 都是用户可配字段，放进 `Scheduler` 配置（与 `period` 同级） |
| 3 | **支持自学习** | `ObservedWindow` 记录实际跑通的时刻，反推真实时段，与配置比对后**提示用户**（不是自动改配置） |

**能力**：

* 每天固定时段：`AvailabilityWindow(True, time(17), time(23))`
* 限定星期：`AvailabilityWindow(True, time(19), time(21), days=(4,5,6))`（周五六日）
* **跨午夜**：`AvailabilityWindow(True, time(22), time(2))`（22:00–次日 02:00）

**自学习的工作方式**：

```
运行中记录"每次成功发生的时刻"(只记成功 —— 失败可能因体力/网络等无关原因)
        ↓  样本 >= 5 个才下结论(避免误报)
      取 1%/99% 分位并向外扩 5 分钟(抵抗偶发异常值)
        ↓
    反推出实测时段 → 与用户配置比对
        ↓
不一致时**提示**用户: "实测该任务只在 每天 17:00-22:05 运行过(共 12 次); 可考虑启用时段限制"
```

★ 这样即使初始配置不准、或游戏改版，软件也能**自我纠正并告知**，
而不是依赖某一次把数据填对。

### 3.1 Resource —— 四种补充方式覆盖全部 54 个任务

`Resource`【**已删**】把"补充方式"独立成分层的 `Recharge`【**已删**】，避免出现**自相矛盾的状态**。

```python
@dataclass(frozen=True)
class Recharge:   # ★【已删】(S5) —— 现由「窗口」取代
    """池子如何补充 —— 三种互斥的方式(一次只用一种)。"""
    kind: Literal['none', 'interval', 'slots', 'window'] = 'none'
    interval: tuple = (0, 0, 0)      # (天, 时, 分), kind=INTERVAL
    slots: tuple = ()                # ((时, 分), ...), kind=SLOTS
    period: Period = Period.NONE     # 周期边界重置
    amount: int = 1                  # 增量补充几格
    refill_to_full: bool = False     # True: 每次补充直接回满 capacity
    reset_at: time = time(0, 0)

@dataclass(frozen=True)
class Resource:
    capacity: int = 1
    consume: int = 1
    recharge: Recharge = None   # ★【已删】
    window: AvailabilityWindow = None
```

★ **为什么分层**：早期版本把 `kind` 与 `period` **平铺**在 `Resource` 上，结果出现
`kind='interval'` 与 `period=WEEKLY` **同时非默认**的组合（真八岐大蛇：每周回满 2 次，
同时"距上次运行 3 天"）。那种状态**语义含糊** —— 读者判断不出到底哪天能跑。
分层后每种方式自带它需要的参数，不存在自相矛盾的组合。

★ **为什么需要 `refill_to_full`**：两种补充语义都真实存在，必须显式区分：

| `refill_to_full` | 语义 | 例 |
|---|---|---|
| `False`（默认） | 每次补充 **+amount** 格（增量式） | 逢魔之时：每小时 +1 |
| `True` | 每次补充**直接回满 capacity** | 金币妖怪：0/12 点各回满到 2 次 |

**周期边界**（`period`）的语义固定为**回满 `capacity`** ——
"每天/每周重置"就是"新周期一池子满的"。

| 形态 | 用于 | 例 | 旧实现用了几个字段 |
|---|---|---|---|
| `none` + `period` | 固定任务 | 日轮之陨：每天 50 次 | `success_interval=1d` + `limit_count=50` → **2 个** |
| `interval` | 按间隔补充 | 逢魔之时：每 1 小时 | `success_interval=1h` → 1 |
| `slots`【**该机制已删**】 | 固定时刻补充 | 金币妖怪：0/12 点各回满，上限 2 | `charge_slots`+`charge_max`+`charge_consume`+`success_interval` → **4 个**（**全已删**）|
| `window` | 只在活动期 | 超鬼王：活动期内每天 1 次 | **无**（靠推远 `next_run` 假装不存在） |

★ `Resource(capacity=50, recharge=Recharge(period=DAILY))`【**均已删**】**一个概念**即表达旧的
`success_interval=1d` + `limit_count=50`。

**从旧字段推导**（`Resource.from_legacy`，迁移桥梁，已实测正确）：

| 旧 `success_interval` | 推导结果 |
|---|---|
| `01 00:00:00`（1 天） | `Recharge(period=DAILY)`【**已删**】|
| `07 00:00:00`（7 天） | `Recharge(period=WEEKLY)`【**已删**】|
| `00 03:00:00`（3 小时） | `Recharge(...)`【**已删**】← **不再是 period** |
| `03 00:00:00`（3 天） | `Recharge(...)`【**已删**】← **不再是 period** |

★ 最后一行的修正很重要：早期版本把 `days<7` 一律归为 `daily`，于是真蛇的
"每 3 天"变成"每天"、3 小时的斗技变成"每天 1 次"，**间隔信息全丢**。

### 3.2 RunState

```python
@dataclass
class RunState:
    used: int = 0                  # 本周期/本窗口内已用次数
    last_refill: datetime | None
    retry_after: datetime | None   # 失败重试退避(与资源无关, 单独概念)
```

**不存 `next_run`** —— 它变成纯函数的结果。

### 3.3 `next_available()` —— 取代所有零散排期逻辑

```python
def next_available(res: Resource, st: RunState, now) -> datetime:
    if res.kind == 'window':
        return now if in_window(now) else next_window_opening(now)
    if res.kind == 'period':
        if st.used + res.consume <= res.capacity:
            return now
        return next_period_start(res.period, now)
    if res.kind == 'slots':
        if remaining(res, st, now) >= res.consume:
            return now
        return next_slot(res.slots, now)
```

**无副作用、可单测、可解释。**

### 3.4 `TaskSpec` —— 调度器与任务的唯一契约

```python
class TaskSpec(Protocol):
    task: str
    name_zh: str
    category: Category
    resource: Resource
    target_field: str | None      # 用户可改的"次数"字段名; None = 不可改
    requires: tuple = ()          # 需要的平台能力(见 §7.4)
```

★ `resource` 是**纯数据**，不含任务代码引用 —— 调度器**永远不需要 import 任务模块**，
避免"调度器改动引发全任务回归"的连锁。

---

## 4. 调度器

### 4.1 决策

```python
class Scheduler:
    def next_task(self, now) -> TaskSpec | None:
        if self.paused:                                 return None
        if self.rest_until and now < self.rest_until:   return None   # 休息: 全停

        ready = []
        for spec in self.specs():
            if not spec.enabled:                        continue
            if self.postponed(spec, now):               continue      # 延后: 只缓列表
            if spec.resource.kind == 'window' and not in_window(now):
                continue
            if next_available(spec.resource, self.state(spec), now) > now:
                continue
            ready.append(spec)

        return min(ready, key=self._order_key, default=None)

    def _order_key(self, spec):
        pos = spec.list_pos if spec.list_pos is not None else math.inf
        if self.mode == 'timer_first':
            return (next_available(...), pos, spec.priority)
        return (pos, spec.priority, next_available(...))    # list_first
```

**`rest_until` 与 `postponed()` 的差别就是"休息 vs 延后"的全部实现** ——
前者直接 `return None`（全停），后者只过滤列表内的任务。**一处判断，语义自明。**

### 4.2 排序模式

| 模式 | 语义 |
|---|---|
| `timer_first`（默认） | 谁的时间到了先跑谁；列表只决定"同时到点"时的次序 |
| `list_first` | 严格按用户列表顺序，忽略时间 |

旧的 `Filter` / `FIFO` / `Priority` **保留为 `timer_first` 下的细化排序**，
不是并列概念。

### 4.3 插件点：Availability Oracle（跨账号协同）

调度器留了一个**决策插件点**，供跨账号组队协同使用：

```
┌──────────────────────────────────────────────────────┐
│  L3  决策层  team_coordinator.py【**已删**】           │
│      读双方状态 -> START / WAIT / YIELD / DEFER        │
├──────────────────────────────────────────────────────┤
│  L2  状态层  log/.team_state.json                     │
│      双方发布: 当前任务/阶段/队列/组队进度/心跳          │
├──────────────────────────────────────────────────────┤
│  L1  接入层  Scheduler.next_task() 的排序阶段          │
│      + 组队任务开始前                                  │
└──────────────────────────────────────────────────────┘
```

决策规则（优先级从上到下）：

| # | 条件 | 决策 | 理由 |
|---|---|---|---|
| 1 | 对方不在线（心跳过期） | **START** | 不能等 |
| 2 | 对方在边界 且 对方组队进度落后 | **YIELD** | 让对方先赶上 |
| 3 | 对方 `expected_remaining_sec` ≤ `wait_time` | **WAIT** | 马上能组上 |
| 4 | 我方组队进度落后 | **START** | 我该补进度 |
| 5 | 其他 | **DEFER** | 排到本轮之后再试 |

★ 规则 2/4 是"合理分配"的关键 —— 让**进度落后的一方优先发起**，
双方自然收敛，而不是各自按顺序跑然后错位。

**新调度器给 Oracle 提供了明确的接入位置**（`_order_key` 阶段），
这比旧设计里"在任务边界打补丁"干净得多。

---

## 5. 任务列表

**任务列表就是一个调度器模式**，不是新子系统。

配套三个概念：

| 概念 | 实现 |
|---|---|
| 列表顺序 | `spec.list_pos`（`None` = 未编排，排最后） |
| 每行次数 | `scheduler.target`（`0` = 用默认值） |
| 列表优先 / 定时优先 | `Scheduler.mode` |

### 5.1 休息（v2 只有这一个控制条目）

| 条目 | 语义 | 实现 |
|---|---|---|
| **休息** | **去庭院待着** N 分钟 | `state.rest_until = now + N` |


#### ★ **用户的定义（第三次提出, 以此为准）**:
> **休息就是临时任务**（回庭院待着），只不过**可以选择被定时任务插队**。
>
> 推论: 休息与其它**临时任务**同一套规则 ——
> 没有"恒排最后"、没有特殊段名 `'__rest__'`、没有特殊 rank、**可自由拖动**；
> 唯一特殊性 = **可被定时任务插队**（`rest_interleave`, 一个**可选能力**, 不是约束）。

★ 这条定义**取代**了此前文档里的"休息恒排最后"（那句话**不是**用户的裁定）。
★ 实现: `Config._tag_and_place_rest()` 只打段名、**不排序**；
  `Config.place_rest_last()` 保留名字但**直通**（见 OAS `832f467e`）。

★ 休息**不是**"什么都不做"，而是**去庭院**：游戏不会因长时间无操作而断线，
组队任务回来时人也"在"。

#### 为什么去掉了 v1 的「延后（只停列表）」

v1 有 `休息`（连定时任务一起停）与 `延后`（只停列表、定时照常）两个条目，
用来表达"要不要连定时任务一起停"。

**v2 之后固定任务与定时任务分开管理**（定时任务有自己的总开关），
"只停列表" 不再有意义 —— **想只停列表就关掉定时任务开关**。

同理，运行控制条上的「全部停止 / 只停列表」两个按钮也一并去掉，
只留 `暂停调度 / 本轮跑完再停 / 继续调度`。

★ 历史教训：设计过程中还曾错误地引入"休息作用范围(SELF/WHOLE_LIST)"参数 ——
**那是把"条目"和"动作"两个概念混在一起**。几轮迭代后的结论是：
**控制条目只该有一个「休息」**，其余的"谁停谁不停"交给**总开关**表达。

### 5.2 界面职责划分（v2 · **统一控制台**）

#### 演进过程（三轮用户反馈）

| 轮次 | 用户的意见 | 我的处理 |
|---|---|---|
| 1 | "没必要重新构建流程，把功能加入旧总览就行" | 合并成一个控制台（去掉重复的总览页）|
| 2 | "执行顺序和监控不能合在一起吗" | 3 tab → 2 tab |
| 3 | "监控窗口和预期流程不应该是一种东西吗"<br>"待执行/等待中就是预期执行流程，也应该可以拖拽"<br>"这个任务表格不涉及执行顺序的改变" | 合并监控与预期流程；表格去掉 ↑↓ |
| 4 | "执行队列应该和队列视图是一个东西吧"<br>"预期执行流程可以删去了，似乎和上边的队列冗余了"<br>"正在运行的逢魔之时，下边显示还可以加入逢魔之时" | **最终结构: 单页**（见下）|

★ 三轮里有**两次是我理解偏了**：第一轮我另建了重复的监控页；
第二轮我把"合并"做成了"**删掉**观察窗"。教训记在 §5.2.2。

#### 最终结构：**单页**（无 tab）+ 日志常驻右半栏（宽度可拖）

★ 第四轮用户指出「执行队列」与「队列视图」**也是一个东西**,
而且「预期执行流程」与队列**冗余** —— 于是**去掉全部 tab**:

```
┌─ 运行控制条:  [● 状态] [暂停调度] / [继续调度] ────────────────┐
├────────────────────────────────────┬───────────────────────┤
│                                    ║  ← 拖这条改左右宽度   │
│  1. 状态行（进程状态 / 待执行数 /   │                        │
│     等待中数 / 冷却数）             │       日 志            │
│  2. 批量操作（进程开关 + 批量启停/  │    （常驻右半栏）      │
│     运行一次/重置选中/搜索/筛选）    │                        │
│  3. ★ 全局开关（**顶部**）          │                        │
│  4. ★ **执行队列**                  │                        │
│       ▶ 0  正在运行: xxx  ← 队首    │                        │
│       ⠿ 1  探索   [待执行] 次数/耗时 │                        │
│       ⠿ 2  御魂   [等待中 18:00]     │                        │
│       ⠿ 3  契灵   [冷却中 42 分]     │                        │
│       ⠿ 4  休息 30 分钟              │                        │
│       ─── 未编排（可加入）───        │                        │
│  5. 任务表格（Excel 式批量管理）    │                        │
└────────────────────────────────────┴───────────────────────┘
```

**没有 tab** —— 一页从上到下就是全部。日志常驻右半栏, 宽度可拖。

#### ★★ 为什么「执行队列」是**唯一**的观察与编排入口

用户四轮反馈最终收敛到一句话: **「正在运行 / 待执行 / 等待中 / 预期流程」
本来就是一件事** —— 都是"接下来会跑什么"。

| 曾经 | 现在 |
|---|---|
| 四个只读观察窗（`_MonitorTab`）| **队列第 0 项 = 正在运行**, 其余就是待执行/等待中 |
| 「执行顺序」页（拖拽）| 队列本身可拖拽 |
| 「预期执行流程」面板（推算）| **删除** —— 队列已经按顺序列出, 再画一遍是重复 |
| 两个 tab（调度 / 队列视图）| **单页** |

★ 后端 `/run_list/preview`（预期流程）**接口保留** —— 它是有用的能力,
  只是界面不再单独画一块（与「本轮跑完再停」「只停列表」同样的处置）。

#### ★ 状态徽标取代了"待执行 / 等待中"两个列表

每行右侧一个徽标说明**为什么在等**（数据来自后端
`slot` / `reason` / `in_cooldown`, 前端**不重新推导**）:

| 徽标 | 含义 |
|---|---|
| `待执行` | 已到点, 马上要跑 |
| `等待中 18:00` | 还没到点（定时任务）|
| `冷却中 42 分` | 连续失败 3 次进入冷却 |
| `未启用` | 任务级开关关着 |

★ 这样"待执行 11 / 等待中 6"变成队列里的**徽标**, 信息没丢,
  还多了"为什么等"。

#### ★★ 正在运行的任务**不出现**在"未编排（可加入）"里

**踩过的坑**: `run_list` 为空时（还没编排过）**所有**启用任务都落进
"未编排"候选 —— 包括**此刻正在跑**的那个。于是队列里同一个任务出现两条:

```
▶ 0  正在运行: 逢魔之时
   ─── 未编排 ───
   ⠿  逢魔之时   [加入]      ← 用户: "这是不是个bug"
```

**是 bug。** 它其实只是"不在编排列表里"（调度器用内置默认顺序）,
与"可以加入队列"是两件事。

修法: 控制器用 `runningTaskCommand`（**安全**读 WebSocket 的
`ScriptModel.runningTask`）把正在跑的那个**排除**掉。

#### ★★ 「执行队列」与「任务表格」的分工（用户明确纠正过我）

| 面板 | 管什么 | 交互 |
|---|---|---|
| **任务表格** | Excel 式的**批量查看与管理** —— 启停 / 运行一次 / 多列排序 / 筛选 | 只读的 `✓/—` 表示在不在队列；**不改执行顺序** |
| **执行队列** | **执行顺序** + 每任务的次数 / 预期耗时 / 优先级 | 拖 `⠿` 改顺序；内联编辑数值 |

★ 我第一版在任务表格里放了"位次 + ↑↓"来调顺序, 用户纠正:

> 这个位次列执行顺序和我的想法不相符，我要的 ↑↓ 是为了像 EXCEL 那样
> 方便查看和管理任务（如启停和运行一次的测试），
> **这个任务表格不涉及执行顺序的改变**

所以 ↑↓ 全部删除。

#### ★ 为什么「待执行 / 等待中」是**一个可拖拽队列**而不是两个只读窗

用户: "待执行、等待中这类就是预期执行流程，也相当于包含所有任务的执行顺序，
也应该可以拖拽排列顺序"。

原先的问题: 「待执行」「等待中」是**"到没到点"**的划分（由**时间**决定）,
不是**顺序**; 而用户真正想管的是**顺序** —— 顺序只能拖。

现在是一个有序队列:

```
执行队列（拖 ⠿ 改执行顺序 · 每行次数/预期耗时可直接改）
  ⠿ 1 探索        [待执行]   次数[5] 预期耗时[10] 优先级[5]
  ⠿ 2 御魂        [待执行]
  ⠿ 3 日轮之陨    [等待中 18:00]
  ⠿ 4 契灵之境    [冷却中 42 分]
  ⠿ 5 休息 30 分钟
  ─── 未编排（共 N 个 · 拖上来或点「加入」进队列）───
  ⠿ 探索寮突      [待执行]  [加入]
```

* **有序部分** = 运行列表（`run_list`）—— 拖完直接存回后端
* **未编排部分** = 启用了但没进列表的任务
* **状态徽标** = 后端给的 `slot` / `reason` / `in_cooldown`
  —— 前端**不重新推导**调度规则（那会与后端漂移）

#### ★ 面板尺寸可拖拽调整 + 持久记忆

* 分界线上有一根 **7px 拖拽条**（左右各 3px 热区）, 光标变 `resizeColumn`
* 范围钳制 `[420, 可用宽度-320]` —— **任一侧都不会被拖没**
  （用户说过"看不到就以为功能没了", 这点必须防住）
* 松手存进偏好（`task_prefs`, 按账号隔离）
* 拖动过程中**不写存储**, 只在 `onDragEnd` 写一次（免得每帧一个 IO）

#### ★ 进程级 vs 调度级

| 层级 | 控件 | 在哪 | 行为 |
|---|---|---|---|
| **进程级** | 启动/停止脚本 | 「调度」tab 的批量操作卡片 | 起/停**子进程**（硬停, **会打断当前战斗**）|
| **调度级** | 暂停调度 / 继续调度 | 顶部运行控制条 | 软停, 在**安全点**（战斗边界）生效 |

★ **运行控制条的状态必须同时看进程与暂停**（这是个真 bug）:

用户反馈"未暂停调度就绿色运行中，但脚本进程停止时这个还显示运行中"。
根因是它只看 `run_control` 的 `paused`, **完全没看脚本进程**。
现在:

| 进程 | 圆点 | 文字 |
|---|---|---|
| 未跑 | 灰 | **脚本未启动** |
| 在跑 · 休息中 | 橙 | 休息中 至 … |
| 在跑 · 已暂停 | 橙 | 已暂停调度 |
| 在跑 · 未暂停 | 绿 | 运行中 |

且进程没跑时「暂停调度」**置灰**。

#### ★ 中文显示

| 位置 | 原因 | 修法 |
|---|---|---|
| 调度器状态 | `'$state'` 打印 `ScriptState.inactive`（**英文枚举名**）| `_stateLabel()` |
| 任务名 | WebSocket 推的是**大驼峰命令名** | `TaskListController.zhNameOf()` 用 `/overview` 的 `name_zh`（源头是各任务 `meta.py`）|

#### 旧「总览」页的处置

**从菜单隐藏**, 进账号后默认进控制台。
⚠ **视图文件保留** —— `OverviewController` 还承担历史日志路由,
`TaskItemModel` 是 `script_model.dart` 的依赖。

### 5.2.1 列表页的三个面板（对应原型）

| 面板 | 内容 | 数据来源 |
|---|---|---|
| **全局设置** | 两个总开关（启用固定 / 启用定时）、定时优先级、休息时穿插<br>跑完循环整表、优先级依据（四个调度模式）| `schema.list.global_fields` + `modes` |
| **执行顺序** | 拖拽排序、增删条目、恢复默认 | `/{script}/run_list` |
| **预期执行流程** | 按当前列表**推算**的执行流程 | `/{script}/run_list/preview` |

★ 「预期执行流程」**必须显示 `disclaimer`** —— 它是推算不是保证
（实际还受体力/网络/开放时段影响），不能让用户以为精确。

★ **前端不硬编码条目类型**：效果名、说明、`needs_minutes` / `needs_task` /
`blocks_list` 全部读 `schema.list.entry_kinds` ——
后端改名（如 `rest` 的界面名从"全部停止"改成"休息"）前端自动跟上。

★ **添加条目选择器**：**「休息」置顶**（用户要求），
带**分类筛选**，且**只列固定任务**（`countable == true`）——
定时任务有自己的 window/存量/周期，给无效选项比不给更糟。

★ **点任务行 → 进该任务的设置页**。这里**不能**复用
`NavCtrl.switchContent()` —— 它开头有 `useablemenus` 白名单
（只列侧边栏里的任务），点一个不在侧边栏的任务会被**静默忽略**
（用户看到"点了没反应"，很难排查）。改用 `openTaskSettings()`，
只保留 `TaskList` 防呆（后端没有 `/{script}/TaskList/args`，
`loadGroups` 会崩 → 界面 500）。

### 5.3 目标次数只对"固定任务"

| 类别 | 界面显示 |
|---|---|
| `fixed`（13）/ `toppa`（2） | ✅ 目标次数输入框 + 进度 |
| `charge`（3） | 存量 x/y（如 `0,12 点刷新`），**不设次数** |
| `limited`（8） | 活动期 / 非活动期 |
| `timed`（28） | 下次运行时间 |

---

### 5.4 运行列表 = **固定任务 + 休息**；定时任务**独立调度**

> **v2 相对 v1 的最大变化**：把**固定任务**与**定时任务**分开管理。
> v1 把所有任务混在一个列表里按用户顺序跑 —— 但定时任务有自己的
> window / 存量 / 周期，"排在第三个" 跟 "17:00 才开放" 会互相打脸。

#### 分工

| 谁来管 | 内容 | 排序依据 |
|---|---|---|
| **运行列表** | 固定任务（`fixed`/`toppa`）+ 休息 | **用户拖拽的顺序** |
| **定时调度器** | `timed` / `charge` / `limited` | window、剩余时间、预计耗时、自定义优先级 |

☞ 判定"能不能进列表"用 `run_list.is_list_task(task)`（只有固定任务能进）。
`RunList.from_list()` **默认校验**，定时任务会被跳过并记录。

#### 条目只有两种（按行为命名）

| 条目 | 界面名 | 效果 | 阻塞列表 |
|---|---|---|---|
| `task` | 任务 | 跑一个**固定任务** | ❌ **不阻塞** |
| `rest` | **休息** | **去庭院待着** N 分钟 | ✅ 阻塞 |

存储（`Script.optimization.run_list`，JSON 数组，顺序天然保留）：

```json
"run_list": [
    {"kind": "task",  "task": "Exploration"},
    {"kind": "task",  "task": "Orochi"},
    {"kind": "rest",  "minutes": 30},
    {"kind": "task",  "task": "FallenSun"}
]
```

#### ★ `task` 为什么不阻塞

若任务会阻塞，则"列表里第一个任务在 6 小时冷却中"会**卡死整个列表**。
所以：

* 列表提供的是**优先顺序**（排前面的先跑），不是"必须按顺序做完"
* 真正的"在此处停下"由 `rest` **显式表达**

这与 `FILTER/FIFO/PRIORITY` 一致 —— 它们也是**排序**而非**阻塞**。

#### ★ 休息是一次性条目

被"轮到时"生效，生效期间列表**停在该条目之前**；时间到后该条目
**被移除并持久化**，列表继续。

这样用户看到的是"这一行消失了"，而不是"每次循环都休息一次" ——
后者会让人以为软件坏了。

#### 与旧 `task_order` 的关系

`task_order`（逗号分隔任务名）是**旧字段，已移除**。
`RunList.from_task_order()` 保留了一次性迁移能力，
`TaskScheduler.list_order()` 也接受旧字符串（向后兼容）。

#### 界面契约

`/schema` 的 `list.entry_kinds` 直接给出条目类型、名称、说明、
`needs_minutes` / `needs_task` / `blocks_list` 标志 ——
**前端不必自己维护一份映射**。

---

### 5.4.1 两个总开关与"两者关系"

> ★★ **S7 更新（2026-10-10）**: 本节原表里的 `timed_priority`【**已废弃**】、以及后来的
> `priority_mode` **三模式** —— **均已删除**。
> 现行做法: **执行顺序 ≡ `run_list`**; 「定时排前面 / 固定排前面」是
> `PUT /{script}/queue/sort` 的**一次性动作**; ★ **拖动永远自由**
> （**没有**任何跨类别拖动约束）。权威见
> [`scheduler-architecture.md`](scheduler-architecture.md) §2.3 / §3.3 与
> [`deprecated.md`](deprecated.md) §3.2。

| 字段 | 位置 | 作用 |
|---|---|---|
| `enable_fixed` | `Script.optimization` | **固定任务**总开关 |
| `enable_timed` | `Script.optimization` | **定时任务**总开关 |
| `timed_priority`【**已废弃**】【**已并入 `priority_mode`**; 而后者**也已在 S7 删除**】 | `Script.optimization` | 定时任务到点时怎么跟固定任务抢 |
| `rest_interleave` | `Script.optimization` | 休息期间能否**穿插**定时任务 |

★ **两个总开关互不影响** —— 关掉固定任务不该影响定时任务，反之亦然。
判定用 `timed_schedule.should_consider(category, enable_fixed, enable_timed)`。

#### `timed_priority`【**已废弃**】【**S7 后连它的替代物也删了**】

| 取值 | 界面名 | 行为 | ★ S7 现状 |
|---|---|---|---|
| `timed` | **定时优先** | 固定任务在跑、定时任务到点 → **打完当前这场战斗**就让位 | ❌ 字段不再影响行为 |
| `list` | **列表优先** | 定时任务等固定任务跑完 | ❌ 同上 |

★ **现在该怎么做**: 想让"定时全跑完再跑固定"—— 点一次界面上
  **「定时排前面」**按钮（`PUT /{script}/queue/sort` body `{"by":"timed"}`）,
  它把 timed 条目**物理挪到 `run_list` 前面**; ★ **不是**设置一个模式。
★ 插队时机是**战斗边界**，不是立即打断 ——
与「暂停调度」用同一个安全点（立即打断会卡在半途）。

#### `rest_interleave`（休息时穿插）

判据（用户确认）：

    定时任务的**预期完成时间** < 休息剩余时间  →  允许穿插

**目的**：保护**组队任务**。休息期间在庭院干等，会让组队很难凑齐人；
能塞进去就把空等的时间利用起来。

★ `expected_minutes == 0`（未配）算"**不能**穿插" ——
拿未知值去比会得出错误结论，宁可少穿插。

字段：`Scheduler.expected_minutes`（每个定时任务自己的预期耗时，分钟）。

#### 定时任务内部排序（`timed_schedule.timed_sort_key`）

优先级从高到低：

1. **能否跑**（不在 window 内的排最后）
2. **到点程度**（`next_run` 越早越先）
3. **窗口快关的优先**（`window_end` 近的先跑 —— 错过就没了）
4. **预计耗时短的优先**（减少"跑到一半窗口关了"）
5. **用户自定义优先级**（`scheduler.priority`，小的先跑）

★ 这个顺序是**刻意**标定的：**时间约束比"预计耗时"重要** ——
窗口关了就是彻底做不了，而耗时只影响效率。

---

### 5.5 次数：**统一到一个入口**

#### 改造前的"双轨"（坏的）

| 来源 | 位置 | 问题 |
|---|---|---|
| `scheduler.target` | 界面上的"次数"输入框 | **全仓无人读取** —— 空壳 |
| `limit_count` 等 | 各任务配置里 | 界面**改不到**；且字段名有别名 |

于是"设置次数"这个功能实际上是坏的：**改了界面上的次数，什么都不会发生**。

字段名还不统一：

| 任务 | 实际字段 |
|---|---|
| 多数 | `limit_count` |
| `Exploration` | `minions_cnt` |
| `Hyakkiyakou` | `hya_limit_count` |
| `RealmRaid` | `number_attack` |

#### 改造后：`BaseTask.effective_target()`

```python
def effective_target(self) -> int | None:
    # 1) scheduler.target > 0  ->  用它（用户编排，优先级最高）
    # 2) 否则                  ->  任务配置里的值（能力默认）
    # 3) 再否则                ->  meta.py 的 count_default
```

`TaskMeta.count_field_effective` 负责把**别名统一**成 `limit_count`，
所以上层（API / 界面 / 调度器）只需认一个名字。

#### `bind_counter()` 现在做两件事

```python
self.bind_counter()          # ① 从磁盘恢复 current_count
                             # ② 设定 self.limit_count = effective_target()
```

★ **这是"次数统一"的关键** —— 任务里只调一行，不必再自己读配置。

#### ★ 顺带修掉的"计数不落盘"

`commit_count()` 在**没调过 `bind_counter()` 时是空操作**
（`_counter_task` 是 `None`）。而改造前有 12 个可计数任务**从不 bind**：

* 它们只读 `current_count`，递增发生在通用战斗类里
* 于是计数**既不落盘、也不从磁盘恢复**
* 表现：进程重启后从头再打，**永远打不满 N**

`FallenSun` 早就修了（它是唯一 bind 的），其余 11 个这次一并接上。

#### ★ 哪些任务**不能**用 `bind_counter()`

| 任务 | 原因 |
|---|---|
| `BondlingFairyland` | handoff 双人模式**分两段**（一人打一半，`//= 2`），下半场要**从 0 重新计数**。套 `bind_counter()` 会把上半场的计数带进来 |

这类任务用 `effective_target()` 只统一"上限从哪来"，保留自己的清零。

#### 防回归

`tests/tasks/test_count_wiring.py` **读源码**检查：

* 每个可计数任务都必须出现 `bind_counter()` 或 `effective_target()`
* 不允许无条件 `self.current_count = 0`（除非在白名单里**并写明原因**）

★ 这条守卫写完后**立刻抓到一个我漏掉的任务**（`SixRealms`）——
说明"靠人肉盘点"不可靠，必须让机器盯着。

#### 引导式约定

| 场景 | 该用 |
|---|---|
| 单段任务（多数） | `self.bind_counter()` |
| 分段计数（handoff 等） | `self.limit_count = self.effective_target() or 0` |
| 只是想读一次上限 | `self.effective_target()` |

---

### 5.6 运行记录与归档（**重置 ≠ 删除**）

#### 为什么需要

用户明确要求两件事：

1. **任务记录必须落盘** —— "即使进程停止也能继续恢复"
2. **「重置」不是清除，而是归档后重开** ——
   "这样后续可以分析运行记录和展示运行结果，如御魂战斗多少次，
    消耗多少体力，花了多少时间等等"

★ 用户确认**先只要"次数 + 耗时"**（体力以后再考虑）。

#### 与 `task_state` 的分工

| 模块 | 存什么 | 用途 |
|---|---|---|
| `task_state` | 计数、周期完成记忆、存量/充能 | **调度决策**（要不要跑、还能跑几次）|
| `run_record` | 每轮的**次数 + 耗时** + 归档 | **统计与展示** |

★ 都是落盘、都按 `(账号, 任务)` 隔离，但**职责不同** ——
把"报表"塞进 `task_state` 会让那个文件既管决策又管统计。

#### 数据模型

```json
{
  "<账号>": {
    "<task>": {
      "current": {"started_at": "...", "updated_at": "...",
                  "runs": 12, "seconds": 345},
      "archive": [
        {"started_at": "...", "updated_at": "...", "archived_at": "...",
         "runs": 30, "seconds": 900}
      ]
    }
  }
}
```

* 文件：`log/.run_record.json`（与 `.task_state.json` 同级）
* 键**归一化为小写** —— `Orochi` / `orochi` 落到同一条记录

#### ★ `reset()` = 归档后重开

1. 把 `current` 追加到 `archive`（**只增不改**）
2. 把 `current` 清零（重开一轮）

两条刻意的规则：

| 规则 | 理由 |
|---|---|
| `runs == 0` 的当前记录**不归档** | 否则误点重置会留一堆空条目 |
| 从没记录过的任务 `reset` **什么都不做** | `reset` 不该凭空造记录（那是 `finish` 的职责）|

#### 落盘方式：原子替换

写入用 **临时文件 + `os.replace`** ——
直接写的话，写到一半进程被杀会留下**半截 JSON**，下次读取全丢。
`os.replace` 在同一分区上是原子的。

#### 记录点在**框架层**

`Script._record_task_run()` 包住任务的 `run()`：

```python
runs_before = self._task_runs_snapshot(task_obj)
started = datetime.now()
try:
    task_obj.run()
finally:
    self._record_task_run(task_obj, command, started, runs_before)
```

★ **放在 `finally` 里** —— OAS 的任务正常结束时是 `raise TaskEnd`（不是
`return`），若把记录写在 `except TaskEnd` 之后，**正常结束就全丢了**。
`finally` 同时覆盖"正常结束"与"中途崩了"两条路径。

★ **放在框架层而不是 54 个任务里** —— 逐个改既容易漏，又会让"统计"
散落各处。包一层，所有任务自动获得。

★ 统计失败**绝不能影响任务** —— 全部异常吞掉并记 warning。
记录只是报表，跑任务才是正事。

#### 接口

| 端点 | 作用 |
|---|---|
| `GET /{script}/run_record` | 全部任务汇总（不传 `task`）或单个任务（含归档）|
| `GET /{script}/run_record/{task}/archive` | 该任务的归档明细 |
| `PUT /{script}/run_record/reset` | 「重置选中」：body 是任务名数组，**归档后重开** |

`/schema` 的 `list.run_record` 也带一份汇总 —— 让"进页面"只发一次请求。

---

### 5.7 「运行一次」—— 手动请求插队

#### 语义（用户确认）

> 点击后按照**点击先后顺序**，直接排在最高优先级
> （就是**跑完当前任务/战斗后**插队运行）

1. **所有任务**都能点（固定任务与定时任务都可以）
2. **按点击先后**排队
3. **跑完当前任务/战斗后**才插队 —— **不是立即打断**
4. 只跑**一次** —— 跑完就出队

#### 为什么用"队列"而不是布尔标记

用户要"按点击先后顺序"。若只记一个 `set`，多个任务同时被点就
**丢了顺序**。用 `[(ts, task)]` 列表天然有序。

#### ★ 队列在"派发点"消耗，不在"排序点"

`get_next()` 每轮会被调**多次**（等待 / 重试 / 暂停恢复都会重算）。
若在排序那一步就消耗队列，会出现"**点了 3 个只跑 1 个**"。

所以分两处：

| 位置 | 做什么 |
|---|---|
| `Config._order_by_manual_run()` | **只排序**（把手动请求的提到最前）|
| `Script._consume_manual_run()` | **出队**（在任务真正要跑时）|

#### 不与调度约束冲突

请求了但**不在 `pending` 里**的任务（还没到点 / 被禁用）会被**忽略** ——
不能因为用户点了就跳过调度约束。

调用链上，手动请求是在 `_order_by_timed_priority()`【**已删除**】 **之后**应用的 ——
所以"点了就最快跑"但"仍然是在可跑集合内"。

#### 与「重置选中」的区别（界面上是邻居）

| 按钮 | 做什么 | 影响历史 |
|---|---|---|
| **运行一次** | 排队立刻跑一次 | **不改**历史记录 |
| **重置选中** | 归档 + 重开（§5.6）| 当前计数清零，历史进归档 |

#### 接口

| 端点 | 作用 |
|---|---|
| `GET /{script}/manual_run` | 读队列（按点击顺序）|
| `PUT /{script}/manual_run` | 请求（body 是任务名数组，**按数组顺序**排队）|
| `DELETE /{script}/manual_run?task=X` | 取消一个（`task` 留空则清空）|

`/schema` 的 `list.manual_run` 也带一份摘要。

---

### 5.8 连续失败与冷却（**不再 `exit(1)`**）

#### 改造前的无限重启循环

`script.py` 原先的逻辑：

```python
self.failure_record[task] = failed     # Script 实例上的**内存**字典
if failed >= 3:
    logger.critical("Task `{task}` failed 3 or more times.")
    ...
    exit(1)                            # 整个子进程退出
```

`failure_record` **不在磁盘上**。进程一退出，服务器就重新拉起一个
（`module/server/script_process.py`），**新进程的计数是空的** —— 于是：

    失败 3 次 → exit → 重启 → 计数归零 → 又能失败 3 次 → 再重启 → …

**永远停不下来。**

#### 这是从真实日志读出来的

`log/2026-10-09_伴生树.txt`（7 小时）：

| 现象 | 计数 |
|---|---|
| `START` 块（进程重启）| **97 次** |
| `RyouToppa` 被派发 | **25 次**，一次都没打成（每 14 秒一轮）|
| `Duel` / `WantedQuests` 连续触发 | 各 20 次 |

#### 现在的做法

`module/config/failure_state.py`，落盘 `log/.failure_state.json`：

| 事件 | 行为 |
|---|---|
| 成功 | **清零**（含冷却）—— 完全恢复正常调度 |
| 失败 1、2 次 | 计数 +1，照常按 `failure_interval` 重试 |
| 失败到 **3** 次 | `CRITICAL` 日志 + **推送通知** + **冷却 1 小时** + **计数减半** |
| 冷却到期 | **允许再试**（不是永久拉黑）|
| 冷却中 | `update_scheduler()` **不入 pending** —— 不会被反复选中 |

★ **计数减半而不是清零**：清零等于又给满 3 次机会，持续故障会变成
"每 1 小时重启 3 次"的慢速循环；减半是**逐步升级**，同时不会
一次失败就永久放弃。

★ **为什么不用进程级手段**：「重启进程」是**用户可见且昂贵**的动作
（模拟器要重新连、界面要重开）。对一个**任务级**失败用进程级手段，
既不匹配也不安全。

★ `update_scheduler()` 里的冷却检查是**兜底** —— 即使 `task_delay()`
那一步失败（配置保存异常），也不会变成热循环。

#### 界面

| 端点 | 作用 |
|---|---|
| `GET /{script}/failure_state` | 哪些任务在冷却、还剩几分钟 |
| `DELETE /{script}/failure_state?task=X` | **清除失败 + 解除冷却** |

★ "清除失败"的用途：用户修好了问题（改配置 / 换素材）之后
**不想等 1 小时**，点一下就能立刻重试。

`/schema` 的 `list.failure_state` 也带一份。

#### 回归守卫

`tests/module/config/test_failure_state.py` 里有一组**源码级**断言：

* 失败分支**不再出现** `exit(1)` / `exit(-1)` / `sys.exit`
* 必须调用 `record_success` 与 `record_failure`
* 计数与冷却都**落盘**（跨重启不丢）
* 成功能清零、冷却到期能再试（**自愈**）

---

## 6. 运行控制

### 6.1 暂停（⏸）

**现状：没有暂停机制。** 唯一的"停止"是硬杀进程：

```python
# module/server/script_process.py:52
async def stop(self):
    self._process.terminate()          # ← SIGTERM
    self._process.join(timeout=0.7)
    if self._process.is_alive():
        self._process.kill()           # ← 0.7 秒后强杀
```

`script.py` 里 `stop_event` 的检查**被注释掉了**，且该变量从未赋值 ——
原作者想做但没做完。

**设计**（用户确认）：

| 控件 | 语义 |
|---|---|
| **⏸ 暂停调度** | **跑完当前这场战斗（到安全点）**后不再开新任务 |
| **⏭ 本轮跑完再停** | 本任务本轮跑完（把目标次数打满）再停 |
| **▶ 继续调度** | 恢复 |

**不提供「立即停」** —— 会卡在半途（战斗中/组队房间中），不安全。

**实现点（已实测）**：`run_general_battle()` 返回的那一刻 = 战斗、结算、领奖
全部完成 = **正是安全点**：

```python
# tasks/Component/GeneralBattle/general_battle.py 末尾
win = self.battle_wait(...)          # 含战斗中 + 结算 + 领奖

if self.requested_pause():           # ← 新增
    logger.info('收到暂停请求, 本场已结束, 回到安全点后停止调度')
    return win

return win
```

★ **只改这一处，所有走 `GeneralBattle` 的任务自动受益** ——
与此前 `commit_count()` 用的是同一手法（放在共享层，一次改动全体受益）。

### 6.2 休息 / 延后

见 §5.1。

---

## 7. 可演进性

四项关切与对应机制：

| 关切 | 机制 | 判据 |
|---|---|---|
| **新增任务** | 任务**自描述** | 调度器**零改动** |
| **维护任务** | 契约收窄 | 只影响该任务目录 |
| **前后端** | 单一 schema | 前端**不内置任务知识** |
| **跨平台** | 平台能力接口 | 调度核心**零平台依赖** |

### 7.1 新增任务：`tasks/<Name>/meta.py` 自描述

```
tasks/<Name>/
    meta.py          ★ 自描述(唯一的"注册"动作)
    config.py        用户可改的配置
    script_task.py   执行逻辑
    page.py          页面导航(可选)
    assets.py        素材(标注器生成)
```

```python
# tasks/NewActivity/meta.py
SPEC = TaskSpec(
    task='NewActivity',
    name_zh='新活动名',                    # ← i18n 从这里生成
    category=Category.LIMITED,
    resource=Resource(kind='window'),
    detection=ActivityDetection(probe='module.activities.new_activity.probe'),
    requires=(),
)
```

`task_catalog` 扫描 `tasks/*/meta.py` 自动汇总。未提供 `meta.py` 的任务
**自动降级**为 `Category.TIMED` + warning，**不崩**。

### 7.2 消除中心化注册

| 原本手改 | 改为 |
|---|---|
| `config_model.py` 57 行 import | **删除** —— 扫描 `tasks/*/config.py` 用 `create_model` 动态构造 |
| `config_model.py` 56 行字段 | **删除** —— 同上 |
| OAS `zh_CN.xml` | 由 `meta.py` 的 `name_zh` **生成** |
| OASX 两个 i18n 文件 | 由 `/schema` **运行时提供**，前端不内置 |

**已实测验证可行性**：

```
发现 54 个任务配置类
字段集合一致(无漏无多)            OK
create_model 成功                  OK
实例化 + config.model.<task> 访问  OK
嵌套模型已实例化                    OK
顶层键集合一致 (58 == 58)          OK
fallen_sun / scheduler 子键一致    OK
字段顺序                          差异(手写声明序 vs 字母序)
```

**唯一差异是字段顺序，而顺序不是契约**：JSON 对象无序、pydantic 按名取值；
且实测 `config_model.py` 自身**声明就不齐**（58 字段只有 56 处声明）。

### 7.3 维护既有任务的影响范围

| 变动 | 影响范围 | 调度器 |
|---|---|---|
| UI 改了（素材/ROI） | `tasks/<N>/assets.py` + 图片 | ❌ 不影响 |
| 执行逻辑改了 | `tasks/<N>/*.py` | ❌ 不影响 |
| 配置项增删 | `config.py` + i18n | ❌ 不影响（调度器只读 `target`/`enable`/`priority`） |
| 次数语义变了 | `tasks/<N>/meta.py` 的 `resource` | ✅ 仅此一处 |

### 7.4 跨平台

**改造前的状况**：平台判断已集中在设备层，但靠 `if IS_WINDOWS` 散点判断，
且有一处是**硬阻塞**：

```python
# module/device/emulator.py 顶层
import winreg        # ← Linux/macOS 上直接 ModuleNotFoundError
```

也就是说：在非 Windows 上，只要 import 到 `emulator` 模块就**崩**，
而不是"优雅地告诉用户这个功能不可用"。

**现在**：

```python
# module/device/capabilities.py —— 能力集中声明
class DeviceCapabilities(NamedTuple):
    window_message: bool = False      # 窗口消息点击/长按
    window_background: bool = False   # 窗口后台截图
    emulator_manage: bool = False     # 启动/关闭模拟器实例

def detect_capabilities() -> DeviceCapabilities:
    is_win = sys.platform == 'win32'
    return DeviceCapabilities(is_win, is_win, is_win)
```

改动清单：

| 位置 | 改动 |
|---|---|
| `emulator.py` | `winreg` 改为**可选导入**；真正需要时 `_require_winreg()` 抛**可读异常**而不是崩 |
| `control.py` / `screenshot.py` / `device.py` | `if IS_WINDOWS` → 读**能力** |
| `provider.py` | `DeviceProvider` **Protocol**（截图 / 点击 / 能力） |
| `app.py` | 启动时打印能力报告 |
| `GET /capabilities` | 前端据此**明确禁用**不可用的控件 |

#### ★ 一个实测后的**设计修正**（重要）

设计文档最初设想"任务声明所需能力，能力不足则禁用该任务"。**实测后推翻**：

> **没有任务真正需要这些能力。**

| 能力 | 真实情况 |
|---|---|
| `window_message` | 截图/点击有**多条路径**（ADB / uiautomator2 / minitouch / DroidCast / scrcpy / nemu_ipc），窗口消息只是其中一种**可选方式** |
| `window_background` | 同上 |
| `emulator_manage` | 只在"任务队列空 → 关闭模拟器"这类**运行策略**里用（`script.py`），不是任何单个任务的前提 |
| — | `Restart` 任务只是重启**游戏 app**（`app_stop`/`app_start`），与模拟器无关 |

因此能力是**全局可用性**，不是**任务前提**。
`TaskSpec.requires` 保留为**扩展点** —— 将来若真有任务强依赖某能力
（如"必须用窗口消息才能操作"），在那里声明即可。
**但现在不该假装已有这样的任务**，否则就是在声明不存在的约束。

有一条测试专门守住这个判断（`test_no_task_declares_requires`）：
若将来有人声明了 `requires`，测试会失败，**提醒他确认那是强依赖而非"有则更好"**。

#### 架构护栏（写成测试，破坏就红）

`tests/test_architecture_guard.py` 用 **AST 解析 import 关系**（比正则可靠，
不会误匹配注释与字符串），强制三条：

| # | 护栏 | 为什么 |
|---|---|---|
| 1 | **`module/config` 不得 import `module/device`** | 调度器必须能在**无设备**环境里被单测 —— 本项目大量调度测试正是这样跑的。一旦耦合，就会连带拉起 adbutils / cv2 / PySide6 |
| 2 | 任务不得直接 import 设备层内部模块 | 应经 `self.device` 门面，换后端时不会漏改 |
| 3 | `module/device` 下不得有散落的 `IS_WINDOWS` 分支 | 统一读能力。"**选平台实现**"是合法例外（如 `method/windows.py` 本身就是 Windows 版实现），已在 `ALLOWED` 里注明理由 |

★ 护栏**立刻抓到一处真实问题**：`tasks/Quiz/script_task.py` 有一个
**从未使用**的 `from module.device.screenshot import Screenshot`（死 import）。已删。

#### 7.4.1 非桌面平台：能做到什么程度

**先分清三种"跨平台"** —— 它们难度完全不同：

| 需求 | 现状 | 原因 |
|---|---|---|
| ① 后端跑在 **Linux/macOS**（连模拟器/真机）| ✅ **本来就能** | 只有 3 个**可选**能力是 Windows 专有；靠 ADB 截图/点击本来就跨平台 |
| ② **界面**跨平台（桌面/移动/网页）| ✅ **OASX 已做到** | Flutter 天然跨平台 |
| ③ 后端跑在**手机**上 | ❌ **不轻松** | **运行时问题**，不是设计问题 |

**③ 的障碍（按硬度排序）**：

| # | 障碍 | 能否靠改代码解决 |
|---|---|---|
| 1 | **Python + OpenCV + ONNX 在 Android 上没有轻量可行的运行时** | ❌ 平台能力问题。Chaquopy 能塞进去但要 +50~100MB 且慢 |
| 2 | **`tasks/` 有 49,002 行过程式代码** | ❌ 换语言 = 重写；只能"只移植常用几个任务" |
| 3 | 坐标硬编码 1280×720 | ✅ **已解决**（见下）|
| 4 | `module/config` 耦合设备层 | ✅ **已解决**（架构护栏测试守着）|
| 5 | iOS | ❌ **不可能**（不允许嵌入任意 Python 运行时，也无法注入输入）|

**坐标问题为何已解决**（实测，见 `docs/android-feasibility.md` §A）：

```
手机画面 = 模拟器画面 × 1.5 ，居中
    x_phone = 1.5 * x_emu + 210
    y_phone = 1.5 * y_emu
```

* **1.5** 恰好 = 高度比 `1080/720`
* **210** 恰好 = `(2340 − 1280×1.5) / 2 = 420 / 2`

即游戏把 16:9 画面**等比放大居中**，**没有重排 UI**。
所以 **1,935 条规则坐标 + 1,926 张模板图都不必重做** ——
只需在**设备层**加一层"裁剪 + 缩放"（截图）与"缩放 + 平移"（点击）。

★ 复算时注意顺序：反向是 `(x − 210) / 1.5`；
写成 `(x / 1.5) − 210` **是错的**（差 `210/1.5 = 140` px）。

**"轻松"的边界**：

| 能做到 | 做不到 |
|---|---|
| ✅ 加新任务（只写 `tasks/<New>/`）| ❌ 后端跑到手机上（运行时是硬门槛）|
| ✅ 换界面（消费 `/schema`）| ❌ 执行逻辑换语言（等于重写）|
| ✅ 跑在 Linux/macOS | ❌ 后端跑到 iOS |
| ✅ 换模拟器/真机（改 `serial`）| |
| ✅ 换 1280×720 之外的屏幕（一次变换）| |

★ **归根到底**：`module/config` 已经平台无关，任务**知识**也有了不依赖 Python
的出口（`meta.py` + `/schema`）。真要继续移植，**元数据层不用重写**，
只有那 49,002 行**执行逻辑**需要重写。

★★ **`tasks/`（49,002 行）是"资产"，但以代码形式存在** ——
这是"跨平台难"的**根本原因**。若将来要真跨平台，这一层必须变成**数据/DSL**，
而不是 Python 过程式代码。

### 7.5 加一个游戏活动的操作清单

```bash
# 1. 建目录 + meta.py
tasks/NewActivity/{meta.py, config.py, script_task.py, page.py, assets.py}

# 2. 素材标注（现有工具）
python dev_tools/assets_extract.py

# 3. 校验漏写
python dev_tools/gen_task_catalog.py --check

# 4. 完事 —— 调度器/配置模型/前端 schema/i18n 全部自动获得该任务
```

**验收判据：加一个活动只写 `tasks/<New>/`，零改动其它文件。**

### 7.6 任务分类（依据游戏机制）

| 类别 | 数量 | 判定 | 例 |
|---|---|---|---|
| `fixed` | 13 | 有"打满 N 次"语义 | 日轮之陨、八岐大蛇、觉醒副本、业原火、**探索**、**英杰试炼** |
| `charge` | 3 | 按存量、固定时刻补充 | 金币妖怪、经验妖怪、石距 |
| `toppa` | 2 | 结界突破的两个子分类 | 寮突破、个人突破 |
| `limited` | 8 | 隔一段时间才推出 | 当期爬塔、超鬼王、对弈竞猜、花车巡游、智力竞赛、猫咪铺子、灵染试炼、武道大会 |
| `timed` | 28 | 其余 | 地域鬼王、逢魔之时… |

★ 权威中文名来自 **OASX `lib/config/translation/i18n_cn.dart`**，
不在 OAS 里。可用 `python dev_tools/gen_task_catalog.py` 生成对照。

---

## 8. 游戏机制数据从哪来（调研方法论）

> 这一节是**给未来的我**写的。本轮为了查"逢魔之时的开放时段"，我在搜索上花了
> 大量时间却几乎一无所获，踩过的坑必须记下来，避免重复劳动。

### 8.1 核心教训：**不要把用户配置当游戏机制读**

这是本轮最贵的一个错误。

```python
# 我曾经的推理(错)
demon_encounter.success_interval = "00 01:00:00"
→ "逢魔之时每小时可以做一次"
```

**真相**：用户把 `success_interval` 设成 1 小时，是因为**软件无法保证在开放时段内
一定会打开该任务**，所以让它每小时醒来碰运气。这是**用户为了绕过软件限制而设的
轮询节奏**，不是游戏机制。

| 字段 | 实际含义 | 是不是游戏机制 |
|---|---|---|
| `success_interval` | 用户希望的轮询/冷却节奏 | ❌ **用户意图** |
| `charge_slots` / `charge_max`【**均已删**】 | 游戏内补充时刻与上限 | ✅ 是（现由**窗口**表达）|
| `limit_count` | 单次运行打几次 | ⚠️ 半是（用户可调） |
| `window`（新增） | 游戏开放时段 | ✅ 是 |

**规则：任何"游戏多久开放一次"的结论，必须来自游戏机制本身，不能从
`success_interval` 反推。** 若拿不准，就问用户或标注"未验证"。

### 8.2 本轮实测到的真实游戏时间（来自代码，可信）

代码里已经**藏着一部分**真实时间，以"定点运行"的形式存在（这是旧的绕过手段）：

| 任务 | 字段 | 值 |
|---|---|---|
| `AbyssShadows` 狭间暗域 | `custom_run_time_friday` / `_saturday` / `_sunday` | **19:00** |
| `DemonRetreat` 首领退治 | `custom_run_time` | **10:00** |
| `GuildBanquet` 寮宴会 | `run_time_1` / `run_time_2` | **19:00** |
| `Hunt` 狩猎战 | `kirin_time` / `netherworld_time` | **19:00** |
| `MemoryScrolls` 绘卷 | `next_exploration_time` | **7:00** |
| `MysteryShop` 神秘商店 | `time_of_mystery` | **0:00** |
| `RyouToppa` 寮突破 | `next_ryoutoppa_time` | **7:00** |

⚠️ 这些是**定点**，不等于**开放时段**。开放时段的上界/下界代码里没有。

用户告知的一条真实机制（可信）：**逢魔之时 每天 17:00–23:00**。

### 8.3 网络途径现状（实测于 2026-10-08）

| 途径 | 状态 | 说明 |
|---|---|---|
| **PowerShell `Invoke-WebRequest`** | ✅ **唯一稳定可用** | 走系统代理；**优先用它** |
| `web_fetch` 工具 | ⚠️ 时好时坏 | **自己解析 DNS**，不读系统设置。代理 fake-ip 模式下域名解析到 `198.18.x.x`（代理保留段），工具据此判定"非公网 IP"并拒绝。每次调用重新解析，所以偶尔能通 |
| `web_search` 工具 | ❌ HTTP 402 | 该工具走 DeepSeek Messages API，**账户余额不足**。与代理无关，关代理无用。修法：Settings → Plugins → Web search 改 endpoint，或设 `DEEPSEEK_SEARCH_BASE_URL` |
| Bing / Google / 百度 / 搜狗 / 360 / DuckDuckGo | ❌ | 全部反爬：中文切词错误、验证码、JS 重定向、403。Bing 会把「阴阳师」切成「阴阳」，返回哲学内容 |
| **bilibili 阴阳师 wiki** | ✅ 可达但**只有剧情** | `wiki.biligame.com/yys/` —— 500+ 页面全是剧情/角色，`含'玩法'`、`含'逢魔'` 均为空。**没有玩法时间表** |
| `yys.huijiwiki.com` | ❌ 403 | |
| GitHub API（仓库搜索） | ✅ 可用 | 找同类项目；但**代码搜索需认证**（401） |
| GitHub raw | ✅ 可用 | 可直读文件 |

### 8.4 可用的抓取手法（供复用）

**基础连通性自检**：

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'
$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
function WJ($u) {
  try { return (Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 30 -Headers @{'User-Agent'=$ua}).Content }
  catch { return $null }
}
```

**HTML 转纯文本**：

```powershell
function ToText($h) {
  if (-not $h) { return '' }
  $t = [regex]::Replace($h, '(?is)<(script|style)[^>]*>.*?</\1>', ' ')
  $t = [regex]::Replace($t, '(?s)<[^>]+>', ' ')
  return ([regex]::Replace($t, '\s+', ' ')).Trim()
}
```

**MediaWiki API**（若目标站点是 wiki，比抓 HTML 可靠得多）：

```
# 搜索
https://<wiki>/api.php?action=query&format=json&list=search&srlimit=20&srsearch=<urlencoded>

# 列页面(注意 apprefix/allpages 在部分站点被禁用, 会返回空)
https://<wiki>/api.php?action=query&format=json&list=allpages&aplimit=500

# 取页面正文渲染后 HTML
https://<wiki>/api.php?action=parse&format=json&page=<urlencoded>&prop=text
```

**注意事项（都踩过）**：

1. **执行策略**：`.ps1` 文件被拦（`not digitally signed`）。直接内联命令，或
   `powershell -ExecutionPolicy Bypass -File x.ps1`。
2. **`pwsh` 不存在** —— 本机只有 Windows PowerShell 5.1，调用要用 `powershell`。
3. **Python 子进程调不通** —— `subprocess.run(['pwsh', ...])` 报
   `FileNotFoundError`，因为 `pwsh` 不在该 Python 的 PATH 里。
4. **`allpages` 可能返回空** —— 部分 wiki 禁用该接口（用 `srsearch` 替代）。
5. **`prop=extracts` 未安装**时返回 `Unrecognized value for parameter "prop"`，
   改用 `action=parse&prop=text`。
6. **编码**：中文页面用 UTF-8 解码；若出现乱码试 `gbk`。

### 8.5 结论：数据来源的优先级

```
1. 用户直接告知                    ← 最权威, 优先问
2. 代码里已存在的真实字段(定点/时段)  ← 本轮已挖出 7 处
3. 其它同类开源脚本的常量            ← GitHub 仓库搜索 + raw 直读
4. 官方/wiki/攻略站                 ← 中文搜索基本被反爬, wiki 只有剧情
5. 自学习(ObservedWindow)           ← 兜底, 且能纠正以上任何一层的错误
```

★ **第 5 条是关键**：既然外部数据既难拿又可能过时，就让软件**从自己的运行记录里
推断**。这样任何一层的错误都能被发现并提示，而不是永久错下去。

---

## 9. 路线图

| # | 内容 | 状态 |
|---|---|---|
| 1 | `task_catalog` 任务元数据目录 | ✅ 已提交 `b004d6ed` |
| 2 | `Resource` + `RunState` + `next_available()` 纯函数核心 | ✅ 已提交 `90f803de` |
| 3 | **`AvailabilityWindow` 开放时段 + `ObservedWindow` 自学习** | ✅ 已提交（本步） |
| 4 | `Resource`【已删】分层（`Recharge`【已删】）+ 修正误分类 + `resource_specs.json` | ✅ 已提交（★ 后被 S5 **删除**）|
| 5 | 开放时段接入用户配置（`Scheduler` 四个 `window_*` 字段 + `build_window()`） | ✅ 已提交 |
| 6 | 一次性迁移脚本 + `get_next()` 引入开放时段闸门 | ✅ 已提交 |
| 7 | 任务自描述 `tasks/<Name>/meta.py`（54 个已生成 + 自动发现） | ✅ 已提交 |
| 8 | `config_model` 自动发现（替换 113 行手写声明） | ✅ 已提交 |
| 9 | i18n 从 `meta.py` 生成（修 39 处漂移）+ `/schema` 接口 | ✅ 已提交 |
| 10 | 休息 / 延后 / 暂停 | ⬜ 下一步 |
| 11 | 任务列表（`list_pos` / `mode`） | ⬜ |
| 12 | `GET /{script}/schema` + `/overview` + `/capabilities` | ✅ 已提交 |
| 13 | `DeviceProvider` 契约 + 平台能力集中化 + 架构护栏 | ✅ 已提交 |
| 14 | OASX 前端页面（含开放时段配置 + 自学习提示） | ⬜ |

### 待修 bug（独立于上述路线图）

| 项 | 说明 |
|---|---|
| **完成记忆从未生效** | 所有任务 `period=none`；真实周期由 `success_interval` 控制 |
| **`WantedQuests` 硬编码 30** | 用户无法配置次数 |
| 4 处字段不统一 | `Exploration.minions_cnt` / `Hyakkiyakou.hya_limit_count` / `RealmRaid.number_attack` / 上述硬编码 |

★ **第 2-4 步是安全支点**：新核心以**纯函数 + 单测**独立写完，不碰现有代码。
即使后续切换出问题，回退成本是"把 `get_next()` 指回旧实现"，
而不是"拆掉半新半旧的东西"。

### 用户配置面的变化（第 4 步后）

| | 字段 |
|---|---|
| 旧（10 个） | `enable` `next_run` `priority` `success_interval` `failure_interval` `server_update` `delay_date` `float_time` `period` `reset_at` |
| 新（3 个） | `enable` `priority` **`target`** |

`failure_interval` → 重命名 **`retry_interval`**（它是"失败后多久重试"的退避，
与资源无关，原名会误导）。

---

## 10. 决策台账

> 每条都记录了出处。**实施前逐条核对，避免"用户答过我又问一遍"。**
> 建立起因：曾漏记用户「好的，A就行」，之后反复把它当待确认项重复询问。

### 10.1 暂停 / 运行控制

| # | 决定 | 状态 |
|---|---|---|
| 1.1 | `⏸` = 跑完当前这场战斗（安全点）后不再开新任务 | ✅ |
| 1.2 | ~~要第二个按钮 `⏭ 本轮跑完再停`~~ **已作废** —— 用户第二轮实测后要求去掉。后端 `pause_mode=round` 能力保留, 界面不再暴露入口 | ❌ 作废 |
| 1.3 | **不提供**「立即停」（不安全） | ✅ |
| 1.4 | 这是**新功能**（现有只有 `terminate()` 硬杀） | ✅ 事实 |

### 10.2 界面职责

| # | 决定 | 状态 |
|---|---|---|
| 2.1 | 总览页 = **监控面板**，去掉每行启停开关 | ✅ |
| 2.2 | 改为**批量操作条** + 搜索 + 过滤 | ✅ |
| 2.3 | 任务级 `enable` 禁用时列表行显示 `⚠ 配置中已停用` | ✅ |

### 10.3 任务列表

| # | 决定 | 状态 |
|---|---|---|
| 3.1 | 任务列表**只是一个调度器**（`Scheduler.mode` 取值） | ✅ |
| 3.2 | 列表行开关 = **唯一**启停入口 | ✅ |
| 3.3 | 原 `Filter`/`FIFO`/`Priority` 保留为 `timer_first` 下的细化排序 | ✅ |
| 3.4 | 不在列表里的任务排到最后（不丢弃） | ✅ |
| 3.5 | 每行次数 `0`=用默认，`>0`=本次覆盖 | ✅ |
| 3.6 | 列表存在 `Script` 全局配置的 `task_list` 分组 | ✅ |
| 3.7 | ~~`priority_mode` 默认「定时优先」~~ ★ **S7 已删除该字段**（排序改为一次性动作 `PUT /{script}/queue/sort`） | ❌ 作废 |

### 10.4 休息 / 延后

| # | 决定 | 状态 |
|---|---|---|
| 4.1 | 删除「休息作用范围」概念（v1 的多余设计） | ✅ |
| 4.2 | 改为**两个独立条目类型**：休息（全停）+ 延后（只缓列表） | ✅ |

### 10.5 次数字段

| # | 决定 | 状态 |
|---|---|---|
| 5.1 | 字段不统一的**要改为统一字段** | ✅ |
| 5.2 | 待统一：`Exploration` / `Hyakkiyakou` / `RealmRaid` / `WantedQuests` | ✅ 已列出 |
| 5.3 | 旧配置用一次性迁移脚本，**脚本用完即删** | ✅ |

### 10.6 任务分类

| # | 决定 | 状态 |
|---|---|---|
| 6.1 | 次数**只针对固定任务**，不含金币/经验妖怪/石距 | ✅ |
| 6.2 | **探索是固定任务**（字段 `minions_cnt`） | ✅ |
| 6.3 | **英杰试炼 = HeroTest，是固定任务** | ✅ |
| 6.4 | 寮突破 + 个人突破 = **结界突破的两个子分类** | ✅ |
| 6.5 | **限时活动**独立一类（8 个） | ✅ |
| 6.6 | `AbyssShadows` = **狭间暗域** | ✅ |
| 6.7 | 中文名以 **OASX i18n 为权威**，54/54 已解析 | ✅ |
| 6.8 | `FallenSun` = **日轮之陨**（非"日轮之城"） | ✅ 已修 `d9053699` |

### 10.7 调度器重设计

> ★★ **本节曾大面积虚报**。2026-10-10 逐条实测后修正, 证据见 `docs/SESSION-LEDGER.md`。
> 教训: 标 ✅ 前必须有**可复现的证据**（命令输出 / 文件行号）, 不许凭印象。

| # | 决定 | 状态 | 实测证据（2026-10-10）|
|---|---|---|---|
| 7.1 | **删字段**：`success_interval` / `charge_*` / `next_run` 不再是**配置项** | ✅ **已达成（方式: 从界面隐藏, 非从模型删除）** | `Scheduler` 模型仍有 16 个字段（`task_delay` 要落盘 `next_run`、`_skip_by_period` 要读 `period`/`reset_at` —— 删了会崩）; 但 `merge_value` 按 `json_schema_extra={'internal': True}` 过滤, **界面只剩 4 个**: `enable`/`priority`/`target`/`expected_minutes`。守卫: `tests/module/config/test_user_config_surface.py`（16 个测试）|
| 7.2 | 游戏知识只放 catalog，不在 54 个配置界面暴露 | ✅ | `TaskSpec` 承载 `category` / `auto_queue` / `window` / `resource`, 各任务自己的 `meta.py` |
| 7.3 | `failure_interval` → `retry_interval` | ✅ **已完成（带向后兼容别名）** | 字段改名, 且加 `validation_alias=AliasChoices(...)` —— 因为 `Scheduler.model_config = {}` 让 pydantic v2 **默认 `extra='ignore'`**, 实测给改名后的模型传**旧键不报错也不生效**, 会让**磁盘上 54 个配置里的该字段静默失效**; 而 **8 个任务覆盖了它**（`KekkaiActivation` 10 小时等）—— 丢失后重试节奏会悄悄变默认 1 天。**不设** `serialization_alias`, 于是写盘用新名, 旧配置首次 `save()` 后**自然迁移**。实测 `kekkai_activation.retry_interval = 10:00:00` 保住 |
| 7.4 | **删除**曾提的 `scheduler_v2` 开关（技术债） | ✅ | `config.py` / `config_scheduler.py` / `config_model.py` 里搜 `scheduler_v2` → **0 处**（本会话唯一一条原本就属实的）|
| 7.5 | 核心抽象只有 `Resource`【已删】+ `RunState`【已删】| 🔄 **部分（曾虚报）** | `resource.py`【已删】/ `scheduler_core.py`(291 行) 早已写好, 但**从没被调度器调用**（在 `config.py`/`script.py` 搜 `next_available\|Resource\|RunState` 得 **0 处**）。2026-10-10 已接线: `Config._next_run_from_resource()` 调 `next_available()`; 守卫 `test_task_window.py::TestResourceWiring`。**但 `next_run` 仍是落盘字段** —— 完全"纯函数化"未做 |
| 7.6 | 「次数」与「冷却」**解耦** | ✅ | 失败走 `failure_interval`（退避重试）, 与资源补充无关; `_next_run_from_resource()` 只处理成功路径 |
| 7.7 | 用户配置面 10 → 3 个字段 | ✅ **实际是 16 → 4** |
| **7.8** | `custom_next_run`（用户偏好时刻）| ⛔ **决策: 保留** —— 它与"开放时段"是**两个概念**（允许 vs 希望几点）。4 个调用点全部属于"用户配置的时刻"（`banquet_day_*` / `next_ryoutoppa_time` / 领体力时刻 / 跨任务排期）, 无法用固定 window 声明。详见 §13.1 | | 见 7.1 的证据。原计划"3 个", 实测需要 4 个（`enable`/`priority`/`target`/`expected_minutes`）|

### 10.8 架构与可演进性

| # | 决定 | 状态 |
|---|---|---|
| 8.1 | `config_model` 改为**自动发现**（已实测可行） | ✅ |
| 8.2 | 任务 `meta.py` **自描述** | ✅ |
| 8.3 | i18n **停止手写**，改为生成 / `/schema` 提供 | ✅ |
| 8.4 | 一次性脚本为 54 个任务批量生成 `meta.py` | ✅ |
| 8.5 | 验收判据：加活动**只写 `tasks/<New>/`** | ✅ |
| 8.6 | 调度器**不得 import 设备层**（写成护栏测试） | ✅ |
| 8.7 | 跨平台：`DeviceProvider` + `requires` 声明 + 优雅降级 | ✅ |
| 8.8 | 前端**不内置任务知识**，全部从 `/schema` 拉 | ✅ |

### 10.9 游戏机制数据与开放时段

| # | 决定 | 状态 | 出处 |
|---|---|---|---|
| 9.1 | **不要把用户配置当游戏机制读** —— `success_interval` 是用户轮询节奏，不是游戏机制 | ✅ | 用户：「逢魔不是每1小时，这个是我为了确保不会错过…所以我让他每1小时轮询下」 |
| 9.2 | 新增 **`AvailabilityWindow`** 概念：开放时段是**硬约束** | ✅ **已接线** | 类早已实现, 但**曾经默认全关且不参与 `next_run` 计算**（等于没生效）。2026-10-10 起: ①`Config._align_to_window()` 让 `next_run` **必须落在窗口内**; ②窗口按任务写在 `tasks/*/meta.py` 的 `TaskSpec.window`（7 个任务已落）。守卫: `test_task_window.py`（25 个测试）|
| 9.3 | 时段**不写死**, 但**来源改为任务 `meta.py`**（原: "全部由用户配置"）| ✅ **表述已修订** | 原表述让用户在 54 个界面各填一遍游戏机制 —— 实测**没人会填**: 54 个任务的 `window_enable` **全为 False**。现改为"游戏机制写在任务自己的 `meta.py`", 未声明 window 的任务仍为"不限时段", **既有行为不变**。★ 与原始表述的差异是**刻意的** |
| 9.4 | （原本空缺 —— 编号跳过）| — | — |
| 9.5 | **自学习**：记录实际跑通时刻反推时段，与配置比对后提示 | ⚠ **类已实现, 无调用者** | `ObservedWindow` 在 `availability.py` 里, 但全库**搜不到使用点** —— 台账曾标"✅ 已实现", 严格说只是"写好了"（**同类虚报**）|
| 9.6 | 逢魔之时真实机制 = **每天 17:00–23:00** | ✅ **已落进 `meta.py`** | 2026-10-10 加入 `DemonEncounter/meta.py` 的 `TaskSpec.window`; 依据是任务代码 `check_time()`（docstring 里写的 22:00 是**过时注释**）。实测 23:00 → 次日 17:00, 与代码一致 |
| 9.7 | 搜索方式与调研方法论写进文档（§8） | ✅ | 用户：「记得更新文档，包括搜索方式」 |

### 10.10 工程纪律

| # | 决定 | 状态 |
|---|---|---|
| 10.1 | `KeepLocalChanges: true` | ✅ 已做 |
| 10.2 | `AutoUpdate: false`（开发期） | ✅ 已做 |
| 10.3 | 不为兼容旧配置留双轨 / 兼容层 / feature flag | ✅ |
| **10.4** | **★ 不许"未完成却标记完成"** —— 任何 ✅ 都必须附**可复现的证据**（命令输出 / 文件行号）。状态只有 `⬜ 未开始` / `🔄 进行中` / `✅ 已完成（附证据）`, 不存在"大概做了" | ✅ **本条为最高纪律** |
| **10.5** | **不猜语义** —— 配置字段的语义从代码里看不出唯一答案时, **不做**, 并记录原因（例: 4-B 用 `custom_run_time_friday` 移动窗口, 实测把合法时刻推走 -> 退掉）| ✅ |
| **10.6** | **"删掉" ≠ "合并"** —— 用户说"合并"时, 先确认**保留什么**, 不许按"看起来更简洁"去删（用户原话: "你这次是直接删除了监控，而不是合并"）| ✅ |
| **10.7** | **剥注释再断言** —— 守卫测试若检查"某写法不存在", 必须先剥掉注释与 docstring, 否则"说明我改了什么"的注释会被误判（本会话踩过 4 次: `exit(1)` / `save_zh_cn(data)` / `putChineseTranslate()` / `_configured_start_times`）| ✅ |
| **10.8** | **单一数据源** —— 同一知识不许存在两处。已收敛的: 翻译（后端 `zh-CN.json` 权威, 前端只读）/ 时段（`meta.py` 的 `TaskSpec.window`）/ 队列成员（后端 `build_queue()`）/ 任务分类（`meta.py` 的 `auto_queue`）| ✅ |

---

## 2.1 ★★ 「三套机制 → 一套」—— 本会话彻查发现的核心问题 ★★

### 曾经并存的三套东西

2026-10-10 彻查发现, "任务什么时候跑"这件事在代码里有**三套互不相干的机制**:

| # | 机制 | 位置 | 当时状态 |
|---|---|---|---|
| **①** | `success_interval` / `failure_interval` / `next_run` / `charge_*` / `window_*` | `tasks/Component/config_scheduler.py` | ✅ **正在执行**（唯一真正生效的）|
| **②** | 任务代码里的**硬编码星期/时刻判断** | `tasks/*/script_task.py`（**22 处**）| ✅ **正在执行** |
| **③** | `Resource`【已删】/ `Recharge`【已删】/ `RunState`【已删】/ `next_available()`【已删】/ `AvailabilityWindow` | `module/config/{resource,scheduler_core,availability}.py` | ❌ **写好了但从没接进调度** |

**证据**（可复现）:

```bash
# ③ 完全没被调用 —— 搜遍调度核心得 0 处
grep -rn 'next_available\|Resource\|RunState\|scheduler_core' \   # ★ 这些符号【均已删】
     module/config/config.py script.py module/config/config_model.py
# -> 0 处

# ② 仍在跑
grep -rn 'custom_next_run' tasks/*/script_task.py
# -> 一度有 22 处
```

### 危害

1. **同一知识存在三处** —— 改一处不改另两处就出不一致（本项目已因"知识存在两处"栽过多次）
2. **文档与代码脱节** —— 台账 10.7 把 7.1/7.5/7.7 标成 ✅, 但代码里**一样都没做**
   （详见 `docs/SESSION-LEDGER.md` §0.2「文档虚报清单」）
3. `success_interval` 里**混进了用户意图**（"为了不错过而每小时轮询"）,
   任何拿它当游戏知识读的逻辑都会出错

### 收敛过程（2026-10）

| 步 | 做了什么 |
|---|---|
| **4-A** | 把散落在任务代码里的**开放时段**搬进各任务 `meta.py` 的 `TaskSpec.window`（支持**多段**, 如 Hunt 早晚两段）|
| **4-C** | `Config._align_to_window()`：`next_run` 算完后**必须落在窗口内**（不在则推到 `next_opening()`）—— 这就是用户要求的 K |
| **4-D** | `Config._next_run_from_resource()`：**接入机制 ③** —— 用 `Resource` + `RunState` + `next_available()` 算排期 |
| **4-E** | 机制 ① 的字段从**界面**移除（16 → 4）; 字段保留在模型里供内部读写 |
| **4-F** | 逐任务删除机制 ②（**进行中**, 见 §13）|

### 现在的单一来源

| 知识 | 唯一来源 |
|---|---|
| 什么时候**允许**跑 | `tasks/*/meta.py` 的 `TaskSpec.window` |
| **能跑几次** / 怎么补充 | `tasks/*/meta.py` 的 `TaskSpec.resource`（`Resource`）|
| **该不该自动进队列** | `tasks/*/meta.py` 的 `TaskSpec.auto_queue` |
| 现在能不能跑（动态）| `scheduler_core.next_available()`【**已删**】+ `Config._align_to_window()` |
| 用户配置面 | 只剩 `enable` / `priority` / `target` / `expected_minutes` |

---

## 12. 本会话（2026-10 改造）的决策

> 完整进度与**逐条证据**见 `docs/SESSION-LEDGER.md`（★ **历史台账** ——
> 第二轮复审修正: 它已**降级**, **不再**是"唯一事实来源"。
> 查**现状**请看 `docs/scheduler-architecture.md` / `docs/deprecated.md`）。

### 12.1 翻译

| # | 决定 | 状态 |
|---|---|---|
| 12.1.1 | 翻译**单一数据源** = 后端 `module/config/i18n/zh-CN.json`（973 → 1090 条）| ✅ |
| 12.1.2 | 前端**拉取**而非推送 —— 原来 OASX 启动 `PUT` 自己那 746 条**整份覆盖**后端 1090 条, **每次启动丢 344 条**（这才是"翻译永远补不齐"的真正根因）| ✅ |
| 12.1.3 | `PUT /home/chinese_translate` 改为**增量合并**; 整份替换另开 `/replace` | ✅ |
| 12.1.4 | **未命中不再静默**: `trOrRecord()` 记录 + `POST /home/missing_translate` 落 `log/missing_translate.txt` | ✅ |
| 12.1.5 | 枚举选项值也要翻译（`args_view` 对 enum 也走 `.tr`; 60 个枚举值从来没进过翻译表）| ✅ |

### 12.2 执行队列

| # | 决定 | 状态 |
|---|---|---|
| 12.2.1 | 四类: **正在运行**（第0行, 不可拖）/ **待运行**（可拖）/ **启用但不会运行**（只在【添加任务】）/ **未启用** | ✅ |
| 12.2.2 | **`auto_queue` 是任务类别属性**（`meta.py` 显式声明, 可覆盖）: `countable=False` → 自动进队列; `countable=True`（次数任务）→ 需手动添加。**54 个已落值**（40 自动 / 14 手动）| ✅ |
| 12.2.3 | 队列 = 用户编排（`run_list`）**+ 自动补齐**（追加在已编排之后, **不回写配置**）| ✅ |
| 12.2.4 | **移除队列 = 同时 `enable=false`** —— 否则自动任务会被 `build_queue()` 重新补回来（"移除"变成无效操作）| ✅ |
| 12.2.5 | 【添加任务】候选 = `enable && !auto_queue && !queued`（**走后端端点**, 前端不重复实现规则）| ✅ |
| 12.2.6 | 第 3 类**不堆在队列下面**（用户原话）—— 只给指引 + 「去添加」按钮 | ✅ |

### 12.3 汇报纪律

| # | 决定 | 状态 |
|---|---|---|
| 12.3.1 | **不许"未完成却标记完成"** —— 每个 ✅ 必须附可复现证据 | ✅ 见 §10.10 |
| 12.3.2 | 每步完成后**重新核对文档与代码事实** + 跑全量测试 + 汇报 | ✅ |
| 12.3.3 | 发现文档虚报时, **先修文档**并记录差在哪 | ✅ 见 §10.7 / §10.9 |

---

## 13. 进行中的工作（★ 未完成, 不许标 ✅）

### 13.1 4-F · 删任务内硬编码时段 —— **决策已定**

#### 已清理（3 个任务, 有等价性实测）

| 任务 | 证据 |
|---|---|
| `DemonRetreat` | 删 20 行 `weekday()` 判断 + 3 处 `custom_next_run`。**实测 4/4 场景等价**（周一/周三/周日 → 本周六 19:00; 周六成功 → 下周六）|
| `AbyssShadows` | 删 `today not in [4,5,6]` + 4 处。**实测 3/3 等价**（周五→周六 · 周六→周日 · **周日→下周五**）|
| `Hunt` | 删"太早/太晚"分支 + `plan_tomorrow_hunt` + `con_time`。**关键**: 窗口 23:00 结束 → 23:00 后不派发 → 原 `>23:00` 分支是**死代码** |

#### ★★ 决策: **保留** `BaseTask.custom_next_run()`, 不删 ★★

**理由（这是概念区分, 不是偷懒）**:

| 概念 | 回答的问题 | 载体 |
|---|---|---|
| **开放时段** | 什么时候**允许**跑 | `TaskSpec.window`（**游戏机制**）|
| **用户偏好时刻** | 我希望**几点**跑 | `next_ryoutoppa_time` 等（**用户配置**）|

两者**不是同一个概念**, 硬合并会**丢掉表达能力**。剩余 4 个调用点全部属于后者:

| 任务 | 处数 | 用途 | 为什么不能改成窗口 |
|---|---|---|---|
| `GuildBanquet` | 3 | 用**用户配置的 `banquet_day_1/_2`** 排下次宴会 | 周几是用户选的, 无法用固定的 `days=(...)` 声明 |
| `RyouToppa` | 2 | 用**用户配置的 `next_ryoutoppa_time`**（默认 07:00）| 时刻是用户选的 |
| `Restart` | 3 | 领体力时刻 `Time(12,0)` / `Time(20,0)` | 同上 |
| `MemoryScrolls` | 1 | 给**别的任务**（`Exploration`）排期 | 跨任务排期, 窗口表达不了 |

**为什么不给它们硬加窗口**: 试过评估, 但 `RyouToppa` 的 `limit_time` 字段
（`00:30`）**语义无法从代码唯一确定** —— 是"时长上限"还是"时刻"?
按 §10.5（**不猜语义**）: **不做会静默改变用户行为的改动**。

#### 诚实结论（写进台账, 不虚报）

目标④中「**彻底删除** `custom_next_run`」这一项 **⛔ 无法达成**, 原因是它承载的
"用户偏好时刻"是一个**独立且正当**的概念。已达成的是:

* ✅ 机制 ② 中**属于游戏机制**的部分已全部搬进 `meta.py`（3 个任务, 22 → 9~10 处）
* ✅ `next_run` 对齐窗口（4-C）, 保证不白跑
* ✅ `Resource`/`next_available` 接进调度（4-D）
* ⛔ `custom_next_run` 保留（**附上完整原因**）

★ 守卫 `tests/tasks/test_no_hardcoded_windows.py` 钉住**已清理的 3 个任务**不得回退。

### 13.2 其它未完成

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| 13.2.1 | 台账 9.6 逢魔之时时段落进 `meta.py` | ✅ **已完成** | `DemonEncounter/meta.py` 加 `window=AvailabilityWindow(True, 17:00, 23:00)`。依据是**任务代码** `check_time()`（`<17` 太早 / `>=23` 太晚）。<br>⚠ 该方法的 **docstring 写"17:00到22:00"是过时注释**, 代码实际用 23 —— **以代码为准**（已核对 L647/L653）。<br>实测: 17:00/18:00/22:00 不变; 16:00 → 当天 17:00; **23:00 → 次日 17:00**。带 window 的任务 **7 → 8**。守卫 `TestDemonEncounterWindow`（5 个）|
| 13.2.2 | 台账 7.3 `failure_interval → retry_interval` 重命名 | ✅ **已完成** | 用 `validation_alias` 读旧名 + 不设 `serialization_alias` 写新名 —— **不需要迁移任何配置文件**, 旧配置首次 `save()` 后自然迁移。影响面核查: 全库 25 处; `Function` **不读**该字段（只读 enable/next_run/priority/window）; 3 处任务代码读取（`Dokan`/`TrueOrochi`）已同步改名; 8 个任务的 `config.py` 覆盖点已同步 |
| 13.2.3 | 台账 9.5 `ObservedWindow` 自学习接进调用 | ⬜ | 类已实现（`availability.py`）, 全库无调用者。要接需要"记录每次成功时刻"的钩子, 属新功能 |
| 13.2.4 | `charge_*` 字段**真正删除**（现仅从界面隐藏）| ⬜ | 需先核实任务自己的存量簿记与 `Resource.recharge` 是否等价（**不能猜**）|
| 13.2.5 | 4-G 测试重写 | ⬜ | 预计 200-300 个既有测试需适配 |
| 13.2.6 | `next_run` 完全"纯函数化"（不再落盘）| ⬜ | 需要状态存储改造 |


---

## 11. 已修复的 bug

| 项 | 提交 | 核实依据 |
|---|---|---|
| OCR 关键词跨行误匹配（金币妖怪多开觉醒加成） | `7f947575` | `base_ocr.py` 含 `_match_across_lines` |
| `TeamUserStatus` 漏导入（组队不点开始挑战） | `e7e854e9` | `general_invite.py` 导入行含该名 |
| 战斗计数持久化 + 奖励弹窗卡住 | `6700e911` | `I_END_FIX_3` 出现 5 次（修复前 1 次） |
| 移除旧内置 PySide6 GUI | `7d980485` | `module/gui`、`gui.py` 均不存在 |
| `task_catalog` 任务元数据目录 | `b004d6ed` | 模块 + 数据文件齐备 |
| i18n `FallenSun` 修正 | `d9053699` | 两处均为 `日轮之陨` |
| OASX 乱码修复 + 假错误清理 | 本地 | 含 `ShellLinesController(encoding: utf8)` |

### 关键 bug 的根因记录（避免重犯）

| bug | 根因 | 教训 |
|---|---|---|
| 金币妖怪多开觉醒加成 | `filter()` 的"逐字符各找一行"回退把 3 行合并，`merge_area` 出一大片区域 | 匹配结果必须**连续** |
| 奖励弹窗卡住 | 只认 2 个模板（实有 3 个）+ 弹窗遮住奖励图导致误判"领完" | 退出条件不能依赖"看不见" |
| 组队不点开始挑战 | `general_invite.py` 用了 `TeamUserStatus` 却漏 import | 加 `symtable` 静态检查测试 |
| 完成记忆无效 | `period` 默认全为 `none`，真实周期在 `success_interval` | 加了功能要验证**真的生效** |
| 我丢失两个提交 | `AutoUpdate: true` + `KeepLocalChanges: false` → `git reset --hard` | 开发期必须关自动更新 |
| 把用户配置当游戏机制 | `success_interval=1h` 是用户轮询节奏，我读成"逢魔每小时一次" | **游戏机制不能从用户配置反推** |
| 窗口候选点枚举退化 | `next_opening` 在窗口内返回 `now`，枚举时反复得到同一时刻 | 枚举需要 `strict` 语义 |

---

## 附：相关文件

| 文件 | 内容 |
|---|---|
| `docs/team-coordination.md` | 跨账号组队协同详细设计（Availability Oracle） |
| `docs/android-feasibility.md` | **安卓端运行可行性**（含大狮 APK 逆向分析） |
| `docs/ui-api-mapping.md` | **界面设计 ↔ 后端接口对照表** |
| `docs/task-list-prototype.html` | 任务列表界面原型（可交互，设计稿） |
| `module/config/task_catalog.py` | 任务元数据（运行时） |
| `module/config/resource.py` | **`Resource` 资源规则**（interval / slots / window / period） |
| `module/config/availability.py` | **`AvailabilityWindow` 开放时段 + `ObservedWindow` 自学习** |
| ~~`module/config/scheduler_core.py`~~ | ★ **已删除**（S5: 死代码, 346 行）—— 见 [`deprecated.md`](deprecated.md) |
| `dev_tools/gen_task_catalog.py` | 元数据生成 / 校验（支持 `--dump-names`） |
| ~~`dev_tools/gen_resource_specs.py`~~ | ★ **已删除**（S5）—— 现在直接在各任务 `meta.py` 写 `period=` |
| ~~`tests/module/config/test_scheduler_core.py`~~ | ★ **已删除**（被测模块没了） |
| ~~`tests/module/config/test_availability.py`~~ | ★ **已删除**（全测 `scheduler_core.next_available()`） |
| `docs/scheduler-architecture.md` | ★ **调度域唯一权威**（窗口 / 队列 / 三优先级模式 / 不变量） |
| `docs/deprecated.md` | ★ **唯一废弃清单**（"某东西还在不在"查这里） |
| `module/config/run_control.py` | **暂停调度 / 本轮跑完再停 / 继续调度**（运行控制状态） |
| `module/config/run_list.py` | **运行列表 = 固定任务 + 休息**（`task` / `rest`） |
| `module/config/timed_schedule.py` | **固定/定时分开管理**：总开关、穿插判定、定时排序（纯函数） |
| `module/config/run_record.py` | **运行记录与归档**（次数 + 耗时；重置 = 归档后重开） |
| `module/config/failure_state.py` | **连续失败与冷却**（落盘；到阈值冷却而非退出进程） |
| `module/config/manual_run.py` | **「运行一次」队列**（按点击顺序插队，跑一次出队） |
| `module/device/capabilities.py` | **平台能力**集中声明（跨平台） |
| `module/server/schema_router.py` | **`/schema` `/overview` `/capabilities` `/run_control` 接口** |
| `tests/test_architecture_guard.py` | **架构护栏**（AST 强制分层，破坏就红） |
| `tests/tasks/test_count_wiring.py` | **次数接线护栏**（可计数任务必须走统一入口） |
| `tests/tasks/test_effective_target.py` | 次数的三级回落与别名适配 |
| `tests/module/config/test_run_record.py` | 运行记录/归档的语义（重置 ≠ 删除） |
| `tests/test_run_record_wiring.py` | 记录点必须在 `finally`（覆盖 TaskEnd 与异常） |
| `tests/module/config/test_failure_state.py` | 失败冷却语义 + **源码级断言"不再 exit(1)"** |
| `dev_tools/diag_android_layout.py` | 安卓布局诊断（求手机↔1280x720 坐标关系） |
| `dev_tools/gen_i18n.py` | 任务名从 `meta.py` 生成到各 i18n 副本 |
| `dev_tools/diag_dead_code.py` | 死代码扫描（只读诊断） |
