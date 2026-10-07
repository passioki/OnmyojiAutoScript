# 调度系统改进方案：任务完成记忆 + 组队协同

> 状态：**P1 与 P2 的基础部分已实现**（P3 组队协同见 `team-coordination.md`）
> 日期：2026-10-07
> 背景：从同类脚本（大狮）的使用习惯出发，解决 OAS 当前调度系统的两个痛点

## 实现进度

| 阶段 | 内容 | 状态 | 提交 |
|---|---|---|---|
| **P1** | 定时任务完成记忆（`period` / `reset_at`） | ✅ **已实现** | `c2e68769`、`c2e68769`→`6cad9da9`(i18n) |
| P2 | `required_count` + 任务上报（刷 N 次） | ⬜ 未实现 | — |
| P3 | 组队协同（同步点 / 两阶段调度） | ⬜ 见 `team-coordination.md` | — |
| P4 | 设置界面展示完成进度 | ⬜ 未实现 | — |

**P1 落地内容**（与本文件 §4.1/§4.2 的设计基本一致）：

- 新增 `module/config/task_state.py`：周期计算与状态持久化
- `Scheduler` 新增 `period: TaskPeriod = NONE`（none/daily/weekly）、
  `reset_at: Time = 05:00`
- `Config.task_delay()` 在 `success=True` 时记录"本周期已完成"
- `Config.update_scheduler()` 用 `_skip_by_period()` 跳过本周期已完成的任务，
  并把 `next_run` 推到下个周期起点
- 状态存 `log/.task_state.json`（可用环境变量 `OAS_TASK_STATE_FILE` 覆盖）
- 测试：`tests/module/config/test_task_state.py`（35 项）

**与初版设计的差异**：

1. 初版把 `period` 设计为 `TaskPeriod.NONE/DAILY/WEEKLY`——已按此实现；
2. 初版数据结构里 `period` 用大写字符串（`"DAILY"`），实际实现用小写枚举值
   （`"daily"`），与仓库既有枚举风格一致；
3. 初版把状态文件定位在 `log/.task_state.json`，已采用；
4. P2 的 `required_count` / 计数上报未实现——**仅 `period` 已能解决"每天/每周
   只做一次"的诉求**，而"刷满 N 次"是另一类需求，留待后续。

---

## 1. 需求来源

### 1.1 用户提出的两个痛点

**痛点一：组队任务无法对齐**

> 我打算今天完成 100 次御魂，需要和另一个模拟器里的角色组队完成。
> 现在的 OAS 很难保证组队任务在同时触发，就会出现一个账号在完成定时任务，
> 另一个账号已经在邀请了，这样组不上队伍。

**痛点二：定时任务没有完成记忆**

> 当前的每日、周定时任务似乎没有记忆功能，如完成后标记为已完成，
> 第二天/下一周记忆重置。当前要手动设置隔几天触发任务。

### 1.2 来自同类脚本的启发

大狮（早年流行的阴阳师脚本）把任务分成两类，这个二分法抓住了本质：

| 类型 | 含义 | 例子 | 调度依据 |
|---|---|---|---|
| **定时任务** | 到点就该做，且**每天/每周只做一次** | 每日签到、每周秘闻 | **周期**（做完就标记） |
| **固定任务** | "我今天想刷 N 次" | 御魂 ×100、组队刷本 | **完成条件**（刷够次数） |

OAS 目前**只有"间隔"这一个概念**，两类任务都用它凑合，因此各有不适。

### 1.3 用户对超时行为的初步想法

> 我初步的想法是，先跳过，等所有定时任务完成了再重试。
> 不过我觉得如果能协同上应该是挺优雅的，就是工作量大。

---

## 2. OAS 现状（已核实的代码事实）

### 2.1 调度器字段

`tasks/Component/config_scheduler.py`：

```python
class Scheduler(ConfigBase):
    enable: bool
    next_run: DateTime
    priority: int                     # 1~15, 数字越小优先级越高
    success_interval: TimeDelta       # 成功后 = 现在 + 该间隔
    failure_interval: TimeDelta       # 失败后 = 现在 + 该间隔
    server_update: Time               # 非默认值时, 强制执行时间
    delay_date: int                   # 配合 server_update, 几天后
    float_time: Time                  # 防封随机浮动
```

### 2.2 调度流程

`module/config/config.py`：

