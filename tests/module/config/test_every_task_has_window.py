# -*- coding: utf-8 -*-
"""F2: **所有**定时任务都必须有开放时段（用户明确要求）。

## 用户原话

> "所有的定时都有着 window 属性"
> "我顺便发现了很多定时任务没有开放 window 和周期的设置"

## 为什么要测试

如果"没写 window"只是静默退化成"不限时段", 就**永远看不出有没有漏** ——
这正是本项目反复出现的**静默降级**缺陷模式（已知 4 例）。

所以本测试钉住: **54 个任务一个都不能缺窗口**,
并且**每个任务要么显式声明、要么能由周期推导**。
"""
import sys
from pathlib import Path

# ⚠ 本文件在 `tests/module/config/` -> 上溯 3 层才到仓库根。
#   （踩过两次: `tests/tasks/` 的文件要用 `parents[2]`, 这个要用 `parents[3]`。
#    写错会得到 `tests/` 或 `D:\OAS-dev`, 报 FileNotFoundError。）
REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pytest  # noqa: E402

from module.config import task_catalog as TC  # noqa: E402
from module.config.availability import (  # noqa: E402
    AvailabilityWindow, window_for_period)
from module.config.resource import Period  # noqa: E402


class TestEveryTaskHasWindow:
    """★ 核心不变量: **每个任务都有可用的开放时段**。"""

    def test_no_task_without_window(self):
        specs = TC._load_specs()
        assert specs, '一个任务都没加载到 —— 说明 catalog 坏了, 不是好事'
        missing = sorted(
            t for t, s in specs.items()
            if not any(w.enabled for w in s.windows_effective))
        assert not missing, (
            f'这些任务**没有**开放时段（既没显式声明, 也无法由周期推导）:\n'
            f'  {missing}\n'
            f'用户要求: "所有的定时都有着 window 属性"。\n'
            f'修法: 在 tasks/<Name>/meta.py 写 window=AvailabilityWindow(...), '
            f'或给 Resource.recharge 设 period=Period.DAILY/WEEKLY/MONTHLY。\n'
            f'自检: python dev_tools/check_windows.py')

    def test_declared_or_derived(self):
        """每个任务必须落在"显式声明"或"周期推导"之一 —— 不能是"都没有"。"""
        specs = TC._load_specs()
        undecided = sorted(
            t for t, s in specs.items()
            if s.declared_window is None
            and window_for_period(s.period_effective) is None)
        assert not undecided, f'这些任务既没声明也无法推导: {undecided}'

    def test_check_windows_script_passes(self):
        """★ `dev_tools/check_windows.py` 必须 exit 0（同一份审计, 供 CI/命令行用）。"""
        import importlib.util
        p = REPO / 'dev_tools' / 'check_windows.py'
        assert p.is_file(), '缺 check_windows.py'
        spec = importlib.util.spec_from_file_location('_cw', p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        r = mod.audit()
        assert not r['missing'], (
            f'check_windows 报告 {len(r["missing"])} 个任务缺窗口: {r["missing"]}')
        assert r['total'] == len(TC._load_specs())


class TestPeriodDerivation:
    """周期推导的规则（用户: 每日 0-24 / 每周 周一0点-周日24点 / 每月）。"""

    def test_daily_covers_all_days(self):
        w = window_for_period(Period.DAILY)
        assert w.enabled and set(w.days) == set(range(7))
        assert w.start.hour == 0 and w.start.minute == 0

    def test_weekly_covers_all_days(self):
        """一周 = 7 天, 所以 WEEKLY 的窗口也是全周（表达"节奏", 不是"限制几天"）。"""
        w = window_for_period(Period.WEEKLY)
        assert w.enabled and set(w.days) == set(range(7))

    def test_monthly_covers_whole_month(self):
        w = window_for_period(Period.MONTHLY)
        assert w.enabled
        assert set(w.days_of_month) == set(range(1, 32))

    def test_none_has_no_derivation(self):
        assert window_for_period(Period.NONE) is None

    def test_derived_windows_are_unrestricted(self):
        """★ 推导出来的窗口**不该**限制任何时刻（否则会改变既有行为）。"""
        from datetime import datetime
        for p in (Period.DAILY, Period.WEEKLY, Period.MONTHLY):
            w = window_for_period(p)
            assert w.is_unrestricted is True, f'{p} 推导出的窗口不该限制时刻'
            assert w.contains(datetime(2026, 10, 5, 3, 0)) is True
            assert w.contains(datetime(2026, 10, 5, 23, 58)) is True


class TestExplicitWindowsAreHonoured:
    """显式声明的**真实**活动窗口不能被推导覆盖。"""

    @pytest.mark.parametrize('task,keyword', [
        ('DemonEncounter', '17:00'),
        ('AbyssShadows', '19:00'),
        ('Hunt', '06:00'),
        # ★ `GuildBanquet` 是**动态窗口**（宴会日/时刻引用 `guild_banquet_time`）
        #   -> `window_describe` 显示"来自配置", 不含具体时刻。
        #   它的真实判定由 `Config.in_window()` 解析 `days_from_config` 完成
        #   （见 tests/module/config/test_dynamic_window.py）。
        ('DemonRetreat', '19:00'),
        ('Dokan', '19:00'),
        ('MysteryShop', '00:00'),
        ('Secret', '08:00'),
    ])
    def test_explicit_window_present(self, task, keyword):
        spec = TC.get_spec(task)
        assert spec is not None, f'{task} 不在 catalog 里'
        assert spec.declared_window is not None, f'{task} 应**显式**声明窗口'
        assert keyword in spec.window_describe, (
            f'{task} 的窗口描述里应有 {keyword}, 实际 {spec.window_describe!r}')

    def test_abyss_shadows_is_weekend_evening(self):
        spec = TC.get_spec('AbyssShadows')
        days = set()
        for w in spec.windows_effective:
            days |= set(w.days)
        assert days == {4, 5, 6}, f'狭间暗域应只在周五六日, 实际 {sorted(days)}'
