# This Python file uses the following encoding: utf-8
"""`Rest` (休息) 的任务配置.

## ★★★ 休息就是临时任务（用户裁定）★★★

用户原话:
> "**休息就是临时任务**（回庭院待着），只不过**可以选择被定时任务插队**。"

> "休息作为**空置任务**它本身就会带来**阻塞**的效果。"

## ★ 分钟数放在 `scheduler.target`

用户裁定 (乙-A):
> "需要**分钟**, 不是次数。"

★ 所以休息任务**不新增 `minutes` 字段** —— 直接用**通用的**
  `scheduler.target`（那个"目标次数"框），只是它的语义对休息是"**分钟**"。

这样休息与其它临时任务**共用一套字段**:
    `scheduler.enable`    -> 临时关掉这条休息
    `scheduler.target`    -> ★ **休息多少分钟**
    `scheduler.period`    -> 默认 `none`（= 临时任务）; 改成 daily/weekly 就按调度走
    `scheduler.windows`   -> "只在这个时段才休息"（例如午休 12:00-14:00）
    `scheduler.priority`  -> 通用
    `scheduler.expected_minutes` -> 通用（"预期完成时间"）

★ 这正是用户要的"**统一管理**"。
"""
from pydantic import Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class Rest(ConfigBase):
    """休息任务配置。

    ★ **没有自己的参数字段** —— 分钟数复用通用的 `scheduler.target`。
      这样"休息"在配置层面**与其它临时任务完全同构**
      （用户裁定: "有 period 和 window 属性, 是为了统一管理"）。
    """

    scheduler: Scheduler = Field(default_factory=Scheduler)
