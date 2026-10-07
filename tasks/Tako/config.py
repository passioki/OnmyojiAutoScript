# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, time

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase
from tasks.Component.GeneralInvite.config_invite import InviteConfig, TeamUserStatus
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig


class TakoConfig(BaseModel):
    """
    石距的任务配置。

    注意: user_status 必须放在本分组内部, 而不是 Tako 的顶层。
    原因见 module/config/config_model.py 的 script_task(): 它要求任务模型的
    顶层字段都是**嵌套模型**(即一个"分组"), 标量字段(如枚举)必须落在分组内,
    否则 merge_value 会因取不到该分组的 properties 而抛 KeyError,
    导致该任务在 GUI 中整个界面渲染失败。
    Orochi 的做法同样是 user_status 放在 OrochiConfig 内部。
    """
    enable: bool = Field(default=False)
    # 组队身份。默认 alone -> 与改造前行为一致(开公开房等路人)
    user_status: TeamUserStatus = Field(default=TeamUserStatus.ALONE,
                                        description='user_status_help')
    buff_gold_50_click: bool = Field(default=False)
    buff_gold_100_click: bool = Field(default=False)
    buff_exp_50_click: bool = Field(default=False)
    buff_exp_100_click: bool = Field(default=False)


class Tako(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    tako_config: TakoConfig = Field(default_factory=TakoConfig)
    # 仅当 user_status 为 leader / member 时生效
    invite_config: InviteConfig = Field(default_factory=InviteConfig)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
