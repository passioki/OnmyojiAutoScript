# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum
from datetime import datetime, time
from pydantic import BaseModel, ValidationError, validator, Field

from tasks.Component.config_base import Time

class InviteNumber(str, Enum):
    ONE = 'one'
    TWO = 'two'

class FindMode(str, Enum):
    AUTO_FIND = 'auto_find'
    RECENT_FRIEND = 'recent_friend'


class TeamUserStatus(str, Enum):
    """
    组队身份(通用定义)。

    - ALONE  : 不邀请指定好友, 开公开房等路人
    - LEADER : 开房并循环邀请 invite_config 中指定的好友
    - MEMBER : 等待并自动接受队长邀请

    说明: 历史上 BondlingFairyland / EvoZone / Exploration / FallenSun / Orochi
    各自在 config.py 中复制了一份同名枚举(部分还带 WILD / handoff1 / handoff2)。
    新增任务请复用本定义, 不要再复制。
    """
    ALONE = 'alone'
    LEADER = 'leader'
    MEMBER = 'member'


# 兼容别名: 新代码可用 TeamUserStatus, 习惯写法 UserStatus 亦可
UserStatus = TeamUserStatus

class InviteConfig(BaseModel):

    invite_number: InviteNumber = Field(default=InviteNumber.ONE, description='invite_number_help')
    friend_1: str = Field(default='', description='friend_name_help')
    friend_2: str = Field(default='', description='friend_2_name_help')
    find_mode: FindMode = Field(default=FindMode.AUTO_FIND, description='find_mode_help')
    wait_time: Time = Field(default=Time(minute=2), description='wait_time_help')
    default_invite: bool = Field(default=True, description='default_invite_help')

    # @validator('wait_time', pre=False, always=False)
    # def parse_time(cls, value):
    #     print('parse_time', value)
    #     if isinstance(value, str):
    #         try:
    #             return datetime.strptime(value, '%H:%M:%S').time()
    #         except ValueError:
    #             raise ValueError('Invalid time value. Expected format: HH:MM:SS')
    #     return value

if __name__ == "__main__":
    i = InviteConfig()
    print(isinstance(i.wait_time, time))
    i.wait_time = "00:05:00"
    print(i.wait_time)
    print(isinstance(i.wait_time, time))

