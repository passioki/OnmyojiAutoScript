# -*- coding: utf-8 -*-
"""#7: `Function` 必须支持**精确多段窗口**（不能压成有损并集）。

## 修的是什么（实测）

`Hunt` 的窗口是**两段**:

    周一~周四 06:00-23:00  +  周五~周日 17:00-23:00

而 `Function._build_window()` 曾用**并集**表达成单段:

    每天 06:00-23:00      ← **丢了** "周五六日下午才开放"

后果: **周五 10:00 被判成"在窗口内"**, 但那时根本不能跑（要 17:00 后）。
布尔判断**偏宽**（漏拦）, `next_opening` 也不准。

## 现在的契约

* `Function.windows` 是**一串**（精确保留每段）
* `in_window()` **逐段取或** —— 任一段命中即可
* `Function.window` 保留为**第一段**（兼容旧调用方）
* `window_reason` 列出**所有**段, 取**最早**的下次开放
"""
import sys
from datetime import datetime, time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture()
def hunt():
    """真实 `Hunt` 的 `Function`（两段窗口）。"""
    import logging
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.config.config import Function
    from module.server.main_manager import mm

    cfg = mm.config_cache('恋鸟树')
    raw = cfg.model.model_dump()
    if 'hunt' not in raw:
        pytest.skip('配置里没有 hunt')
    return Function('hunt', raw['hunt'])


class TestMultiSegmentWindows:
    def test_keeps_all_segments(self, hunt):
        """★ 段数必须是 **2**, 不能被并成 1。"""
        assert len(hunt.windows) == 2, (
            f'应保留 2 段, 实际 {len(hunt.windows)}: '
            f'{[w.describe() for w in hunt.windows]}')

    def test_segments_match_the_declared_meta(self, hunt):
        from module.config import task_catalog as TC
        spec = TC.get_spec('Hunt')
        expect = {w.describe() for w in spec.windows_effective}
        got = {w.describe() for w in hunt.windows}
        assert got == expect, f'段不一致\n  期望: {expect}\n  实际: {got}'

    def test_friday_morning_is_outside(self, hunt):
        """★★ 核心回归: 周五 10:00 **不在**窗口内。

        修复前（有损并集"每天 06:00-23:00"）这里会返回 `True`。
        """
        # 2026-10-09 是周五
        fri = datetime(2026, 10, 9, 10, 0)
        assert fri.weekday() == 4, '前提: 2026-10-09 是周五'
        assert hunt.in_window(fri) is False, (
            '周五 10:00 被判成在窗口内 —— 说明多段又被并成单段了')

    def test_friday_evening_is_inside(self, hunt):
        fri = datetime(2026, 10, 9, 18, 0)
        assert hunt.in_window(fri) is True

    def test_monday_morning_is_inside(self, hunt):
        """周一~周四 06:00-23:00 -> 上午也在窗口内。"""
        mon = datetime(2026, 10, 5, 10, 0)
        assert mon.weekday() == 0, '前提: 2026-10-05 是周一'
        assert hunt.in_window(mon) is True

    def test_monday_early_morning_is_outside(self, hunt):
        """周一 05:00 还没开放（06:00 才开）。"""
        mon = datetime(2026, 10, 5, 5, 0)
        assert hunt.in_window(mon) is False

    def test_weekend_early_morning_is_outside(self, hunt):
        """周日 05:00 也不在（周末要 17:00 才开）。"""
        sun = datetime(2026, 10, 11, 5, 0)
        assert sun.weekday() == 6, '前提: 2026-10-11 是周日'
        assert hunt.in_window(sun) is False

    def test_in_window_is_or_of_segments(self, hunt):
        """★ `in_window` 必须等于"任一段命中"（逐段取或）。"""
        for day in range(5, 12):          # 10-05 ~ 10-11（周一到周日）
            for hour in (5, 10, 18, 23):
                when = datetime(2026, 10, day, hour, 0)
                expect = any(w.contains(when) for w in hunt.windows)
                assert hunt.in_window(when) == expect, (
                    f'{when} 的 in_window 与"逐段取或"不一致')


class TestWindowCompat:
    """`window` 保留为第一段 —— 旧调用方不该坏。"""

    def test_window_is_first_segment(self, hunt):
        assert hunt.window is hunt.windows[0]

    def test_window_reason_lists_all_segments(self, hunt):
        """★ 原因里要能看到**所有**段（否则用户不知道为什么不能跑）。"""
        fri = datetime(2026, 10, 9, 10, 0)
        import unittest.mock as mock
        # `window_reason` 内部取 now -> 打桩
        with mock.patch('module.config.config.datetime') as md:
            md.now.return_value = fri
            md.side_effect = lambda *a, **k: datetime(*a, **k)
            md.strptime = datetime.strptime
            got = hunt.window_reason
        assert got, '周五 10:00 应该给出"不在开放时段"的原因'
        assert '06:00-23:00' in got
        assert '17:00-23:00' in got, f'原因里缺第二段: {got}'

    def test_no_windows_means_unrestricted(self):
        """没有启用中的时段 -> 恒 True（不限时段）。"""
        from module.config.config import Function
        f = Function('orochi', {'scheduler': {
            'enable': True, 'next_run': '2023-01-01 00:00:00', 'priority': 5}})
        assert f.in_window() is True
        assert f.window_reason is None


class TestEveryTaskSegmentsPreserved:
    """★ 反向守卫: **所有**任务的多段都要被保留（不只 Hunt）。"""

    def test_no_task_loses_segments(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.config.config import Function
        from module.config import task_catalog as TC
        from module.server.main_manager import mm

        cfg = mm.config_cache('恋鸟树')
        raw = cfg.model.model_dump()
        lost = []
        for key, val in raw.items():
            meta = TC.get(key)
            if meta is None:
                continue
            # ⚠ `TC.get()` 返回 **TaskMeta**（没有 `windows_effective`）——
            #   `windows_effective` 在 **TaskSpec** 上, 要用 `TC.get_spec()`。
            #   （踩过: 直接对 TaskMeta 取该属性 -> AttributeError）
            spec = TC.get_spec(meta.task)
            if spec is None:
                continue
            expect = len([w for w in spec.windows_effective if w.enabled])
            if expect <= 1:
                continue
            try:
                f = Function(key, val)
            except Exception:
                continue
            if len(f.windows) != expect:
                lost.append((key, expect, len(f.windows)))
        assert not lost, (
            f'这些任务的多段窗口被压缩了 (任务, 应有, 实际): {lost}')
