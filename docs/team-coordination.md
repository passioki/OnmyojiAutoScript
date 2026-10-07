# 跨账号组队协同方案：状态感知的调度层协同

> 状态：**部分实现** —— §3.8 的"待转组队任务"已完成（提交 `5b677fea`）；
> §3（Availability Oracle 跨账号协同）**仍是设计稿，未实现**。
> 日期：2026-10-07
> v1 的偏差：v1 设计的是"两个账号到同步点互相等"（对称 rendezvous）。
> 用户澄清本意是"**两个账号互相知道对方在执行什么任务、处于什么阶段，据此合理分配谁来做组队这件事**"。
> 本版按此重写。

## 实现进度

| 部分 | 内容 | 状态 | 提交 |
|---|---|---|---|
| **§3.8** | **石距 / 经验妖怪 / 金币妖怪 支持组队**（队长/队员/单刷三态） | ✅ **已实现** | `5b677fea` |
| §3.1–3.6 | Availability Oracle：跨账号状态感知与智能分配 | ⬜ 未实现 | — |
| §4.3 | DEFER 两阶段调度 | ⬜ 未实现 | — |
| §5 | 组队任务登记表（`TeamTaskSpec`） | ⬜ 未实现 | — |

**§3.8 落地内容**：

- 在 `tasks/Component/GeneralInvite/config_invite.py` 新增共用枚举
  `TeamUserStatus`（ALONE / LEADER / MEMBER），历史上有 5 份复制的 `UserStatus`
  不再继续增加；
- 新增两个可复用方法（`general_invite.py`）：
  - `enter_room_and_fire(user_status, invite_config, random_wait, joiner_image)`
    —— 已在房内时按身份等待队友并点挑战（不含战斗流程）
  - `run_battle_by_accept(battle_config)` —— 队员身份自动接受邀请并完成战斗
- 三个任务的 `config.py` 增加 `user_status`（默认 ALONE）与 `invite_config`；
  `script_task.py` 的 `run()` 按身份分支，**ALONE 完整保留原有"开公开房等路人"
  行为**（向后兼容）；
- 测试：`tests/tasks/test_team_modes.py`（22 项）

**顺带核实（与 v2 正文中的更正记录一致）**：

- `Orochi`（八岐大蛇/御魂）确实使用 `GeneralInvite` 组队系统，
  v2 初版"御魂走迷之队"的说法是错的，已在 §5 更正；
- `run_invite()` **已具备反复邀请能力**（每约 20 秒重发一次，
  见 `general_invite.py` 的 `timer_invite` 分支，i18n 的 `wait_time_help`
  亦写明"期间每隔20s邀请一次"），v2 初版"反复邀请尚未实现"的说法是错的，
  已在 §3.7 更正；
- `Tako` 的 `check_zones('喷怒的石距')` **不是笔误**：
  `GeneralRoom.check_zones` 已同时接受 `'愤怒的石距'` 与 `'喷怒的石距'`
  并归一化为 OCR 实际读出的 `'价悠的石距'`，故未改动。

---

## 1. 需求

### 1.1 用户原话

> 我想请你帮忙设计下（组队任务难以同时触发的问题）。
> 我初步的想法是，先跳过，等所有定时任务完成了再重试。

> 我说的优雅协同是 OAS 判断两个账号当前执行的任务重是否有组队任务，
> **判断任务阶段并合理分配**。

> 其实只有"固定任务"（我想刷 N 次的那种）需要组队。

### 1.2 提炼

真正的诉求是**跨账号的状态感知 + 智能任务分配**：

- 两个账号**互相可见**对方当前在做什么任务、进度如何
- 调度器据此**动态决定**：谁先去做组队任务、另一个何时跟上
- 而不是简单"两边都在同一时刻卡在同一个点上等"

---

## 2. 现状（已核实的代码事实）

### 2.1 组队玩法的能力已经齐了

**共 7 个任务共用 `GeneralInvite` 组队系统**（实测全仓：`Orochi` / `FallenSun` /
`EvoZone` / `BondlingFairyland` / `OtherWorldTwilight` / `EternitySea` / `Exploration`），
其中 5 个具备完整的 `LEADER`/`MEMBER` + `wait_time` 流程。

