# -*- coding: utf-8 -*-
"""运行列表（条目清单 / 模型 B）的测试。

## 为什么是"条目清单"而不是"任务顺序"

早期实现只有 `task_order`（逗号分隔任务名）—— 那**只能排任务**，无法表达
"打完御魂后全部停止 30 分钟"这类**在序列中间发生的事**。

本模型把列表做成**有序条目**，条目三种：

    task   执行某个任务
    rest   **全部停止** N 分钟（连定时任务一起停）
    delay  **只停列表** N 分钟（定时任务照常）

★ 命名按**效果**而非"休息/延后"—— 用户明确要求，因为效果名一目了然。

## 关键语义（设计决定，不是实现细节）

| 条目 | 是否**阻塞**列表 | 理由 |
|---|---|---|
| `task` | ❌ 不阻塞 | 若阻塞，则"第一个任务在 6 小时冷却中"会卡死整个列表 |
| `rest` | ✅ 阻塞 | 这就是它存在的意义 |
| `delay` | ✅ 阻塞 | 同上 |

`rest` / `delay` 是**一次性条目**：时间到后**被移除**（持久化），
而不是每次循环都触发一次 —— 后者会让用户以为软件坏了。
"""
from datetime import datetime, timedelta

import pytest

from module.config.run_list import (DURATION_CHOICES, KIND_HELP, KIND_LABEL,
                                    EntryKind, RunEntry, RunList)
from module.config.scheduler import TaskScheduler
from tasks.Script.config_optimization import ScheduleRule


class TestRunEntry:
    def test_task_entry(self):
        e = RunEntry(kind=EntryKind.TASK, task='FallenSun')
        assert e.describe() == 'FallenSun'
        assert e.to_dict() == {'kind': 'task', 'task': 'FallenSun'}

    def test_rest_entry(self):
        e = RunEntry(kind=EntryKind.REST, minutes=30)
        assert '30 分钟' in e.describe()
        assert e.to_dict() == {'kind': 'rest', 'minutes': 30}

    def test_delay_entry(self):
        e = RunEntry(kind=EntryKind.DELAY, minutes=60)
        assert e.to_dict() == {'kind': 'delay', 'minutes': 60}

    def test_hours_are_readable(self):
        assert '小时' in RunEntry(kind=EntryKind.REST, minutes=120).describe()

    def test_string_kind_accepted(self):
        """宽松解析: 从 JSON 读出来是字符串。"""
        assert RunEntry(kind='rest', minutes=5).kind == EntryKind.REST

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValueError):
            RunEntry(kind='nonsense')

    def test_task_requires_name(self):
        with pytest.raises(ValueError):
            RunEntry(kind=EntryKind.TASK, task='')

    @pytest.mark.parametrize('mins', [0, -1])
    def test_non_task_requires_positive_minutes(self, mins):
        with pytest.raises(ValueError):
            RunEntry(kind=EntryKind.REST, minutes=mins)

    def test_non_task_rejects_bad_minutes(self):
        with pytest.raises(ValueError):
            RunEntry(kind=EntryKind.DELAY, minutes='abc')

    def test_task_entry_forces_minutes_zero(self):
        """task 条目不该带 minutes —— 自动归一化。"""
        assert RunEntry(kind=EntryKind.TASK, task='A', minutes=99).minutes == 0

    def test_non_task_forces_task_empty(self):
        assert RunEntry(kind=EntryKind.REST, minutes=5, task='X').task == ''


class TestRunEntryFromDict:
    def test_roundtrip(self):
        for e in (RunEntry(kind=EntryKind.TASK, task='A'),
                  RunEntry(kind=EntryKind.REST, minutes=7),
                  RunEntry(kind=EntryKind.DELAY, minutes=9)):
            assert RunEntry.from_dict(e.to_dict()) == e

    def test_lenient_kind_missing(self):
        """没有 kind 但给了 task -> 当作 task(旧数据兼容)。"""
        assert RunEntry.from_dict({'task': 'A'}).kind == EntryKind.TASK

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError):
            RunEntry.from_dict('not a dict')

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError):
            RunEntry.from_dict({'kind': 'xx'})


