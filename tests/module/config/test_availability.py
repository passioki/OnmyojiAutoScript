# -*- coding: utf-8 -*-
"""开放时段(AvailabilityWindow)与自学习(ObservedWindow)的测试。

## 背景

阴阳师很多玩法**不是随时能做**, 而 OAS 此前**没有"开放时段"概念**。
用户只能把 `success_interval` 设短, 让任务频繁醒来碰运气 ——
于是"用户轮询节奏"混进了本该表达游戏机制的字段。

`AvailabilityWindow` 把游戏时段显式建模为**硬约束**, 与 `interval`(用户轮询)分开。

**不写死任何时段**: 全部由用户配置; 默认 `enabled=False` 表示不限时段,
因此新字段不改变既有行为。
"""
from datetime import datetime, time, timedelta

import pytest

from module.config.availability import (
    ALL_DAYS, DAY_NAMES, AvailabilityWindow, ObservedWindow)
from module.config.resource import Period, Recharge, Resource
from module.config.scheduler_core import (
    RunState, cannot_run_reason, next_available)

# 2026-10-08 是周四(weekday=3); 10-09 周五; 10-10 周六; 10-11 周日; 10-12 周一
THU = datetime(2026, 10, 8, 0, 0)
FRI = datetime(2026, 10, 9, 0, 0)
SAT = datetime(2026, 10, 10, 0, 0)


def at(day: datetime, h, m=0) -> datetime:
    return day.replace(hour=h, minute=m)


class TestDisabledByDefault:
    """默认不限时段 —— 保证新字段不改变既有行为。"""

    def test_default_is_unrestricted(self):
        w = AvailabilityWindow()
        assert w.enabled is False
        assert w.is_unrestricted is True
        assert w.contains(at(THU, 3)) is True
        assert w.contains(at(THU, 20)) is True

    def test_next_opening_is_now(self):
        w = AvailabilityWindow()
        now = at(THU, 3)
        assert w.next_opening(now) == now

    def test_describe(self):
        assert AvailabilityWindow().describe() == '不限时段'


class TestDailyWindow:
    """每天固定时段, 如逢魔之时 17:00-23:00(用户告知的真实机制)。"""

    def w(self):
        return AvailabilityWindow(True, time(17, 0), time(23, 0))

    @pytest.mark.parametrize('h,inside', [
        (16, False), (17, True), (18, True), (22, True), (23, False), (0, False),
    ])
    def test_contains(self, h, inside):
        assert self.w().contains(at(THU, h)) is inside

    def test_next_opening_before_window(self):
        assert self.w().next_opening(at(THU, 10)) == at(THU, 17)

    def test_next_opening_after_window(self):
        """23:00 已过 -> 次日 17:00。"""
        assert self.w().next_opening(at(THU, 23, 30)) == at(FRI, 17)

    def test_next_opening_inside_window_is_now(self):
        now = at(THU, 18)
        assert self.w().next_opening(now) == now

    def test_duration(self):
        assert self.w().duration_minutes == 6 * 60

    def test_describe(self):
        assert self.w().describe() == '每天 17:00-23:00'


class TestCrossMidnight:
    """跨午夜窗口, 如 22:00-02:00。"""

    def w(self):
        return AvailabilityWindow(True, time(22, 0), time(2, 0))

    @pytest.mark.parametrize('h,inside', [
        (21, False), (22, True), (23, True), (0, True), (1, True), (2, False), (3, False),
    ])
    def test_contains(self, h, inside):
        assert self.w().contains(at(THU, h)) is inside

    def test_next_opening_before(self):
        assert self.w().next_opening(at(THU, 10)) == at(THU, 22)

    def test_next_opening_after(self):
        assert self.w().next_opening(at(THU, 3)) == at(THU, 22)

    def test_duration(self):
        assert self.w().duration_minutes == 4 * 60

    def test_describe_marks_cross_night(self):
        assert '跨夜' in self.w().describe()

    def test_next_closing_wraps_to_next_day(self):
        """22:30 时, 关闭时刻应是次日 02:00。"""
        assert self.w().next_closing(at(THU, 22, 30)) == at(FRI, 2)


