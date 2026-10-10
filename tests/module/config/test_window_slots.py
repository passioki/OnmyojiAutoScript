# -*- coding: utf-8 -*-
"""旧的 `window_slots` 字段**已废弃**（S3）-> 本文件重写为**多窗口**测试。

用户裁定:
> "不是 window slots, 而是**设置多个 window**！slots 不是已经废弃了吗"
> "一天跑两次 = **两个窗口**"
"""
import sys
from datetime import datetime, time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _win(start, end, period='daily', days='', dom='', enabled=True,
         wid='w'):
    return {'id': wid, 'enabled': enabled, 'period': period,
            'start': start, 'end': end, 'days': days, 'days_of_month': dom}


def _fn(windows, task='restart'):
    import copy
    import logging
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.config.config import Function
    from module.server.main_manager import mm

    cfg = mm.config_cache('恋鸟树')
    raw = copy.deepcopy(cfg.model.model_dump())
    d = copy.deepcopy(raw[task])
    d['scheduler'] = dict(d['scheduler'])
    d['scheduler']['windows'] = windows
    return Function(task, d)


class TestWindowSlotsRemoved:
    """★ S3: `window_slots` 字段**必须不存在**了。"""

    def test_field_gone(self):
        from tasks.Component.config_scheduler import Scheduler
        assert 'window_slots' not in Scheduler.model_fields, \
            'window_slots 已废弃, 不该还在'

    def test_single_value_fields_gone(self):
        """★ 单值 `window_*` 也已删除（换成 `windows` 列表）。"""
        from tasks.Component.config_scheduler import Scheduler
        for dead in ('window_enable', 'window_start', 'window_end',
                     'window_days', 'window_period', 'window_dom',
                     'window_slots'):
            assert dead not in Scheduler.model_fields, f'{dead} 应已删除'

    def test_windows_field_present(self):
        from tasks.Component.config_scheduler import Scheduler, TaskWindow
        assert 'windows' in Scheduler.model_fields
        assert TaskWindow is not None
        props = Scheduler.model_json_schema()['properties']
        assert 'windows' in props
        assert not props['windows'].get('internal'), \
            'windows 必须**用户可见可改**'


class TestMultipleWindows:
    """★ **一天跑两次 = 两个窗口**。"""

    def test_two_windows_two_segments(self):
        f = _fn([_win('12:00:00', '14:00:00', wid='a'),
                 _win('20:00:00', '22:00:00', wid='b')])
        segs = f.resolve_windows()
        assert len(segs) == 2, [w.describe() for w in segs]

    def test_in_window_follows_both(self):
        f = _fn([_win('12:00:00', '14:00:00', wid='a'),
                 _win('20:00:00', '22:00:00', wid='b')])
        expect = {11: False, 12: True, 13: True, 15: False,
                  19: False, 20: True, 21: True, 22: False}
        for h, want in expect.items():
            got = f.in_window(datetime(2026, 10, 7, h, 0))
            assert got is want, f'{h:02d}:00 期望 {want}, 实际 {got}'

    def test_disabled_window_ignored(self):
        """★ 某一段 `enabled=False` -> 只剩另一段。"""
        f = _fn([_win('12:00:00', '14:00:00', wid='a'),
                 _win('20:00:00', '22:00:00', wid='b', enabled=False)])
        segs = f.resolve_windows()
        assert len(segs) == 1, [w.describe() for w in segs]
        assert f.in_window(datetime(2026, 10, 7, 12, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 20, 0)) is False

    def test_empty_windows_falls_back_to_meta(self):
        """★ 空 `windows` -> 用 `meta.py` 的游戏机制窗口兜底。"""
        f = _fn([])
        ws = f.resolve_windows()
        assert ws, '空 windows 时应回退到 meta 或"不限时段"'

    def test_weekly_window(self):
        f = _fn([_win('19:00:00', '21:00:00', period='weekly',
                      days='4,5,6', wid='w')])
        assert f.in_window(datetime(2026, 10, 7, 20, 0)) is False  # 周三
        assert f.in_window(datetime(2026, 10, 9, 20, 0)) is True   # 周五

    def test_monthly_window(self):
        f = _fn([_win('19:00:00', '21:00:00', period='monthly',
                      dom='1,15', wid='w')])
        assert f.in_window(datetime(2026, 10, 15, 20, 0)) is True
        assert f.in_window(datetime(2026, 10, 20, 20, 0)) is False

    def test_bad_days_ignored_not_blocked(self):
        """★ 乱码 days **不该**让整段失效（只忽略无效项）。"""
        f = _fn([_win('00:00:00', '23:59:00', period='weekly',
                      days='abc', wid='w')])
        # days 全无效 -> 退化为每天
        assert f.in_window(datetime(2026, 10, 8, 10, 0)) is True

    def test_partially_valid_days_kept(self):
        f = _fn([_win('00:00:00', '23:59:00', period='weekly',
                      days='4,abc,6', wid='w')])
        seg = f.resolve_windows()[0]
        assert set(seg.days) == {4, 6}, sorted(seg.days)
