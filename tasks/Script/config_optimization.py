# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum
from typing import Any, Dict, List

from pydantic import BaseModel, ValidationError, validator, Field

from module.logger import logger
from tasks.Component.config_base import Time

class WhenTaskQueueEmpty(str, Enum):
    GOTO_MAIN = 'goto_main'
    CLOSE_GAME = 'close_game'

class TimedPriority(str, Enum):
    """
    **定时任务**到点时, 怎么跟**固定任务**抢设备。

    ★ 插队时机是**战斗边界**, 不是立即打断 ——
      与"暂停调度"用同一个安全点（那会卡在半途）。

    | 取值 | 界面名 | 行为 |
    |---|---|---|
    | `TIMED` | 定时优先 | 固定任务在跑, 定时任务到点 -> **打完当前这场战斗**就让位 |
    | `LIST`  | 列表优先 | 定时任务等固定任务跑完 |
    """
    TIMED = 'timed'
    LIST = 'list'

class PriorityMode(str, Enum):
    """★★ **调度优先级三模式**（用户裁定, S6）★★

    用户原话:

    > "拖动只在同类别内生效是在选了**定时优先**或者**固定任务优先**时,
    >  如果选了**列表自定义**, 那么全都可以拖动次序。你理解下, 也就是
    >  **三个选项**: **定时任务优先、固定任务优先、自定义**"

    ## 为什么合并两个旧设置

    原来有**两个重叠**的下拉:

    | 旧字段 | 取值 | 含义 |
    |---|---|---|
    | `schedule_rule` | `Filter` / `FIFO` / `Priority` / `List` | 调度规则(4 路)|
    | `timed_priority` | `timed` / `list` | 定时任务怎么跟固定任务抢设备(2 路)|

    ★ 用户要的是**一个**三选项, 于是合并成本枚举。

    ## 三模式

    | 值 | 界面名 | 队列顺序 | 拖动范围 |
    |---|---|---|---|
    | `timed_first` | **定时任务优先** | 定时段在前, 固定段在后 | 只能**同类别段内**拖 |
    | `fixed_first` | **固定任务优先** | 固定段在前, 定时段在后 | 只能**同类别段内**拖 |
    | `custom`      | **自定义**     | **完全按用户拖的顺序** | ★ **全都能拖** |

    ★ `timed_first` 的界面名沿用用户看到过的字眼:
      「**定时优先（打完当前这场就让位）**」—— 插队时机是**战斗边界**,
      不是立即打断（与"暂停调度"用同一个安全点）。
    """
    TIMED_FIRST = 'timed_first'
    FIXED_FIRST = 'fixed_first'
    CUSTOM = 'custom'


class ScheduleRule(str, Enum):
    FILTER = 'Filter'  # 默认的基于过滤器，（按照开发者设定的调度规则进行调度）
    FIFO = 'FIFO'  # 先来后到，（按照任务的先后顺序进行调度）
    PRIORITY = 'Priority'  # 基于优先级，同一个优先级的任务按照先来后到的顺序进行调度，优先级高的任务先调度
    # 列表模式: 按**用户自己编排**的任务列表顺序调度(见 docs/architecture.md §5)。
    #
    # ★ 与 FIFO 的区别: FIFO 按 `next_run`(先到点先跑), 仍是"定时优先";
    #   LIST 按用户拖拽出来的顺序, 是真正的"列表优先"。
    # ★ 与 FILTER 的区别: FILTER 的顺序硬编码在
    #   `module/config/config_manual.py` 的 `SCHEDULER_PRIORITY` 里, 用户改不了;
    #   LIST 的顺序存在下方 `task_order`, 界面可直接编辑。
    LIST = 'List'