class TestDayRestriction:
    """限定星期, 如狭间暗域只在周五/六/日。"""

    def w(self):
        return AvailabilityWindow(True, time(19, 0), time(21, 0), days=(4, 5, 6))

    def test_contains_only_listed_days(self):
        assert self.w().contains(at(FRI, 20)) is True   # 周五
        assert self.w().contains(at(SAT, 20)) is True   # 周六
        assert self.w().contains(at(THU, 20)) is False  # 周四

    def test_next_opening_skips_to_allowed_day(self):
        """周四 20:00 问 -> 应给周五 19:00(跳过周四)。"""
        assert self.w().next_opening(at(THU, 20)) == at(FRI, 19)

    def test_next_opening_from_wednesday(self):
        """周三 -> 周五。2026-10-07 是周三。"""
        wed = datetime(2026, 10, 7, 10, 0)
        assert self.w().next_opening(wed) == at(FRI, 19)

    def test_describe_lists_days(self):
        d = self.w().describe()
        assert '周五' in d and '周六' in d and '周日' in d
        assert '每天' not in d

    def test_invalid_days_rejected(self):
        with pytest.raises(ValueError):
            AvailabilityWindow(True, time(1), time(2), days=(7,))
        with pytest.raises(ValueError):
            AvailabilityWindow(True, time(1), time(2), days=())

    def test_all_days_described_as_daily(self):
        w = AvailabilityWindow(True, time(1), time(2), days=ALL_DAYS)
        assert w.describe().startswith('每天')


class TestWindowInScheduler:
    """窗口是**硬约束**: 不在时段内一律不跑。"""

    def res(self, **kw):
        return Resource(capacity=1, recharge=Recharge(period=Period.DAILY),
                        window=AvailabilityWindow(True, time(17, 0), time(23, 0)),
                        **kw)

    def test_blocked_outside_window(self):
        st = RunState(credits=1, refill_anchor=THU)
        now = at(THU, 10)
        nxt = next_available(self.res(), st, now)
        assert nxt == at(THU, 17), '应等到开放时刻, 而不是原地重试'

    def test_allowed_inside_window(self):
        st = RunState(credits=1, refill_anchor=THU)
        now = at(THU, 18)
        assert next_available(self.res(), st, now) == now

    def test_reason_mentions_window(self):
        st = RunState(credits=1, refill_anchor=THU)
        msg = cannot_run_reason(self.res(), st, at(THU, 10))
        assert msg and '不在开放时段' in msg
        assert '17:00-23:00' in msg

    def test_window_and_interval_are_independent(self):
        """
        关键设计: `window`(游戏机制, 硬) 与 `interval`(用户轮询, 软) 可以共存。

        这里 `interval=1h` 是用户为了"确保不错过"而设的轮询节奏;
        真正的允许时刻由 `window` 决定。
        """
        res = Resource(
            capacity=1,
            recharge=Recharge(kind='interval', interval=(0, 1, 0)),
            window=AvailabilityWindow(True, time(17, 0), time(23, 0)),
        )
        st = RunState(credits=0, refill_anchor=at(THU, 20, 0))
        # 冷却 1 小时 -> 21:00, 且仍在窗口内
        assert next_available(res, st, at(THU, 20, 30)) == at(THU, 21, 0)
        # 23:30 时冷却早已结束, 但窗口关了 -> 次日 17:00
        assert next_available(res, st, at(THU, 23, 30)) == at(FRI, 17)

    def test_window_with_exhausted_credits(self):
        """
        窗口内但额度用完 -> 等下一个周期**且要等到窗口开**。

        额度在次日 00:00 回满, 但窗口 17:00 才开, 所以最早能跑的是次日 17:00
        (而不是次日 00:00 —— 那一刻虽然有权重, 却不在开放时段内)。
        """
        st = RunState(credits=0, refill_anchor=THU)
        assert next_available(self.res(), st, at(THU, 18)) == at(FRI, 17)

    def test_next_opening_strict_skips_current_window(self):
        """
        `strict=True` 必须跳过当前窗口 —— 否则枚举候选点时会反复返回同一个 now,
        漏掉次日的开放点(踩过: next_available 跳到 32 天上界)。
        """
        w = AvailabilityWindow(True, time(17, 0), time(23, 0))
        inside = at(THU, 18)
        assert w.next_opening(inside) == inside            # 非严格: 就是现在
        assert w.next_opening(inside, strict=True) == at(FRI, 17)


