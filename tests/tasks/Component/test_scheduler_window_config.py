# -*- coding: utf-8 -*-
"""`Scheduler.build_window()` 的测试 —— 开放时段配置的解析与健壮性。

## 背景

阴阳师很多玩法有固定开放时段（如逢魔之时 17:00-23:00），而此前 OAS 没有这个概念，
用户只能把 `success_interval` 设短让任务频繁醒来碰运气 —— 于是"用户轮询节奏"
混进了本该表达游戏机制的字段。

现在开放时段是**用户可配**的 `Scheduler` 字段（`window_enable` / `window_start` /
`window_end` / `window_days`），由 `build_window()` 转成 `AvailabilityWindow`。

## 本测试关注什么

1. **默认关闭** —— 新增字段不得改变既有行为
2. **正确解析** —— 每天 / 限定星期 / 跨午夜
3. **健壮性** —— 配置写错时**退化为不限时段**并记 warning，而不是让任务跑不起来
"""
from datetime import time

import pytest

from module.config.availability import ALL_DAYS
from tasks.Component.config_scheduler import Scheduler


class TestDefaults:
    """默认必须"不限时段" —— 否则会改变所有既有用户的行为。"""

    def test_disabled_by_default(self):
        w = Scheduler().build_window()
        assert w.enabled is False
        assert w.is_unrestricted is True
        assert w.describe() == '不限时段'

    def test_default_times_are_sane_but_inactive(self):
        s = Scheduler()
        # 默认给了 17-23 作为示例值, 但 enable=False 所以不生效
        assert s.window_enable is False
        assert s.window_start == time(17, 0)
        assert s.window_end == time(23, 0)
        assert s.window_days == '0,1,2,3,4,5,6'


class TestDailyWindow:
    def test_fengmo(self):
        """用户告知的真实机制: 逢魔之时 每天 17:00-23:00。"""
        s = Scheduler(window_enable=True,
                      window_start=time(17, 0), window_end=time(23, 0))
        w = s.build_window()
        assert w.enabled is True
        assert w.start == time(17, 0)
        assert w.end == time(23, 0)
        assert set(w.days) == set(ALL_DAYS)
        assert w.describe() == '每天 17:00-23:00'


class TestDayRestriction:
    def test_weekend_only(self):
        """狭间暗域: 只在周五/六/日。"""
        s = Scheduler(window_enable=True,
                      window_start=time(19, 0), window_end=time(21, 0),
                      window_days='4,5,6')
        w = s.build_window()
        assert set(w.days) == {4, 5, 6}
        assert '周五' in w.describe()

    def test_days_are_deduped_and_sorted(self):
        s = Scheduler(window_enable=True, window_days='6,4,5,4')
        w = s.build_window()
        assert w.days == (4, 5, 6)

    def test_empty_days_means_every_day(self):
        s = Scheduler(window_enable=True, window_days='')
        assert set(s.build_window().days) == set(ALL_DAYS)


class TestCrossMidnight:
    def test_cross_midnight(self):
        s = Scheduler(window_enable=True,
                      window_start=time(22, 0), window_end=time(2, 0))
        w = s.build_window()
        assert w.crosses_midnight is True
        assert '跨夜' in w.describe()


class TestRobustness:
    """配置写错时退化, 而不是抛异常 —— 时段错误不该让任务跑不起来。"""

    def test_garbage_days_falls_back_to_every_day(self):
        s = Scheduler(window_enable=True, window_days='abc,xyz')
        w = s.build_window()
        assert w.enabled is True
        assert set(w.days) == set(ALL_DAYS)

    def test_out_of_range_days_falls_back(self):
        s = Scheduler(window_enable=True, window_days='9,-1,99')
        w = s.build_window()
        assert set(w.days) == set(ALL_DAYS)

    def test_partially_valid_days_keeps_valid_ones(self):
        s = Scheduler(window_enable=True, window_days='4,abc,6')
        w = s.build_window()
        assert set(w.days) == {4, 6}

    def test_whitespace_tolerated(self):
        s = Scheduler(window_enable=True, window_days=' 4 , 5 , 6 ')
        assert set(s.build_window().days) == {4, 5, 6}