| 能力 | 代码位置 | 说明 |
|---|---|---|
| 角色区分 | `UserStatus.LEADER/MEMBER/ALONE`（如 `tasks/Orochi/config.py`） | 谁是房主、谁是加入者 |
| **房主等待加入** | `InviteConfig.wait_time`（默认 **2 分钟**） | 房主开着房间等人，**不必同时到达** |
| 房间创建/维持 | `tasks/Component/GeneralRoom/general_room.py`（`create_room`/`ensure_private`/`ensure_public`/`exit_team`） | 11 个任务共用 |
| 房间类型 | `general_invite.py` `RoomType.NORMAL_2/3/5/ETERNITY_SEA` | 不同玩法房间规格 |
| 邀请指定好友 | `detect_select(name)` | 按名字邀请（即之前繁体字问题的位置） |
| 房主等待战斗 | `wait_battle(wait_time=...)` | 如 `tasks/Orochi/script_task.py` |

**结论：玩法层不缺东西。缺的是"调度层怎么配合"。**

### 2.2 调度层现状

```
module/config/config.py
    pending = [t for t in 已启用任务 if t.next_run < now]
    pending = TaskScheduler.schedule(rule=schedule_rule, pending)
    task = pending[0]
```

调度策略只有 `Filter` / `FIFO` / `Priority`，**全部是单账号视角，没有任何跨账号信息**。

### 2.3 任务是不可中断的原子单元

`script.py`：

```python
task_module.ScriptTask(config=self.config, device=self.device).run()
```

一次 `run()` 跑完整个任务（御魂 100 次就是一个任务从头跑到尾）。

**这是本方案最重要的约束：**
- ✅ **可以在任务边界调度**（决定下一个跑什么）
- ❌ **不能在任务中途抢占**（除非改每个任务的内部循环，工程量大且易错）

### 2.4 已有的跨实例机制（方向不同）

`module/config/instance_guard.py`：确保同一时间只有一个实例运行（`queue_mode`）。
**那是互斥，与本方案的协同目标相反**，需要互斥处理（见 §6）。

---

## 3. 核心设计：Availability Oracle

### 3.1 一句话概括

> 每个账号**发布自己的状态**（在做什么、快做完了吗、还有哪些组队任务待做）；
> 组队任务开始前先**查询对方状态**，据此决定：现在做，还是让给顺序更合适的账号做。

### 3.2 三层结构

```
┌──────────────────────────────────────────────────────┐
│  L3  决策层  team_coordinator.py                      │
│      读双方状态 -> 给出建议: START / WAIT / YIELD / DEFER │
├──────────────────────────────────────────────────────┤
│  L2  状态层  log/.team_state.json                     │
│      双方定期发布: 当前任务 / 阶段 / 队列 / 组队进度 / 心跳 │
├──────────────────────────────────────────────────────┤
│  L1  接入层  script.py 的任务边界 + 组队任务开始前         │
│      只在这两个位置调用, 不入侵任务内部                   │
└──────────────────────────────────────────────────────┘
```

### 3.3 共享状态文件

`log/.team_state.json`（沿用 `instance_guard` 用 `log/` 放状态文件的约定）：

```json
{
  "伴生树": {
    "heartbeat": "2026-10-07T21:40:02",
    "current_task": "Exploration",
    "task_started_at": "2026-10-07T21:33:10",
    "phase": "running",
    "expected_remaining_sec": 180,
    "queue": ["WantedQuests", "MetaDemon", "SoulsTidy"],
    "team_pending": {
      "MetaDemon": {"need": 100, "done": 37}
    },
    "at_boundary": false
  },
  "恋鸟树": {
    "heartbeat": "2026-10-07T21:40:05",
    "current_task": null,
    "phase": "idle",
    "expected_remaining_sec": 0,
    "queue": ["MetaDemon", "SoulsTidy"],
    "team_pending": {
      "MetaDemon": {"need": 100, "done": 0}
    },
    "at_boundary": true
  }
}
```

**字段含义**：

| 字段 | 用途 |
|---|---|
| `current_task` / `phase` | **"对方在做什么"** —— 你提的核心诉求 |
| `task_started_at` | 已运行多久 |
| `expected_remaining_sec` | **预计还要多久**（用历史耗时估算，见 3.5） |
| `queue` | 对方的待办任务，用于判断"谁更适合先做组队" |
| `team_pending` | **组队任务还差多少** —— 决定该轮到谁做 |
| `at_boundary` | **关键**：是否停在任务边界（只有此时才能"让位"） |

### 3.4 决策逻辑

组队任务开始前，询问协调器：

