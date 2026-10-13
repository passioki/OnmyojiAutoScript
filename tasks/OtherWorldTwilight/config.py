# This Python file uses the following encoding: utf-8
# @author AzurTian
from datetime import timedelta, time

from pydantic import Field, field_validator
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig, GreenMarkEnum
from tasks.Component.GeneralInvite.config_invite import InviteConfig
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Component.config_base import ConfigBase, Time, dynamic_hide
from tasks.Component.config_scheduler import Scheduler
from tasks.Orochi.config import UserStatus


class OtherWorldTwilightConfig(ConfigBase):
    # 身份
    user_status: UserStatus = Field(default=UserStatus.LEADER, description='user_status_help')
    # ★ 片 2: 原 `limit_time_v` 把配置里的 `Time` 转成 `timedelta` ——
    #   配置字段已删除, 时间上限统一到 `scheduler.expected_minutes`
    #   （任务侧用 `BaseTask.time_limit`）。


class OWTBattleConfig(GeneralBattleConfig):
    hide_fields = dynamic_hide('preset_enable', 'preset_group', 'preset_team', 'green_mark', 'green_mark_type')

    # pydantic v2 默认不校验默认值, validator 拦不到 CHOOSE, 必须直接给 NAME
    green_mark_type: GreenMarkEnum = Field(default=GreenMarkEnum.NAME, description='green_mark_type_help')

    @field_validator('green_mark_type')
    @classmethod
    def green_mark_type_validator(cls, v):
        return GreenMarkEnum.NAME


class OtherWorldTwilight(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    other_world_twilight_config: OtherWorldTwilightConfig = Field(default_factory=OtherWorldTwilightConfig)
    invite_config: InviteConfig = Field(default_factory=InviteConfig)
    general_battle_config: OWTBattleConfig = Field(default_factory=OWTBattleConfig)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