```
pending = [t for t in 已启用任务 if t.next_run < now]     # 到点了
pending = TaskScheduler.schedule(rule=schedule_rule, pending)
task = pending[0]                                          # 执行第一个
```

排序策略（`tasks/Script/config_optimization.py`）：

| 策略 | 含义 |
|---|---|
| `FILTER`（默认） | 按开发者设定的调度规则 |
| `FIFO` | 按 `next_run` 先后 |
| `PRIORITY` | 高优先级先执行，同级先来后到 |

### 2.3 现有的"半个记忆"机制

`server_update` 的中文说明（i18n）：

> 如果设定不是默认的 "09:00:00"，该任务每次执行完毕后会强制设定下次运行时间为
> 第二天的设定值

**它回答的是"下次什么时候跑"，不回答"今天到底做成没有"。**

因此：

- ✅ 对"每天固定跑一次"的任务够用（设 `server_update` + `success_interval=1天`）
- ❌ 对"刷满 100 次才算完成"的任务无效——即使只刷了 10 次就因故中断，
  它照样把下次运行推到明天
- ❌ 用户必须**手算间隔天数**来近似表达"每天/每周"

### 2.4 已有的跨实例机制（方向相反）

`module/config/instance_guard.py`（社区贡献）已接入 `script.py`：

> 确保**同一时间只有一个实例**操作模拟器。持有执行权的实例可执行任务，
> 其他实例排队等待。

开关：`script.optimization.queue_mode`（默认 `False`）

**这是"互斥"，用于避免多开时同时抢服务器资源；与组队所需的"同时协同"方向相反。**

### 2.5 结论

| 需求 | OAS 现状 |
|---|---|
| 定时任务的完成记忆 | ❌ 没有，只能用间隔近似 |
| 固定任务的完成条件（刷 N 次） | ⚠️ 各任务内部自行计数，与调度器无关 |
| 组队任务跨账号对齐 | ❌ 没有，只有反向的互斥排队 |

---

## 3. 设计目标与非目标

### 3.1 目标

- **G1** 定时任务具备完成记忆：完成后标记，到重置时间自动失效，不再需要手算间隔
- **G2** 固定任务能表达完成条件（如"刷 100 次"），并支持中断后继续
- **G3** 组队型固定任务能在多个账号间**对齐开始**
- **G4** 未对齐时有明确、可配的降级行为，**绝不卡死**
- **G5** 不破坏现有配置语义（老配置照常工作）

### 3.2 非目标

- 不做"完美同步"（帧级对齐）——OCR 识别本身有延迟，没必要
- 不改动各任务内部的玩法逻辑，只改**调度的"何时开始"**
- 不替代 `InstanceGuard`（互斥场景仍需要它）

---

## 4. 核心设计

### 4.1 概念模型：把任务分成两类

沿用大狮的二分法，但在配置层显式表达：

```python
class TaskKind(str, Enum):
    SCHEDULED = 'scheduled'   # 定时任务: 每周期做一次, 做完标记
    REPEAT = 'repeat'         # 固定任务: 做到满足完成条件为止
```

### 4.2 数据结构

**新增配置字段**（追加到 `Scheduler`，全部有默认值，保证向后兼容）：

```python
class Scheduler(ConfigBase):
    # ... 现有字段不变 ...

    # ---- G1: 完成记忆 ----
    kind: TaskKind = TaskKind.SCHEDULED
    period: TaskPeriod = TaskPeriod.NONE
    #   NONE     : 维持现状(用 next_run + success_interval)
    #   DAILY    : 本游戏日已成功 -> 不再入 pending; 跨日自动失效
    #   WEEKLY   : 本游戏周已成功 -> 不再入 pending; 跨周自动失效
    reset_at: Time = Time(hour=5)      # 游戏重置时间(默认 5:00)

    # ---- G2: 完成条件 ----
    required_count: int = 0            # >0 表示需要完成 N 次; 0 = 不限
    count_source: CountSource = CountSource.TASK_REPORT
    #   TASK_REPORT: 由任务自己上报本次完成了多少次(见 4.4)

    # ---- G3: 组队协同 ----
    team_sync: bool = False            # 该任务参与跨实例同步
    team_sync_group: str = 'default'   # 同步组名(哪几个账号一起)
    team_sync_timeout: int = 180       # 等待上限(秒)
    team_sync_fallback: TeamFallback = TeamFallback.DEFER
    #   DEFER   : 跳过, 排到定时任务之后再重试  (推荐, 见 4.5)
    #   SOLO    : 降级为单刷
    #   WAIT    : 继续等(有上限保护)
```

