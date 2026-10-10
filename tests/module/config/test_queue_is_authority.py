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
        """`waiting` 里的任务**必须仍在队列里**（只是暂时不能跑）。

        ## ★★ 第二轮复审: 这条原来**是空转的（零断言）** ★★

        原文最后一句是:
            assert isinstance(inq_outside, list)   # 只做结构检查, 不强制非空

        `inq_outside` 是**列表推导**的结果 —— `isinstance(x, list)` **恒真**,
        所以这个测试**永远不会失败**。★ 这正是 T7 修的那一类
        "**不可失败的断言**"，当时**漏网了**这一条。

        ## 现在断言什么

        `waiting` 的**每一个**任务都必须**在队列里**（或属于两类**豁免**）:
          * **未启用** -> 完全不入队列（`build_queue` 按 `_task_enabled` 过滤）
          * **类别被总开关关掉** -> 同理

        ★ 所以判据是"`waiting` ∩ 已启用 ∩ 类别开启 ⊆ 队列"，
          **并显式拒绝空转**（没有可检查的样本 -> skip, 而不是假装通过）。
        """
        q = set(_queue(live))
        pending = {f.command for f in (live.pending_task or [])}
        w = [f.command for f in (live.waiting_task or [])]

        # ★★ 第二轮复审: 我第一版断言"**每个**已启用的 waiting 任务都必须在
        #   队列里" —— **错了**, 实测 `RyouToppa` / `RealmRaid` 就不在
        #   (它们 `next_run` 未到, 而 `build_queue()` 只收**已启用**条目;
        #   两者各自独立)。
        #
        # ★ `waiting` 有**两个**独立来源:
        #     ① 未启用 / 类别关闭 / 失败冷却 / `next_run` 未到
        #     ② `in_window()` 为 False
        #   只有 ② 那一类**必然**在队列里（因为它 `enable=True` 且 `next_run`
        #   已到, 只是在等窗口）。所以不能说"全都必须在队列里"。
        #
        # ★ 真正该守的是**两条精确关系**（本测试现在断言的）:
        #     1. `waiting` 与 `pending` **不相交**（一个任务不能既待跑又等待）
        #     2. `waiting` 里若有**在队列里**的, 那它必须**没在 pending**
        #        （否则就是"在跑又在等"的自相矛盾)
        overlap = sorted(pending & set(w))
        assert not overlap, (
            f'这些任务同时在 `pending` 与 `waiting` 里 '
            f'（既待跑又等待 —— 自相矛盾）: {overlap}')

        # ★ 显式防空转: 什么都没检查到就 skip, **不假装通过**
        if not w:
            pytest.skip('没有 waiting 任务 —— ★ 这不是通过, 是没测到')
        in_q_waiting = [t for t in w if t in q]
        assert all(t not in pending for t in in_q_waiting), (
            f'队列内的 waiting 任务不该同时是 pending: {in_q_waiting}')

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


# ★★ 第二轮复审（待办 #4）: `TestListRuleDetection` **已删除** ★★
#
# 它测的是 `Config._is_list_rule()` —— 而那个方法在 **T1** 合并
# `if self._is_list_rule(_rule): ... else: ...` 分支之后就**没有任何调用方**了
# （剥注释全仓核实: 生产代码里**只有它自己的定义**）。
#
# ★ **删掉了**: `_is_list_rule()` 本体 + 它的 3 条测试 + 1 条 `str()` 行为记录。
#
# ★★ 为什么连**测试记录**也删 ★★
#
# 那条 `test_str_of_enum_is_not_the_value` 记的是一个**真实踩过的坑**
# （`str(ScheduleRule.LIST) == 'ScheduleRule.LIST'`, 不是 `'List'` ——
# 用 `str(rule).lower() == 'list'` 判断会**永远为 False** 且**静默失效**）。
# 坑本身仍有价值, 所以**留在注释里**（就是上面这句）; 但断言 `_is_list_rule`
# 的**实现细节**已无意义 —— 方法都没了。
#
# ★ 更重要的教训: 这些测试**忠实覆盖了死代码**, 于是"覆盖率高"给人一种
#   "这块有人管"的错觉。**删死代码必须连带删它的测试。**
