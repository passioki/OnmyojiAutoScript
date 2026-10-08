# -*- coding: utf-8 -*-
"""调度核心(scheduler_core + resource)的测试。

这是整个调度改造的**安全支点**: 新核心以纯函数形式先独立跑通,
不接线到 `get_next()`。因此这里必须覆盖足够多的边界。

## 被测试的核心主张

旧调度器用**一个标量间隔**表达"多久能跑一次", 导致:
  * "每天打 50 次"要拆成两个字段(`success_interval=1d` + `limit_count=50`)
  * "0/12 点各补 1 次"要靠另一套 `charge_*` 代码旁路

新模型用 `Resource` + `RunState` + `next_available()` 统一表达。
下面用**真实任务参数**验证它能正确复现各类任务的语义。
"""
from datetime import datetime, time, timedelta

import pytest

from module.config.resource import Period, Recharge, Resource
from module.config.scheduler_core import (
    RunState, cannot_run_reason, credits_at, next_available, remaining)


# --------------------------------------------------------------------- 真实任务参数
def R_fallen_sun() -> Resource:
    """日轮之陨: 每天打 50 次。旧代码 = success_interval=1d + limit_count=50。"""
    return Resource(capacity=50, recharge=Recharge(period=Period.DAILY))


def R_demon_encounter() -> Resource:
    """逢魔之时: 每 1 小时 1 次。旧代码 = success_interval=1h。"""
    return Resource(capacity=1, recharge=Recharge(kind='interval', interval=(0, 1, 0)))


def R_gold_youkai() -> Resource:
    """金币妖怪: 0 点 +1、12 点 +1, 上限 2。
    旧代码 = charge_slots='0,12' + charge_max=2 + charge_consume=1。

    `refill_to_full=True`: 游戏语义是"补充时刻**回满**可用次数"。"""
    return Resource(capacity=2,
                    recharge=Recharge(kind='slots', slots=((0, 0), (12, 0)),
                                      refill_to_full=True))


def R_true_orochi() -> Resource:
    """真八岐大蛇: 每周 2 次(用户确认)。"""
    return Resource(capacity=2, recharge=Recharge(period=Period.WEEKLY))


def R_activity() -> Resource:
    """限时活动(如超鬼王): 活动期内每天 1 次额度。"""
    return Resource(capacity=1, recharge=Recharge(kind='window', period=Period.DAILY))


D0 = datetime(2026, 10, 8, 0, 0)          # 周四 0 点
T10 = datetime(2026, 10, 8, 10, 0)


class TestFallenSun:
    """每天 50 次 —— 验证"周期回满"语义。"""

    def test_full_at_day_start(self):
        st = RunState(credits=50, refill_anchor=D0)
        assert credits_at(R_fallen_sun(), st, T10) == 50
        assert next_available(R_fallen_sun(), st, T10) == T10
        assert cannot_run_reason(R_fallen_sun(), st, T10) is None

    def test_exhausted_waits_next_period(self):
        st = RunState(credits=0, refill_anchor=D0)
        assert credits_at(R_fallen_sun(), st, T10) == 0
        assert next_available(R_fallen_sun(), st, T10) == datetime(2026, 10, 9, 0, 0)

    def test_refilled_next_day(self):
        st = RunState(credits=0, refill_anchor=D0)
        nxt = datetime(2026, 10, 9, 0, 0)
        assert credits_at(R_fallen_sun(), st, nxt) == 50
        assert next_available(R_fallen_sun(), st, nxt) == nxt

    def test_partial_credits_allow_run(self):
        st = RunState(credits=1, refill_anchor=D0)
        assert next_available(R_fallen_sun(), st, T10) == T10

    def test_reset_at_respected(self):
        """自定义重置点 05:00: 04:00 仍属前一日, 06:00 才算新周期。"""
        res = Resource(capacity=50,
                       recharge=Recharge(period=Period.DAILY, reset_at=time(5, 0)))
        st = RunState(credits=0, refill_anchor=datetime(2026, 10, 8, 5, 0))
        assert credits_at(res, st, datetime(2026, 10, 9, 4, 0)) == 0
        assert credits_at(res, st, datetime(2026, 10, 9, 6, 0)) == 50


