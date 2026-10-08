# -*- coding: utf-8 -*-
"""任务列表（调度器的一种模式）的测试。

## 设计（见 docs/architecture.md §5）

**任务列表就是一个调度器模式**, 不是新子系统。三个概念:

| 概念 | 实现 |
|---|---|
| 列表顺序 | `TaskSpec.list_pos`（`None` = 未编排, 排最后） |
| 用户编排 | `Script.optimization.task_order`（逗号分隔任务名） |
| 每行次数 | `Scheduler.target`（`0` = 用任务配置的默认值） |

## 为什么改这个

原先调度顺序**硬编码**在 `module/config/config_manual.py`:

    SCHEDULER_PRIORITY = "Restart > SoulsTidy > KekkaiUtilize > ..."

用户**改不了**。`ScheduleRule.FIFO` 是按 `next_run`（先到点先跑）,
仍是"定时优先", 不是"列表优先"。

新增 `ScheduleRule.LIST` + `task_order`, 顺序终于可编排。

## 迁移时发现的两处不一致(已记录)

* 清单里的 `OrochiMoans` / `OrochiJudgement` —— **任务早已不存在**(陈旧条目)
* `FindJade` / `GotoMain` 是任务, 却**不在清单里** -> 一直被排最后
"""
import pytest

from module.config import task_catalog as TC
from module.config.scheduler import TaskScheduler
from tasks.Script.config_optimization import ScheduleRule


class FakeFunc:
    """最小化的 Function 替身。"""

    def __init__(self, command, next_run='2026-01-01 00:00:00', priority=5):
        self.command = command
        self.next_run = next_run
        self.priority = priority

    def __repr__(self):
        return self.command


class TestListPosMigration:
    def test_most_tasks_have_list_pos(self):
        """默认顺序应从硬编码清单迁到 meta.py。"""
        specs = TC.all_specs()
        have = [t for t, s in specs.items() if s.list_pos is not None]
        assert len(have) >= 50, f'只有 {len(have)} 个任务有 list_pos'

    def test_positions_are_unique(self):
        """位置不能重复 —— 否则顺序不确定。"""
        pos = [s.list_pos for s in TC.all_specs().values()
               if s.list_pos is not None]
        assert len(pos) == len(set(pos)), 'list_pos 有重复'

    def test_known_order_preserved(self):
        """迁移应保持原清单的相对顺序(抽几个已知位置核对)。"""
        def p(task):
            spec = TC.get_spec(task)
            return spec.list_pos if spec else None

        # 原清单: Restart > SoulsTidy > KekkaiUtilize > KekkaiActivation >
        #         DemonEncounter > AreaBoss > GoldYoukai ...
        assert p('SoulsTidy') < p('KekkaiUtilize') < p('KekkaiActivation')
        assert p('KekkaiActivation') < p('DemonEncounter')
        assert p('DemonEncounter') < p('AreaBoss') < p('GoldYoukai')
        # 原清单末尾: ... > KittyShop > DyeTrials > MemoryScrolls
        assert p('DyeTrials') < p('MemoryScrolls')

    def test_unlisted_tasks_have_no_pos(self):
        """不在原清单里的任务应留空(排最后), 而不是被随便塞个位置。"""
        for task in ('FindJade', 'GotoMain'):
            spec = TC.get_spec(task)
            if spec is not None:
                assert spec.list_pos is None, f'{task} 不该有 list_pos'


