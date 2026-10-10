# -*- coding: utf-8 -*-
"""**允许重复添加同一任务**（用户 2026-10-10 裁定）。

## 用户原话

> "现在的任务执行里**添加任务应该设置为可以重复添加相同的任务**,
>  这样就**变相实现了多次跑任务**"

## 两个障碍（本测试钉住已修的两个）

1. **候选端点**原来排除 `queued` -> 任务加入后就从候选消失 -> 无法加第二次
2. **`list_order`** 原来用 `task_order()`（去重保首）-> 重复条目拿不到位置

## ★ 仍未解决（第三个障碍, 见台账 §21.3）

派发状态是**按任务**存的（`Scheduler.next_run` / `task_state`）,
所以同一任务的两条重复条目**无法各自追踪"这条跑过没有"**。
要真正"各跑一次"需按**条目**追踪 —— **待用户确认**。
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture()
def live():
    import logging
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.server.main_manager import mm
    return mm.config_cache('恋鸟树')


def _fn(cfg, key):
    from module.config.config import Function
    return Function(key, cfg.model.model_dump()[key])


class TestCandidatesAllowDuplicates:
    """★ 障碍 1: 候选端点**不该**排除"已在队列"的任务。"""

    def test_source_does_not_filter_queued(self):
        """源码里候选规则**不该**再有 `if command in queued: continue`。"""
        import re
        src = (REPO / 'module' / 'server' / 'schema_router.py').read_text(
            encoding='utf-8')
        i = src.find('async def get_queue_candidates')
        assert i > 0
        j = src.find('\n@', i)
        body = src[i:j if j > i else i + 4000]
        assert 'if command in queued' not in body, (
            '候选端点仍在排除"已在队列"的任务 —— '
            '用户要求可以重复添加相同的任务')
        assert '_auto_queue_of(meta)' in body, \
            '仍应排除"自动进队列"的任务（它们靠 build_queue 补齐）'

    def test_queued_task_still_in_candidates(self, live):
        """★ 端到端: 已在队列的任务**仍应**出现在候选里（可以再加一次）。"""
        import asyncio
        from module.server.schema_router import get_queue_candidates

        queued = live.queued_commands()
        got = asyncio.new_event_loop().run_until_complete(
            get_queue_candidates('恋鸟树'))
        names = {c['command'] for c in got.get('candidates', [])}
        both = names & queued
        # 只要队列里有一个 `auto_queue=False` 的任务, 它就该出现在候选里
        from module.config import task_catalog as TC
        manual_queued = {t for t in queued
                         if (TC.get_spec(t) is not None
                             and not TC.get_spec(t).auto_queue_effective)}
        if not manual_queued:
            pytest.skip('队列里没有次数任务, 无法验证')
        assert manual_queued & names, (
            f'这些已在队列的次数任务没出现在候选里: {sorted(manual_queued)} —— '
            f'用户无法重复添加它们')


class TestDuplicateEntriesKeepPosition:
    """★ 障碍 2: 重复条目必须**各占一个队列位置**。"""

    def test_list_order_uses_entry_positions(self, live):
        """★ 核心: 重复条目后面的任务**位置不被前移**。

        编排 `[Delegation, RealmRaid, RealmRaid, AreaBoss]`:
        * 旧行为（去重保首）-> AreaBoss 的位置被算成 **2**
        * 新行为（按条目）  -> AreaBoss 的位置是 **3**

        排序结果都一样, 但**位置语义**不同 —— 后续插入/拖拽会受影响。
        """
        from module.config.run_list import RunEntry, RunList
        from module.config.scheduler import TaskScheduler
        from module.config.utils import convert_to_underscore
        from tasks.Script.config_optimization import ScheduleRule

        rl = RunList([
            RunEntry(kind='task', task='Delegation'),
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='AreaBoss'),
        ])
        pending = [_fn(live, 'delegation'), _fn(live, 'realm_raid'),
                   _fn(live, 'area_boss')]
        got = TaskScheduler.schedule(ScheduleRule.LIST, pending, rl)
        order = [f.command for f in got]
        assert order == ['Delegation', 'RealmRaid', 'AreaBoss'], order

    def test_duplicates_are_preserved_in_run_list(self):
        """`RunList` 本身必须**允许**重复条目（不去重）。"""
        from module.config.run_list import RunEntry, RunList
        rl = RunList([
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='RealmRaid'),
        ])
        assert len(rl.entries) == 2, 'RunList 把重复条目吃掉了'

    def test_task_order_still_dedups_for_legacy(self):
        """`task_order()`（旧字段）**仍然**去重 —— 那是它的既有契约, 不改。

        ⚠ 但 `list_order` **不再**用它来定位（改用条目遍历）。
        """
        from module.config.run_list import RunEntry, RunList
        rl = RunList([
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='Delegation'),
        ])
        assert rl.task_order() == ['RealmRaid', 'Delegation']

    def test_list_order_source_no_task_order(self):
        """★ 反向守卫: `list_order` **不该**再用 `task_order()` 建位置映射。"""
        src = (REPO / 'module' / 'config' / 'scheduler.py').read_text(
            encoding='utf-8')
        i = src.find('def list_order')
        j = src.find('def ', i + 100)
        body = src[i:j if j > i else i + 4000]
        assert 'run_list.task_order()' not in body, (
            '`list_order` 又用回了 `task_order()`（去重保首）—— '
            '重复条目会拿不到位置')
        assert "getattr(run_list, 'entries'" in body, \
            '`list_order` 应按**条目**建位置'