class TestDemonEncounter:
    """每 1 小时 1 次 —— 验证"间隔补充"语义。"""

    def test_cooldown(self):
        last = datetime(2026, 10, 8, 10, 0)
        st = RunState(credits=0, refill_anchor=last)
        assert next_available(R_demon_encounter(), st, last) == last + timedelta(hours=1)
        assert credits_at(R_demon_encounter(), st,
                          last + timedelta(minutes=30)) == 0
        assert credits_at(R_demon_encounter(), st,
                          last + timedelta(hours=1)) == 1

    def test_does_not_accumulate(self):
        """容量 1: 久不运行也只积 1 次。"""
        last = datetime(2026, 10, 8, 10, 0)
        st = RunState(credits=0, refill_anchor=last)
        assert credits_at(R_demon_encounter(), st,
                          last + timedelta(hours=10)) == 1

    def test_next_available_is_exact(self):
        last = datetime(2026, 10, 8, 10, 0)
        st = RunState(credits=0, refill_anchor=last)
        # 从 +30min 问, 应精确到 +1h 那一刻(不是 +59s 或 +1h1s)
        assert next_available(R_demon_encounter(), st,
                              last + timedelta(minutes=30)) == last + timedelta(hours=1)

    def test_consume_updates_anchor(self):
        """interval 形态: 锚点是"上次运行时刻"(相对时间)。"""
        st = RunState(credits=1, refill_anchor=D0)
        st2 = st.consumed(R_demon_encounter(), at=T10)
        assert st2.refill_anchor == T10
        assert st2.credits == 0


class TestGoldYoukai:
    """0/12 点各补 1, 上限 2 —— 验证"固定时刻补充"语义。"""

    def test_full_after_first_slot(self):
        st = RunState(credits=0, refill_anchor=datetime(2026, 10, 7, 23, 0))
        assert credits_at(R_gold_youkai(), st, datetime(2026, 10, 8, 0, 1)) == 2

    def test_capped_at_capacity(self):
        st = RunState(credits=0, refill_anchor=datetime(2026, 10, 7, 23, 0))
        assert credits_at(R_gold_youkai(), st, datetime(2026, 10, 8, 13, 0)) == 2

    def test_partial_credits_allow_run_immediately(self):
        st = RunState(credits=1, refill_anchor=D0)
        assert next_available(R_gold_youkai(), st, datetime(2026, 10, 8, 1, 0)) \
            == datetime(2026, 10, 8, 1, 0)

    def test_next_slot_is_exact(self):
        """
        0 点用掉一次(credits 归 0, 锚点=0 点)后, 下一次可用**正好是 12:00**。

        这是修复后的行为: 补充时刻 12:00 的那次补充在 12:00 整即生效,
        不再要求等到 12:00:00.000001。
        """
        st = RunState(credits=0, refill_anchor=D0)
        nxt = next_available(R_gold_youkai(), st, datetime(2026, 10, 8, 1, 0))
        assert nxt == datetime(2026, 10, 8, 12, 0)

    def test_credits_increase_after_slot(self):
        st = RunState(credits=0, refill_anchor=D0)
        before = datetime(2026, 10, 8, 11, 59, 59)
        after = datetime(2026, 10, 8, 12, 0, 1)
        assert credits_at(R_gold_youkai(), st, before) == 0
        assert credits_at(R_gold_youkai(), st, after) == 2

    def test_consume_keeps_anchor(self):
        """slots 形态: 锚点不被消耗改变(补充是绝对时刻)。"""
        st = RunState(credits=2, refill_anchor=D0)
        st2 = st.consumed(R_gold_youkai(), at=T10)
        assert st2.refill_anchor == D0
        assert st2.credits == 1


