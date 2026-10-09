# -*- coding: utf-8 -*-
"""固定任务与定时任务**分开管理**的调度语义。

## 用户确认的设计

| 概念 | 取值 | 含义 |
|---|---|---|
| `enable_fixed` | bool | **固定任务总开关** |
| `enable_timed` | bool | **定时任务总开关** |
| `timed_priority` | `timed` / `list` | 定时任务到点时, 怎么跟固定任务抢 |
| `rest_interleave` | bool | 休息期间可否**穿插**定时任务 |

### `timed_priority`

* **`timed`（定时优先）** —— 固定任务在跑 → 定时任务到点 →
  **打完当前这场战斗**（安全点）就让位去跑定时任务
* **`list`（列表优先）** —— 定时任务等固定任务跑完

★ 插队时机是**战斗边界**，不是立即打断 —— 与"暂停调度"同一个安全点。

### `rest_interleave`（休息时穿插）

判据（用户确认）:

    定时任务的**预期完成时间** < 休息剩余时间
    -> 允许穿插

★ 这条是为了**保护组队任务**: 休息期间如果在庭院干等，
  组队任务很难凑齐人；能穿插就把时间利用起来。

### 休息 = 去庭院

休息不是"什么都不做"，而是**去庭院待着** —— 游戏不会断线，
组队回来时人也"在"。
"""
import pytest

from module.config.run_list import EntryKind, RunList


class TestTimedPriorityConfig:
    """
    这四个字段属于 `Script.optimization`（全局）, 不是每个任务的。
    """

    def test_config_fields_exist(self):
        from tasks.Script.config_optimization import Optimization
        o = Optimization()
        for name in ('enable_fixed', 'enable_timed',
                     'timed_priority', 'rest_interleave'):
            assert hasattr(o, name), f'缺字段 {name}'

    def test_defaults_are_enabled(self):
        """默认两个开关都开着 —— 不改变现有用户的行为。"""
        from tasks.Script.config_optimization import Optimization
        o = Optimization()
        assert o.enable_fixed is True
        assert o.enable_timed is True

    def test_timed_priority_values(self):
        from tasks.Script.config_optimization import Optimization, TimedPriority
        assert {v.value for v in TimedPriority} == {'timed', 'list'}
        o = Optimization(timed_priority='timed')
        assert o.timed_priority == TimedPriority.TIMED

    def test_timed_priority_rejects_garbage(self):
        """
        非法值要**响亮失败**（抛 ValidationError）, 不是静默回落。

        ★ 注意 `Optimization` 是**纯 pydantic BaseModel**（不是 `ConfigBase`）,
          所以它**严格校验**。这与 `ConfigBase` 的"静默回落默认值"不同 ——
          对枚举这种"值必须是几个之一"的字段, 响亮失败更好:
          静默回落会让用户以为设置生效了。
        """
        from pydantic import ValidationError

        from tasks.Script.config_optimization import Optimization
        with pytest.raises(ValidationError):
            Optimization(timed_priority='nonsense')

    def test_rest_interleave_default_off(self):
        """
        默认**关**。

        因为"能不能穿插"取决于定时任务的预期完成时间是否可靠 ——
        默认开启会让没配期望值的任务被误判。
        """
        from tasks.Script.config_optimization import Optimization
        assert Optimization().rest_interleave is False


class TestTimedExpectedDuration:
    """每个定时任务的**预期完成时间** —— 穿插判定的输入。"""

    def test_field_exists_on_scheduler(self):
        """放在 `scheduler` 里(与 target 同级), 因为它也是调度决策。"""
        from tasks.Component.config_scheduler import Scheduler
        assert hasattr(Scheduler(), 'expected_minutes')

    def test_default_zero_means_unknown(self):
        """0 = 不知道 -> 不参与穿插判定(不能拿 0 去比)。"""
        from tasks.Component.config_scheduler import Scheduler
        assert Scheduler().expected_minutes == 0

    def test_negative_rejected_by_validation_falls_back(self):
        from tasks.Component.config_scheduler import Scheduler
        assert Scheduler(expected_minutes=-1).expected_minutes == 0


