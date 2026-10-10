# -*- coding: utf-8 -*-
"""S5 最终守卫: **存量机制已彻底移除**（用户裁定）。

用户原话:
> "去掉组队协同，去掉存量次数。组队协同应该是单独模块啊，不应该放在金币妖怪里。"
> "去除旧的充能存量说法。现在靠 window 的**多次设置**完全可以做到正常运行。"
> "连 `charge_*` 字段和存量逻辑一起删"
> "金币妖怪 (a) 多个 window —— 配 2 个窗口（0:00-11:59、12:00-23:59）"

★ 这些守卫**反向断言**"东西不存在了" —— 防止它们**悄悄回来**。
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TASKS = ('GoldYoukai', 'ExperienceYoukai', 'Tako')


def _code(rel: str) -> str:
    """剥掉 docstring 与注释后的**会执行**的代码。"""
    t = (REPO / rel).read_text(encoding='utf-8', errors='replace')
    t = re.sub(r'"""[\s\S]*?"""', '', t)
    return '\n'.join(l.split('#', 1)[0] for l in t.split('\n'))


class TestModulesDeleted:
    def test_team_coordinator_gone(self):
        """★ 跨账号组队协同模块已删除（用户: "应该是单独模块"）。"""
        assert not (REPO / 'module/config/team_coordinator.py').exists()

    def test_scheduler_core_gone(self):
        """★ 上一代调度核（`Resource` 池子模型）是死代码, 已删除。"""
        assert not (REPO / 'module/config/scheduler_core.py').exists()

    def test_resource_classes_gone(self):
        """★ `Recharge` / `Resource`（存量机制）已删除。"""
        from module.config import resource
        assert not hasattr(resource, 'Recharge')
        assert not hasattr(resource, 'Resource')

    def test_period_kept(self):
        """★ `Period` **必须保留** —— `TaskSpec.period` 还在用。"""
        from module.config.resource import Period
        assert Period.DAILY.value == 'daily'
        assert Period.NONE.value == 'none'

    def test_category_charge_gone(self):
        """★ `Category.CHARGE` 已删除。"""
        from module.config import task_catalog as TC
        assert not hasattr(TC.Category, 'CHARGE')
        assert {c.value for c in TC.Category} == {
            'fixed', 'toppa', 'limited', 'timed'}

    def test_timed_categories_no_charge(self):
        from module.config import timed_schedule as TS
        assert 'charge' not in TS.TIMED_CATEGORIES


class TestTaskSpecClean:
    def test_no_resource_field(self):
        from module.config import task_catalog as TC
        assert not hasattr(TC.TaskSpec(task='Demo', name_zh='演示'), 'resource')

    def test_period_is_independent_field(self):
        """★ `period` 是**独立字段**（不再来自 `resource.recharge.period`）。"""
        from module.config import task_catalog as TC
        from module.config.resource import Period
        s = TC.TaskSpec(task='Demo', name_zh='演示', period=Period.WEEKLY)
        assert s.period == Period.WEEKLY
        assert s.period_effective == Period.WEEKLY

    def test_task_meta_has_no_charge_fields(self):
        from module.config import task_catalog as TC
        for f in ('has_charge', 'charge_max', 'charge_slots', 'charge_consume'):
            assert f not in TC.TaskMeta.__dataclass_fields__, f'{f} 还在'


class TestTaskConfigsClean:
    @pytest.mark.parametrize('task', TASKS)
    def test_config_has_no_charge_fields(self, task):
        import importlib
        mod = importlib.import_module(f'tasks.{task}.config')
        for cls in vars(mod).values():
            if not (isinstance(cls, type) and hasattr(cls, 'model_fields')):
                continue
            for f in cls.model_fields:
                assert not f.startswith('charge_'), \
                    f'{task}.{cls.__name__}.{f} 应已删除'

    @pytest.mark.parametrize('task', TASKS)
    def test_script_task_has_no_charge_or_coord(self, task):
        code = _code(f'tasks/{task}/script_task.py')
        assert 'task_state' not in code, f'{task} 仍用 task_state（存量/心跳）'
        assert 'team_coordinator' not in code, f'{task} 仍用 team_coordinator'
        assert 'charge_' not in code, f'{task} 仍用 charge_*'
        assert 'cfg_name' not in code, f'{task} 仍有存量记账用的 cfg_name'

    @pytest.mark.parametrize('task', TASKS)
    def test_meta_has_no_resource(self, task):
        code = _code(f'tasks/{task}/meta.py')
        assert 'Recharge' not in code, f'{task}/meta.py 仍引用 Recharge'
        assert 'Resource(' not in code, f'{task}/meta.py 仍引用 Resource('


class TestTwoWindows:
    """★ 用户指定: "金币妖怪 (a) 多个 window —— 配 2 个窗口
    （0:00-11:59、12:00-23:59）"。"""

    @pytest.mark.parametrize('task', TASKS)
    def test_two_windows(self, task):
        from module.config import task_catalog as TC
        ws = TC.get_spec(task).windows_effective
        assert len(ws) == 2, f'{task} 应有 2 个窗口, 实际 {len(ws)}'
        got = {(w.start.hour, w.start.minute, w.end.hour, w.end.minute)
               for w in ws}
        assert got == {(0, 0, 11, 59), (12, 0, 23, 59)}, f'{task} 窗口不对: {got}'


class TestTaskStateClean:
    def test_charge_functions_gone(self):
        from module.config import task_state as TS
        for f in ('get_charges', 'consume_charge', 'next_charge_time',
                  'parse_slots', 'peer_charges', '_decode_charges_v2'):
            assert not hasattr(TS, f), f'task_state.{f} 应已删除'

    def test_summarize_has_no_charges(self):
        from module.config import task_state as TS
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as d:
            os.environ['OAS_TASK_STATE_FILE'] = str(Path(d) / 'st.json')
            try:
                out = TS.summarize('nosuchconfig')
            finally:
                os.environ.pop('OAS_TASK_STATE_FILE', None)
        assert 'charges' not in out
        assert set(out) == {'config', 'global'}

    def test_peers_status_kept_but_no_charges(self):
        """★ `peers_status` **保留**（2 个 router 在用）, 但不再返回 charges。"""
        from module.config import task_state as TS
        assert callable(TS.peers_status)
        out = TS.peers_status('nosuchconfig')
        for rec in out:
            assert 'charges' not in rec


class TestOverviewNoCharges:
    def test_overview_fields(self):
        import asyncio
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server import schema_router as SR
        r = asyncio.run(SR.script_overview('恋鸟树'))
        tasks = r.get('tasks') or []
        assert tasks, 'overview 应有任务'
        for t in tasks:
            assert 'charges' not in t, f'{t["name"]} 仍有 charges'
            assert 'resource_describe' not in t, \
                f'{t["name"]} 仍有 resource_describe'
