# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from pydantic import BaseModel, Field

from tasks.Component.config_scheduler import Scheduler
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig


class SixRealmsGate(BaseModel):
    # ★ 片 2: `limit_time` **已删除**（时间上限统一到
    #   `scheduler.expected_minutes`，见 `tasks/base_task.py` 的 `time_limit`）。
    # ⚠ 它是本类**唯一**的字段 ⇒ 删掉后类体为空 ⇒ 必须留一个语句，
    #   否则 `IndentationError: expected an indented block`
    #   （★ 实测踩过：批量删字段的脚本会把整个类体吞掉）。
    # ★ 保留这个空类而不是删掉它，是因为 `SixRealms.six_realms_gate`
    #   这个字段名仍被配置树/界面引用（删了会改变配置结构）。
    pass


class SixRealms(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    switch_soul_config: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
    six_realms_gate: SixRealmsGate = Field(default_factory=SixRealmsGate)













