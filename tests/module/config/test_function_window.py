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

    ## ★★ S3: 单值 `window_*` 已删除 -> 改用 `windows` 列表 ★★

    用户裁定: "不是 window slots, 而是**设置多个 window**！"
    `windows` 是 `List[TaskWindow]`, 传 `windows=[{...}]` 即可。

    ★ 仍然允许**任意**调度器字段覆盖 —— 白名单会让新字段被**静默丢弃**
      （踩过: 测试说设了 weekly 其实还是 daily）。
    """
    sch = {
        'enable': True,
        'next_run': '2023-01-01 00:00:00',
        'priority': 5,
        # ★ 空 `windows` = 用户没配 -> 回退 `meta.py` 的游戏机制窗口
        'windows': [],
    }
    for k in list(overrides):
        sch[k] = overrides.pop(k)
    return {'scheduler': sch}


def win(start, end, period='daily', days='', dom='', enabled=True, wid='w'):
    """构造一条 `TaskWindow`（dict 形式, 与 `model_dump()` 一致）。"""
    return {'id': wid, 'enabled': enabled, 'period': period,
            'start': start, 'end': end, 'days': days, 'days_of_month': dom}


class TestMetaWindowPriority:
    """★★ 优先级（#1 已**调正**）: **用户配置优先**, `meta.py` 兜底 ★★

    ★ 此前是反的（meta 永远压过用户）—— 实测用户把窗口改成 17:00-23:00
      **完全没用**。用户原话:
        "用户可以选择每天, 然后把时间改为 17-23 点"

    ## 为什么这里必须改（曾经的假设已经不成立）

    原版类名叫 `TestDefaultsUnchanged`, 断言是"既有配置（无 `window_*` 字段）
    的行为完全不变 -> `f.window.enabled is False`"。

    那个前提**已经不存在**: 用户明确要求

        所有的定时都有着 window 属性

    所以 `Function._build_window()` 现在**优先读 `TaskSpec.window`**,
    `FallenSun` / `Tako` 这些任务在 `meta.py` 里已有窗口 ->
    `scheduler.window_*` **不再生效**（那是旧机制的遗留字段, 4-E 已从界面移除）。

    ★ 但仍然要保证: **没有 `meta.py` 窗口时, `scheduler.window_*` 照旧生效**
      （见 `TestSchedulerConfigFallback`）—— 那是配置项路径, 不能坏。
    """

    def test_user_config_wins_over_meta(self):
        """★ #1: 用户**启用**了窗口 -> **以用户为准**（meta 只兜底）。"""
        f = Function('fallen_sun', make_node(
            windows=[win('22:00:00', '02:00:00')]))
        assert f.window is not None and f.window.enabled is True
        assert f.window.crosses_midnight is True, (
            '用户配置的 22:00-02:00 应生效（跨午夜）')

    def test_meta_used_when_user_disabled(self):
        """★ #1: 用户**没启用** -> 用 meta 的窗口兜底。"""
        f = Function('fallen_sun', make_node(windows=[]))
        assert f.window is not None and f.window.enabled is True, (
            '用户没启用时应有 meta 窗口兜底')

    def test_normal_fields_still_parsed(self):
        f = Function('fallen_sun', make_node())
        assert f.enable is True
        assert f.priority == 5


class TestSchedulerConfigFallback:
    """没有 `meta.py` 窗口时, `scheduler.window_*`（配置项）**照旧生效**。

    ★ 为什么要 monkeypatch: 54 个任务**全部**都有 `meta.py` 了
      （F2c 补齐），所以**没有真实任务**能走"配置项"这条路。
      而合成任务名走不通 —— `ConfigModel.type()` 对未知任务名抛 `KeyError`。

      所以用 monkeypatch 把 `TC.get_spec` 变成"查不到"，
      等价于"这个任务没写 meta.py"，从而测到回退分支。
    """

    @pytest.fixture()
    def no_meta(self, monkeypatch):
        """让 `TC.get_spec` 恒返回 None -> 走 `scheduler.window_*` 回退。"""
        import module.config.config as cfgmod
        monkeypatch.setattr(cfgmod, '_spec_for_tests', None, raising=False)

        from module.config import task_catalog as TC
        monkeypatch.setattr(TC, 'get_spec', lambda task: None)
        return None

    def test_no_meta_means_unrestricted(self, no_meta):
        f = Function('fallen_sun', make_node())
        assert f.window is not None
        assert f.window.enabled is False
        assert f.in_window() is True
        assert f.window_reason is None

    def test_window_disabled_explicitly(self, no_meta):
        f = Function('fallen_sun', make_node(windows=[]))
        assert f.in_window() is True
        assert f.window_reason is None

    def test_config_window_is_honoured(self, no_meta):
        f = Function('fallen_sun', make_node(windows=[win('17:00:00', '23:00:00')]))
        assert f.window.enabled is True
        assert f.window.describe() == '每天 17:00-23:00'

    def test_cross_midnight_from_config(self, no_meta):
        f = Function('fallen_sun', make_node(
            windows=[win('22:00:00', '02:00:00')]))
        assert f.window.crosses_midnight is True

    def test_partially_valid_days_keeps_valid(self, no_meta):
        """`'4,abc,6'` -> 有效项保留（4/6）, 无效项忽略。"""
        # ★ #1: `window_days` 只在 `window_period='weekly'` 时生效
        f = Function('fallen_sun', make_node(
            windows=[win('17:00:00', '23:00:00', period='weekly',
                         days='4,abc,6')]))
        assert set(f.window.days) == {4, 6}