```python
action = coordinator.decide(task='MetaDemon', me='伴生树', peer='恋鸟树')
```

```
START  立即开始, 对方会配合
YIELD  让对方先做这件事, 我跳过 (对方更合适)
WAIT   先等一小会儿 (对方快结束了, 在 wait_time 窗口内)
DEFER  推迟到本轮定时任务之后 (对方还很久)
```

**决策规则（按优先级从上到下）**：

| # | 条件 | 决策 | 理由 |
|---|---|---|---|
| 1 | 对方不在线（心跳过期） | **START** | 不能等，按自己的能力做 |
| 2 | 对方 `at_boundary=true` 且对方组队进度落后 | **YIELD** | 让对方先赶上，避免一方刷满另一方还差很多 |
| 3 | 对方 `expected_remaining_sec` ≤ `wait_time` 窗口 | **WAIT** | 对方马上到边界，稍等即可组上 |
| 4 | 我方组队进度落后对方 | **START** | 我该补进度 |
| 5 | 其他 | **DEFER** | 排到本轮定时任务之后再试 |

**规则 2 和 4 是实现"合理分配"的关键**——让**进度落后的那一方优先发起**，
这样两个账号能自然收敛，而不是各自按顺序跑然后错位。

### 3.5 `expected_remaining_sec` 怎么来

**不能靠猜。** 用历史耗时统计：

在任务状态文件里累计每个任务的历史耗时（`log/.task_duration.json`）：

```json
{"Exploration": {"samples": 42, "p50_sec": 180, "p90_sec": 420}}
```

首次运行时没有样本 → `expected_remaining_sec = null`，决策规则 3 自动跳过
（退化为"不等待"），不会因为没数据而卡住。

> **副作用（正面）**：这份耗时统计本身对用户有用，可以回答"我这个任务一般跑多久"。

### 3.6 两台机器/两个 OAS 目录也能用

L2 状态层只依赖**一个文件**。因此：

| 部署方式 | 配置 |
|---|---|
| 同一 OAS，两账号（**你当前的方式**） | 默认 `log/`，天然共享 |
| 两个 OAS 目录 / 两台机器 | 配 `script.optimization.state_dir` 指向共享目录（网络盘亦可） |

**不额外增加复杂度**：未配置时各自独立，行为退化为"不协同"，不会出错。

---

### 3.7 游戏实际时序约束（用户实测提供）

以下数值是用户在游戏里实测的，**直接决定协同方案能否成立**：

| 参数 | 实测值 | 对设计的影响 |
|---|---|---|
| **房间等待上限** | **约 5 分钟** | 房主开房后可等 5 分钟，`wait_time` 应可调到 300s 级别 |
| **邀请发起** | **必须房主点邀请** | 成员不能自行申请加入 → 协同必须保证"邀请发出时成员在接收状态" |
| **邀请接受时限** | **约 10 秒** | ⚠️ **这是最紧的约束**。邀请发出后成员只有 ~10s 响应 |
| **邀请可否重发** | **可以反复邀请** | ✅ 这把 10s 的硬约束变成了"重试问题"，大幅降低难度 |

### 关键推论

**10 秒的接受时限 + 可反复邀请 = 房主应该"循环邀请 + 观察是否进来"，而不是"邀一次就等"。**

```
房主: 开房 → 循环 { 点邀请好友; 等 ~10s; 若成员未进 → 再邀一次 } 直到:
          a) 成员进入        -> 开始挑战
          b) 超过房间等待上限 (5min) -> 放弃, 退出房间
```

成员侧则只需**尽快到达邀请界面**。因此协同的**真正难点从"精确同步"降级为"让成员及时处于可接受邀请的状态"** ——
这正是 §3.4 决策规则要解决的：成员若还在跑长任务，房主就不该现在开房。

### 现有实现：反复邀请**已经具备**

`run_invite()` 的循环里已有重发逻辑（`general_invite.py:124-131`）：

```python
if self.timer_invite and self.timer_invite.reached():
    if is_first:
        logger.info('Invitation is triggered every 20s')
        self.timer_invite.reset()          # 每 20s 重发
    else:
        logger.info('Wait for 30s and invite again')
        self.timer_invite = None
    self.invite_friends(config)            # 重新邀请
```

**结论：房主每约 20 秒自动重新邀请一次，直到 `wait_time` 超时。**

这正好匹配用户实测的"可以反复邀请"。因此 **10 秒接受时限不再是硬约束** ——
单次邀请若错过，20 秒后会自动重发。**协同的难点进一步降级为"让成员尽快到达邀请界面"**，
而非精确的时间对齐。