class TestTrueOrochi:
    """每周 2 次 —— 验证"周周期"语义。"""

    def test_week_starts_monday(self):
        res = R_true_orochi()
        assert res.period_start(datetime(2026, 10, 8, 15, 0)) == datetime(2026, 10, 5)
        assert res.next_period_start(datetime(2026, 10, 8, 15, 0)) \
            == datetime(2026, 10, 12)

    def test_exhausted_waits_next_week(self):
        st = RunState(credits=0, refill_anchor=datetime(2026, 10, 5))
        assert next_available(R_true_orochi(), st, datetime(2026, 10, 8, 15, 0)) \
            == datetime(2026, 10, 12)

    def test_refilled_next_week(self):
        st = RunState(credits=0, refill_anchor=datetime(2026, 10, 5))
        assert credits_at(R_true_orochi(), st, datetime(2026, 10, 12, 0, 1)) == 2

    def test_one_left_allows_run(self):
        st = RunState(credits=1, refill_anchor=datetime(2026, 10, 5))
        assert next_available(R_true_orochi(), st, datetime(2026, 10, 8, 15, 0)) \
            == datetime(2026, 10, 8, 15, 0)


class TestActivityWindow:
    """限时活动 —— 活动期是"闸门", 与额度无关。"""

    def test_open_and_has_credit(self):
        st = RunState(credits=1, refill_anchor=D0)
        assert next_available(R_activity(), st, T10, window_open=True) == T10
        assert cannot_run_reason(R_activity(), st, T10, window_open=True) is None

    def test_closed_blocks(self):
        st = RunState(credits=1, refill_anchor=D0)
        nxt = next_available(R_activity(), st, T10, window_open=False)
        assert nxt > T10
        assert cannot_run_reason(R_activity(), st, T10, window_open=False) == '不在活动期'

    def test_credit_refills_daily(self):
        """额度按周期回满 —— 否则跑过一次就永远不可用。"""
        st = RunState(credits=0, refill_anchor=D0)
        assert credits_at(R_activity(), st, T10) == 0
        assert credits_at(R_activity(), st, datetime(2026, 10, 9, 1, 0)) == 1


class TestRetryBackoff:
    """失败重试退避 —— 与资源无关的独立概念(原名 failure_interval 会误导)。"""

    def test_backoff_blocks(self):
        st = RunState(credits=1, refill_anchor=D0)
        st_r = st.mark_failure(R_fallen_sun(), at=T10, retry=timedelta(minutes=30))
        assert next_available(R_fallen_sun(), st_r, T10) == T10 + timedelta(minutes=30)

    def test_backoff_does_not_consume_credit(self):
        st = RunState(credits=1, refill_anchor=D0)
        st_r = st.mark_failure(R_fallen_sun(), at=T10, retry=timedelta(minutes=30))
        assert credits_at(R_fallen_sun(), st_r, T10) == 1

    def test_reason_mentions_backoff(self):
        st = RunState(credits=1, refill_anchor=D0)
        st_r = st.mark_failure(R_fallen_sun(), at=T10, retry=timedelta(minutes=30))
        assert '退避' in cannot_run_reason(R_fallen_sun(), st_r, T10)


class TestStateIsImmutable:
    def test_consumed_returns_new_object(self):
        st = RunState(credits=3, refill_anchor=D0)
        st2 = st.consumed(R_gold_youkai(), at=T10)
        assert st.credits == 3
        assert st2.credits == 2
        assert st is not st2

    def test_with_credits_clamps_at_zero(self):
        st = RunState(credits=1, refill_anchor=D0)
        assert st.with_credits(-5).credits == 0