**新增持久化状态文件** `log/.task_state.json`：

```json
{
  "伴生树": {
    "WantedQuests": {
      "period": "DAILY",
      "last_success": "2026-10-07T05:12:33",
      "period_key": "2026-10-07",
      "streak_fail": 0
    },
    "MetaDemon": {
      "period": "NONE",
      "required_count": 100,
      "done_count": 37,
      "count_date": "2026-10-07",
      "last_update": "2026-10-07T21:40:02"
    }
  }
}
```

**为什么用文件而不是内存**：状态要跨进程（每个账号一个子进程）、跨重启（后端重启后
不能丢失当天进度）。仓库已有同类做法（`instance_guard` 用 `log/.queue_state.json`）。

**为"以后可能拆成两个 OAS 目录"预留**：状态文件路径可配
（`script.optimization.state_dir`），默认 `log/`。若状态落在同一目录，
两个 OAS 目录也能共享。

### 4.3 调度判断改造（G1 + G2）

现在：

```python
if func.next_run < now:
    pending.append(func)
```

改为：

```python
state = task_state.get(config_name, task_name)

# G1: 本周期已完成 -> 不入 pending, 直接把 next_run 推到下个周期
if func.period != NONE and state.is_completed_in_current_period():
    func.next_run = state.next_period_start()
    waiting.append(func)
    continue

# G2: 固定任务已刷够 -> 同样不再入 pending
if func.required_count and state.done_count >= func.required_count:
    func.next_run = state.next_period_start()   # 或按配置推到明天
    waiting.append(func)
    continue

if func.next_run < now:
    pending.append(func)
```

**关键点：周期边界用"游戏重置时间"计算，而不是自然日。**

```
period_key(DAILY)  = (now - reset_at) 的日期
period_key(WEEKLY) = (now - reset_at) 所在周的周一
```

举例（`reset_at = 05:00`）：

- 10-07 23:00 完成 → `period_key = 2026-10-07`
- 10-08 03:00 检查 → 仍是 `2026-10-07`（因为未过 5:00）→ 判定"本周期已完成"，跳过
- 10-08 05:01 检查 → `period_key = 2026-10-08` → 判定"新周期"，重新入队

**这就消除了"手算隔几天"的需求。**

### 4.4 完成次数上报（G2）

任务执行完一轮后向调度器上报：

```python
# tasks/base_task.py 或 script.py 的收尾处
self.report_task_progress(done=1)     # 或 done=N(如一次性刷了 N 次)
```

**为什么不复用 `next_run`**：`next_run` 只能表达"何时再跑"，而固定任务的语义是
"累计完成量"。中断后继续刷，必须知道**已经刷了多少**。

### 4.5 组队同步（G3 + G4）

#### 同步点协议

状态文件 `log/.team_sync.json`：

```json
{
  "default": {
    "task": "MetaDemon",
    "epoch": 3,
    "arrived": ["伴生树"],
    "expected": ["伴生树", "恋鸟树"],
    "ts": "2026-10-07T21:40:02"
  }
}
```

流程（每个参与者在**开始该任务之前**执行）：

```
1. 到达同步点: 把自己的名字写入 arrived
2. 若 arrived ⊇ expected  -> 双方放行, epoch += 1, 清除 arrived
3. 否则轮询等待, 直到:
     a) 条件满足          -> 放行
     b) 超过 team_sync_timeout -> 按 team_sync_fallback 处理
     c) 发现 epoch 已变   -> 说明别人已触发新一轮, 重新加入
```

#### 超时降级：用户提议的 DEFER（推荐）

用户的想法是"先跳过，等所有定时任务完成了再重试"。我建议把它形式化为**两阶段调度**：

```
阶段一（正常调度）
    所有任务按现有规则跑
    遇到 team_sync 任务 -> 尝试同步
        成功 -> 立即执行该组队任务
        超时 -> 标记 deferred, 跳过(不阻塞), 继续跑其他任务

阶段二（补偿调度）
    当 pending 队列只剩 deferred 的组队任务时
    -> 一次性把它们捞回来, 再次尝试同步
    -> 若仍失败: 按配置决定 (延迟 X 分钟重试 / 放弃并记录)
```

