# -*- coding: utf-8 -*-
"""运行列表（**固定任务 + 休息**）的测试。

## v2 的设计（用户确认）

| 谁来管 | 内容 | 排序依据 |
|---|---|---|
| **运行列表** | 固定任务 + **休息** | 用户拖拽的顺序 |
| **定时调度器** | `timed` / `charge` / `limited` | window、剩余时间、预计耗时、自定义优先级 |

### 条目只有两种（按效果命名）

    task   跑一个**固定任务**
    rest   **休息** —— 去**庭院**待着 N 分钟

### 为什么去掉了 v1 的 `delay`

v1 有 `delay`（"只停列表"）与 `rest`（"全部停止"），用于表达
"连定时任务一起停 / 只停列表"。但 v2 之后**固定与定时分开管理**
（定时任务有自己的总开关），这两个概念都不需要了 ——
想只停列表就关掉定时任务开关。

### 关键语义

* `task` **不阻塞**列表 —— 未就绪（冷却/额度/不在时段）就**跳过它继续看后面的**。
  否则"列表里第一个任务在 6 小时冷却中"会**卡死整个列表**。
* `rest` **阻塞**列表 —— 这就是它存在的意义。生效后**移除该条目**
  （用户看到的是"这一行消失了"，而不是每次循环都休息一次）。
"""
from datetime import datetime, timedelta

import pytest

from module.config.run_list import (DURATION_CHOICES, KIND_HELP, KIND_LABEL,
                                    EntryKind, RunEntry, RunList, is_list_task)
from tasks.Script.config_optimization import ScheduleRule


class TestEntryKind:
    def test_only_two_kinds(self):
        """v2 只保留 `task` 与 `rest`（`delay` 已作废）。"""
        assert {k.value for k in EntryKind} == {'task', 'rest'}

    def test_labels_are_effect_based(self):
        """按**效果**命名, 不用"停止/延后"那种容易误解的词。"""
        assert KIND_LABEL[EntryKind.TASK] == '任务'
        assert KIND_LABEL[EntryKind.REST] == '休息'

    def test_rest_help_mentions_town(self):
        """休息 = **去庭院**待着（不是"什么都不做"）。"""
        assert '庭院' in KIND_HELP[EntryKind.REST]

    def test_duration_choices_positive_sorted(self):
        assert DURATION_CHOICES == tuple(sorted(DURATION_CHOICES))
        assert all(m > 0 for m in DURATION_CHOICES)


class TestRunEntry:
    def test_task_entry(self):
        e = RunEntry(kind=EntryKind.TASK, task='FallenSun')
        # ★ C: `describe()` 现在带"加入时间"（同一任务多条时用来区分）
        assert 'FallenSun' in e.describe()
        # ★ C: `to_dict()` 现在**带 `entry_id`**（条目身份）
        d = e.to_dict()
        assert d['kind'] == 'task' and d['task'] == 'FallenSun'
        assert d['entry_id'] == e.entry_id and e.entry_id, \
            'to_dict 必须带 entry_id（重复条目的身份）'

    def test_rest_entry_shows_unit(self):
        """界面显示要带单位 —— `30 分钟` / `2 小时`, 不是裸数字。"""
        e = RunEntry(kind=EntryKind.REST, minutes=30)
        assert '30 分钟' in e.describe()
        assert e.to_dict() == {'kind': 'rest', 'minutes': 30}
        assert '小时' in RunEntry(kind=EntryKind.REST, minutes=120).describe()

    def test_string_kind_accepted(self):
        assert RunEntry(kind='rest', minutes=5).kind == EntryKind.REST

    def test_invalid_kind_rejected(self):
        with pytest.raises(ValueError):
            RunEntry(kind='nonsense')

    def test_delay_kind_rejected(self):
        """v1 的 `delay` 不再合法。"""
        with pytest.raises(ValueError):
            RunEntry(kind='delay', minutes=5)

    def test_task_requires_name(self):
        with pytest.raises(ValueError):
            RunEntry(kind=EntryKind.TASK, task='')

    @pytest.mark.parametrize('mins', [0, -1])
    def test_rest_requires_positive_minutes(self, mins):
        with pytest.raises(ValueError):
            RunEntry(kind=EntryKind.REST, minutes=mins)

    def test_task_entry_forces_minutes_zero(self):
        assert RunEntry(kind=EntryKind.TASK, task='A', minutes=99).minutes == 0