> 更正记录：本节初稿曾写"`invite_friends` 只在 `is_first` 时调用一次，
> while 循环里没有重新邀请，反复邀请尚未实现"。该结论错误 —— 重申逻辑确实存在，
> 只是位于 `timer_invite` 分支内（`general_invite.py:124-131`）。
> 错误原因：只读了 `run_invite` 的前 60 行就下结论，未看到后面的循环分支。


---

### 3.8 待转为组队的任务（用户提出）

用户明确要求把以下任务的**组队模式**做出来（当前只能"开公开房等路人"）：

| 任务 | 中文名 | 现状 | 改动点 |
|---|---|---|---|
| `Tako` | 石距 / **愤怒的石距**（周末） | 已继承 `GeneralRoom`+`GeneralInvite`，`create_room`→`ensure_public`→等 60s 路人 | 接 `InviteConfig` + 邀请循环 |
| `ExperienceYoukai` | 经验妖怪 | 同上，等 50s 路人 | 同上 |
| `GoldYoukai` | 金币妖怪 | 同上，等 ~50s 路人 | 同上 |

**好消息：三者结构完全同构，且都已继承组队组件**，因此可以共用同一套改造模板，
无需各写一遍。改造要点：

1. `config.py` 增加 `invite_config: InviteConfig`（与 `Orochi` 等一致）
2. `run()` 中把"`ensure_public` + 等路人"改为按 `UserStatus` 分支：
   - `LEADER`：开房 → 循环邀请 → 等成员进入 → 挑战
   - `MEMBER`：等房主邀请 → 接受 → 挑战
3. 保留原有的"公开房等路人"作为 `ALONE` 模式（向后兼容，也便于没有队友时兜底）

> 注：`Tako` 的 `check_zones('喷怒的石距')` 中"喷"疑为"愤"的笔误，改造时一并核对。

---


## 4. 与现有机制的配合

### 4.1 复用 `wait_time`，不新造等待

房主开始组队任务后，**继续用现有的 `wait_battle(wait_time)`** 等对方加入。
本方案的贡献是**让房主在开始前就知道"等不等得到"**：

- 对方 `expected_remaining_sec` 在窗口内 → **WAIT**，然后照常开始并等待加入
- 对方还很久 → **DEFER**，不要白等 2 分钟又失败

**所以不是替代 `wait_time`，而是让 `wait_time` 用得值。**

### 4.2 与 `InstanceGuard` 的冲突处理

```python
if optimization.queue_mode and team_pending_exists:
    logger.warning(
        'queue_mode(实例互斥) 与组队协同语义冲突: 互斥下两账号不可能同时在游戏中, '
        '组队任务无法完成; 已临时跳过组队任务')
    # 建议: queue_mode=True 时组队任务不入 pending, 避免必然失败
```

### 4.3 复用"跳过 + 补偿"两阶段（用户的提议）

用户的初版想法仍然保留，作为 `DEFER` 的落地方式：

```
阶段一: 正常调度; DEFER 的组队任务暂存, 不阻塞其他任务
阶段二: pending 只剩 DEFER 的组队任务时 -> 捞回来重试
        仍失败 -> 按配置: 延迟重试 / 放弃并记录
```

**这样"优雅协同"与"不卡死"两者兼得**：能协同就协同（规则 2/3/4），
协不上就退化为顺序执行（DEFER + 阶段二）。

---

## 5. 需要声明的"组队任务登记表"

协同要能判断"哪些任务需要组队、配对关系是什么"。用一份**声明式登记**（而非散落在代码里）：

```python
# 建议位置: tasks/Component/GeneralInvite/team_registry.py
@dataclass
class TeamTaskSpec:
    task: str                 # 任务名, 如 'MetaDemon'
    role: TeamRole            # LEADER / MEMBER / EITHER
    wait_capable: bool        # 房主是否可等待加入(依赖 wait_time)
    max_wait_sec: int         # 等待上限(默认取 wait_time)
    peer: str                 # 配对的账号名
```

配置侧新增字段（追加到 `Scheduler`，有默认值，向后兼容）：

```python
team_sync: bool = False            # 该任务需要跨账号协同
team_peer: str = ''                # 配对账号名, 空=自动取另一个已启用账号
```