**为什么这个设计好**：

- **不阻塞**：组队任务失败不会卡住"签到、秘闻"这些本来能独立完成的事
- **有机会成功**：等定时任务都跑完，两个账号都空闲了，同步成功率最高
- **不会死循环**：阶段二有次数上限，超限就记录并放弃

```
时间线示例:
  21:00  A/B 都到点
  A: 悬赏封印(5min) -> 组队任务[尝试同步: B还没到] -> deferred, 继续
  B: 秘闻(8min)     -> 悬赏封印(4min) -> 组队任务[尝试同步: 双方都在] -> 成功!
  A: ...其他定时任务... -> 阶段二: 重试组队 -> 成功
```

#### 与 `InstanceGuard` 的关系

两者目的相反，必须互斥：

```python
if optimization.queue_mode and 存在 team_sync 任务:
    logger.warning('queue_mode(实例互斥) 与 team_sync(组队协同) 语义冲突: '
                   '互斥下两个账号不可能同时在游戏中, 组队任务无法完成')
    # 建议: queue_mode 生效时自动禁用 team_sync, 并明确提示
```

### 4.6 三种方案的取舍（供决策）

| 方案 | 机制 | 收益 | 成本 | 风险 |
|---|---|---|---|---|
| **B. 只调优先级** | 设 `schedule_rule=Priority`，组队任务同优先级 | **零代码改动** | 0 | 耗时差异会逐渐错位，治标 |
| **A. 同步点 + DEFER** | 本节设计 | 真正对齐；不阻塞 | **中**：新增状态文件 + 同步协议 + 两阶段调度 | 需处理超时/崩溃残留 |
| C. 主从驱动 | 一账号当"队长"统一发令 | 最严格 | 高 | 单点故障；改两大块 |

**我的建议：先做 B 验证问题严重程度，再做 A。**

理由：B 的配置改动只需几分钟。如果 B 就能让组队成功率可接受，那 A 的复杂度不值得；
如果 B 明显不够，A 的收益也能被量化验证。

---

## 5. 实施分期

| 阶段 | 内容 | 依赖 | 工作量估计 |
|---|---|---|---|
| **P0** | 试验方案 B（纯配置） | 无 | 分钟级 |
| **P1** | `log/.task_state.json` + `period` 完成记忆（G1） | 无 | 小 |
| **P2** | `required_count` + 任务上报（G2） | P1 的状态层 | 小 |
| **P3** | 同步点协议 + DEFER 两阶段调度（G3/G4） | P1 的状态层 | **中** |
| **P4** | 设置界面（OASX/内置 GUI 展示完成进度） | P1~P3 | 看 GUI 侧配合 |

**P1 与 P3 都有独立价值**，可以分开上线。若只做 P1+P2，痛点二就解决了。

---

## 6. 边界与风险

| 风险 | 处理 |
|---|---|
| 状态文件损坏 | 与 `instance_guard` 一致的策略：解析失败则告警并重置为空 |
| 进程崩溃残留 `arrived` | 加时间戳，超过阈值（如 10 分钟）视为过期并清理 |
| 用户手工改了系统时间 | `period_key` 由 `now` 计算，异常时降级为"不做周期判断"并告警 |
| 老配置兼容 | 新字段全部有默认值；`period=NONE` 时行为与现在**完全一致** |
| 两个 OAS 目录共享状态 | 状态目录可配；未配置时各自独立（行为退化为"不同步"，不会出错） |
| 组队任务数量少（用户反馈只有固定任务需要） | 阶段 P3 可按需实施，不做也不影响 P1/P2 |

---

## 7. 待评审的决策点

1. **是否先做 P0（纯配置试验）**，用真实数据判断 A 方案是否值得做？
2. **P1 的 `period` 语义**：`DAILY`/`WEEKLY` 是否够用？是否需要 `MONTHLY`（如神秘商店）？
3. **周期边界**：默认 `reset_at = 05:00` 是否符合你的游戏区服？（跨服可能不同）
4. **P3 超时降级**：默认用 `DEFER`（你的提议），确认吗？
5. **状态文件位置**：`log/` 下是否可以？还是希望放到 `config/` 旁边？
6. **实施顺序**：是否按 P1 -> P2 -> P3 逐个来，每步都可独立验证？
