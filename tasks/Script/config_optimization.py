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

    # 排队模式：多个实例排队依次执行任务，避免同时执行造成服务器压力
    queue_mode: bool = Field(default=False, description='queue_mode_help')
    # 释放执行权的空闲阈值（分钟），仅 queue_mode=True 时生效
    queue_idle_threshold: int = Field(default=10, description='queue_idle_threshold_help')

