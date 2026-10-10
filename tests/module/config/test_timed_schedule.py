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

    # ★ S5: `'charge'` 已删（充能机制移除, 用户裁定）
    @pytest.mark.parametrize('cat', ['timed', 'limited'])
    def test_timed_switch_controls_timed(self, cat):
        assert self.should_consider(cat, True, True)
        assert not self.should_consider(cat, True, False)
        # 固定开关不该影响定时任务
        assert self.should_consider(cat, False, True)

    def test_unknown_category_is_ignored(self):
        """不认识的任务类别 -> 不参与调度（而不是崩）。"""
        assert not self.should_consider('nonsense', True, True)


# ★★ 第二轮复审（待办 #4）: **删掉 4 个测试类** —— 被测函数已删除 ★★
#
# | 被删的类 | 测的函数 | 为什么删 |
# |---|---|---|
# | `TestYieldToTimed` | `should_yield_to_timed` | ★ 生产**只有定义**, 0 调用 |
# | `TestPartitionPending` | `partition_pending` | 同上 |
# | `TestSortTimed` | `sort_timed` | 同上 |
# | `TestTimedSortKey` | `timed_sort_key` | 同上 |
#
# ★ 保留 `TestInterleaveDecision`（测 `can_interleave`, **仍活**）与
#   `TestTwoMasterSwitches`（测 `should_consider`, **仍活**）。
#
# ★ 教训: 这些测试**忠实覆盖了死代码** —— 于是"覆盖率高"给人一种
#   "这块有人管"的错觉, 而实际上**没有任何生产路径**会走到它们。
#   这就是为什么"删死代码"必须**连带删它的测试**。

class TestRunListAndTaskCategories:
    """
    ⚠️ 这里曾经断言"列表**只该有固定任务**"（定时任务被拒绝）。

    **那个设计是错的** —— 它在真实使用中造成了一次**静默的数据破坏**:
    `countable` 的判据是"有 `count_field`", 54 个任务里只有 14 个满足,
    于是用户列表里的 `DemonEncounter` / `WantedQuests` / `MysteryShop` /
    `Duel` / `ExperienceYoukai` / `TrueOrochi` / `WeeklyTrifles`
    **全部被跳过**, 而过滤结果还会被 `save_run_list()` 写回配置。

    现在的规则（见 `module/config/run_list.py` 的"踩过的坑"）:

    **列表接受任意任务名。** "固定/定时分开管理"是**调度器**的事
    （`enable_fixed` / `enable_timed` / `timed_priority`）。
    """

    def test_run_list_keeps_timed_task(self):
        from module.config.run_list import RunList

        bad = []
        rl = RunList.from_list(
            [
                {'kind': 'task', 'task': 'Orochi'},           # 固定
                {'kind': 'task', 'task': 'DemonEncounter'},   # 定时
                {'kind': 'rest', 'minutes': 10},
            ],
            on_bad=lambda item, exc: bad.append(item))
        assert rl.task_order() == ['Orochi', 'DemonEncounter'], \
            f'定时任务不该被丢弃: {rl.task_order()}'
        assert bad == [], f'不该有坏条目: {bad}'

    def test_is_list_task_is_only_a_query_helper(self):
        """
        `is_list_task` = "是否可计数"的查询辅助, **不是列表准入规则**。
        """
        from module.config.run_list import is_list_task
        assert is_list_task('Orochi') is True
        assert is_list_task('FallenSun') is True
        assert is_list_task('DemonEncounter') is False
        assert is_list_task('GoldYoukai') is False