class TestResourceValidation:
    """
    非法构造必须给出 **ValueError**。

    注意 `Recharge` 的校验发生在**构造时**, 所以这些用例必须把"构造动作"
    推迟到 `pytest.raises` **内部**执行 —— 若把 `Recharge(...)` 直接写进
    parametrize 列表, 异常会在**收集阶段**抛出, 导致整个模块 import 失败;
    若在 `pytest.raises` 之前就调用, 则异常逃逸, 断言到的是外层错误。
    因此统一传"零参构造函数"。
    """

    @pytest.mark.parametrize('make_kwargs', [
        lambda: dict(capacity=0),
        lambda: dict(consume=0),
        lambda: dict(capacity=2, consume=3),   # consume > capacity 会永远跑不起来
        # --- Recharge 自身的非法构造 ---
        lambda: dict(recharge=Recharge(kind='interval')),               # 缺 interval
        lambda: dict(recharge=Recharge(kind='slots')),                  # 缺 slots
        lambda: dict(recharge=Recharge(kind='slots', slots=((25, 0),))),  # 非法小时
        lambda: dict(recharge=Recharge(kind='slots', slots=((0, 61),))),  # 非法分钟
        lambda: dict(recharge=Recharge(kind='unknown')),                # 未知 kind
        lambda: dict(recharge=Recharge(amount=0)),                      # amount < 1
        # --- 畸形 slot 也要 ValueError 而不是 TypeError ---
        lambda: dict(recharge=Recharge(kind='slots', slots=(25,))),
        lambda: dict(recharge=Recharge(kind='slots', slots=((1, 2, 3),))),
    ])
    def test_invalid_raises(self, make_kwargs):
        with pytest.raises(ValueError):
            kwargs = make_kwargs()
            Resource(**kwargs)

    def test_valid_minimal(self):
        assert Resource().capacity == 1
        assert Resource().refill == 'none'


class TestSlotsBetween:
    """`start < slot <= end`(默认 include_end=True)。

    踩过的坑: 曾用单一 `[start, end)` 语义, 调用方靠"start 加 1 微秒"回避锚点
    重复计数 —— 结果把 end 侧恰好落在 slot 上的那次也排除了, 使额度要等到
    slot **之后**才生效, `next_available` 于是跳到下一个 slot
    (12:00 整不可行、12:00:01 才行)。现改为显式 `include_end`。
    """

    def test_include_end_default(self):
        res = R_gold_youkai()
        # start=00:00 之后的 slot 是 12:00; end=12:00 时它已发生 -> 计入
        assert res.slots_between(datetime(2026, 10, 8, 0, 0),
                                 datetime(2026, 10, 8, 12, 0)) == 1
        # 跨过 12:00 -> 仍是 1(00:00 是起点, 计入其后; 下一个 slot 是次日 00:00)
        assert res.slots_between(datetime(2026, 10, 8, 0, 0),
                                 datetime(2026, 10, 8, 12, 0, 1)) == 1
        # 跨到次日 -> 两个(12:00 与次日 00:00)
        assert res.slots_between(datetime(2026, 10, 8, 0, 0),
                                 datetime(2026, 10, 9, 0, 0)) == 2
        # end 还没到 12:00 -> 0 个
        assert res.slots_between(datetime(2026, 10, 8, 0, 0),
                                 datetime(2026, 10, 8, 11, 59)) == 0

    def test_exclude_end(self):
        res = R_gold_youkai()
        assert res.slots_between(datetime(2026, 10, 8, 0, 0),
                                 datetime(2026, 10, 8, 12, 0),
                                 include_end=False) == 0
        assert res.slots_between(datetime(2026, 10, 8, 0, 0),
                                 datetime(2026, 10, 8, 12, 0, 1),
                                 include_end=False) == 1

    def test_start_is_exclusive(self):
        """锚点本身是"已结算点", 其 slot 不计入。"""
        res = R_gold_youkai()
        # start 恰在 00:00 这个 slot 上 -> 不算; 只有 12:00 算
        assert res.slots_between(datetime(2026, 10, 8, 0, 0),
                                 datetime(2026, 10, 8, 23, 59)) == 1

    def test_cross_midnight(self):
        res = R_gold_youkai()
        assert res.slots_between(datetime(2026, 10, 7, 23, 0),
                                 datetime(2026, 10, 8, 0, 1)) == 1

    def test_empty_when_reversed(self):
        res = R_gold_youkai()
        assert res.slots_between(datetime(2026, 10, 8, 5, 0),
                                 datetime(2026, 10, 8, 5, 0)) == 0