**为什么需要登记表**：组队玩法不止一个，且**并非全部同构**。实测全仓：
走 `GeneralInvite`（共用组队系统）的任务共 **7 个**，
用 `GeneralRoom`（房间创建/等待）的任务共 **11 个**：

| 任务 | 中文名 | LEADER/MEMBER | wait_time | create_room |
|---|---|---|---|---|
| `Orochi` | 八岐大蛇（御魂） | ✅ | ✅ | ✅ |
| `FallenSun` | 日轮之陨 | ✅ | ✅ | ✅ |
| `EvoZone` | 觉醒副本 | ✅ | ✅ | ✅ |
| `BondlingFairyland` | 契灵之境 | ✅ | ✅ | — |
| `OtherWorldTwilight` | 彼世逢魔 | ✅ | ✅ | ✅ |
| `EternitySea` | 永生之海 | — | ✅ | ✅ |
| `Exploration` | 探索 | — | — | — |

另有 `TrueOrochi` / `Tako` / `Nian` / `GoldYoukai` / `ExperienceYoukai` 等使用
`GeneralRoom`。**所以不能统一假设，必须逐个声明**角色的默认值、等待上限与配对关系。

> 更正记录：本文档初版曾写"御魂(Orochi)不走 GeneralInvite，用的是匹配/迷之队"。
> 该结论错误——`tasks/Orochi/config.py` 明确 `from ...config_invite import InviteConfig`，
> 且 `script_task.py` 有 `run_leader` / `run_member` / `create_room` / `wait_battle`。
> 错误原因是仅凭 grep 输出的前几行就下结论，未完整阅读配置文件。


---

## 6. 边界、风险与"不作恶"原则

| 风险 | 处理 |
|---|---|
| 状态文件损坏 | 与 `instance_guard` 一致：解析失败则告警并重置 |
| 进程崩溃残留状态 | 心跳超时（如 120s）视为离线 → 决策退化为 START |
| 对方时钟不同步 | 所有时间用各自本地时钟，比较用"相对时长"而非绝对时刻 |
| 无历史耗时样本 | `expected_remaining_sec = null` → 跳过 WAIT 规则，不阻塞 |
| 老配置兼容 | `team_sync=false`（默认）时行为与现在**完全一致** |
| 两个 OAS 未共享 state_dir | 各自独立 → 退化为"不协同"，不报错 |
| 协同判断出错 | **所有决策都只是"建议"**，最坏情况退化为原行为，不会卡死 |

**不作恶原则**：本方案的任何新增逻辑，**在信息不足或异常时都必须退化为当前行为**。
宁可不同步，也不能因为同步逻辑把原本能跑的任务搞挂。

---

## 7. 分期实施

| 阶段 | 内容 | 依赖 | 价值 | 工作量 |
|---|---|---|---|---|
| **P0** | 纯配置试验（`Priority` + 组队任务同优先级） | 无 | 量化问题严重程度 | 分钟级 |
| **P1** | L2 状态层：双方发布状态 + 心跳 | 无 | 让"对方在干什么"可见（**你诉求的基础**） | 小 |
| **P2** | L3 决策层：START/WAIT/YIELD/DEFER + 历史耗时统计 | P1 | 真正"合理分配" | 中 |
| **P3** | L1 接入层：任务边界查询 + DEFER 两阶段调度 | P1+P2 | 落地执行 | 中 |
| **P4** | 独立痛点：定时任务完成记忆（`period`） | 无 | 消灭"手算隔几天" | 小 |

**P4 与协同无关、可独立做**，且收益确定、风险低（详见另一份 `scheduler-redesign.md` 的
period 设计）。**建议 P4 与 P1 并行推进**，因为它们互不依赖。

---

## 8. 待评审的决策点

1. **是否先做 P0（纯配置）**，用真实数据判断 P2/P3 是否值得？
2. **配对关系怎么声明**：`team_peer` 手工填账号名，还是"自动取另一个已启用账号"？
3. **YIELD 规则是否可接受**：为了进度对齐，主动**让出**当前轮次的组队任务给对
   方先做——这会让某个账号当次不做组队，但长期更均衡。是否同意？
4. **`expected_remaining_sec` 用 p50 还是 p90 估计**？（p50 更易命中，p90 更保守）
5. **状态目录**默认 `log/` 是否合适？
6. **组队任务登记表**放在 `tasks/Component/GeneralInvite/team_registry.py` 可否？
7. **是否先做 P4（定时任务记忆）**，它与本方案独立、见效快？