class TestRunListBasics:
    def sample(self):
        return RunList.from_list([
            {'kind': 'task', 'task': 'Exploration'},
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'rest', 'minutes': 30},
            {'kind': 'task', 'task': 'GoldYoukai'},
            {'kind': 'delay', 'minutes': 60},
        ])

    def test_length_and_iter(self):
        rl = self.sample()
        assert len(rl) == 5
        assert [e.kind for e in rl] == [
            EntryKind.TASK, EntryKind.TASK, EntryKind.REST,
            EntryKind.TASK, EntryKind.DELAY]

    def test_task_order_dedupes(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'A'},
            {'kind': 'task', 'task': 'B'},
            {'kind': 'task', 'task': 'A'},
        ])
        assert rl.task_order() == ['A', 'B'], '同名任务应去重'

    def test_blocking_entry_is_first_control(self):
        b = self.sample().blocking_entry()
        assert b.kind == EntryKind.REST and b.minutes == 30

    def test_index_of_blocker(self):
        assert self.sample().index_of_blocker() == 2

    def test_no_blocker_when_only_tasks(self):
        rl = RunList.from_list([{'kind': 'task', 'task': 'A'}])
        assert rl.blocking_entry() is None
        assert rl.index_of_blocker() == -1

    def test_add_and_remove(self):
        rl = RunList()
        rl.add(RunEntry(kind=EntryKind.TASK, task='A'))
        rl.add(RunEntry(kind=EntryKind.REST, minutes=5), index=0)
        assert rl.to_list()[0]['kind'] == 'rest'
        removed = rl.remove_at(0)
        assert removed.kind == EntryKind.REST
        assert len(rl) == 1

    def test_remove_blocker(self):
        rl = self.sample()
        rl.remove_blocker()
        assert rl.index_of_blocker() == 3, '移除第一个阻塞条目后, 应是后面的 delay'

    def test_serialization_roundtrip(self):
        rl = self.sample()
        assert RunList.from_list(rl.to_list()).to_list() == rl.to_list()

    def test_from_list_is_lenient(self):
        """
        坏条目**跳过**, 不让一条写坏整份配置。

        这是刻意的: 列表是用户编辑的内容。
        """
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'A'},
            {'kind': 'rest', 'minutes': 0},    # 非法
            None,                               # 不是对象
            {'kind': 'xx'},                     # 未知类型
            {'kind': 'task'},                   # 缺 task
            {'kind': 'delay', 'minutes': 15},   # 合法
        ])
        assert len(rl) == 2
        assert [e.kind for e in rl] == [EntryKind.TASK, EntryKind.DELAY]

    def test_on_bad_callback(self):
        seen = []
        RunList.from_list([{'kind': 'xx'}], on_bad=lambda i, e: seen.append(i))
        assert seen == [{'kind': 'xx'}]

    def test_empty(self):
        assert RunList.from_list(None).is_empty()
        assert RunList.from_list([]).is_empty()


class TestLegacyCompat:
    """旧的 `task_order`(逗号分隔)必须还能用。"""

    def test_from_task_order(self):
        rl = RunList.from_task_order('A,B,C')
        assert len(rl) == 3
        assert all(e.kind == EntryKind.TASK for e in rl)
        assert rl.task_order() == ['A', 'B', 'C']

    def test_from_task_order_tolerates_spaces_and_blanks(self):
        rl = RunList.from_task_order(' A , , B ,')
        assert rl.task_order() == ['A', 'B']

    def test_to_task_order(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'A'},
            {'kind': 'rest', 'minutes': 5},
            {'kind': 'task', 'task': 'B'},
        ])
        assert rl.to_task_order() == 'A,B'

    def test_from_empty(self):
        assert RunList.from_task_order('').is_empty()
        assert RunList.from_task_order(None).is_empty()


class TestReorder:
    """
    两种重排方式, 用途不同 —— 混用会出错。
    """

    def test_set_from_task_order_keeps_control_in_place(self):
        """
        只给任务名时, 控制条目的**下标不变**。

        因为任务名列表里没有控制条目的位置信息, 只能原地不动。
        """
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'A'},
            {'kind': 'rest', 'minutes': 10},
            {'kind': 'task', 'task': 'B'},
            {'kind': 'task', 'task': 'C'},
        ])
        rl.set_from_task_order(['C', 'A', 'B'])
        lst = rl.to_list()
        assert [e['task'] for e in lst if e['kind'] == 'task'] == ['C', 'A', 'B']
        assert lst[1]['kind'] == 'rest', 'rest 应仍在第 2 位'

    def test_set_from_task_order_appends_new_tasks(self):
        rl = RunList.from_list([{'kind': 'task', 'task': 'A'}])
        rl.set_from_task_order(['A', 'B', 'C'])
        assert rl.task_order() == ['A', 'B', 'C']

    def test_set_from_task_order_can_shrink(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'A'},
            {'kind': 'task', 'task': 'B'},
            {'kind': 'task', 'task': 'C'},
        ])
        rl.set_from_task_order(['A'])
        assert rl.task_order() == ['A'], '应只留下给定的任务'
        assert len(rl) == 1, '多余的槽位应被移除'

    def test_replace_all_allows_inserting_control_anywhere(self):
        """
        ★ 模型 B 的核心: 控制条目可以**插到任意位置**。

        界面拖拽走这条路径 —— 用户拖的就是完整清单, 位置信息完整。
        """
        rl = RunList([RunEntry(kind=EntryKind.TASK, task='A')])
        rl.replace_all([
            {'kind': 'task', 'task': 'A'},
            {'kind': 'rest', 'minutes': 20},
            {'kind': 'task', 'task': 'B'},
        ])
        lst = rl.to_list()
        assert [e['kind'] for e in lst] == ['task', 'rest', 'task']
        assert lst[1]['minutes'] == 20

    def test_replace_all_accepts_runentry_objects(self):
        rl = RunList()
        rl.replace_all([RunEntry(kind=EntryKind.TASK, task='A'),
                        RunEntry(kind=EntryKind.DELAY, minutes=5)])
        assert len(rl) == 2

    def test_replace_all_with_empty(self):
        rl = RunList([RunEntry(kind=EntryKind.TASK, task='A')])
        rl.replace_all([])
        assert rl.is_empty()