class TestRunEntryFromDict:
    def test_roundtrip(self):
        for e in (RunEntry(kind=EntryKind.TASK, task='A'),
                  RunEntry(kind=EntryKind.REST, minutes=7)):
            assert RunEntry.from_dict(e.to_dict()) == e

    def test_lenient_kind_missing(self):
        assert RunEntry.from_dict({'task': 'A'}).kind == EntryKind.TASK

    def test_rejects_non_dict(self):
        with pytest.raises(ValueError):
            RunEntry.from_dict('not a dict')

    def test_rejects_delay(self):
        with pytest.raises(ValueError):
            RunEntry.from_dict({'kind': 'delay', 'minutes': 5})

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError):
            RunEntry.from_dict({'kind': 'xx'})


class TestRunListBasics:
    def sample(self):
        # ★ 只用固定任务（Orochi / FallenSun / GoryouRealm 都是 fixed）
        return RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'task', 'task': 'FallenSun'},
            {'kind': 'rest', 'minutes': 30},
            {'kind': 'task', 'task': 'GoryouRealm'},
        ])

    def test_length_and_iter(self):
        rl = self.sample()
        assert len(rl) == 4
        assert [e.kind for e in rl] == [
            EntryKind.TASK, EntryKind.TASK, EntryKind.REST, EntryKind.TASK]

    def test_task_order_dedupes(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'task', 'task': 'FallenSun'},
            {'kind': 'task', 'task': 'Orochi'},
        ])
        assert rl.task_order() == ['Orochi', 'FallenSun'], '同名任务应去重'

    def test_blocking_entry_is_rest(self):
        b = self.sample().blocking_entry()
        assert b is not None and b.kind == EntryKind.REST and b.minutes == 30
        assert self.sample().index_of_blocker() == 2

    def test_task_does_not_block(self):
        """
        `task` **不阻塞** —— 只有 rest 会。

        ★ 若 task 阻塞, "列表里第一个任务在 6 小时冷却中"会卡死整个列表。
        """
        rl = RunList.from_list([{'kind': 'task', 'task': 'Orochi'}])
        assert rl.blocking_entry() is None
        assert rl.index_of_blocker() == -1

    def test_total_rest_minutes(self):
        assert self.sample().total_rest_minutes() == 30

    def test_total_rest_minutes_zero_when_no_rest(self):
        rl = RunList.from_list([{'kind': 'task', 'task': 'Orochi'}])
        assert rl.total_rest_minutes() == 0

    def test_add_and_remove(self):
        rl = RunList()
        rl.add(RunEntry(kind=EntryKind.TASK, task='Orochi'))
        rl.add(RunEntry(kind=EntryKind.REST, minutes=5), index=0)
        assert rl.to_list()[0]['kind'] == 'rest'
        removed = rl.remove_at(0)
        assert removed.kind == EntryKind.REST
        assert len(rl) == 1

    def test_remove_blocker(self):
        rl = self.sample()
        rl.remove_blocker()
        assert rl.index_of_blocker() == -1, '示例里只有一个 rest'
        assert len(rl) == 3

    def test_serialization_roundtrip(self):
        rl = self.sample()
        assert RunList.from_list(rl.to_list()).to_list() == rl.to_list()

    def test_from_list_is_lenient(self):
        """坏条目**跳过**, 不让一条写坏整份配置（列表是用户编辑的内容）。"""
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'rest', 'minutes': 0},      # 非法
            None,                                 # 不是对象
            {'kind': 'xx'},                       # 未知类型
            {'kind': 'delay', 'minutes': 5},      # v1 遗留
            {'kind': 'task'},                     # 缺 task
            {'kind': 'rest', 'minutes': 15},      # 合法
        ])
        assert len(rl) == 2
        assert [e.kind for e in rl] == [EntryKind.TASK, EntryKind.REST]

    def test_on_bad_callback(self):
        seen = []
        RunList.from_list([{'kind': 'xx'}], on_bad=lambda i, e: seen.append(i))
        assert seen == [{'kind': 'xx'}]

    def test_empty(self):
        assert RunList.from_list(None).is_empty()
        assert RunList.from_list([]).is_empty()


