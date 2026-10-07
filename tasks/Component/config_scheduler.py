# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum

from pydantic import Field

from tasks.Component.config_base import ConfigBase, TimeDelta, DateTime, Time


class TaskPeriod(str, Enum):
    """
    任务完成周期。

    - NONE   : 不启用完成记忆, 行为与改造前完全一致(用 next_run + success_interval)
    - DAILY  : 本(游戏)日已成功完成 -> 不再入队; 跨日自动失效
    - WEEKLY : 本(游戏)周已成功完成 -> 不再入队; 跨周自动失效

    周期边界按 reset_at(游戏重置时间, 默认 05:00)计算, 因此在 04:00 仍算作前一天。
    """
    NONE = 'none'
    DAILY = 'daily'
    WEEKLY = 'weekly'


class Scheduler(ConfigBase):
    enable: bool = Field(default=False, description='enable_help')
    next_run: DateTime = Field(default=DateTime.fromisoformat("2023-01-01 00:00:00"), description='next_run_help')
    priority: int = Field(default=5, description='priority_help')

    success_interval: TimeDelta = Field(default=TimeDelta(days=1), description='success_interval_help')
    failure_interval: TimeDelta = Field(default=TimeDelta(days=1), description='failure_interval_help')
    server_update: Time = Field(default=Time(hour=9, minute=0, second=0), description='server_update_help')
    delay_date: int = Field(default=1, description='delay_date_help', ge=1, le=31)
    float_time: Time = Field(default=Time(hour=0, minute=0, second=0), description='float_time_help')

    # 完成记忆。默认 none -> 新字段不改变既有行为
    period: TaskPeriod = Field(default=TaskPeriod.NONE, description='period_help')
    # 周期边界(游戏每日重置时刻)。阴阳师以凌晨 0 点为界, 故默认为 00:00
    reset_at: Time = Field(default=Time(hour=0, minute=0, second=0), description='reset_at_help')


if __name__ == "__main__":
    dict_s = {
        "enable": False,
        "next_run": "2026-07-19T14:15:37",
        "priority": 5,
        "success_interval": "10 00:00:01",
        "failure_interval": "10 00:00:01",
        "server_update": "09:03:00",
        "float_time": "02:00:05"
    }
    s = Scheduler(**dict_s)
    print(s.model_dump())
