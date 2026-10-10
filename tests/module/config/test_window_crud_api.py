# -*- coding: utf-8 -*-
"""S4: 窗口 CRUD 端点（**按 `id`**, 不按下标）。

设计依据: `docs/scheduler-architecture.md` §5.1。

★★ 为什么**按 `id`**（而不是下标）★★

窗口是**原子实体**, 有稳定身份（§1.5 "身份不是位置"）。
按**下标**删在"前端重排后"会删错 —— 这与队列条目的 ⑨（按任务名删导致
"一删全删"）是**同一类**错误。
"""
import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CFG = '恋鸟树'
TASK = 'restart'


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def sr():
    import logging
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.server import schema_router as SR
    return SR


@pytest.fixture()
def restored(sr):
    """★ 备份 + **必定还原**（我实测时曾把用户配置改坏 —— 见台账 §34）。"""
    before = _run(sr.get_task_windows(CFG, TASK)).get('windows') or []
    yield
    _run(sr.put_task_windows(CFG, TASK, before))


class TestEndpointsExist:
    def test_all_five(self, sr):
        for name in ('get_task_windows', 'put_task_windows', 'post_task_window',
                     'put_task_window', 'delete_task_window'):
            assert hasattr(sr, name), f'{name} 端点未注册'


class TestCrud:
    def test_get(self, sr):
        r = _run(sr.get_task_windows(CFG, TASK))
        assert 'windows' in r, r
        assert r['count'] == len(r['windows'])

    def test_put_replaces_all(self, sr, restored):
        r = _run(sr.put_task_windows(CFG, TASK, [
            {'start': '01:00:00', 'end': '02:00:00'},
            {'start': '03:00:00', 'end': '04:00:00'},
            {'start': '05:00:00', 'end': '06:00:00'},
        ]))
        assert r.get('ok') is True, r
        assert r['count'] == 3, r
        # ★ 没给 id 的会自动补（前端新增行可不生成 id）
        assert all(w['id'] for w in r['windows']), r['windows']

    def test_put_by_id_updates_only_that_one(self, sr, restored):
        r = _run(sr.put_task_windows(CFG, TASK, [
            {'start': '01:00:00', 'end': '02:00:00'},
            {'start': '03:00:00', 'end': '04:00:00'},
        ]))
        ids = [w['id'] for w in r['windows']]
        r2 = _run(sr.put_task_window(CFG, TASK, ids[1],
                                     {'start': '09:00:00', 'end': '10:00:00'}))
        assert r2.get('ok') is True, r2
        got = {w['id']: w['start'] for w in r2['windows']}
        assert got[ids[0]] == '01:00:00', '改一条不该影响另一条'
        assert got[ids[1]] == '09:00:00'

    def test_id_not_changeable(self, sr, restored):
        """★ `id` **不可改**（身份稳定）。"""
        r = _run(sr.put_task_windows(CFG, TASK,
                                     [{'start': '01:00:00', 'end': '02:00:00'}]))
        wid = r['windows'][0]['id']
        r2 = _run(sr.put_task_window(CFG, TASK, wid,
                                     {'id': 'hacked', 'start': '03:00:00',
                                      'end': '04:00:00'}))
        assert r2['windows'][0]['id'] == wid, 'id 被改掉了 —— 身份不稳定'

    def test_delete_by_id_removes_only_one(self, sr, restored):
        """★★ 与队列 ⑨ 同类：删一条**不该**影响另一条。"""
        r = _run(sr.put_task_windows(CFG, TASK, [
            {'start': '01:00:00', 'end': '02:00:00'},
            {'start': '03:00:00', 'end': '04:00:00'},
        ]))
        ids = [w['id'] for w in r['windows']]
        r2 = _run(sr.delete_task_window(CFG, TASK, ids[0]))
        assert r2.get('ok') is True, r2
        assert r2['count'] == 1, r2
        assert [w['id'] for w in r2['windows']] == [ids[1]]

    def test_post_adds_with_new_id(self, sr, restored):
        before = _run(sr.get_task_windows(CFG, TASK))['count']
        r = _run(sr.post_task_window(CFG, TASK,
                                     {'start': '07:00:00', 'end': '08:00:00'}))
        assert r.get('ok') is True, r
        assert r['count'] == before + 1
        assert r['added']['id'], '新增应有 id'


class TestErrors:
    def test_delete_unknown_id_errors(self, sr):
        """★ 找不到 id -> **报错**（不静默"成功"）。"""
        r = _run(sr.delete_task_window(CFG, TASK, 'no-such-id'))
        assert r.get('error'), r
        assert 'no-such-id' in r['error']

    def test_put_unknown_id_errors(self, sr):
        r = _run(sr.put_task_window(CFG, TASK, 'no-such-id',
                                    {'start': '01:00:00', 'end': '02:00:00'}))
        assert r.get('error'), r

    def test_unknown_task_errors(self, sr):
        r = _run(sr.get_task_windows(CFG, 'NoSuchTask'))
        assert r.get('error'), r


class TestTypes:
    def test_windows_are_taskwindow_objects(self, sr, restored):
        """★ 赋值后列表里必须是 `TaskWindow`（不是 dict）。

        否则 pydantic 序列化会警告
        （`Expected TaskWindow but got dict` —— 实测踩过）。
        """
        import logging
        logging.disable(logging.CRITICAL)
        from module.server.main_manager import mm
        from tasks.Component.config_scheduler import TaskWindow
        _run(sr.put_task_windows(CFG, TASK,
                                 [{'start': '01:00:00', 'end': '02:00:00'}]))
        cfg = mm.config_cache(CFG)
        ws = cfg.model.restart.scheduler.windows
        assert all(isinstance(w, TaskWindow) for w in ws), \
            [type(w).__name__ for w in ws]
