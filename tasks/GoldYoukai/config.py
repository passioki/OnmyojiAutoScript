# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, Field

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase
from tasks.Component.GeneralInvite.config_invite import InviteConfig, TeamUserStatus
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig


class GoldYoukaiConfig(ConfigBase):
    """
    金币妖怪的任务配置。

    注意: user_status 必须放在本分组内部, 而不是 GoldYoukai 的顶层。
    原因见 module/config/config_model.py 的 script_task(): 顶层字段必须是
    嵌套模型(分组), 标量字段需落在分组内, 否则该任务在 GUI 中界面会渲染失败。
    """
    # 组队身份。默认 alone -> 与改造前行为一致(开公开房等路人)
    user_status: TeamUserStatus = Field(default=TeamUserStatus.ALONE,
                                        description='user_status_help')
    enable: bool = Field(default=False)
    buff_gold_50_click: bool = Field(default=False)
    buff_gold_100_click: bool = Field(default=False)

    # ---- 挑战次数 ----
    # 金币妖怪的挑战次数在**每天的固定时刻**刷新(0 点与 12 点), 最多储存 2 次。
    # 注意这不是"间隔 12 小时": 若在 01:00 用掉一次, 下一次是当天 12:00 刷新。
    # 关闭时保持改造前的行为(一次运行内连打 2 场)。
    charge_enable: bool = Field(default=True, description='charge_enable_help')
    charge_max: int = Field(default=2, description='charge_max_help', ge=1, le=10)
    # 刷新时刻(整点小时), 逗号分隔; 游戏内为 0 点和 12 点
    charge_slots: str = Field(default='0,12', description='charge_slots_help')
    # 每次运行消耗几次(每次运行打几场)。组队场景建议 1
    charge_consume: int = Field(default=1, description='charge_consume_help', ge=1, le=5)
    # 该玩法在"便捷组队"页左栏的名称, 用于读取次数刷新倒计时
    zone_name: str = Field(default='金币妖怪', description='zone_name_help')


class GoldYoukai(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    gold_youkai: GoldYoukaiConfig = Field(default_factory=GoldYoukaiConfig)
    # 仅当 user_status 为 leader / member 时生效
    invite_config: InviteConfig = Field(default_factory=InviteConfig)
    switch_soul: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