class TestListRuleScheduling:
    """`ScheduleRule.LIST` 按 run_list 的 task 顺序排 pending 任务。"""

    class F:
        def __init__(self, cmd, nr='2026-01-01 00:00:00'):
            self.command = cmd
            self.next_run = nr
            self.priority = 5

        def __repr__(self):
            return self.command

    def test_orders_by_run_list(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Exploration'},
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'task', 'task': 'GoldYoukai'},
        ])
        pend = [self.F('GoldYoukai'), self.F('MemoryScrolls'),
                self.F('Exploration'), self.F('Orochi')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.LIST, list(pend), rl)]
        assert got[:3] == ['Exploration', 'Orochi', 'GoldYoukai']
        assert got[-1] == 'MemoryScrolls', '未编排的排最后'

    def test_control_entries_do_not_appear_as_tasks(self):
        rl = RunList.from_list([
            {'kind': 'rest', 'minutes': 10},
            {'kind': 'task', 'task': 'A'},
        ])
        pend = [self.F('A'), self.F('B')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.LIST, list(pend), rl)]
        assert got[0] == 'A'
        assert set(got) == {'A', 'B'}, '控制条目不该引入任务'

    def test_legacy_string_still_works(self):
        pend = [self.F('B'), self.F('A')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.LIST, list(pend), 'B,A')]
        assert got[:2] == ['B', 'A']

    def test_empty_run_list_falls_back_to_list_pos(self):
        """空清单 -> 回退到各任务 `meta.py` 的 `list_pos`。"""
        pend = [self.F('FallenSun'), self.F('SoulsTidy')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.LIST, list(pend), RunList())]
        # SoulsTidy 的 list_pos 是 1, 应排在前面
        assert got[0] == 'SoulsTidy', f'应按 list_pos 排(期望 SoulsTidy 在前): {got}'

    def test_restart_always_first(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'FallenSun'},
            {'kind': 'task', 'task': 'Restart'},
        ])
        pend = [self.F('FallenSun'), self.F('Restart')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.LIST, list(pend), rl)]
        assert got[0] == 'Restart'


class TestPreview:
    """预演(界面「预期执行流程」面板)。

    ★ 必须标注是**推算**, 不是保证。
    """

    def test_rest_advances_time(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'A'},
            {'kind': 'rest', 'minutes': 30},
            {'kind': 'task', 'task': 'B'},
        ])
        pv = rl.preview(datetime(2026, 10, 9, 10, 0))
        assert pv[0]['at'] == datetime(2026, 10, 9, 10, 0)
        assert pv[2]['at'] == datetime(2026, 10, 9, 10, 30)

    def test_delay_advances_time(self):
        rl = RunList.from_list([
            {'kind': 'delay', 'minutes': 60},
            {'kind': 'task', 'task': 'A'},
        ])
        pv = rl.preview(datetime(2026, 10, 9, 10, 0))
        assert pv[1]['at'] == datetime(2026, 10, 9, 11, 0)

    def test_tasks_share_same_instant(self):
        """任务条目只定**先后**, 不定间隔。"""
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'A'},
            {'kind': 'task', 'task': 'B'},
        ])
        pv = rl.preview(datetime(2026, 10, 9, 10, 0))
        assert pv[0]['at'] == pv[1]['at']

    def test_note_marks_running(self):
        rl = RunList.from_list([{'kind': 'task', 'task': 'A'}])
        pv = rl.preview(datetime(2026, 10, 9, 10, 0),
                        running_lookup=lambda t: t == 'A')
        assert pv[0]['note'] == '进行中'


class TestNamingAndLabels:
    """效果命名(用户明确要求)。"""

    def test_effect_based_names(self):
        assert KIND_LABEL[EntryKind.REST] == '全部停止'
        assert KIND_LABEL[EntryKind.DELAY] == '只停列表'

    def test_labels_are_distinguishable(self):
        """两个名字必须能一眼区分 —— 这是改名的目的。"""
        assert KIND_LABEL[EntryKind.REST] != KIND_LABEL[EntryKind.DELAY]

    def test_help_text_explains_timed_task_behaviour(self):
        """说明里必须写明对**定时任务**的不同处理(这是两者唯一区别)。"""
        assert '定时任务一起停' in KIND_HELP[EntryKind.REST]
        assert '定时任务照常' in KIND_HELP[EntryKind.DELAY]

    def test_duration_choices_positive(self):
        assert all(m > 0 for m in DURATION_CHOICES)
        assert DURATION_CHOICES == tuple(sorted(DURATION_CHOICES))
