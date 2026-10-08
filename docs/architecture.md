# OAS 架构与调度系统

> 状态：**设计已定稿，实施进行中**（详见 §8 路线图）
> 更新：2026-10-08
> 读者：后续维护者（包括未来的我）

本文档是 OAS 架构与调度系统的**单一入口**。合并自此前分散的多份设计稿：
`scheduler-redesign.md`（旧版）、`task-list-design.md`、
`architecture-evolvability.md`、`adding-new-activity.md`、`decision-log.md`。

**为什么要有这份文档**：此前的设计过程暴露出一个真实问题 —— 同一个概念
（"多久跑一次"）在代码里有四个载体（`success_interval` / `charge_slots` /
`charge_max` / `next_run`），而设计知识又散在五份文档里。**概念要收敛，文档也要收敛。**

---

## 0. 目录

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
| 1 | **一个概念只用一个词表达** | "多久跑一次"同时有 `success_interval`、`charge_slots`、`charge_max`、`next_run` |
| 2 | **知识只存在一处** | 金币妖怪"0/12 点补 2 次"散在 3 个配置字段 + 代码里 |
| 3 | **用户只看到他该管的** | 54 个任务暴露 `charge_max`/`charge_slots`/`success_interval`，用户只想改"打几次" |

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

`Resource` 把"补充方式"独立成分层的 `Recharge`，避免出现**自相矛盾的状态**。

```python
@dataclass(frozen=True)
class Recharge:
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
    recharge: Recharge = None
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
| `slots` | 固定时刻补充 | 金币妖怪：0/12 点各回满，上限 2 | `charge_slots`+`charge_max`+`charge_consume`+`success_interval` → **4 个** |
| `window` | 只在活动期 | 超鬼王：活动期内每天 1 次 | **无**（靠推远 `next_run` 假装不存在） |

★ `Resource(capacity=50, recharge=Recharge(period=DAILY))` **一个概念**即表达旧的
`success_interval=1d` + `limit_count=50`。

**从旧字段推导**（`Resource.from_legacy`，迁移桥梁，已实测正确）：

| 旧 `success_interval` | 推导结果 |
|---|---|
| `01 00:00:00`（1 天） | `Recharge(period=DAILY)` |
| `07 00:00:00`（7 天） | `Recharge(period=WEEKLY)` |
| `00 03:00:00`（3 小时） | `Recharge(kind='interval', interval=(0,3,0))` ← **不再是 period** |
| `03 00:00:00`（3 天） | `Recharge(kind='interval', interval=(3,0,0))` ← **不再是 period** |

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
│  L3  决策层  team_coordinator.py                      │
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

### 5.1 休息 vs 延后（两个条目类型，不是"作用范围"参数）

| 条目 | 语义 | 实现 |
|---|---|---|
| **休息** | 全局暂停 N 分钟（定时任务也不跑）—— 真休息 | `state.rest_until = now + N` |
| **延后** | 只推迟列表推进 N 分钟（定时任务照常） | `state.list_resume_at = now + N` |

★ 设计过程中曾错误地引入"休息作用范围(SELF/WHOLE_LIST)"参数 ——
**那是把"条目"和"动作"两个概念混在一起**。休息既然是列表里的一行，
就是"执行到它暂停"，不存在"推迟谁"的问题。改为两个条目类型后语义自明。

### 5.2 界面职责划分

| 页面 | 定位 | 能做什么 | 不能做什么 |
|---|---|---|---|
| **任务总览** | **监控面板** | 看状态/进度/下次运行<br>**批量**启停<br>调目标次数 | ❌ 单个任务的启停开关 |
| **任务列表** | **唯一调度控制台** | 排序、每行启停、每行次数、休息/延后<br>全局模式、▶/⏸ | — |

★ **理由**：`enable` 放两处必然出现"列表行开着却不跑"的静默矛盾。
所以只有一个开关（列表行），但**不隐藏**任务级状态 —— 行尾显示
`⚠ 配置中已停用`，点一下即可启用，**不会静默不跑**。

### 5.3 目标次数只对"固定任务"

| 类别 | 界面显示 |
|---|---|
| `fixed`（13）/ `toppa`（2） | ✅ 目标次数输入框 + 进度 |
| `charge`（3） | 存量 x/y（如 `0,12 点刷新`），**不设次数** |
| `limited`（8） | 活动期 / 非活动期 |
| `timed`（28） | 下次运行时间 |

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

**现状**：平台判断**已集中在设备层**，但靠 `if IS_WINDOWS` 散点判断：

```
module/device/env.py        IS_WINDOWS = sys.platform == 'win32'
module/device/emulator.py   import winreg            ← 硬依赖 Windows 注册表
module/device/control.py    'window_message': ... if IS_WINDOWS else None
module/device/device.py     if IS_WINDOWS and ...emulatorinfo_type == 'auto'
```

**设计**：

```python
class DeviceCapabilities(NamedTuple):
    window_message: bool      # 窗口消息点击(仅 Windows)
    emulator_manage: bool     # 启动/关闭模拟器(仅 Windows)
    registry_probe: bool      # 读注册表找模拟器路径(仅 Windows)

