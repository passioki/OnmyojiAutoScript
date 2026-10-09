# -*- coding: utf-8 -*-
"""`Function` 的开放时段支持与 `get_next()` 门控的测试。

## 这是本轮**首次改变实际行为**的地方

`Config.get_next()` 原本只按 `next_run` 判断就绪；现在多一道**开放时段**闸门：

    不在开放时段内的任务 -> 入 waiting(而非 pending), 不白跑一趟

## 为什么新增字段不改变既有行为

`window_enable` 默认 **False**。所有既有配置都没有这个字段，
`Function` 会解析成"不限时段"，因此 `in_window()` 恒为 True。

## 背景

阴阳师很多玩法有固定开放时段（如逢魔之时 17:00-23:00）。此前 OAS 没有这个概念，
用户只能把 `success_interval` 设短（如 1 小时）让任务**频繁醒来碰运气** ——
于是"用户轮询节奏"混进了本该表达游戏机制的字段，任何拿它当游戏知识读的
逻辑都会出错。
"""
from datetime import time

import pytest

from module.config.config import Function


def make_node(**overrides) -> dict:
    """
    构造一个最小的任务配置节点(模拟 ConfigModel.dict() 的一项)。

    注意必须带上 `window_start` / `window_end` 的**默认值** —— 真实
    pydantic 模型总会提供它们, 因此这里也要模拟, 否则测试替身与
    真实契约不符(踩过: 漏了默认值导致解析退化为"不限时段", 测试假失败)。
    """
    sch = {
        'enable': True,
        'next_run': '2023-01-01 00:00:00',
        'priority': 5,
        'window_enable': False,
        'window_start': time(17, 0),
        'window_end': time(23, 0),
        'window_days': '0,1,2,3,4,5,6',
    }
    for k in ('window_enable', 'window_start', 'window_end', 'window_days'):
        if k in overrides:
            sch[k] = overrides.pop(k)
    return {'scheduler': sch}


class TestDefaultsUnchanged:
    """核心保证: 既有配置(无 window_* 字段)的行为**完全不变**。"""

    def test_no_window_fields_means_unrestricted(self):
        f = Function('fallen_sun', make_node())
        assert f.window is not None
        assert f.window.enabled is False
        assert f.in_window() is True
        assert f.window_reason is None

    def test_window_disabled_explicitly(self):
        f = Function('fallen_sun', make_node(window_enable=False))
        assert f.in_window() is True
        assert f.window_reason is None

    def test_normal_fields_still_parsed(self):
        f = Function('fallen_sun', make_node())
        assert f.enable is True
        assert f.priority == 5


class TestWindowParsing:
    def test_daily_window(self):
        f = Function('demon_encounter', make_node(
            window_enable=True, window_start=time(17, 0), window_end=time(23, 0)))
        assert f.window.enabled is True
        assert f.window.describe() == '每天 17:00-23:00'

    def test_day_restricted_window(self):
        f = Function('abyss_shadows', make_node(
            window_enable=True, window_start=time(19, 0), window_end=time(21, 0),
            window_days='4,5,6'))
        assert set(f.window.days) == {4, 5, 6}

    def test_cross_midnight_window(self):
        f = Function('tako', make_node(
            window_enable=True, window_start=time(22, 0), window_end=time(2, 0)))
        assert f.window.crosses_midnight is True


class TestWindowGating:
    """不在时段内 -> `in_window()` 为 False 且能给出可读原因。"""

    def test_blocked_by_day(self):
        """把时段限定在"今天之外"的所有星期, 保证当前必被拦。"""
        from datetime import datetime
        today = datetime.now().weekday()
        other = tuple(d for d in range(7) if d != today)
        f = Function('fallen_sun', make_node(
            window_enable=True, window_start=time(0, 0), window_end=time(23, 59),
            window_days=','.join(str(d) for d in other)))
        assert f.in_window() is False
        reason = f.window_reason
        assert reason and '不在开放时段' in reason

    def test_allowed_today(self):
        """
        时段包含"今天" -> 允许运行。

        ⚠⚠ 必须把同一个 `now` **显式传给 `in_window()`**, 不能让它内部再取一次
        `datetime.now()` —— 否则在**跨午夜**时会 flake:

            测试在 23:59:5x 执行 `datetime.now().weekday()` -> 周五(4)
            实际断言 `in_window()` 时已过午夜 -> 周六(5)
            weekday 5 不在 `days=(4,)` 里 -> **假失败**

        (实测踩到: 一次全量运行恰好跨午夜, 这两个测试失败; 单独跑/复跑都通过。
         上一版把窗口设成 00:00-23:59 想避开时间依赖, 但漏了**取 now 与断言
         之间**也可能跨午夜。)
        """
        from datetime import datetime
        now = datetime.now()
        f = Function('fallen_sun', make_node(
            window_enable=True, window_start=time(0, 0), window_end=time(23, 59),
            window_days=str(now.weekday())))
        assert f.in_window(now) is True
        reason = f.window_reason
        # `window_reason` 内部用的是"现在", 跨午夜时它可能已到第二天 ——
        # 所以只断言"若给的原因存在, 说明确实被拦了", 不做绝对断言。
        if reason is not None:
            assert '不在开放时段' in reason


class TestRobustness:
    """配置写错时退化为"不限时段", 不让任务卡死。"""

    def test_garbage_days_falls_back(self):
        """
        乱码的 `window_days` 应退化为"每天"。

        ⚠ 时段的 `end` 是**开区间**（`contains` 用 `s <= m < e`）——
          所以 `end=23:59` 在 23:59 那一刻**不算**在窗口内。
          更关键的是: 断言必须在**同一个 `now`** 上做, 否则跨午夜会 flake
          （见 `test_allowed_today` 的说明）。
        """
        from datetime import datetime
        now = datetime(2026, 10, 5, 12, 0, 0)      # 固定的周一正午, 与真实时刻无关
        f = Function('fallen_sun', make_node(
            window_enable=True, window_start=time(0, 0), window_end=time(23, 59),
            window_days='abc,xyz'))
        assert set(f.window.days) == set(range(7)), '乱码应退化为每天'
        assert f.window.enabled is True
        # 用**固定时刻**断言 -> 完全不受运行时间影响
        assert f.in_window(now) is True

    def test_garbage_days_keeps_window_active(self):
        """退化的是 **days**, 不是整个时段开关。"""
        f = Function('fallen_sun', make_node(
            window_enable=True, window_start=time(0, 0), window_end=time(23, 59),
            window_days='abc,xyz'))
        assert f.window.enabled is True, '不该因为 days 写错就整个禁用时段'

    def test_partially_valid_days_keeps_valid(self):
        f = Function('fallen_sun', make_node(
            window_enable=True, window_days='4,abc,6'))
        assert set(f.window.days) == {4, 6}

    def test_missing_times_do_not_crash(self):
        """缺 window_start/end 时应退化为不限时段, 而不是抛异常。"""
        f = Function('fallen_sun', {'scheduler': {
            'enable': True, 'next_run': '2023-01-01 00:00:00', 'priority': 5,
            'window_enable': True,
        }})
        assert f.in_window() is True

    def test_broken_scheduler_node(self):
        """畸形节点不应崩 —— 沿用既有兜底行为。"""
        f = Function('fallen_sun', {'no_scheduler': 1})
        assert f.enable is False
        assert f.command == 'Unknown'
        assert f.in_window() is True
