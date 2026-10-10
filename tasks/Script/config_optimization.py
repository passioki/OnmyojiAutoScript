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

# ★★★ `PriorityMode`（调度优先级三模式）**已整簇删除**（用户裁定）★★★
#
# ## 用户原话
#
# > "我觉得……这个**固定任务优先和定时任务优先以及不能跨类别拖动太蠢了**。
# >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
# >  定时任务优先**直接作为一个快捷排序**就好, **而不是定义一些没有意义的
# >  不能跨类别拖动以及单独的调度优先级**。"
#
# ## 删掉了什么
#
# | 删除 | 原来在哪 |
# |---|---|
# | `PriorityMode` 枚举 | 这里 |
# | `Optimization.priority_mode` / `priority_mode_explicit` | 本文件下方 |
# | `migrate_priority_mode_once()` | `module/config/config.py` |
# | `Config.priority_mode()` / `_order_by_priority_mode()` | 同上 |
# | `_check_drag_allowed()` / `drag_blocked` | `module/server/schema_router.py` |
# | `GET`/`PUT /{script}/priority_mode` | 同上 |
# | `/schema` 的 `global_fields.priority_mode` + `drag_within_group_only` | 同上 |
# | 前端「调度优先级」下拉 + 全部拖动判据 | `OASX-src/lib/...` |
#
# ## 取而代之
#
# * **执行顺序 = `run_list` 的顺序本身**（唯一权威, 永远可以自由拖）
# * 「定时排前面 / 固定排前面」= `PUT /{script}/queue/sort`
#   的**一次性动作**（`Config.sort_run_list(by)`）—— **不留状态**
# * 唯一硬约束: 「休息」条目**恒最后**（`Config.place_rest_last()`,
#   **归一化**而不是拒绝）
#
# ⚠ 老配置里遗留的 `priority_mode` / `priority_mode_explicit` 键:
#   `Optimization` 不再声明它们 -> pydantic 加载时**静默忽略多余键**
#   -> 下次 `save()` 时从磁盘上**自然消失**。**不需要写清理迁移。**


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
    # | **定时调度器** | timed / limited | window、剩余时间、预计耗时、自定义优先级 |
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

    # ★★★ S7: **`priority_mode` / `priority_mode_explicit` 已删除** ★★★
    #
    # 用户原话:
    # > "固定任务优先和定时任务优先以及**不能跨类别拖动太蠢了**。
    # >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
    # >  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有
    # >  意义的不能跨类别拖动以及**单独的调度优先级**。"
    #
    # ★ 现在**没有"调度优先级"这个概念** —— 执行顺序就是 `run_list`
    #   的顺序本身, 永远可以自由拖动。
    # ★ 「定时排前面 / 固定排前面」是 `PUT /{script}/queue/sort` 的
    #   **一次性动作**（`Config.sort_run_list(by)`）, **不留状态**。
    #
    # ⚠ 老配置里遗留的这两个键: pydantic 加载时**静默忽略多余键**
    #   -> 下次 `save()` 时从磁盘上**自然消失**。不需要清理迁移。


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

    # ★★★ 一次性标记: `scheduler.period` 是否已按出厂默认值**回填过** ★★★
    #
    # ## 为什么必须有它（不只是一个布尔值那么简单）
    #
    # 分类判据读的是**配置里的** `scheduler.period`（用户在前端改的那个）,
    # 而老配置里那 52 个任务写的都是 `none` —— 若不回填, 它们会突然全变成
    # 「临时任务」。所以启动时要**按出厂默认值回填一次**。
    #
    # ⚠ **但如果只按"当前值是 `none` 就回填", 就会把用户的"不限"永久锁死:**
    #   用户把某任务设成「不限」-> 下次 `Config()` 构造（**每个 HTTP 请求
    #   都会新建一个**）-> 迁移又把它改回出厂值 -> ★ **用户改不动**。
    #
    #   实测复现: 写入 `period='none'` -> `Config(cfg)` 之后
    #   `task_period()` 直接返回 `'daily'`, **磁盘也被改回 `'daily'`**。
    #
    # ★ 修法: 用这个**一次性标记** —— 回填只做**第一次**, 之后永不再碰。
    #   与已删的 `priority_mode_explicit` 同一思路（"不能用默认值当哨兵"）。
    period_backfilled: bool = Field(
        default=False,
        description='period_backfilled_help',
        title='任务周期是否已按出厂默认值回填',
        json_schema_extra={'internal': True})

    # ★★★ 执行顺序**配置页**（用户要求: "配置页 1/2/3/…"）★★★
    #
    # 用户原话:
    # > "添加**执行顺序配置页 1/2/3/……**，可以添加、删除和切换配置页"
    #
    # ## 语义
    #
    # 一页 = **一套执行顺序**（`run_list` 的快照）。用户可以:
    #   * **添加**一页（把当前顺序存为一页）
    #   * **切换**到某一页（把那页的顺序应用回 `run_list`）
    #   * **删除**一页
    #
    # ## 数据结构
    #
    # ```json
    # "profiles": {
    #   "active_id": "p1",
    #   "items": [
    #     {"id": "p1", "name": "1", "entries": [{"kind":"task","task":"Orochi"}]}
    #   ]
    # }
    # ```
    #
    # ★ 每项的 `entries` 就是 `run_list` 的形状（同一套 `RunEntry` 序列化）,
    #   所以"应用一页"= 把 `entries` 写回 `optimization.run_list` ——
    #   **复用同一个写入路径**, 不新增第二套数据结构
    #  （本轮刚修过"两套定义打架"的教训）。
    #
    # ⚠ 与 `run_list` 的关系: `run_list` 永远是**当前生效**的那份;
    #   `profiles` 只是**存档**。切换 = 存当前 + 载目标。
    profiles: dict = Field(
        default_factory=dict,
        description='profiles_help',
        title='执行顺序配置页',
        json_schema_extra={'internal': True})

