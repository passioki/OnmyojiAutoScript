# -*- coding: utf-8 -*-
"""★★★ 窗口的**前置条件**: `period != none` 才能**新增**窗口（用户裁定）★★★

## 用户原话

> "**窗口必须在选了周期后才能设置。这样子判断依据就可以按有没有周期来判断**"

## 规则（以及为什么只拦"新增"）

| 操作 | 要求周期 | 为什么 |
|---|---|---|
| **新增**窗口（`POST` / `PUT` 出现新 id）| ★ **必须** `period != none` | 这是用户要的约束 |
| **编辑已有**窗口（id 集合不变）| 不要求 | 否则历史数据改不动 |
| **删除**窗口 | 不要求 | 否则删不掉 |

★ "只拦新增"是**必要的**: 用户配置里存在"有窗口但 `period=none`"的历史数据
（别的账号/别的任务）, 若编辑也拦, 用户会被**锁死** —— 那不是约束, 是砖。
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

CFG = '__win_require_period__'
P = REPO / 'config' / f'{CFG}.json'


def _call(fn, *a, **kw):
    return asyncio.new_event_loop().run_until_complete(fn(*a, **kw))


def _mk(period, windows=None):
    """造临时配置; `period_backfilled=True` 以免回填干预。"""
    os.chdir(REPO)
    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization']['period_backfilled'] = True
    tmpl['orochi']['scheduler']['period'] = period
    tmpl['orochi']['scheduler']['windows'] = windows or []
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')


def _new_window(start='09:00', end='11:00'):
    """★ 字段按**真实契约**: `days` / `days_of_month` 是**逗号分隔字符串**。

    ⚠ 我第一版写成 list（`[0,1,...]`）-> `TaskWindow` 校验失败
      （`days: str`）。真实契约见 `window_editor.dart` 的 payload。
    """
    return {'enabled': True, 'period': 'daily', 'start': start, 'end': end,
            'days': '', 'days_of_month': ''}


def _existing(id_='w1'):
    d = _new_window()
    d['id'] = id_
    return d


def _disk_windows():
    d = json.loads(P.read_text(encoding='utf-8'))
    return (d['orochi']['scheduler'] or {}).get('windows') or []


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    try:
        P.unlink()
    except OSError:
        pass


class TestPeriodNoneBlocksAdding:
    def test_post_is_blocked(self):
        """`period=none` + `POST`（新增一条）-> **被拦**。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk('none')
        r = _call(SR.post_task_window, CFG, 'Orochi', _new_window())
        assert 'error' in r, f'★ 竟然放行了: {r}'
        assert r.get('needs_period') is True, (
            '★ 应带 `needs_period` 标记, 前端据此提示"请先选周期"')
        assert not _disk_windows(), '★ 被拦时不该写盘'

    def test_put_with_new_id_is_blocked(self):
        """`period=none` + `PUT` 整单里出现**新 id** -> **被拦**。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk('none')
        r = _call(SR.put_task_windows, CFG, 'Orochi', [_new_window()])
        assert 'error' in r and r.get('needs_period') is True, f'{r}'
        assert not _disk_windows()

    def test_error_message_is_actionable(self):
        """★ 错误文案要**告诉用户怎么做**（不是只说"不允许"）。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk('none')
        r = _call(SR.post_task_window, CFG, 'Orochi', _new_window())
        msg = str(r.get('error', ''))
        assert '周期' in msg, msg
        assert ('每天' in msg or '每周' in msg), (
            '★ 应告诉用户"去调度器选每天/每周/每月" —— 只说"不允许"没法用')


class TestExistingWindowsStillEditable:
    """★ 只拦新增: 编辑/删除必须放行, 否则历史数据被锁死。"""

    def test_edit_existing_window_allowed(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk('none', [_existing()])
        r = _call(SR.put_task_window, CFG, 'Orochi', 'w1',
                  _new_window('10:00', '12:00'))
        assert r.get('ok') is True, f'★ 编辑已有窗口被拦了: {r}'

    def test_put_same_ids_allowed(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk('none', [_existing()])
        r = _call(SR.put_task_windows, CFG, 'Orochi', [_existing()])
        assert r.get('ok') is True, f'★ 整单替换（id 不变）被拦了: {r}'

    def test_delete_allowed(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk('none', [_existing()])
        r = _call(SR.delete_task_window, CFG, 'Orochi', 'w1')
        assert r.get('ok') is True, f'★ 删除被拦了: {r}'


class TestPeriodSetAllowsEverything:
    def test_daily_allows_add(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk('daily')
        r = _call(SR.post_task_window, CFG, 'Orochi', _new_window())
        assert r.get('ok') is True, f'{r}'
        assert len(_disk_windows()) == 1

    def test_weekly_allows_add(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk('weekly')
        r = _call(SR.post_task_window, CFG, 'Orochi', _new_window())
        assert r.get('ok') is True, f'{r}'