class TestListAcceptsAnyTask:
    """
    ★★ 列表**接受任意任务名** —— 这是踩过坑之后的决定 ★★

    ## 曾经的错误

    为了"固定/定时分开管理", 在 `from_list()` 里加了校验:
    **只允许 `countable`(fixed/toppa) 的任务进列表**, 其余跳过。

    后果是一次**静默的数据破坏**:

    * `countable` 的判据是"有 `count_field`", 54 个任务里只有 **14 个**
    * `WantedQuests` 是 `fixed` 却**没有** `count_field` -> 被丢弃
    * 用户的 7 个条目（`DemonEncounter` / `WantedQuests` / `MysteryShop` /
      `Duel` / `ExperienceYoukai` / `TrueOrochi` / `WeeklyTrifles`）**全被跳过**
    * 更糟: `build_run_list()` 过滤后 `save_run_list()` 会把**过滤结果写回**
      -> 用户的编排可能被永久抹掉

    ## 现在的规则

    列表接受任意任务名。"固定/定时分开管理"是**调度器**的事
    （`enable_fixed` / `enable_timed` / `timed_priority`），
    不该由**列表的准入规则**承担。
    """

    def test_is_list_task_is_only_a_query_helper(self):
        """
        `is_list_task` 仍是"是否可计数"的**查询辅助**, 但**不用于过滤**。
        """
        assert is_list_task('Orochi') is True
        assert is_list_task('FallenSun') is True
        assert is_list_task('DemonEncounter') is False   # timed
        assert is_list_task('GoldYoukai') is False        # charge
        assert is_list_task('NotARealTask') is False      # 未知 -> 不崩

    def test_timed_task_is_kept(self):
        """★ 定时任务**不该**被跳过（这就是那个数据破坏）。"""
        bad = []
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},           # 固定
            {'kind': 'task', 'task': 'DemonEncounter'},   # 定时
            {'kind': 'rest', 'minutes': 10},
        ], on_bad=lambda item, exc: bad.append(item))
        assert rl.task_order() == ['Orochi', 'DemonEncounter'], \
            f'定时任务不该被丢弃: {rl.task_order()}'
        assert bad == [], f'不该有坏条目: {bad}'

    def test_the_seven_tasks_that_were_destroyed(self):
        """
        ★ **回归守卫**: 日志里被丢弃的那 7 个条目必须全部保留。

        它们来自真实用户的 `run_list`, 我把它固化成测试 ——
        这样"只收固定任务"这类改动一旦回来, 立刻红。
        """
        tasks = ['DemonEncounter', 'WantedQuests', 'MysteryShop', 'Duel',
                 'ExperienceYoukai', 'TrueOrochi', 'WeeklyTrifles']
        bad = []
        rl = RunList.from_list(
            [{'kind': 'task', 'task': t} for t in tasks],
            on_bad=lambda item, exc: bad.append(item))
        assert rl.task_order() == tasks, f'条目被丢弃: {rl.task_order()}'
        assert bad == []

    def test_only_list_tasks_is_opt_in_and_not_default(self):
        """
        `only_list_tasks` 默认必须是 `False`。

        ★ 曾经默认 `True` -> 静默丢条目。这个断言防止它被改回去。
        """
        import inspect
        sig = inspect.signature(RunList.from_list)
        assert sig.parameters['only_list_tasks'].default is False

    def test_opt_in_filter_still_works(self):
        """显式传 `True` 时过滤仍生效（供"只想看固定任务"的查询场景）。"""
        rl = RunList.from_list(
            [{'kind': 'task', 'task': 'DemonEncounter'}],
            only_list_tasks=True)
        assert rl.task_order() == []

    def test_bad_entries_are_still_skipped(self):
        """只跳过**真正坏的**（结构错误 / 未知类型 / 数字非法）。"""
        bad = []
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'rest', 'minutes': 0},      # 数字非法
            None,                                 # 不是对象
            {'kind': 'xx'},                       # 未知类型
            {'kind': 'delay', 'minutes': 5},      # v1 遗留
            {'kind': 'task'},                     # 缺 task
        ], on_bad=lambda item, exc: bad.append(item))
        assert len(rl) == 1
        assert len(bad) == 5, f'应记录 5 条坏条目: {len(bad)}'