class DeviceProvider(Protocol):
    def screenshot(self): ...
    def click(self, x, y): ...
    def capabilities(self) -> DeviceCapabilities: ...
```

任务侧**声明所需能力**，框架启动时校验并给出可读的降级提示：

```python
SPEC = TaskSpec(..., requires=('emulator_manage',))
# 启动时: [Task] MuMuEmulator 需要 emulator_manage 能力,
#         当前平台(Linux)不支持, 已自动禁用
```

★ **关键约束：`module/config`（调度器所在层）不得 import 任何 `module/device`。**
写成**架构护栏测试**，防止以后有人图省事在调度器里直接读设备。

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
| `charge_slots` / `charge_max` | 游戏内补充时刻与上限 | ✅ 是 |
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
| 4 | `Resource` 分层（`Recharge`）+ 修正误分类 + `resource_specs.json` | ✅ 已提交 |
| 5 | 开放时段接入用户配置（`Scheduler` 四个 `window_*` 字段 + `build_window()`） | ✅ 已提交 |
| 6 | 一次性迁移脚本 + `get_next()` 引入开放时段闸门 | ✅ 已提交 |
| 7 | 任务自描述 `tasks/<Name>/meta.py`（54 个已生成 + 自动发现） | ✅ 已提交 |
| 8 | `config_model` 自动发现（删 113 行手写声明） | ⬜ 下一步 |
| 9 | i18n 改为生成 / `/schema` 提供 | ⬜ |
| 10 | 休息 / 延后 / 暂停 | ⬜ |
| 11 | 任务列表（`list_pos` / `mode`） | ⬜ |
| 12 | `GET /{script}/schema` + `/overview` | ⬜ |
| 13 | `StateProvider`（界面感知）+ `DeviceProvider` | ⬜ |
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
| 1.2 | 要第二个按钮 `⏭ 本轮跑完再停` | ✅ |
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
| 3.7 | `priority_mode` 默认「定时优先」 | ✅ |

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

| # | 决定 | 状态 |
|---|---|---|
| 7.1 | **删字段**：`success_interval` / `charge_*` / `next_run` 不再是配置项 | ✅ |
| 7.2 | 游戏知识只放 catalog，不在 54 个配置界面暴露 | ✅ |
| 7.3 | `failure_interval` → `retry_interval` | ✅ |
| 7.4 | **删除**曾提的 `scheduler_v2` 开关（技术债） | ✅ |
| 7.5 | 核心抽象只有 `Resource` + `RunState` | ✅ |
| 7.6 | 「次数」与「冷却」**解耦** | ✅ |
| 7.7 | 用户配置面 10 → 3 个字段 | ✅ |

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
| 9.2 | 新增 **`AvailabilityWindow`** 概念：开放时段是**硬约束** | ✅ 已实现 | 同上 |
| 9.3 | **不写死任何时段** —— 全部由用户配置；默认 `enabled=False`（不限时段），不改变既有行为 | ✅ 已实现 | 用户：「不要写死时间段」 |
| 9.4 | **全部开放出来** —— `start`/`end`/`days` 都是用户可配字段 | ✅ 已实现 | 用户：「都开放出来时间」 |
| 9.5 | **自学习**：记录实际跑通时刻反推时段，与配置比对后提示 | ✅ 已实现 | 用户：「自学习加用户可配置」 |
| 9.6 | 逢魔之时真实机制 = **每天 17:00–23:00** | ✅ 记录（**不写死**） | 用户告知 |
| 9.7 | 搜索方式与调研方法论写进文档（§8） | ✅ | 用户：「记得更新文档，包括搜索方式」 |

### 10.10 工程纪律

| # | 决定 | 状态 |
|---|---|---|
| 10.1 | `KeepLocalChanges: true` | ✅ 已做 |
| 10.2 | `AutoUpdate: false`（开发期） | ✅ 已做 |
| 10.3 | 不为兼容旧配置留双轨 / 兼容层 / feature flag | ✅ |

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
| `docs/task-list-prototype.html` | 任务列表界面原型（可交互） |
| `module/config/task_catalog.py` | 任务元数据（运行时） |
| `module/config/resource.py` | **`Resource` 资源规则**（interval / slots / window / period） |
| `module/config/availability.py` | **`AvailabilityWindow` 开放时段 + `ObservedWindow` 自学习** |
| `module/config/scheduler_core.py` | **`RunState` + `next_available()` 纯函数调度核心** |
| `dev_tools/gen_task_catalog.py` | 元数据生成 / 校验（支持 `--dump-names`） |
| `dev_tools/gen_resource_specs.py` | 为 54 个任务生成 `Resource` 定义 |
| `tests/module/config/test_scheduler_core.py` | 调度核心测试（57 项） |
| `tests/module/config/test_availability.py` | 开放时段与自学习测试（47 项） |