class TestObservedWindow:
    """自学习: 从实际成功记录反推时段。"""

    def test_no_conclusion_without_enough_samples(self):
        ow = ObservedWindow()
        for h in (17, 18, 19):
            ow.observe(at(THU, h))
        assert ow.has_enough_data is False
        assert ow.infer() is None
        assert ow.suggest(AvailabilityWindow()) is None

    def test_infer_from_samples(self):
        ow = ObservedWindow()
        for h in (17, 18, 19, 20, 21, 22):
            ow.observe(at(THU, h))
        assert ow.has_enough_data is True
        w = ow.infer(pad_minutes=5)
        assert w is not None
        assert w.enabled is True
        # 最早样本 17:00 向前扩 5 分
        assert w.start == time(16, 55)
        # 最晚样本 22:00 向后扩 5 分
        assert w.end == time(22, 5)

    def test_infer_records_days(self):
        ow = ObservedWindow()
        for d in (FRI, SAT):
            for h in (19, 20, 21):
                ow.observe(at(d, h))
        w = ow.infer()
        assert set(w.days) == {4, 5}   # 周五(4)、周六(5)

    def test_suggest_when_unconfigured(self):
        ow = ObservedWindow()
        for h in (17, 18, 19, 20, 21):
            ow.observe(at(THU, h))
        msg = ow.suggest(AvailabilityWindow())      # 用户没配时段
        assert msg and '实测该任务只在' in msg

    def test_suggest_when_mismatched(self):
        ow = ObservedWindow()
        # 实测 17-22 点
        for h in (17, 18, 19, 20, 21, 22):
            ow.observe(at(THU, h))
        # 用户却配成 19-20 点(过窄)
        configured = AvailabilityWindow(True, time(19, 0), time(20, 0))
        msg = ow.suggest(configured)
        assert msg and '不符' in msg

    def test_no_suggestion_when_consistent(self):
        ow = ObservedWindow()
        for h in (18, 19, 20):
            ow.observe(at(THU, h))
        configured = AvailabilityWindow(True, time(17, 0), time(22, 0))
        assert ow.suggest(configured) is None

    def test_serialization_roundtrip(self):
        ow = ObservedWindow()
        ow.observe(at(THU, 18))
        ow.observe(at(FRI, 19))
        data = ow.to_dict()
        back = ObservedWindow.from_dict(data)
        assert back.count == 2
        assert back.days == ow.days
        assert back.samples == ow.samples

    def test_from_dict_handles_garbage(self):
        assert ObservedWindow.from_dict(None).count == 0
        assert ObservedWindow.from_dict({}).count == 0

    def test_samples_are_bounded(self):
        """样本量有上限, 防止状态文件无限膨胀。"""
        ow = ObservedWindow()
        for i in range(800):
            ow.observe(at(THU, 12))
        assert len(ow.samples) <= 500
        assert ow.count == 800


class TestDayNames:
    def test_constants(self):
        assert DAY_NAMES[0] == '周一'
        assert DAY_NAMES[6] == '周日'
        assert len(ALL_DAYS) == 7
