# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta
from pydantic import BaseModel, Field

from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, Time


class DemonRetreatTime(ConfigBase):
    # ★ 片 4 (W-a/B): 本类原有的「偏好时刻」字段**已删除** ——
    #   用户裁定「放弃'希望几点'这个概念」，改用 `scheduler.windows`
    #   的 `start` 表达（迁移见 `Config.migrate_moment_fields_to_windows_once`）。
    # ⚠ 删完全部字段后类体为空 ⇒ 必须留一个语句,
    #   否则 `IndentationError: expected an indented block`
    #   （★ 本会话在 `SixRealmsGate` 上踩过一次）。
    # ★ 保留空类而不删掉它, 是因为配置树里仍有
    #   `<任务>.<本类对应字段名>` 这个节点 —— 删了会改变配置结构。
    pass

class DemonRetreat(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    demon_retreat_time: DemonRetreatTime = Field(default_factory=DemonRetreatTime)
    general_battle: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    switch_soul_config: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