class TestInterleaveDecision:
    """
    穿插判定的**纯函数** —— 这样语义可以被测试固定下来。

    判定规则:
        1. `rest_interleave` 关 -> 不穿插
        2. 定时任务未启用 -> 不穿插
        3. 任务没到点 -> 不穿插
        4. `expected_minutes == 0`(未知) -> **不穿插**（保守）
        5. `expected_minutes <= 剩余休息时间` -> 穿插
        6. 否则 -> 不穿插
    """

    @staticmethod
    def decide(rest_interleave: bool, enable_timed: bool, is_due: bool,
               expected_minutes: int, rest_remaining_minutes: int) -> bool:
        from module.config.timed_schedule import can_interleave
        return can_interleave(
            rest_interleave=rest_interleave,
            enable_timed=enable_timed,
            is_due=is_due,
            expected_minutes=expected_minutes,
            rest_remaining_minutes=rest_remaining_minutes)

    def test_interleave_off_never(self):
        assert not self.decide(False, True, True, 5, 30)

    def test_timed_disabled_never(self):
        assert not self.decide(True, False, True, 5, 30)

    def test_not_due_never(self):
        assert not self.decide(True, True, False, 5, 30)

    def test_unknown_duration_is_conservative(self):
        """预期完成时间未知(0) -> **不穿插**, 宁可少穿插也不误判。"""
        assert not self.decide(True, True, True, 0, 30)

    def test_fits_exactly(self):
        """恰好相等算能塞进去。"""
        assert self.decide(True, True, True, 30, 30)

    def test_fits_with_room(self):
        assert self.decide(True, True, True, 10, 30)

    def test_does_not_fit(self):
        assert not self.decide(True, True, True, 31, 30)

    def test_negative_rest_remaining(self):
        """休息已结束 -> 不穿插。"""
        assert not self.decide(True, True, True, 5, 0)


class TestTwoMasterSwitches:
    """两个总开关的实际效果 —— 用**纯函数**表达, 便于测试。"""

    @staticmethod
    def should_consider(category_value: str, enable_fixed: bool,
                        enable_timed: bool) -> bool:
        from module.config.timed_schedule import should_consider
        return should_consider(category_value,
                               enable_fixed=enable_fixed,
                               enable_timed=enable_timed)

    @pytest.mark.parametrize('cat', ['fixed', 'toppa'])
    def test_fixed_switch_controls_fixed(self, cat):
        assert self.should_consider(cat, True, True)
        assert not self.should_consider(cat, False, True)
        # 定时开关不该影响固定任务
        assert self.should_consider(cat, True, False)

    @pytest.mark.parametrize('cat', ['timed', 'charge', 'limited'])
    def test_timed_switch_controls_timed(self, cat):
        assert self.should_consider(cat, True, True)
        assert not self.should_consider(cat, True, False)
        # 固定开关不该影响定时任务
        assert self.should_consider(cat, False, True)

    def test_unknown_category_is_ignored(self):
        """不认识的任务类别 -> 不参与调度（而不是崩）。"""
        assert not self.should_consider('nonsense', True, True)


class TestYieldToTimed:
    """
    固定任务在跑时, 要不要**让位**给已到点的定时任务。

    ★ 用户确认的语义:
      * `timed`（定时优先）—— 打完当前这场战斗就让位
      * `list`（列表优先）—— 等固定任务跑完

    ★ 调用时机是**战斗边界**（安全点）。本测试只管"该不该让",
      "什么时候让"由 `script.py` 在战斗结束时判断。
    """

    @staticmethod
    def yield_(priority, current_fixed=True, due=True, enable_timed=True):
        from module.config.timed_schedule import should_yield_to_timed
        return should_yield_to_timed(priority, current_fixed, due, enable_timed)

    def test_timed_priority_yields(self):
        assert self.yield_('timed') is True

    def test_list_priority_does_not_yield(self):
        assert self.yield_('list') is False

    def test_no_due_task_does_not_yield(self):
        """没有到点的定时任务 -> 没什么可让的。"""
        assert self.yield_('timed', due=False) is False

    def test_not_fixed_does_not_yield(self):
        """当前本来就在跑定时任务 -> 没什么可让的。"""
        assert self.yield_('timed', current_fixed=False) is False

    def test_timed_disabled_never_yields(self):
        """定时任务总开关关了 -> 永远不让位。"""
        assert self.yield_('timed', enable_timed=False) is False

    def test_garbage_priority_does_not_yield(self):
        """非法值 -> 保守（不让位）, 不崩。"""
        assert self.yield_('nonsense') is False
        assert self.yield_(None) is False

    def test_case_insensitive(self):
        assert self.yield_('TIMED') is True


class TestPartitionPending:
    """把 pending 分成"定时"与"其余", 便于定时任务优先。"""

    class F:
        def __init__(self, cmd):
            self.command = cmd

        def __repr__(self):
            return self.command

    def test_partition(self):
        from module.config import task_catalog as TC
        from module.config.timed_schedule import partition_pending

        def cat_of(cmd):
            m = TC.get(cmd)
            return m.category.value if m else ''

        pend = [self.F('Orochi'), self.F('DemonEncounter'),
                self.F('FallenSun'), self.F('GoldYoukai')]
        timed, others = partition_pending(pend, cat_of)
        assert [x.command for x in timed] == ['DemonEncounter', 'GoldYoukai']
        assert [x.command for x in others] == ['Orochi', 'FallenSun']

    def test_unknown_task_goes_to_others(self):
        """未知任务（没有 meta）-> 归到"其余", 不会被当成定时任务。"""
        from module.config.timed_schedule import partition_pending
        timed, others = partition_pending([self.F('NotARealTask')],
                                          lambda c: '')
        assert timed == []
        assert [x.command for x in others] == ['NotARealTask']

    def test_empty(self):
        from module.config.timed_schedule import partition_pending
        assert partition_pending([], lambda c: '') == ([], [])