class TestWindowGating:
    """不在时段内 -> `in_window()` 为 False 且能给出可读原因。"""

    @pytest.fixture()
    def no_meta(self, monkeypatch):
        """屏蔽 `meta.py` -> 走 `scheduler.window_*` 配置项路径。"""
        from module.config import task_catalog as TC
        monkeypatch.setattr(TC, 'get_spec', lambda task: None)
        return None

    def test_blocked_by_day(self, no_meta):
        """把时段限定在"今天之外"的所有星期, 保证当前必被拦。

        ★ 需要 `no_meta`: 真实任务的 `meta.py` 会覆盖配置项
          （`FallenSun` 有整天窗口 -> 恒允许）。
        """
        from datetime import datetime
        today = datetime.now().weekday()
        other = tuple(d for d in range(7) if d != today)
        f = Function('fallen_sun', make_node(
            # ★ S3: 单值 `window_*` 已删除 -> 用 `windows` 列表。
            #   `days` 只在 `period=weekly` 时生效。
            windows=[win('00:00:00', '23:59:00', period='weekly',
                         days=','.join(str(d) for d in other))]))
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
            windows=[win('00:00:00', '23:59:00', period='weekly',
                         days=str(now.weekday()))]))
        assert f.in_window(now) is True
        reason = f.window_reason
        # `window_reason` 内部用的是"现在", 跨午夜时它可能已到第二天 ——
        # 所以只断言"若给的原因存在, 说明确实被拦了", 不做绝对断言。
        if reason is not None:
            assert '不在开放时段' in reason


class TestRobustness:
    """配置写错时退化为"不限时段", 不让任务卡死。

    ★ 需要 `no_meta`: 这里测的是 **`scheduler.window_*` 配置项**路径,
      真实任务的 `meta.py` 会覆盖它。
    """

    @pytest.fixture()
    def no_meta(self, monkeypatch):
        from module.config import task_catalog as TC
        monkeypatch.setattr(TC, 'get_spec', lambda task: None)
        return None

    def test_garbage_days_falls_back(self, no_meta):
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
            windows=[win('00:00:00', '23:59:00', period='weekly',
                         days='abc,xyz')]))
        assert set(f.window.days) == set(range(7)), '乱码应退化为每天'
        assert f.window.enabled is True
        # 用**固定时刻**断言 -> 完全不受运行时间影响
        assert f.in_window(now) is True

    def test_garbage_days_keeps_window_active(self, no_meta):
        """退化的是 **days**, 不是整个时段开关。"""
        f = Function('fallen_sun', make_node(
            windows=[win('00:00:00', '23:59:00', period='weekly',
                         days='abc,xyz')]))
        assert f.window.enabled is True, '不该因为 days 写错就整个禁用时段'

    def test_partially_valid_days_keeps_valid(self, no_meta):
        # ★ #1: `window_days` 只在 `window_period='weekly'` 时生效
        f = Function('fallen_sun', make_node(
            windows=[win('17:00:00', '23:00:00', period='weekly',
                         days='4,abc,6')]))
        assert set(f.window.days) == {4, 6}

    def test_missing_times_do_not_crash(self, no_meta):
        """缺 window_start/end 时应退化为不限时段, 而不是抛异常。"""
        f = Function('fallen_sun', {'scheduler': {
            'enable': True, 'next_run': '2023-01-01 00:00:00', 'priority': 5,
            'window_enable': True,
        }})
        assert f.in_window() is True

    def test_broken_scheduler_node(self, no_meta):
        """畸形节点不应崩 —— 沿用既有兜底行为。"""
        f = Function('fallen_sun', {'no_scheduler': 1})
        assert f.enable is False
        assert f.command == 'Unknown'
        assert f.in_window() is True