class TestLegacyCompat:
    def test_from_task_order(self):
        rl = RunList.from_task_order('Orochi,FallenSun')
        assert rl.task_order() == ['Orochi', 'FallenSun']

    def test_from_task_order_tolerates_spaces_and_blanks(self):
        assert RunList.from_task_order(' A , , B ,').task_order() == ['A', 'B']

    def test_to_task_order(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'rest', 'minutes': 5},
            {'kind': 'task', 'task': 'FallenSun'},
        ])
        assert rl.to_task_order() == 'Orochi,FallenSun'

    def test_from_empty(self):
        assert RunList.from_task_order('').is_empty()
        assert RunList.from_task_order(None).is_empty()


class TestReorder:
    """两种重排方式, 用途不同 —— 混用会出错。"""

    def test_set_from_task_order_keeps_control_in_place(self):
        """只给任务名时, 休息条目的**下标不变**。"""
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'rest', 'minutes': 10},
            {'kind': 'task', 'task': 'FallenSun'},
            {'kind': 'task', 'task': 'GoryouRealm'},
        ])
        rl.set_from_task_order(['GoryouRealm', 'Orochi', 'FallenSun'])
        lst = rl.to_list()
        assert [e['task'] for e in lst if e['kind'] == 'task'] == \
            ['GoryouRealm', 'Orochi', 'FallenSun']
        assert lst[1]['kind'] == 'rest', 'rest 应仍在第 2 位'

    def test_set_from_task_order_appends_new(self):
        rl = RunList.from_list([{'kind': 'task', 'task': 'Orochi'}])
        rl.set_from_task_order(['Orochi', 'FallenSun', 'GoryouRealm'])
        assert rl.task_order() == ['Orochi', 'FallenSun', 'GoryouRealm']

    def test_set_from_task_order_can_shrink(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'task', 'task': 'FallenSun'},
            {'kind': 'task', 'task': 'GoryouRealm'},
        ])
        rl.set_from_task_order(['Orochi'])
        assert rl.task_order() == ['Orochi']
        assert len(rl) == 1, '多余的槽位应被移除'

    def test_replace_all_inserts_control_anywhere(self):
        """★ 核心: 休息条目可以插到**任意位置**。"""
        rl = RunList([RunEntry(kind=EntryKind.TASK, task='Orochi')])
        rl.replace_all([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'rest', 'minutes': 20},
            {'kind': 'task', 'task': 'FallenSun'},
        ])
        lst = rl.to_list()
        assert [e['kind'] for e in lst] == ['task', 'rest', 'task']
        assert lst[1]['minutes'] == 20

    def test_replace_all_accepts_runentry_objects(self):
        rl = RunList()
        rl.replace_all([RunEntry(kind=EntryKind.TASK, task='Orochi'),
                        RunEntry(kind=EntryKind.REST, minutes=5)])
        assert len(rl) == 2

    def test_replace_all_with_empty(self):
        rl = RunList([RunEntry(kind=EntryKind.TASK, task='Orochi')])
        rl.replace_all([])
        assert rl.is_empty()


# ★★ 第二轮复审（待办 #4）: `TestListRuleScheduling` **已删除** ★★
#
# 它整类测的是 `TaskScheduler.schedule(ScheduleRule.LIST, ...)` —— 那个类
# **生产 0 调用**（剥注释全仓核实: `module/` + `tasks/` 里只有它自己的
# 定义）, 已随 `module/config/scheduler.py` 一起删除。
#
# ★ 那 4 条断言的是「`ScheduleRule.LIST` 按 run_list 顺序排 pending」——
#   这个**语义本身已经搬到** `Config._order_by_queue()`（队列是唯一顺序
#   权威, 且**不再看 `schedule_rule`**）—— 现行守卫在
#   `test_queue_is_authority.py` 与 `test_execution_queue.py::TestWiring`。
#
# ★ 又一次印证: **覆盖率高 != 有人在管** —— 这 4 条忠实覆盖了死代码,
#   全绿但没有任何生产路径会走到它们。