class TestSortTimed:
    def test_sorts_by_key(self):
        from module.config.timed_schedule import sort_timed
        items = [{'n': 'b', 'k': 2}, {'n': 'a', 'k': 1}]
        got = sort_timed(items, lambda x: x['k'])
        assert [x['n'] for x in got] == ['a', 'b']

    def test_stable_for_equal_keys(self):
        from module.config.timed_schedule import sort_timed
        items = [{'n': 'a', 'k': 1}, {'n': 'b', 'k': 1}]
        got = sort_timed(items, lambda x: x['k'])
        assert [x['n'] for x in got] == ['a', 'b']

    def test_incomparable_key_does_not_crash(self):
        """键里有不可比较的东西 -> 宁可不排序, 也不要让调度崩掉。"""
        from module.config.timed_schedule import sort_timed
        items = [{'n': 'a'}, {'n': 'b'}]

        def bad_key(x):
            raise TypeError('unorderable')

        got = sort_timed(items, bad_key)
        assert [x['n'] for x in got] == ['a', 'b']

    def test_empty_and_none(self):
        from module.config.timed_schedule import sort_timed
        assert sort_timed([], lambda x: x) == []
        assert sort_timed(None, lambda x: x) == []


class TestTimedSortKey:
    """定时任务内部排序: 能否跑 > 到点程度 > 窗口快关 > 耗时短 > 用户优先级。"""

    def key(self, **kw):
        from module.config.timed_schedule import timed_sort_key
        return timed_sort_key(**kw)

    def test_out_of_window_sorts_last(self):
        early = self.key(next_run=1, in_window=False)
        late = self.key(next_run=9, in_window=True)
        assert late < early, '在窗口内的必须排前面（比 next_run 更重要）'

    def test_earlier_next_run_first(self):
        assert self.key(next_run=1) < self.key(next_run=5)

    def test_window_ending_sooner_first(self):
        """窗口快关的优先 —— 错过就彻底做不了。"""
        soon = self.key(next_run=1, window_end=10)
        later = self.key(next_run=1, window_end=100)
        assert soon < later

    def test_no_window_end_sorts_after(self):
        has_end = self.key(next_run=1, window_end=50)
        no_end = self.key(next_run=1, window_end=None)
        assert has_end < no_end

    def test_shorter_expected_first(self):
        short = self.key(next_run=1, expected_minutes=5)
        long_ = self.key(next_run=1, expected_minutes=60)
        assert short < long_

    def test_unknown_expected_sorts_after_known(self):
        known = self.key(next_run=1, expected_minutes=10)
        unknown = self.key(next_run=1, expected_minutes=0)
        assert known < unknown, '未知耗时排已知之后（不前不后也行, 但要有定论）'

    def test_priority_is_final_tiebreaker(self):
        hi = self.key(next_run=1, priority=1)
        lo = self.key(next_run=1, priority=9)
        assert hi < lo

    def test_time_beats_duration(self):
        """
        ★ 时间约束比"预计耗时"重要。

        窗口快关但耗时长的, 仍应排在窗口宽松但耗时短的前面 ——
        因为窗口关了就是彻底做不了。
        """
        urgent = self.key(next_run=1, window_end=10, expected_minutes=60)
        relaxed = self.key(next_run=1, window_end=1000, expected_minutes=5)
        assert urgent < relaxed

    def test_garbage_values_do_not_crash(self):
        self.key(next_run=1, expected_minutes='abc', priority=None)
        self.key(next_run=None, window_end=None)


class TestRunListContainsOnlyFixed:
    """列表里**只该有固定任务** —— 定时任务由定时调度器管。"""

    def test_run_list_rejects_timed_task(self):
        """
        往列表里塞定时任务时应被**拒绝**（宽容: 跳过并记录）。

        ★ 为什么不让它进列表: 定时任务有自己的 window/存量/周期,
          "在列表里执行"跟它的机制冲突。
        """
        from module.config.run_list import RunList

        bad = []
        rl = RunList.from_list(
            [
                {'kind': 'task', 'task': 'Orochi'},        # 固定任务
                {'kind': 'task', 'task': 'DemonEncounter'},  # 定时任务 -> 跳过
                {'kind': 'rest', 'minutes': 10},
            ],
            on_bad=lambda item, exc: bad.append(item))
        assert rl.task_order() == ['Orochi'], \
            f'定时任务不该进列表: {rl.task_order()}'
        assert len(bad) == 1, f'应记录一条被跳过: {bad}'

    def test_only_fixed_via_helper(self):
        """提供一个便捷判断: 该任务能不能进列表。"""
        from module.config.run_list import is_list_task
        assert is_list_task('Orochi') is True
        assert is_list_task('FallenSun') is True
        assert is_list_task('DemonEncounter') is False
        assert is_list_task('GoldYoukai') is False
