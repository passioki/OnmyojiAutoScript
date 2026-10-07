# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, Field

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase
from tasks.Component.GeneralInvite.config_invite import InviteConfig, TeamUserStatus
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig


class ExperienceYoukaiConfig(ConfigBase):
    """
    经验妖怪的任务配置。

    注意: user_status 必须放在本分组内部, 而不是 ExperienceYoukai 的顶层。
    原因见 module/config/config_model.py 的 script_task(): 顶层字段必须是
    嵌套模型(分组), 标量字段需落在分组内, 否则该任务在 GUI 中界面会渲染失败。
    """
    # 组队身份。默认 alone -> 与改造前行为一致(开公开房等路人)
    user_status: TeamUserStatus = Field(default=TeamUserStatus.ALONE,
                                        description='user_status_help')
    enable: bool = Field(default=False)
    buff_exp_50_click: bool = Field(default=False)
    buff_exp_100_click: bool = Field(default=False)

    # ---- 挑战次数(充能) ----
    # 经验妖怪的挑战次数每 12 小时恢复 1 次, 最多累积 2 次。
    # 关闭时保持改造前的行为(一次运行内连打 2 场)。
    charge_enable: bool = Field(default=True, description='charge_enable_help')
    charge_max: int = Field(default=2, description='charge_max_help', ge=1, le=10)
    charge_recover_hours: float = Field(default=12.0, ge=0.5, le=72,
                                        description='charge_recover_hours_help')
    # 每次运行消耗几次(每次运行打几场)。组队场景建议 1
    charge_consume: int = Field(default=1, description='charge_consume_help', ge=1, le=5)


class ExperienceYoukai(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    experience_youkai: ExperienceYoukaiConfig = Field(default_factory=ExperienceYoukaiConfig)
    # 仅当 user_status 为 leader / member 时生效
    invite_config: InviteConfig = Field(default_factory=InviteConfig)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
