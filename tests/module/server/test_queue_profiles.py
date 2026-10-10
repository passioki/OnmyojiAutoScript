# -*- coding: utf-8 -*-
"""★★★ 执行顺序**配置页** 1/2/3/…（用户要求）★★★

## 用户原话

> "添加**执行顺序配置页 1/2/3/……**，可以添加、删除和切换配置页"

## 语义

一页 = **一套执行顺序**（`run_list` 的快照）。★ `run_list` 永远是
**当前生效**的那份; `profiles` 只是**存档**。

## ★★ 最关键的一条: 切换前必须**自动保存当前页**

否则用户拖了半天的顺序, 一切页就**丢了**。★ 这条由**后端**保证,
不指望前端记得（本文件专门钉它）。

## 为什么复用 `run_list` 的形状

每页的 `entries` 就是 `run_list` 的样子（同一套 `RunEntry` 序列化）,
"应用一页" = 写回 `optimization.run_list` —— 复用 `Config.save_run_list`。
★ 本轮刚修过"两套定义打架"（`meta` vs 推荐窗口表）, 不再造第二套。
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

CFG = '__profiles_test__'
P = REPO / 'config' / f'{CFG}.json'


def _call(fn, *a, **kw):
    return asyncio.new_event_loop().run_until_complete(fn(*a, **kw))


def _mk(run_list=None):
    os.chdir(REPO)
    import server  # noqa: F401
    from module.server.main_manager import mm

    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization']['period_backfilled'] = True
    tmpl['script']['optimization']['run_list'] = run_list or []
    tmpl['script']['optimization']['profiles'] = {}
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    return mm.config_cache(CFG)


def _rl():
    d = json.loads(P.read_text(encoding='utf-8'))
    return [e.get('task') for e in
            (d['script']['optimization'].get('run_list') or [])
            if isinstance(e, dict)]


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    try:
        P.unlink()
    except OSError:
        pass


class TestProfilesCrud:
    def test_starts_empty(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk()
        r = _call(SR.get_queue_profiles, CFG)
        assert r.get('profiles') == []
        assert not r.get('error')

    def test_create_autonumbers(self):
        """★ 不传名字 -> 自动编号 1 / 2 / …（用户说的"1/2/3/…"）。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk(run_list=[{'kind': 'task', 'task': 'Orochi'}])
        r1 = _call(SR.post_queue_profile, CFG, {})
        assert r1.get('ok') is True, r1
        assert r1.get('name') == '1', r1
        r2 = _call(SR.post_queue_profile, CFG, {})
        assert r2.get('name') == '2', r2

    def test_create_snapshots_current_order(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk(run_list=[{'kind': 'task', 'task': 'Orochi'},
                      {'kind': 'task', 'task': 'Pets'}])
        r = _call(SR.post_queue_profile, CFG, {})
        got = next(p for p in r['profiles'] if p['name'] == '1')
        assert got['count'] == 2, got

    def test_activate_restores_entries(self):
        import server  # noqa: F401
        from module.config.run_list import RunEntry, RunList
        from module.server import schema_router as SR
        from module.server.main_manager import mm

        _mk(run_list=[{'kind': 'task', 'task': 'Orochi'}])
        r1 = _call(SR.post_queue_profile, CFG, {})       # 页1 = [Orochi]
        mm.config_cache(CFG).save_run_list(
            RunList([RunEntry(task='Exploration'), RunEntry(task='Pets')]))
        r2 = _call(SR.post_queue_profile, CFG, {})       # 页2 = [Exploration,Pets]

        p1 = next(p['id'] for p in r2['profiles'] if p['name'] == '1')
        r3 = _call(SR.put_queue_profile_activate, CFG, {'id': p1})
        assert r3.get('ok') is True, r3
        assert _rl() == ['Orochi'], _rl()

    def test_activate_autosaves_previous_page(self):
        """★★★ 核心: 切换前把**当前**顺序存回当前页（否则用户的改动会丢）★★★"""
        import server  # noqa: F401
        from module.config.run_list import RunEntry, RunList
        from module.server import schema_router as SR
        from module.server.main_manager import mm

        _mk(run_list=[{'kind': 'task', 'task': 'Orochi'}])
        _call(SR.post_queue_profile, CFG, {})            # 页1
        mm.config_cache(CFG).save_run_list(
            RunList([RunEntry(task='Exploration'), RunEntry(task='Pets')]))
        r2 = _call(SR.post_queue_profile, CFG, {})       # 页2（当前）

        # ★ 用户在第 2 页上又拖了（改成 3 条），然后切回第 1 页
        mm.config_cache(CFG).save_run_list(
            RunList([RunEntry(task='Orochi'), RunEntry(task='Pets'),
                     RunEntry(task='Exploration')]))
        p1 = next(p['id'] for p in r2['profiles'] if p['name'] == '1')
        r3 = _call(SR.put_queue_profile_activate, CFG, {'id': p1})
        counts = {p['name']: p['count'] for p in r3['profiles']}
        assert counts.get('2') == 3, (
            '★ 切页时没把当前顺序存回第 2 页 -> 用户拖的结果**丢了**！'
            f' 实际计数: {counts}')

    def test_active_flag_follows(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk(run_list=[{'kind': 'task', 'task': 'Orochi'}])
        _call(SR.post_queue_profile, CFG, {})
        r2 = _call(SR.post_queue_profile, CFG, {})
        p1 = next(p['id'] for p in r2['profiles'] if p['name'] == '1')
        r3 = _call(SR.put_queue_profile_activate, CFG, {'id': p1})
        assert [p['name'] for p in r3['profiles'] if p['active']] == ['1']


class TestProfilesSafety:
    def test_delete_does_not_touch_current_order(self):
        """★ 删一页**不该**改动当前执行顺序。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk(run_list=[{'kind': 'task', 'task': 'Orochi'}])
        _call(SR.post_queue_profile, CFG, {})
        r2 = _call(SR.post_queue_profile, CFG, {})
        p2 = next(p['id'] for p in r2['profiles'] if p['name'] == '2')
        before = _rl()
        r3 = _call(SR.delete_queue_profile, CFG, p2)
        assert r3.get('ok') is True, r3
        assert _rl() == before, _rl()

    def test_cannot_delete_last_page(self):
        """★ 至少留一页 —— 否则用户就没有可切换的了。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk(run_list=[{'kind': 'task', 'task': 'Orochi'}])
        r1 = _call(SR.post_queue_profile, CFG, {})
        pid = r1['profiles'][0]['id']
        r2 = _call(SR.delete_queue_profile, CFG, pid)
        assert r2.get('error'), r2

    def test_activate_unknown_id_errors(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk(run_list=[])
        _call(SR.post_queue_profile, CFG, {})
        r = _call(SR.put_queue_profile_activate, CFG, {'id': 'nope'})
        assert r.get('error'), r

    def test_profiles_field_is_internal(self):
        """★ `profiles` 是**内部状态** —— 不该出现在界面的参数表单里。"""
        from pathlib import Path as _P
        src = (_P(REPO) / 'tasks/Script/config_optimization.py').read_text(
            encoding='utf-8')
        i = src.index('profiles: dict = Field')
        block = src[i:i + 320]
        assert "'internal': True" in block, (
            '★ `profiles` 必须标 `internal` —— 否则会被 `/args` 渲染成一个'
            '"参数字段", 用户看到一团看不懂的 JSON')
