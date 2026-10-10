# -*- coding: utf-8 -*-
"""`Scheduler` 的窗口配置（**S3 后: 多窗口**）。

## ★★ S3: 字段模型换了 ★★

用户裁定:
> "不是 window slots, 而是**设置多个 window**！slots 不是已经废弃了吗,
>  请**通读代码、设计文档并更新记忆**！**前后端要同步改**！"
> "一天跑两次 = **两个窗口**"

**删除**的单值字段: `window_enable` / `window_start` / `window_end` /
`window_days` / `window_period` / `window_dom` / **`window_slots`**。

**新增**: `windows: List[TaskWindow]`（结构化的多窗口）。
"""
import json
import sys
from datetime import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestDefaults:
    def test_windows_default_is_empty(self):
        """★ 默认是**空列表**（用户没配 -> 回退 `meta.py`）。"""
        from tasks.Component.config_scheduler import Scheduler
        assert Scheduler().windows == []

    def test_dead_single_value_fields_gone(self):
        """★ 被替代的单值字段**必须不存在**（单一数据源）。"""
        from tasks.Component.config_scheduler import Scheduler
        for dead in ('window_enable', 'window_start', 'window_end',
                     'window_days', 'window_period', 'window_dom',
                     'window_slots'):
            assert dead not in Scheduler.model_fields, f'{dead} 应已删除'

    def test_task_window_defaults_are_sane(self):
        from tasks.Component.config_scheduler import TaskWindow
        w = TaskWindow()
        assert w.enabled is True, '新建窗口默认启用'
        assert w.start == time(17, 0)
        assert w.end == time(23, 0)
        assert w.id == '', 'id 由后端生成（这里默认空）'


class TestTaskWindowValidation:
    def test_accepts_strings(self):
        """★ 从 JSON 读进来时是字符串 —— pydantic 要能转换。"""
        from tasks.Component.config_scheduler import TaskWindow
        w = TaskWindow(id='a', period='weekly', start='12:00:00',
                       end='14:00:00', days='2,5')
        assert w.start == time(12, 0)
        assert w.end == time(14, 0)
        assert w.period.value == 'weekly'

    def test_dump_roundtrip(self):
        from tasks.Component.config_scheduler import TaskWindow
        w = TaskWindow(id='a', start='12:00:00', end='14:00:00')
        d = w.model_dump()
        assert TaskWindow(**d).start == time(12, 0)


def _build(windows, task='fallen_sun'):
    """用真实任务键构造 `Function`（合成名会 KeyError —— 踩过）。"""
    import copy
    import logging
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.config.config import Function
    from module.server.main_manager import mm
    cfg = mm.config_cache('恋鸟树')
    raw = copy.deepcopy(cfg.model.model_dump())
    node = copy.deepcopy(raw[task])
    node['scheduler'] = dict(node['scheduler'])
    node['scheduler']['windows'] = windows
    return Function(task, node)


def _w(start, end, period='daily', days='', dom='', enabled=True, wid='w'):
    return {'id': wid, 'enabled': enabled, 'period': period,
            'start': start, 'end': end, 'days': days, 'days_of_month': dom}


class TestDailyWindow:
    def test_simple_daily(self):
        from datetime import datetime
        f = _build([_w('17:00:00', '23:00:00')])
        assert f.in_window(datetime(2026, 10, 7, 19, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 10, 0)) is False

    def test_fengmo_17_to_23(self):
        """逢魔 17:00-23:00。"""
        from datetime import datetime
        f = _build([_w('17:00:00', '23:00:00')], task='demon_encounter')
        assert f.in_window(datetime(2026, 10, 7, 17, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 23, 0)) is False  # 开区间


class TestMultipleWindows:
    """★ **一天跑两次 = 两个窗口**（用户裁定的核心表达）。"""

    def test_two_windows(self):
        from datetime import datetime
        f = _build([_w('12:00:00', '14:00:00', wid='a'),
                    _w('20:00:00', '22:00:00', wid='b')])
        assert len(f.resolve_windows()) == 2
        assert f.in_window(datetime(2026, 10, 7, 13, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 21, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 16, 0)) is False


class TestDayRestriction:
    def test_weekend_only(self):
        from datetime import datetime
        f = _build([_w('19:00:00', '21:00:00', period='weekly',
                       days='4,5,6')])
        assert f.in_window(datetime(2026, 10, 7, 20, 0)) is False  # 周三
        assert f.in_window(datetime(2026, 10, 9, 20, 0)) is True   # 周五

    def test_days_are_deduped_and_sorted(self):
        f = _build([_w('00:00:00', '23:59:00', period='weekly',
                       days='6,4,4')])
        assert list(f.resolve_windows()[0].days) == [4, 6]

    def test_empty_days_means_every_day(self):
        from datetime import datetime
        f = _build([_w('00:00:00', '23:59:00', period='weekly', days='')])
        assert set(f.resolve_windows()[0].days) == set(range(7))
        assert f.in_window(datetime(2026, 10, 7, 10, 0)) is True


class TestCrossMidnight:
    def test_cross_midnight(self):
        from datetime import datetime
        f = _build([_w('22:00:00', '02:00:00')])
        assert f.in_window(datetime(2026, 10, 7, 23, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 1, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 12, 0)) is False


class TestRobustness:
    def test_garbage_days_falls_back_to_every_day(self):
        f = _build([_w('00:00:00', '23:59:00', period='weekly',
                       days='abc,xyz')])
        assert set(f.resolve_windows()[0].days) == set(range(7))

    def test_out_of_range_days_falls_back(self):
        f = _build([_w('00:00:00', '23:59:00', period='weekly',
                       days='9,-1,abc')])
        assert set(f.resolve_windows()[0].days) == set(range(7))

    def test_partially_valid_days_keeps_valid_ones(self):
        f = _build([_w('00:00:00', '23:59:00', period='weekly',
                       days='4,abc,6')])
        assert list(f.resolve_windows()[0].days) == [4, 6]

    def test_bad_window_skipped_not_fatal(self):
        """★ 一条坏窗口**不该**让整个任务失去窗口。"""
        f = _build([_w('bad', '23:59:00', wid='bad'),
                    _w('12:00:00', '14:00:00', wid='good')])
        ws = f.resolve_windows()
        assert ws, '应至少保留一条有效窗口'

    def test_whitespace_tolerated(self):
        f = _build([_w(' 12:00:00 ', ' 14:00:00 ', period=' weekly ',
                       days=' 4 , 6 ')])
        assert list(f.resolve_windows()[0].days) == [4, 6]