class Optimization(BaseModel):
    screenshot_interval: float = Field(default=0.3,
                                       description='screenshot_interval_help')
    combat_screenshot_interval: float = Field(default=1.0,
                                              description='combat_screenshot_interval_help')
    task_hoarding_duration: float = Field(default=0,
                                          description='task_hoarding_duration_help')
    when_task_queue_empty: WhenTaskQueueEmpty = Field(default=WhenTaskQueueEmpty.GOTO_MAIN,
                                                      description='when_task_queue_empty_help')
    close_game_wait_duration: Time = Field(default=Time(minute=0),
                                          description='close_game_wait_duration_help')
    close_emulator_wait_duration: Time = Field(default=Time(minute=0),
                                              description='close_emulator_wait_duration_help')
    emulator_startup_lead_time: Time = Field(default=Time(minute=2),
                                            description='emulator_startup_lead_time_help')
    schedule_rule: ScheduleRule = Field(default=ScheduleRule.FILTER, description='schedule_rule_help')

    # ------------------------------------------------------------ 运行列表
    #
    # **用户编排的有序条目清单**(见 module/config/run_list.py)。
    #
    # 与旧的 `task_order`(逗号分隔任务名)的区别: 这里能表达
    # **在序列中间发生的事** —— 例如"打完御魂后全部停止 30 分钟"。
    #
    # 条目三种(按**效果**命名):
    #   {"kind": "task",  "task": "Exploration"}   执行任务
    #   {"kind": "rest",  "minutes": 30}           **全部停止** 30 分钟(连定时任务一起停)
    #   {"kind": "delay", "minutes": 30}           **只停列表** 30 分钟(定时任务照常)
    #
    # ★ 数组顺序天然保留插入位置, 不需要额外的 `pos` 字段 ——
    #   这是把列表存成 JSON 数组而不是逗号字符串的理由。
    #
    # 留空表示**未编排** -> 回退到内置默认顺序
    # (源自原先硬编码的 `SCHEDULER_PRIORITY`, 已迁到各任务 `meta.py` 的 `list_pos`)。
    run_list: List[Dict[str, Any]] = Field(
        default_factory=list,
        description='run_list_help',
        title='运行列表')

    # ------------------------------------------------------------ 固定 / 定时 分开管理
    #
    # 用户确认的设计: **固定任务**（有"打满 N 次"语义）与**定时任务**
    # （有自己的 window / 存量 / 周期）分开管理。
    #
    # | 谁来管 | 内容 | 排序依据 |
    # |---|---|---|
    # | **运行列表** | 固定任务 + 休息 | 用户拖拽的顺序 |
    # | **定时调度器** | timed / charge / limited | window、剩余时间、预计耗时、自定义优先级 |
    #
    # 见 `docs/architecture.md` §5.4 与 `module/config/timed_schedule.py`。

    # 固定任务总开关
    enable_fixed: bool = Field(
        default=True,
        description='enable_fixed_help',
        title='启用固定任务')

    # 定时任务总开关
    enable_timed: bool = Field(
        default=True,
        description='enable_timed_help',
        title='启用定时任务')

    # ★★ S6: **调度优先级三模式**（用户裁定的**唯一**开关）★★
    #
    # 用户原话:
    #   "拖动只在同类别内生效是在选了**定时优先**或者**固定任务优先**时,
    #    如果选了**列表自定义**, 那么全都可以拖动次序。你理解下, 也就是
    #    **三个选项: 定时任务优先、固定任务优先、自定义**"
    #
    # | 值 | 队列顺序 | 拖动范围 |
    # |---|---|---|
    # | `timed_first` | 定时段在前, 固定段在后 | 只能**同类别段内**拖 |
    # | `fixed_first` | 固定段在前, 定时段在后 | 只能**同类别段内**拖 |
    # | `custom`      | **完全按用户拖的顺序** | ★ **全都能拖** |
    #
    # ★ 它**取代**了下面两个重叠的旧字段（`schedule_rule` / `timed_priority`）,
    #   那两个保留仅为**读旧配置**; 迁移见 `Config.migrate_priority_mode_once()`。
    # ★ 默认 = `custom`: **行为保持** —— 与改造前一致（用户拖的顺序就是执行
    #   顺序）。★ 若默认 `timed_first`, 会**悄悄重排**所有既有用户的队列
    #   （实测: `build_queue()` 的"用户编排在前 + 自动追加在后"两条契约
    #   立刻被打破, 2 个测试失败）。本项目一贯做法是**新开关默认不改变行为**。
    priority_mode: PriorityMode = Field(
        default=PriorityMode.CUSTOM,
        description='priority_mode_help',
        title='调度优先级')

    # ★★ S6: 迁移用**显式标记**（不要用默认值当哨兵！）★★
    #
    # ## 为什么必须有这个字段
    #
    # `priority_mode` **有默认值**（`timed_first`）—— 所以"用户没设过"与
    # "用户明确选了 timed_first" **分辨不出来**。
    #
    # 我第一版想"用它是否偏离默认"当判断 -> **逻辑自相矛盾**（会在
    # "还是默认"时提前 `return False`, 于是默认配置永远迁不动）。
    #
    # ★ 改用这个**真实字段**当标记:
    #   * `False` = 还没迁移过 -> 读旧字段推算 `priority_mode`
    #   * `True`  = 用户在新界面**明确表过态** -> 永不覆盖
    #
    # ⚠ 必须是**真实字段**: pydantic v2 的 `extra='ignore'` 会把"自定义键"
    #   从 `model_dump()` 丢掉 -> 用自定义键做标记会**每次启动都覆盖用户设置**
    #   （这个坑我们踩过, 见 `migrate_windows_once` 的注释）。
    priority_mode_explicit: bool = Field(
        default=False,
        description='priority_mode_explicit_help',
        title='调度优先级（是否已由用户明确设置）',
        json_schema_extra={'internal': True})

    # ⚠⚠ **已废弃**（S6）: 请用上面的 `priority_mode`。
    #
    # 保留原因: 旧配置里有这个键, 直接删会让 pydantic 报 `extra_forbidden`
    # （或静默丢字段）—— 用户明确要求"**实时配置改了也没事**", 但**不能崩**。
    # 迁移逻辑会读它并转成 `priority_mode`。
    schedule_rule: ScheduleRule = Field(
        default=ScheduleRule.FILTER,
        description='schedule_rule_help',
        title='选择任务调度规则（已废弃，请用「调度优先级」）',
        json_schema_extra={'internal': True})

    # 定时任务到点时怎么跟固定任务抢（见 TimedPriority）
    #
    # ⚠⚠ **已废弃**（S6）: 已并入 `priority_mode`（`timed` -> `timed_first`,
    #    `list` -> `custom`）。保留仅为读旧配置。
    timed_priority: TimedPriority = Field(
        default=TimedPriority.TIMED,
        description='timed_priority_help',
        title='定时任务优先级（已废弃，请用「调度优先级」）',
        json_schema_extra={'internal': True})
    # 休息期间能否**穿插**定时任务
    #
    # 判据: 定时任务的**预期完成时间** < 休息剩余时间。
    # 目的: 保护**组队任务** —— 休息期间在庭院干等会让组队很难凑齐人。
    #
    # ★ 默认**关**: 判据依赖"预期完成时间", 那个值为 0(未知)时不能瞎比。
    rest_interleave: bool = Field(
        default=False,
        description='rest_interleave_help',
        title='休息时可穿插定时任务')

    # 排队模式：多个实例排队依次执行任务，避免同时执行造成服务器压力
    queue_mode: bool = Field(default=False, description='queue_mode_help')
    # 释放执行权的空闲阈值（分钟），仅 queue_mode=True 时生效
    queue_idle_threshold: int = Field(default=10, description='queue_idle_threshold_help')

