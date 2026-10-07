# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, Field

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase
from tasks.Component.GeneralInvite.config_invite import InviteConfig, TeamUserStatus
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig

class GoldYoukaiConfig(ConfigBase):
    buff_gold_50_click: bool = Field(default=False)
    buff_gold_100_click: bool = Field(default=False)

class GoldYoukai(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    gold_youkai: GoldYoukaiConfig = Field(default_factory=GoldYoukaiConfig)
    # 组队身份。默认 alone -> 新字段不改变既有行为(仍是开公开房等路人)
    user_status: TeamUserStatus = Field(default=TeamUserStatus.ALONE, description='user_status_help')
    # 仅当 user_status 为 leader / member 时生效
    invite_config: InviteConfig = Field(default_factory=InviteConfig)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
