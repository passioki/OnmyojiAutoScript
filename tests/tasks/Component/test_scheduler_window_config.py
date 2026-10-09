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
        # ★ 措辞刻意区分: 未声明 window 是**缺失**, 不是"不限时段"
        #   （用户要求"所有的定时都有着 window 属性"）
        assert w.describe() == '未声明开放时段'

    def test_default_times_are_sane_but_inactive(self):
        s = Scheduler()
        # 默认给了 17-23 作为示例值, 但 enable=False 所以不生效
        assert s.window_enable is False
        assert s.window_start == time(17, 0)
        assert s.window_end == time(23, 0)
        assert s.window_days == '0,1,2,3,4,5,6'


class TestWindowForPeriod:
    """★ F2: 由**周期**推导默认窗口（用户新澄清的设计）。

    用户原话:
        "window 的设计应当再展开说下, 每天的任务其实也有 window,
         只不过是每天的 0 点到 24 点。但是选择周期选择每天, 每周则是
         每周一 0 点到周日 24 点, 每月以此类推。而逢魔则是每天的 17 点-23 点,
         等等。**所有的定时都有着 window 属性**。"
    """

    def test_daily_is_full_day(self):
        from module.config.availability import window_for_period
        from module.config.resource import Period
        w = window_for_period(Period.DAILY)
        assert w is not None and w.enabled is True
        assert w.describe() == '每天 00:00-23:59'
        assert set(w.days) == set(range(7))
        assert not w.days_of_month

    def test_weekly_is_full_week(self):
        """★ 一周 = 7 天, 所以 WEEKLY 的窗口**也是全周**。

        它表达"节奏是每周", 不是"只允许某几天跑" —— 后者是**活动窗口**
        （由各任务 `meta.py` 显式声明, 会覆盖默认）。
        """
        from module.config.availability import window_for_period
        from module.config.resource import Period
        w = window_for_period(Period.WEEKLY)
        assert w is not None and w.enabled is True
        assert set(w.days) == set(range(7))
        assert not w.days_of_month

    def test_monthly_covers_whole_month(self):
        from module.config.availability import window_for_period
        from module.config.resource import Period
        w = window_for_period(Period.MONTHLY)
        assert w is not None and w.enabled is True
        assert w.describe() == '每月 00:00-23:59'
        assert set(w.days_of_month) == set(range(1, 32))
        # 整月的每一天都该命中
        from datetime import datetime
        for d in (1, 15, 28, 31):
            assert w.contains(datetime(2026, 10, d, 12, 0)), f'{d} 日应命中'

    def test_none_period_has_no_derivable_window(self):
        """`Period.NONE` 没有周期 -> 没有可推导的窗口（返回 None）。"""
        from module.config.availability import window_for_period
        from module.config.resource import Period
        assert window_for_period(Period.NONE) is None

    def test_fengmo_narrows_time(self):
        """逢魔 = 每天 17:00-23:00（周期 daily + 收窄时刻）。"""
        from datetime import time

        from module.config.availability import window_for_period
        from module.config.resource import Period
        w = window_for_period(Period.DAILY, start=time(17, 0), end=time(23, 0))
        assert w.describe() == '每天 17:00-23:00'

    def test_monthly_days_of_month_gate(self):
        """★ 月内日**真的**参与判定（不能只是显示）。"""
        from datetime import time

        from module.config.availability import AvailabilityWindow, window_for_period
        from module.config.resource import Period
        from datetime import datetime
        # 只有 1-15 日
        w = AvailabilityWindow(True, time(0, 0), time(23, 59),
                               days_of_month=tuple(range(1, 16)))
        assert w.contains(datetime(2026, 10, 5, 12, 0)) is True
        assert w.contains(datetime(2026, 10, 20, 12, 0)) is False
        assert w.describe() == '每月 1-15 日 00:00-23:59'
        # 16-月末
        w2 = AvailabilityWindow(True, time(0, 0), time(23, 59),
                                days_of_month=tuple(range(16, 32)))
        assert w2.contains(datetime(2026, 10, 5, 12, 0)) is False
        assert w2.contains(datetime(2026, 10, 20, 12, 0)) is True
        assert w2.describe() == '每月 16-月末 日 00:00-23:59'

    def test_invalid_days_of_month_rejected(self):
        from datetime import time as _t

        from module.config.availability import AvailabilityWindow
        import pytest
        with pytest.raises(ValueError):
            AvailabilityWindow(True, _t(0, 0), _t(23, 59), days_of_month=(0,))
        with pytest.raises(ValueError):
            AvailabilityWindow(True, _t(0, 0), _t(23, 59), days_of_month=(32,))

    def test_is_unrestricted_accounts_for_month(self):
        """★ 反向守卫: `enabled=True` + 全 7 天 + 整月 = 实质不限。

        若不看 `days_of_month`, 只判 `len(days)==7`, 会把"每月"误判。
        这里钉住两个方向都正确。
        """
        from datetime import time

        from module.config.availability import window_for_period
        from module.config.resource import Period
        assert window_for_period(Period.DAILY).is_unrestricted is True
        assert window_for_period(Period.MONTHLY).is_unrestricted is True
        # 真正的活动窗口**不是**"不限"
        from module.config.availability import AvailabilityWindow
        narrow = AvailabilityWindow(True, time(17, 0), time(23, 0))
        assert narrow.is_unrestricted is False


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
