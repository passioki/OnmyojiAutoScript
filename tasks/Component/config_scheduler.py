# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum

from pydantic import Field

from module.logger import logger
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

    # ------------------------------------------------------------------ 开放时段
    #
    # 阴阳师很多玩法**不是随时能做**, 而有固定开放时段(如逢魔之时 17:00-23:00)。
    # 此前软件没有这个概念, 用户只能把 success_interval 设短(如 1 小时)让任务
    # **频繁醒来碰运气** —— 于是"用户轮询节奏"混进了本该表达游戏机制的字段。
    #
    # 这里把游戏时段显式建模为**硬约束**: 不在时段内一律不跑。
    #
    # 设计约束:
    #   * **不写死任何时段** —— 全部由用户填写; 默认关闭(不限时段),
    #     因此新增字段**不改变既有行为**。
    #   * 支持**跨午夜**(如 22:00-02:00): end <= start 即视为跨夜。
    #   * 支持**限定星期**(如狭间暗域只有周五/六/日)。
    #   * 软件会通过 `ObservedWindow` **自学习**实际时段并给出提示, 见
    #     `module/config/availability.py` 与 `docs/architecture.md` §3.0。
    window_enable: bool = Field(
        default=False,
        description='window_enable_help',
        title='启用开放时段')
    window_start: Time = Field(
        default=Time(hour=17, minute=0, second=0),
        description='window_start_help',
        title='开放开始')
    window_end: Time = Field(
        default=Time(hour=23, minute=0, second=0),
        description='window_end_help',
        title='开放结束')
    # 限定星期: 逗号分隔的 0-6(周一=0), 空或 "0,1,2,3,4,5,6" 表示每天。
    # 用字符串而非列表, 与既有 charge_slots='0,12' 的风格一致, 也便于 GUI 输入。
    window_days: str = Field(
        default='0,1,2,3,4,5,6',
        description='window_days_help',
        title='开放星期')

    # ------------------------------------------------------------ 开放时段: 便捷访问
    def build_window(self) -> 'AvailabilityWindow':
        """
        把本配置转成 `AvailabilityWindow`。

        解析失败(如 `window_days` 写成乱码)时**退化为不限时段**并记 warning ——
        时段配置错误不该让任务跑不起来。
        """
        from module.config.availability import ALL_DAYS, AvailabilityWindow

        if not self.window_enable:
            return AvailabilityWindow()      # enabled=False -> 不限时段

        days = []
        bad = []
        for part in str(self.window_days or '').split(','):
            part = part.strip()
            if part == '':
                continue
            try:
                d = int(part)
            except (TypeError, ValueError):
                bad.append(part)
                continue
            if 0 <= d <= 6:
                days.append(d)
            else:
                bad.append(part)

        if bad:
            # 逐项跳过而不是整体丢弃 —— 用户写了 '4,abc,6' 时, 4 和 6 仍是有效的意图。
            logger.warning(
                f'window_days 中的无效项已忽略: {bad}（应为 0-6, 周一=0）')

        if not days:
            logger.warning(f'window_days 无有效项({self.window_days!r}), 退化为每天')
            days = list(ALL_DAYS)

        try:
            return AvailabilityWindow(
                enabled=True,
                start=self.window_start,
                end=self.window_end,
                days=tuple(sorted(set(days))),
            )
        except ValueError as exc:
            logger.warning(f'开放时段配置非法({exc}), 退化为不限时段')
            return AvailabilityWindow()


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