class TestRobustness:
    def test_clock_rollback(self):
        """now 早于锚点(时钟回拨)不应崩, 也不应出现负数。"""
        st = RunState(credits=2, refill_anchor=datetime(2026, 10, 9))
        assert credits_at(R_fallen_sun(), st, T10) == 2

    def test_no_anchor_uses_period_start(self):
        st = RunState(credits=0, refill_anchor=None)
        assert credits_at(R_fallen_sun(), st, T10) == 0

    def test_consume_more_than_credit(self):
        res = Resource(capacity=4, consume=2, recharge=Recharge(period=Period.DAILY))
        assert next_available(res, RunState(credits=1, refill_anchor=D0), T10) > T10
        assert next_available(res, RunState(credits=2, refill_anchor=D0), T10) == T10

    def test_remaining_alias(self):
        st = RunState(credits=7, refill_anchor=D0)
        assert remaining(R_fallen_sun(), st, T10) == 7


class TestReasonMessages:
    """`cannot_run_reason` 是界面显示与排障的依据, 要能说清"为什么不能跑"。"""

    def test_period_exhausted(self):
        st = RunState(credits=0, refill_anchor=D0)
        msg = cannot_run_reason(R_fallen_sun(), st, T10)
        assert msg and '本周期已用完' in msg

    def test_slot_waiting(self):
        st = RunState(credits=0, refill_anchor=datetime(2026, 10, 8, 0, 0, 0, 1))
        msg = cannot_run_reason(R_gold_youkai(), st, datetime(2026, 10, 8, 1, 0))
        assert msg and '等待补充' in msg

    def test_interval_cooldown(self):
        st = RunState(credits=0, refill_anchor=T10)
        msg = cannot_run_reason(R_demon_encounter(), st, T10)
        assert msg and '等待冷却' in msg

    def test_runnable_returns_none(self):
        st = RunState(credits=1, refill_anchor=D0)
        assert cannot_run_reason(R_fallen_sun(), st, T10) is None


class TestFromLegacy:
    """`Resource.from_legacy` 是迁移桥梁: 从旧的分散字段推导规则。"""

    def test_daily_interval_becomes_period(self):
        res = Resource.from_legacy(success_interval='01 00:00:00', count_default=50)
        assert res.period == Period.DAILY
        assert res.capacity == 50
        assert res.refill == 'none'

    def test_weekly_interval(self):
        res = Resource.from_legacy(success_interval='07 00:00:00', count_default=1)
        assert res.period == Period.WEEKLY

    def test_hourly_interval_stays_interval(self):
        res = Resource.from_legacy(success_interval='00 03:00:00', count_default=1)
        assert res.refill == 'interval'
        assert res.interval == (0, 3, 0)
        assert res.recharge.period == Period.NONE

    def test_charge_slots(self):
        res = Resource.from_legacy(charge_slots='0,12', charge_max=2,
                                   charge_consume=1)
        assert res.refill == 'slots'
        assert res.slots == ((0, 0), (12, 0))
        assert res.capacity == 2
        assert res.recharge.period == Period.NONE

    def test_limited_becomes_window(self):
        res = Resource.from_legacy(category='limited')
        assert res.refill == 'window'
        assert res.capacity == 1
        assert res.period == Period.DAILY, '额度需按周期回满, 否则跑一次就永不可用'
