# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import timedelta
from pydantic import BaseModel, Field
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, Time, dynamic_hide


class HuntTime(ConfigBase):
    # ★ 片 4 (W-a/B): 本类原有的「偏好时刻」字段**已删除** ——
    #   用户裁定「放弃'希望几点'这个概念」，改用 `scheduler.windows`
    #   的 `start` 表达（迁移见 `Config.migrate_moment_fields_to_windows_once`）。
    # ⚠ 删完全部字段后类体为空 ⇒ 必须留一个语句,
    #   否则 `IndentationError: expected an indented block`
    #   （★ 本会话在 `SixRealmsGate` 上踩过一次）。
    # ★ 保留空类而不删掉它, 是因为配置树里仍有
    #   `<任务>.<本类对应字段名>` 这个节点 —— 删了会改变配置结构。
    pass

class HuntConfig(BaseModel):
    kirin_group_team: str = Field(default='-1,-1', description='switch_group_team_help')
    netherworld_group_team: str = Field(default='-1,-1')


class HuntGeneralBattleConfig(GeneralBattleConfig):
    hide_fields = dynamic_hide('lock_team_enable', 'green_enable', 'green_mark')


class Hunt(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    hunt_time: HuntTime = Field(default_factory=HuntTime)
    hunt_config: HuntConfig = Field(default_factory=HuntConfig)
    kirin_battle_config: HuntGeneralBattleConfig = Field(default_factory=HuntGeneralBattleConfig)
    netherworld_battle_config: HuntGeneralBattleConfig = Field(default_factory=HuntGeneralBattleConfig)
