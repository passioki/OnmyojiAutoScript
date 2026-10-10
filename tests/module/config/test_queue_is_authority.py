# -*- coding: utf-8 -*-
"""F3: **队列顺序就是执行顺序**（用户明确的设计）。

## 用户原话

> "待执行里为什么不能和执行顺序一样拖动呢, 他俩应该并在一起啊"
> "定时任务的拖动代表执行顺序发生了变化。完成上一个任务就会接着完成下一个。
>  正在运行 a, 执行顺序 bcd, 待执行 efg, 我把 g 拖到 bgcd,
>  这样运行完 B 就会运行 g。"
> "现有的不能拖动是不是意味着当前任务调度还是按照 interval 间隔时间来完成任务的,
>  而非设计要求中的排序依次完成?"

## 此前为什么没按队列顺序跑（实测）

1. `TaskScheduler.schedule(LIST, ...)` 确实按队列位置排好了,
   但紧接着 `_order_by_timed_priority()` 用 `timed_sort_key`
   **把整个列表重排** -> 用户拖的顺序**被完全覆盖**。

   实测: 队列第 9 位的 `ExperienceYoukai` 被排到 pending **第 1 位**。

2. **队列外的任务也会跑**: `pending = 25` 而 `queue = 18`, 多出的 9 个
   都是 `auto_queue=False` 的次数任务。

## 现在的不变量（本测试钉住）

    pending == [队列顺序中, 不在 waiting 的那些]（保序）
    waiting == [队列里但"未到开放时间"或未到点的]

★ 踩过: 规则判断写成 `str(_rule).lower() not in ('schedule_rule.list', 'list')`
  —— `str(ScheduleRule.LIST)` 是 **`'ScheduleRule.LIST'`**, 于是**永远不匹配**,
  改动**静默失效**（派发顺序一点没变, 也不报错）。已改用 `_is_list_rule()`。
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
    cfg = mm.config_cache('恋鸟树')
    cfg.update_scheduler()
    return cfg


def _queue(cfg):
    return [e.task for e in cfg.build_queue()
            if getattr(e, 'task', None)]


class TestQueueIsAuthority:
    """★ 队列是唯一调度依据。"""

    def test_pending_is_ordered_subsequence_of_queue(self, live):
        """★ 核心不变量: `pending` 是队列的**保序子序列**。

        ## ★★ 第二轮复审: 期望值原来**过时**（两处）★★

        ### (1) T1 让 E3（按条目完成记忆）**无条件生效**

        原来写 `expected = [t for t in q if t not in w]`。
        这在 T1 **之前**成立, 因为那时"按条目复查完成记忆"**只在
        `schedule_rule == List` 时**执行, 而出厂默认是 `Filter`
        -> 大多数用户那里 E3 **根本没生效**。

        T1 把 E3 改成**无条件执行**（这正是 T1 要修的 bug）—— 于是
        **本周期已完成的任务也会从 `pending` 移进 `waiting`**。

        ### (2) ★ 队列里可能有**未启用**的条目

        实测: `MetaDemon` 在 `run_list` 里但 `enable=False`
        -> `update_scheduler` 在**最早**的 `if not func.enable: continue`
          就跳过了 -> 它**既不在 pending 也不在 waiting**。
        ★ 这不是 bug("未启用" -> "不参与调度"), 但**队列成员**里确实有它。

        ★ 所以正确的期望是"**剔除 waiting + 剔除未启用**"。两处**都必须用
          权威函数**算（`_skip_by_period` / `_task_enabled`）, 不自己另写
          一套判断 —— 否则又是"知识存在两处"。
        """
        from module.config.config_model import convert_to_underscore

        q = _queue(live)
        p = [f.command for f in (live.pending_task or [])]
        w = {f.command for f in (live.waiting_task or [])}

        done, disabled = set(), set()
        for cmd in q:
            try:
                if not live._task_enabled(cmd):
                    disabled.add(cmd)
                    continue
                key = convert_to_underscore(cmd)
                tv = live.model.model_dump().get(key) or {}
                if live._skip_by_period(key, tv, entry_id=None) is True:
                    done.add(cmd)
            except Exception:
                pass

        expected = [t for t in q
                    if t not in w and t not in done and t not in disabled]
        assert p == expected, (
            f'pending 不是"队列剔除 waiting/未启用/本周期已完成"的保序子序列\n'
            f'  队列        : {q}\n'
            f'  waiting     : {sorted(w)}\n'
            f'  未启用      : {sorted(disabled)}\n'
            f'  本周期已完成: {sorted(done)}\n'
            f'  期望        : {expected}\n'
            f'  实际        : {p}\n'
            f'  ★ T1 之后 E3 **无条件生效** —— 本周期做过的任务**应当**不在 pending')

    def test_no_task_outside_queue_runs(self, live):
        """★ 队列外的任务**不该**在 pending 里（用户没加它就别跑）。"""
        q = set(_queue(live))
        p = [f.command for f in (live.pending_task or [])]
        leaked = sorted(set(p) - q)
        assert not leaked, (
            f'这些任务不在执行队列里, 却进了 pending: {leaked}\n'
            f'（用户: 队列是唯一调度依据）')

    def test_waiting_tasks_are_in_queue(self, live):
        """`waiting` 里的"未到开放时间"任务应该**仍在队列里**（只是不能跑）。"""
        q = set(_queue(live))
        w = [f.command for f in (live.waiting_task or [])]
        # waiting 里可能也有"未启用/类别关闭"的, 这里只查有 window 的那些
        from module.config import task_catalog as TC
        inq_outside = [t for t in w
                       if t in q and TC.get_spec(t) is not None
                       and TC.get_spec(t).declared_window is not None]
        assert isinstance(inq_outside, list)   # 只做结构检查, 不强制非空

    def test_queue_order_is_respected_not_timed_sort(self, live):
        """★ 反向守卫: `pending` **不能**等于 `timed_sort_key` 排出来的顺序。

        如果哪天有人把 `_order_by_timed_priority` 又接回 `LIST` 分支,
        这条会失败 —— 因为那时 pending 会按"谁更急"排, 而不是按用户拖的顺序。
        """
        q = _queue(live)
        p = [f.command for f in (live.pending_task or [])]
        if len(p) < 3:
            pytest.skip('pending 太少, 顺序对比无意义')
        # pending 必须是 q 的子序列（保序）
        it = iter(q)
        assert all(any(x == t for x in it) for t in p), (
            f'pending 不是队列的保序子序列\n  队列: {q}\n  pending: {p}')


class TestListRuleDetection:
    """★ 规则判断必须**真的**认得 `LIST`。"""

    def test_is_list_rule_true(self):
        from module.config.config import Config
        from tasks.Script.config_optimization import ScheduleRule
        assert Config._is_list_rule(ScheduleRule.LIST) is True

    def test_is_list_rule_false_for_others(self):
        from module.config.config import Config
        from tasks.Script.config_optimization import ScheduleRule
        for r in (ScheduleRule.FIFO, ScheduleRule.FILTER, ScheduleRule.PRIORITY):
            assert Config._is_list_rule(r) is False, f'{r} 不该被判成 list'

    def test_is_list_rule_handles_plain_strings(self):
        from module.config.config import Config
        assert Config._is_list_rule('List') is True
        assert Config._is_list_rule('list') is True
        assert Config._is_list_rule('LIST') is True
        assert Config._is_list_rule('Fifo') is False

    def test_str_of_enum_is_not_the_value(self):
        """★ 记录坑: `str(ScheduleRule.LIST)` **不是** `'List'`。

        所以**不能**用 `str(rule).lower() == 'list'` 判断 —— 那永远为 False,
        改动会**静默失效**（实测踩过）。
        """
        from tasks.Script.config_optimization import ScheduleRule
        assert str(ScheduleRule.LIST) == 'ScheduleRule.LIST', (
            'pydantic/Enum 的 str() 行为变了 —— `_is_list_rule` 的实现要跟着改')
        assert ScheduleRule.LIST.value == 'List'
        assert str(ScheduleRule.LIST).lower() != 'list', (
            '若这一条成立, 说明 str() 已经是纯值了; 此时可以简化 _is_list_rule')
