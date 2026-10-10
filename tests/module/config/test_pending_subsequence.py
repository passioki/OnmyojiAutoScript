# -*- coding: utf-8 -*-
"""★★★ S7: **`pending` 是 `queue` 的保序子序列**（不变量直测）★★★

## 为什么补这个文件（覆盖面回填）

`tests/module/config/test_priority_mode.py` 里原本有一条
`TestSegmentation::test_queue_invariant_survives` 直测这条不变量。
★ 那个文件整份**已删除**（它测的「调度优先级三模式」被用户裁定删除）,
  于是这条不变量**失去了直测** —— 只剩间接守卫。

★ 而它是**调度设计的核心不变量**（见 `docs/scheduler-architecture.md`
  §W4 / Z1）:

    `pending` 必须是 `queue` 的**保序子序列**

理由: `pending` 是从 `queue` **筛**出来的（只留已到点的）。
事后**重排** `pending` 就不再是子序列了 —— 那正是历史上
`_order_by_timed_priority()` 干过的错事（把队列第 9 位的任务排到 pending
第 1 位，用户拖的顺序被完全覆盖）。

★ 现在没有"模式"了, 所以**唯一**能改变执行顺序的就是
  `run_list` 本身 + 用户点「快捷排序」。这条不变量必须钉住。

## 三条断言

① `pending` ⊆ `queue`（集合层面）
② `pending` 在 `queue` 里的**相对次序不变**（子序列, 不只是子集）
③ `pending` 与 `waiting` **不相交**（既待跑又等待 = 自相矛盾）

★ 排除 `running_task` 置顶（设计例外, 见 §3）与手动插入。
"""
import logging
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)


@pytest.fixture(scope='module')
def live():
    """★ 用**真实配置**（`恋鸟树`）—— 这条不变量只在真实数据上才有意义。

    ⚠ `tests/conftest.py` 有**两层**配置守卫（会话级 + 每测试级快照还原）,
      所以这里的 `update_scheduler()` 不会污染用户配置。
    """
    os.chdir(REPO)
    import server  # noqa: F401
    from module.server.main_manager import mm
    return mm.config_cache('恋鸟树')


def _names(rows):
    return [getattr(x, 'command', None) for x in (rows or [])]


def _queue(cfg):
    return [getattr(e, 'task', None) for e in cfg.build_queue()]


class TestPendingIsOrderedSubsequence:
    def test_pending_is_subsequence_of_queue(self, live):
        """★ 核心不变量: `pending` 是 `queue` 的**保序子序列**。"""
        live.update_scheduler()
        q = _queue(live)
        p = _names(live.pending_task)
        w = set(_names(live.waiting_task))

        # ★ 防空转: `all()` 对空集恒真 —— 必须显式拒绝"什么都没测到"
        if not p:
            pytest.skip('当前没有待跑任务（pending 为空）—— '
                        '★ 这不是通过, 是没测到')

        # ★ 先排除 `running_task` 置顶（设计例外, 见 §3）
        #   `update_scheduler()` 末尾会把正在跑的任务提到 `pending` 最前。
        running = getattr(live, 'running_task', None)
        expected = [t for t in q if t not in w]
        if running:
            expected = [t for t in expected if t != running]
            p = [t for t in p if t != running]

        # ① 集合层面
        assert set(p) <= set(q), (
            f'★ `pending` 里出现了**不在 `queue`** 的任务: '
            f'{sorted(set(p) - set(q))}')

        # ② 保序（子序列, 不只是子集）
        it = iter(expected)
        assert all(any(x == t for x in it) for t in p), (
            f'★ `pending` **不是保序子序列** —— 顺序被某个东西重排了。\n'
            f'  queue(剔 waiting/running)={expected}\n'
            f'  pending={p}')

    def test_pending_and_waiting_are_disjoint(self, live):
        """③ 既待跑又等待 = 自相矛盾。"""
        live.update_scheduler()
        p = set(_names(live.pending_task))
        w = set(_names(live.waiting_task))
        overlap = p & w
        assert not overlap, (
            f'★ 这些任务同时在 `pending` 与 `waiting` 里: {sorted(overlap)}')

    def test_queue_order_is_run_list_order(self, live):
        """★ S7: 队列顺序 = **`run_list` 顺序**（没有"模式"能改它）。

        ★ 这是 S7 与旧设计的**本质区别**: 旧设计下 `priority_mode` 会在
          `build_queue()` 里再排一次段; 现在**不排** —— 队列就是用户编排。
        """
        live.update_scheduler()
        rl = [getattr(e, 'task', '') for e in live.build_run_list()]
        q = _queue(live)
        if not rl:
            pytest.skip('run_list 为空 —— 没测到')

        # 队列的前 N 个应**恰好**是 `run_list` 的顺序（N = run_list 里
        # **已启用**的条目数）; 自动补齐的接在后面。
        enabled = [t for t in rl if t and live._task_enabled(t)]
        if not enabled:
            pytest.skip('run_list 里没有已启用的任务 —— 没测到')
        assert q[:len(enabled)] == enabled, (
            f'★ 队列前缀 ≠ `run_list` 顺序 —— 说明还有东西在重排。\n'
            f'  run_list(已启用)={enabled}\n'
            f'  queue={q}')

    def test_nothing_reorders_pending_during_scheduling(self, live):
        """★★ 调度**不得**按任何"模式/优先级"重排 `pending`。

        ★ 历史事故: `_order_by_timed_priority()` 用 `timed_sort_key`
          把整个列表重排, 用户拖的顺序被完全覆盖（实测: 队列第 9 位的
          `ExperienceYoukai` 被排到 pending 第 1 位）。
        ★ 现在排序只能由**用户点按钮**触发（`sort_run_list`）,
          **不能在每次调度时重来**。
        """
        from _srcutil import code_of

        body = code_of(REPO / 'module' / 'config' / 'config.py',
                       'def update_scheduler')
        for banned in ('_order_by_priority_mode', '_order_by_timed_priority',
                       'timed_sort_key', 'sort_run_list('):
            assert banned not in body, (
                f'★ `update_scheduler()` 里出现了 `{banned}` —— '
                f'调度不该按任何模式/优先级重排（用户拖的顺序就是权威）')