class TestListRule:
    def test_list_rule_exists(self):
        assert ScheduleRule.LIST.value == 'List'

    def test_orders_by_list_pos(self):
        """按 list_pos 排 —— SoulsTidy(1) 应在 FallenSun(25) 之前。"""
        pend = [FakeFunc('FallenSun'), FakeFunc('SoulsTidy'),
                FakeFunc('MemoryScrolls')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.LIST, list(pend), '')]
        assert got[0] == 'SoulsTidy'
        assert got.index('SoulsTidy') < got.index('FallenSun')
        assert got.index('FallenSun') < got.index('MemoryScrolls')

    def test_unordered_task_goes_last(self):
        pend = [FakeFunc('FindJade'), FakeFunc('SoulsTidy')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.LIST, list(pend), '')]
        assert got == ['SoulsTidy', 'FindJade'], '未编排的任务应排最后'

    def test_user_order_overrides_default(self):
        """用户编排优先于内置 list_pos。"""
        pend = [FakeFunc('SoulsTidy'), FakeFunc('FallenSun')]
        got = [f.command for f in TaskScheduler.schedule(
            ScheduleRule.LIST, list(pend), 'FallenSun,SoulsTidy')]
        assert got == ['FallenSun', 'SoulsTidy']

    def test_user_order_accepts_snake_case(self):
        """界面可能传下划线形式, 也要能匹配。"""
        pend = [FakeFunc('SoulsTidy'), FakeFunc('FallenSun')]
        got = [f.command for f in TaskScheduler.schedule(
            ScheduleRule.LIST, list(pend), 'fallen_sun,souls_tidy')]
        assert got == ['FallenSun', 'SoulsTidy']

    def test_restart_always_first(self):
        """与既有 fifo 的约定一致: Restart 永远最先。"""
        pend = [FakeFunc('FallenSun'), FakeFunc('Restart'),
                FakeFunc('SoulsTidy')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.LIST, list(pend), '')]
        assert got[0] == 'Restart'

    def test_whitespace_tolerated(self):
        pend = [FakeFunc('SoulsTidy'), FakeFunc('FallenSun')]
        got = [f.command for f in TaskScheduler.schedule(
            ScheduleRule.LIST, list(pend), ' FallenSun , SoulsTidy ')]
        assert got == ['FallenSun', 'SoulsTidy']

    def test_empty_order_falls_back_to_default(self):
        pend = [FakeFunc('FallenSun'), FakeFunc('SoulsTidy')]
        a = [f.command for f in
             TaskScheduler.schedule(ScheduleRule.LIST, list(pend), '')]
        b = [f.command for f in
             TaskScheduler.schedule(ScheduleRule.LIST, list(pend), None)]
        assert a == b

    def test_other_rules_still_work(self):
        """新增 LIST 不能破坏既有三种规则。"""
        pend = [FakeFunc('FallenSun', '2026-03-01'), FakeFunc('SoulsTidy', '2026-01-01')]
        got = [f.command for f in
               TaskScheduler.schedule(ScheduleRule.FIFO, list(pend))]
        assert got[0] == 'SoulsTidy', 'FIFO 应按 next_run 排'

        ok = TaskScheduler.schedule(ScheduleRule.FILTER, list(pend))
        assert isinstance(ok, list)
        ok = TaskScheduler.schedule(ScheduleRule.PRIORITY, list(pend))
        assert isinstance(ok, list)

    def test_invalid_rule_returns_pending(self):
        pend = [FakeFunc('SoulsTidy')]
        got = TaskScheduler.schedule('NotARule', list(pend))
        assert got == pend


class TestSchedulerTargetField:
    def test_target_defaults_zero(self):
        """0 = 用任务配置里的默认次数 —— 不改变既有行为。"""
        from tasks.Component.config_scheduler import Scheduler
        assert Scheduler().target == 0

    def test_target_range_falls_back_to_default(self):
        """
        越界值**回落到默认值**而不是抛异常 —— 这是 `ConfigBase.__init__` 的
        **既有设计**(它对 greater_than_equal 等范围错误记 warning 后用默认值)。
        因此界面传错值不会让配置整体加载失败。
        """
        from tasks.Component.config_scheduler import Scheduler
        assert Scheduler(target=-1).target == 0, '越界应回落到默认 0'
        assert Scheduler(target=1000).target == 0, '越界应回落到默认 0'
        # 边界内的正常值要保留
        assert Scheduler(target=0).target == 0
        assert Scheduler(target=999).target == 999


class TestRunListField:
    """
    `Script.optimization.run_list` —— 用户编排的**条目清单**(模型 B)。

    取代了早期的 `task_order`(逗号分隔任务名) —— 后者只能排任务,
    无法表达"打完御魂后全部停止 30 分钟"。
    """

    def test_defaults_empty(self):
        """默认空 -> 用内置 list_pos 顺序, 行为不变。"""
        from tasks.Script.config_optimization import Optimization
        assert Optimization().run_list == []

    def test_accepts_entry_list(self):
        from tasks.Script.config_optimization import Optimization
        o = Optimization(run_list=[
            {'kind': 'task', 'task': 'A'},
            {'kind': 'rest', 'minutes': 30},
            {'kind': 'delay', 'minutes': 60},
        ])
        assert len(o.run_list) == 3
        assert o.run_list[1]['kind'] == 'rest'

    def test_order_is_preserved(self):
        """
        顺序必须保留 —— 这是存成 **JSON 数组**而不是逗号字符串的理由:
        数组天然保留插入位置, 不需要额外的 `pos` 字段。
        """
        from tasks.Script.config_optimization import Optimization
        raw = [
            {'kind': 'task', 'task': 'A'},
            {'kind': 'rest', 'minutes': 10},
            {'kind': 'task', 'task': 'B'},
        ]
        o = Optimization(run_list=list(raw))
        assert [e['kind'] for e in o.run_list] == ['task', 'rest', 'task']

    def test_old_task_order_field_removed(self):
        """旧字段应已移除(不留双轨)。"""
        from tasks.Script.config_optimization import Optimization
        assert not hasattr(Optimization(), 'task_order')

    def test_list_mode_in_enum(self):
        from tasks.Script.config_optimization import Optimization
        o = Optimization(schedule_rule='List')
        assert o.schedule_rule == ScheduleRule.LIST
