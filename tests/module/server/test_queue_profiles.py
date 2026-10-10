# -*- coding: utf-8 -*-
"""★★★ 执行顺序**配置页** 1/2/3/…（用户要求, 完整快照版）★★★

## 用户原话

> "添加**执行顺序配置页 1/2/3/……**，可以添加、删除和切换配置页"
> "1甲，全都算"
> "2：**iii**，每个页面都相当于当前的执行顺序页，**包含所有的功能**，
>  只需要当做不同的页切换，满足不同时期的特别需要。"
> "3：这个问题在问题2的前提下不存在，因为**当前的执行顺序就是页1**"
> "4：**需要重命名**"

## 一页 = **完整快照**（跨两个存储层）

**后端**（存进配置）:
* `queue` —— `run_list` 条目
* `scheduler` —— **每任务**的 `enable` / `target` / `priority` /
  `expected_minutes`
* `global` —— 全局开关（`enable_fixed` / `enable_timed` /
  `rest_interleave` / `when_task_queue_empty` / `queue_mode` /
  `queue_idle_threshold`）

**前端**（存本地, 按 `<账号>:<页id>` 隔离 —— 见前端测试）:
排序列+升降序 / 只看筛选 / 分栏宽度

## ★ 刻意**不**入快照的

* `next_run` / `windows` / `period` / `reset_at` —— 那是"这套方案**怎么跑出来的
  运行时排期**", 换方案时应由目标页自己的值决定；`next_run` 尤其**不能跨页搬**
  （它是绝对时刻, 搬过去会立刻过期或推迟）
* `screenshot_interval` 等 —— **设备性能**参数, 与方案无关
* `schedule_rule` / `timed_priority` —— **已废弃**
* `period_backfilled` / `profiles` —— 内部标记与容器本身
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


def _mk(run_list=None, **opt):
    os.chdir(REPO)
    import server  # noqa: F401
    from module.server.main_manager import mm

    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    o = tmpl['script']['optimization']
    o['period_backfilled'] = True
    o['run_list'] = run_list or []
    o['profiles'] = {}
    o.update(opt)
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    return mm.config_cache(CFG)


def _disk():
    return json.loads(P.read_text(encoding='utf-8'))


def _opt():
    return _disk()['script']['optimization']


def _items():
    return _opt()['profiles']['items']


def _rl():
    return [e.get('task') for e in (_opt().get('run_list') or [])
            if isinstance(e, dict)]


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    try:
        P.unlink()
    except OSError:
        pass


class TestPage1AutoCreated:
    """★ 用户: "当前的执行顺序就是页1" —— 首次访问自动建页1。"""

    def test_first_access_creates_page1(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk([{'kind': 'task', 'task': 'Orochi'}])
        r = _call(SR.get_queue_profiles, CFG)
        assert len(r.get('profiles') or []) == 1, r
        assert r['profiles'][0]['active'] is True
        assert r['profiles'][0]['name'] == '1'

    def test_auto_create_is_idempotent(self):
        """★ 第二次访问**不该**再建一页（否则会覆盖用户改的东西）。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk([{'kind': 'task', 'task': 'Orochi'}])
        _call(SR.get_queue_profiles, CFG)
        r2 = _call(SR.get_queue_profiles, CFG)
        assert len(r2['profiles']) == 1, r2

    def test_page1_snapshot_equals_current_state(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk([{'kind': 'task', 'task': 'Orochi'}], enable_timed=False)
        _call(SR.get_queue_profiles, CFG)
        p1 = _items()[0]
        assert [e.get('task') for e in p1['snapshot']['queue']] == ['Orochi']
        assert p1['snapshot']['global']['enable_timed'] is False


class TestSnapshotIsComplete:
    """★★ 甲: 一页要含**所有功能**（队列 + 每任务调度 + 全局开关）。"""

    def test_snapshot_has_three_parts(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk([{'kind': 'task', 'task': 'Orochi'}])
        _call(SR.get_queue_profiles, CFG)
        snap = _items()[0]['snapshot']
        for part in ('queue', 'scheduler', 'global'):
            assert part in snap, f'快照缺 {part}: {sorted(snap.keys())}'

    def test_scheduler_part_covers_all_tasks(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk()
        _call(SR.get_queue_profiles, CFG)
        sched = _items()[0]['snapshot']['scheduler']
        assert len(sched) > 40, f'每任务调度只存了 {len(sched)} 个'
        one = sched.get('orochi') or {}
        for f in ('enable', 'target', 'priority', 'expected_minutes'):
            assert f in one, f'缺字段 {f}: {sorted(one.keys())}'

    def test_snapshot_excludes_runtime_schedule(self):
        """★ `next_run`/`windows`/`period`/`reset_at` **不许**进快照。

        ★ 理由: 它们是"这套方案怎么跑出来的**运行时排期**";
          `next_run` 更是**绝对时刻** —— 跨页搬会立刻过期或推迟。
        """
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk()
        _call(SR.get_queue_profiles, CFG)
        one = _items()[0]['snapshot']['scheduler'].get('orochi') or {}
        for bad in ('next_run', 'windows', 'period', 'reset_at'):
            assert bad not in one, (
                f'★ 快照里不该有 `{bad}` —— 那是运行时排期, 跨页搬会出错 '
                f'（实际字段: {sorted(one.keys())}）')

    def test_global_part_has_the_switches(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        from module.server.schema_router import SNAPSHOT_GLOBAL_FIELDS
        _mk()
        _call(SR.get_queue_profiles, CFG)
        g = _items()[0]['snapshot']['global']
        for f in SNAPSHOT_GLOBAL_FIELDS:
            assert f in g, f'全局开关缺 {f}（实有: {sorted(g.keys())}）'

    def test_snapshot_excludes_device_params(self):
        """★ 设备性能参数**不该**进快照（与"方案"无关）。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk()
        _call(SR.get_queue_profiles, CFG)
        g = _items()[0]['snapshot']['global']
        for bad in ('screenshot_interval', 'combat_screenshot_interval',
                    'task_hoarding_duration', 'close_game_wait_duration'):
            assert bad not in g, f'★ 快照不该含设备参数 {bad}'


class TestSwitchingRestoresEverything:
    """★★★ 切页要**整套**换掉（甲），而且**不能丢**当前页的改动。"""

    def _two_pages(self):
        import server  # noqa: F401
        from module.config.run_list import RunEntry, RunList
        from module.server import schema_router as SR
        from module.server.main_manager import mm

        _mk([{'kind': 'task', 'task': 'Orochi'}], enable_timed=True)
        _call(SR.get_queue_profiles, CFG)                  # 页1
        cfg = mm.config_cache(CFG)
        cfg.model.deep_set(cfg.model,
                           keys='script.optimization.enable_timed', value=False)
        cfg.save_run_list(RunList([RunEntry(task='Exploration')]))
        r2 = _call(SR.post_queue_profile, CFG, {})          # 页2
        p1 = next(p['id'] for p in r2['profiles'] if p['name'] == '1')
        return r2, p1

    def test_switch_restores_queue_and_global(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        r2, p1 = self._two_pages()
        r3 = _call(SR.put_queue_profile_activate, CFG, {'id': p1})
        assert r3.get('ok') is True, r3
        assert _rl() == ['Orochi'], _rl()
        assert _opt().get('enable_timed') is True, (
            '★ 切页必须把**全局开关**也换回来（甲: "包含所有的功能"）')

    def test_switch_autosaves_previous_page_completely(self):
        """★ 切页前把**当前整页**（含总开关）存回当前页。"""
        import server  # noqa: F401
        from module.config.run_list import RunEntry, RunList
        from module.server import schema_router as SR
        from module.server.main_manager import mm
        r2, p1 = self._two_pages()
        # 在页2 上再改（队列 + 总开关）
        cfg = mm.config_cache(CFG)
        cfg.save_run_list(RunList([RunEntry(task='Pets')]))
        cfg.model.deep_set(cfg.model,
                           keys='script.optimization.enable_fixed', value=False)
        cfg.save()
        _call(SR.put_queue_profile_activate, CFG, {'id': p1})
        p2 = next(i for i in _items() if i['name'] == '2')
        assert [e.get('task') for e in p2['snapshot']['queue']] == ['Pets'], (
            '★ 切页没把当前队列存回页2 -> 用户的改动丢了')
        assert p2['snapshot']['global']['enable_fixed'] is False, (
            '★ 切页没把当前总开关存回页2 -> 用户的改动丢了')

    def test_switch_does_not_reuse_stale_next_run(self):
        """★ 换页**不该**把旧页的 `next_run` 搬过来。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        r2, p1 = self._two_pages()
        before = _opt()['profiles']
        _call(SR.put_queue_profile_activate, CFG, {'id': p1})
        # 快照里始终不该出现 next_run
        for it in _items():
            one = (it.get('snapshot') or {}).get('scheduler') or {}
            for _k, fields in one.items():
                assert 'next_run' not in (fields or {})


class TestRenameAndDelete:
    def test_rename(self):
        """★ 用户 4: "需要重命名"。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk()
        r = _call(SR.get_queue_profiles, CFG)
        pid = r['profiles'][0]['id']
        r2 = _call(SR.put_queue_profile_rename, CFG,
                   {'id': pid, 'name': '周末'})
        assert r2.get('ok') is True, r2
        assert [p['name'] for p in r2['profiles']] == ['周末']

    def test_rename_rejects_empty(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk()
        pid = _call(SR.get_queue_profiles, CFG)['profiles'][0]['id']
        assert _call(SR.put_queue_profile_rename, CFG,
                     {'id': pid, 'name': '  '}).get('error')

    def test_rename_keeps_snapshot(self):
        """★ 改名**不动**内容。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk([{'kind': 'task', 'task': 'Orochi'}])
        pid = _call(SR.get_queue_profiles, CFG)['profiles'][0]['id']
        _call(SR.put_queue_profile_rename, CFG, {'id': pid, 'name': '日常'})
        p = _items()[0]
        assert [e.get('task') for e in p['snapshot']['queue']] == ['Orochi']

    def test_delete_keeps_current_order(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk([{'kind': 'task', 'task': 'Orochi'}])
        _call(SR.get_queue_profiles, CFG)
        r2 = _call(SR.post_queue_profile, CFG, {})
        p2 = next(p['id'] for p in r2['profiles'] if p['name'] == '2')
        before = _rl()
        r3 = _call(SR.delete_queue_profile, CFG, p2)
        assert r3.get('ok') is True, r3
        assert _rl() == before

    def test_cannot_delete_last_page(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        _mk()
        pid = _call(SR.get_queue_profiles, CFG)['profiles'][0]['id']
        assert _call(SR.delete_queue_profile, CFG, pid).get('error')


class TestBackwardCompatibility:
    """★ 旧页只有 `entries`（纯顺序）-> 仍能载入, 且**不动**调度/全局。"""

    def test_old_shape_loads_queue_only(self):
        import server  # noqa: F401
        from module.server import schema_router as SR
        from module.server.main_manager import mm
        _mk([{'kind': 'task', 'task': 'Orochi'}], enable_timed=True)
        _call(SR.get_queue_profiles, CFG)
        d = _disk()
        d['script']['optimization']['profiles']['items'].append(
            {'id': 'pOLD', 'name': '旧页',
             'entries': [{'kind': 'task', 'task': 'Pets'}]})
        P.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        mm.config_cache(CFG)
        r = _call(SR.put_queue_profile_activate, CFG, {'id': 'pOLD'})
        assert r.get('ok') is True, r
        assert _rl() == ['Pets'], _rl()
        assert _opt().get('enable_timed') is True, (
            '★ 旧页没有 global 段 -> **不该**把当前总开关改掉')


class TestNoEnumWarnings:
    def test_switching_enum_field_does_not_warn(self):
        """★ 枚举字段回写**不许**触发 pydantic 警告。

        ⚠ 本项目**已多次**踩"传字符串给枚举字段"的坑
          （`TaskPeriod` 那次专门包了一层）。所以快照回写要经过
          `_coerce_for_field`。
        """
        import warnings
        import server  # noqa: F401
        from module.server import schema_router as SR
        from module.server.main_manager import mm
        _mk([{'kind': 'task', 'task': 'Orochi'}],
            when_task_queue_empty='goto_main')
        _call(SR.get_queue_profiles, CFG)
        cfg = mm.config_cache(CFG)
        cfg.model.deep_set(cfg.model,
                           keys='script.optimization.enable_timed', value=False)
        cfg.save()
        r2 = _call(SR.post_queue_profile, CFG, {})
        p1 = next(p['id'] for p in r2['profiles'] if p['name'] == '1')
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            _call(SR.put_queue_profile_activate, CFG, {'id': p1})
        bad = [str(w.message) for w in caught
               if 'enum' in str(w.message).lower()
               or 'serialized value' in str(w.message)]
        assert not bad, (
            '★ 回写枚举字段触发了 pydantic 警告 —— 要走 '
            '`_coerce_for_field` 把字符串转回枚举:\n  ' + str(bad[:2]))


class TestSnapshotFieldListsAreDocumented:
    def test_scheduler_fields_are_the_four(self):
        from module.server.schema_router import SNAPSHOT_SCHEDULER_FIELDS
        assert set(SNAPSHOT_SCHEDULER_FIELDS) == {
            'enable', 'target', 'priority', 'expected_minutes'}, (
            '★ 每任务快照字段变了 —— 请同步本文件的 docstring 与用户确认过的范围')

    def test_global_fields_are_the_six(self):
        from module.server.schema_router import SNAPSHOT_GLOBAL_FIELDS
        assert set(SNAPSHOT_GLOBAL_FIELDS) == {
            'enable_fixed', 'enable_timed', 'rest_interleave',
            'when_task_queue_empty', 'queue_mode',
            'queue_idle_threshold'}, (
            '★ 全局快照字段变了 —— 用户裁定"甲: 全都算", 改动需再确认')

    def test_profiles_field_is_internal(self):
        src = (REPO / 'tasks/Script/config_optimization.py').read_text(
            encoding='utf-8')
        i = src.index('profiles: dict = Field')
        assert "'internal': True" in src[i:i + 320], (
            '★ `profiles` 必须标 `internal` —— 否则会被 `/args` 渲染成'
            '一个参数字段, 用户看到一团看不懂的 JSON')
