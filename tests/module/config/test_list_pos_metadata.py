# -*- coding: utf-8 -*-
"""★ `TaskSpec.list_pos` 的**元数据体检**（从 `test_task_list.py` 抢救）。

## 为什么单独保留这一份

原 `test_task_list.py` 有 21 个测试, 其中 **16 个**只测
`TaskScheduler.schedule()` —— 而那个类在第二轮复审里被确认
**生产 0 调用**（唯一 import 它的就是测试）, 已随
`module/config/scheduler.py` 一起**删除**。

★ 但下面这 5 条**测的是元数据**, 与调度器是否存活无关:
  * 40 个 `tasks/*/meta.py` 的 `list_pos` 是否**唯一**、是否**覆盖够多**
  * 已知的内置顺序是否被保留
  * `ScheduleRule.LIST` 是否还在枚举里（读旧配置要用）

★ `list_pos` 现在的地位（**已不是调度输入**）:
  * 它唯一的调度消费者是死掉的 `scheduler.py:99-100`（`list_order`）
  * 现在只剩两个用途: ① 40 个 `meta.py` 在维护它
    ② `schema_router` 用它算 `in_list`
       （`GET /{script}/queue/default_order` 的"是否在内置清单里"）
  * -> **保留**（对外契约的一部分）, 但**队列顺序才是权威**
"""
import pytest

from module.config import task_catalog as TC


def test_most_tasks_have_list_pos():
    """默认顺序应从硬编码清单迁到 meta.py。"""
    specs = TC.all_specs()
    have = [t for t, s in specs.items() if s.list_pos is not None]
    assert len(have) >= 50, f'只有 {len(have)} 个任务有 list_pos'


def test_positions_are_unique():
    """位置不能重复 —— 否则顺序不确定。"""
    pos = [s.list_pos for s in TC.all_specs().values()
           if s.list_pos is not None]
    assert len(pos) == len(set(pos)), 'list_pos 有重复'


def test_known_order_preserved():
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


def test_unlisted_tasks_have_no_pos():
    """不在原清单里的任务应留空(排最后), 而不是被随便塞个位置。"""
    for task in ('FindJade', 'GotoMain'):
        spec = TC.get_spec(task)
        if spec is not None:
            assert spec.list_pos is None, f'{task} 不该有 list_pos'


def test_list_mode_in_enum():
    """★ `ScheduleRule.LIST` 必须**还在枚举里** —— 读旧配置要用。

    ⚠ 抢救时漏了一个 import（原来在文件头的 `from ... import ScheduleRule`
    被我删掉了, 而这句还在用）—— 已补。
    """
    from tasks.Script.config_optimization import Optimization, ScheduleRule
    o = Optimization(schedule_rule='List')
    assert o.schedule_rule == ScheduleRule.LIST
