# -*- coding: utf-8 -*-
"""C: 条目身份 `entry_id`（用户裁定: "用当前时间 + task 来实现，可拆可合并"）。

## 两件事本测试钉住

1. **`entry_id` 必须唯一** —— `时间 + task` 精确到**秒**, 同一秒内加两次
   同一任务会**撞 id**（实测踩过: 两条 `RealmRaid` 一模一样）。
   所以 `RunList.add()` 会**追加序号**唯一化。

2. **`pending` 里的 `Function` 必须携带 `entry_id`**（选项 2 显式）——
   否则按条目追踪无从谈起。

## 为什么"可拆可合并"重要

* **可拆**: `task_of_entry_id('20261010T091255-RealmRaid-2')` -> `RealmRaid`
* **可合并**: 同一 `task` 的多条条目可以按 task 聚合（界面/统计）
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestEntryIdFormat:
    def test_generated_from_time_and_task(self):
        from module.config.run_list import RunEntry, added_at_of_entry_id
        e = RunEntry(kind='task', task='RealmRaid')
        assert e.entry_id.endswith('-RealmRaid'), e.entry_id
        assert added_at_of_entry_id(e.entry_id) is not None, \
            'entry_id 前缀应是可解析的时间'

    def test_splittable(self):
        """★ 可拆: 剥掉时间前缀（与唯一化序号）得到 task。"""
        from module.config.run_list import task_of_entry_id
        assert task_of_entry_id('20261010T091255-RealmRaid') == 'RealmRaid'
        assert task_of_entry_id('20261010T091255-RealmRaid-2') == 'RealmRaid'

    def test_unknown_format_is_returned_as_is(self):
        """认不出格式就**原样返回** —— 不静默丢东西。"""
        from module.config.run_list import task_of_entry_id
        assert task_of_entry_id('RealmRaid') == 'RealmRaid'
        assert task_of_entry_id('whatever') == 'whatever'
        assert task_of_entry_id('') == ''

    def test_rest_entry_has_no_id(self):
        """「休息」条目没有条目身份的概念。"""
        from module.config.run_list import RunEntry
        assert RunEntry(kind='rest', minutes=30).entry_id == ''

    def test_roundtrip(self):
        from module.config.run_list import RunEntry
        e = RunEntry(kind='task', task='RealmRaid')
        assert RunEntry.from_dict(e.to_dict()).entry_id == e.entry_id

    def test_backward_compat_missing_id(self):
        """★ 旧配置**没有** `entry_id` -> 自动生成（向后兼容）。"""
        from module.config.run_list import RunEntry
        got = RunEntry.from_dict({'kind': 'task', 'task': 'RealmRaid'})
        assert got.entry_id, '旧配置读进来应该自动补 entry_id'


class TestEntryIdUniqueness:
    """★ 同一秒加两次同一任务, id 必须**不同**（否则按条目追踪失效）。"""

    def test_duplicates_get_unique_ids(self):
        from module.config.run_list import RunList, RunEntry
        rl = RunList()
        for _ in range(3):
            rl.add(RunEntry(kind='task', task='RealmRaid'))
        ids = [e.entry_id for e in rl.entries]
        assert len(set(ids)) == 3, f'entry_id 撞了: {ids}'
        # 前缀仍可读
        assert ids[0].endswith('-RealmRaid')
        assert ids[1].endswith('-2')
        assert ids[2].endswith('-3')

    def test_unique_ids_still_splittable(self):
        from module.config.run_list import RunList, RunEntry, task_of_entry_id
        rl = RunList()
        for _ in range(3):
            rl.add(RunEntry(kind='task', task='RealmRaid'))
        for e in rl.entries:
            assert task_of_entry_id(e.entry_id) == 'RealmRaid'

    def test_different_tasks_do_not_collide(self):
        from module.config.run_list import RunList, RunEntry
        rl = RunList()
        rl.add(RunEntry(kind='task', task='RealmRaid'))
        rl.add(RunEntry(kind='task', task='Delegation'))
        assert len({e.entry_id for e in rl.entries}) == 2

    def test_preserves_explicit_unique_id(self):
        """已经是唯一的 id -> **不该**被改（保持用户/上游给的身份）。"""
        from module.config.run_list import RunList, RunEntry
        rl = RunList()
        e = RunEntry(kind='task', task='RealmRaid',
                     entry_id='20200101T000000-RealmRaid')
        rl.add(e)
        assert e.entry_id == '20200101T000000-RealmRaid'


class TestPendingCarriesEntryId:
    """★ 选项 2（显式）: `pending` 里的 `Function` 要带 `entry_id`。"""

    @pytest.fixture()
    def live(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_function_has_entry_id_attribute(self):
        from module.config.config import Function
        f = Function('orochi', {'scheduler': {
            'enable': True, 'next_run': '2023-01-01 00:00:00', 'priority': 5}})
        assert hasattr(f, 'entry_id'), 'Function 必须有 entry_id 字段'

    def test_pending_items_carry_entry_id(self, live):
        """★ `update_scheduler()` 之后, `pending` 里每项都该有 `entry_id`。"""
        from module.config.run_list import RunEntry, RunList
        live.save_run_list(RunList([RunEntry(kind='task', task='Delegation')]))
        live.update_scheduler()
        missing = [getattr(f, 'command', '?')
                   for f in (live.pending_task or [])
                   if not getattr(f, 'entry_id', None)]
        assert not missing, (
            f'这些 pending 项没有 entry_id: {missing} —— '
            f'按条目追踪（选项 2）需要它')

    def test_duplicate_entries_yield_distinct_functions(self, live):
        """★★ 重复条目 -> `pending` 里应出现**两条**、`entry_id` **不同**。

        这是"重复跑整个任务"的机制基础。
        """
        from module.config.run_list import RunEntry, RunList
        live.save_run_list(RunList([
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='RealmRaid'),
        ]))
        live.update_scheduler()
        rr = [f for f in (live.pending_task or [])
              if getattr(f, 'command', None) == 'RealmRaid']
        if not rr:
            pytest.skip('RealmRaid 不在 pending（可能未启用或不在窗口）')
        ids = [f.entry_id for f in rr]
        assert len(rr) == 2, (
            f'重复条目应让 pending 出现两条 RealmRaid, 实际 {len(rr)}')
        assert len(set(ids)) == 2, f'两条的 entry_id 撞了: {ids}'
