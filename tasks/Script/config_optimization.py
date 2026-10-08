# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum
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
    # 任务列表顺序(仅 schedule_rule=List 时生效): 逗号分隔的任务名。
    #
    # 留空表示用**内置默认顺序** —— 源自原先硬编码在 `config_manual.py` 的
    # `SCHEDULER_PRIORITY`, 现已迁到各任务 `meta.py` 的 `list_pos`。
    # 用户拖拽后由界面把新顺序写入本字段。
    #
    # ★ 用逗号分隔的字符串而非列表: 与既有 `charge_slots='0,12'` 风格一致,
    #   也便于 GUI 直接输入与在 git diff 里阅读。
    task_order: str = Field(default='', description='task_order_help')
    # 排队模式：多个实例排队依次执行任务，避免同时执行造成服务器压力
    queue_mode: bool = Field(default=False, description='queue_mode_help')
    # 释放执行权的空闲阈值（分钟），仅 queue_mode=True 时生效
    queue_idle_threshold: int = Field(default=10, description='queue_idle_threshold_help')