class TestPreview:
    """预演（界面「预期执行流程」面板）—— 推算, 不是保证。"""

    def test_rest_advances_time(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'rest', 'minutes': 30},
            {'kind': 'task', 'task': 'FallenSun'},
        ])
        pv = rl.preview(datetime(2026, 10, 9, 10, 0))
        assert len(pv) == 3
        assert pv[0]['at'] == datetime(2026, 10, 9, 10, 0)
        assert pv[1]['at'] == datetime(2026, 10, 9, 10, 30)
        assert pv[2]['at'] == datetime(2026, 10, 9, 10, 30)

    def test_tasks_share_same_instant(self):
        """任务条目只定**先后**, 不定间隔。"""
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'task', 'task': 'FallenSun'},
        ])
        pv = rl.preview(datetime(2026, 10, 9, 10, 0))
        assert pv[0]['at'] == pv[1]['at']

    def test_timestamps_monotonic(self):
        rl = RunList.from_list([
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'rest', 'minutes': 10},
            {'kind': 'rest', 'minutes': 10},
            {'kind': 'task', 'task': 'FallenSun'},
        ])
        ats = [p['at'] for p in rl.preview(datetime(2026, 10, 9, 10, 0))]
        assert ats == sorted(ats), '预演时间必须单调不减'

    def test_note_marks_running(self):
        rl = RunList.from_list([{'kind': 'task', 'task': 'Orochi'}])
        pv = rl.preview(datetime(2026, 10, 9, 10, 0),
                        running_lookup=lambda t: t == 'Orochi')
        assert pv[0]['note'] == '进行中'


# ---------------------------------------------------------------
# ★ 从 test_priority_mode.py 搬来（原文件测的是已删的「调度优先级三模式」，
#   已经整文件删掉；这三条测的是 `RunEntry.group` 的**派生性**，与模式无关，
#   仍然有效 —— 所以搬到这里，而不是连带删掉）。
# ---------------------------------------------------------------
class TestRunEntryGroup:
    def test_group_is_attribute(self):
        """★ `group` 是**内存属性**（`build_queue()` 每次重算）。"""
        from module.config.run_list import RunEntry
        e = RunEntry(kind='task', task='Orochi', group='fixed')
        assert e.group == 'fixed'

    def test_group_is_never_persisted(self):
        """★★ 审计修复: `group` **永不落盘** ★★

        ## 为什么

        段名是 `Config._tag_and_place_rest()` 的**派生结果**, 每次
        `build_queue()` 都会重算。存盘只会:
          ① 破坏"单一数据源"（台账 §10.8）
          ② 前端判据与后端不一致时, 配置里躺着**错的段名**
          ③ 让配置文件多出一堆"用户没写过"的字段

        ★ 我第一版让它"非空才写" —— 但 `_assign_groups()` 会把它算成**非空**,
          于是**照样落盘**（实测抓到）。所以改成**永不写**。
        """
        from module.config.run_list import RunEntry
        for g in ('', 'timed', 'fixed'):
            d = RunEntry(kind='task', task='Orochi', group=g).to_dict()
            assert 'group' not in d, f'group={g!r} 被序列化了: {d}'

    def test_from_dict_still_accepts_group(self):
        """★ 旧配置/前端若带了 `group`, 解析时**接受**（不报错）—— 只是不落盘。"""
        from module.config.run_list import RunEntry
        e = RunEntry.from_dict({'kind': 'task', 'task': 'Orochi',
                                'entry_id': 'x', 'group': 'timed'})
        assert e.group == 'timed'
        assert 'group' not in e.to_dict()

    def test_legacy_config_without_group(self):
        """★ 旧配置没有 `group` -> 空串（**向后兼容**）。"""
        from module.config.run_list import RunEntry
        e = RunEntry.from_dict({'kind': 'task', 'task': 'Orochi',
                                'entry_id': 'x'})
        assert e.group == ''
