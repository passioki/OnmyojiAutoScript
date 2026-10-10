# -*- coding: utf-8 -*-
"""**允许重复添加同一任务**（用户 2026-10-10 裁定）。

## 用户原话

> "现在的任务执行里**添加任务应该设置为可以重复添加相同的任务**,
>  这样就**变相实现了多次跑任务**"

## 两个障碍（本测试钉住已修的两个）

1. **候选端点**原来排除 `queued` -> 任务加入后就从候选消失 -> 无法加第二次
2. **`list_order`** 原来用 `task_order()`（去重保首）-> 重复条目拿不到位置

## ★ 仍未解决（第三个障碍, 见台账 §21.3）

派发状态是**按任务**存的（`Scheduler.next_run` / `task_state`）,
所以同一任务的两条重复条目**无法各自追踪"这条跑过没有"**。
要真正"各跑一次"需按**条目**追踪 —— **待用户确认**。
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
    return mm.config_cache('恋鸟树')


def _fn(cfg, key):
    from module.config.config import Function
    return Function(key, cfg.model.model_dump()[key])


class TestCandidatesAllowDuplicates:
    """★ 障碍 1: 候选端点**不该**排除"已在队列"的任务。"""

    def test_source_does_not_filter_queued(self):
        """源码里候选规则**不该**再有 `if command in queued: continue`。

        ## ★ 第二轮复审修复: 必须**剥注释**（正反两个方向都会错）

        复审员指出这条与 `test_execution_queue.py` 的
        `test_candidates_endpoint_filters_correctly` **是同一守卫的第二份**,
        而**这份没剥注释**:
          * 反向断言 `'if command in queued' not in body` ->
            只要注释里**解释历史**就会**假失败**
          * 正向断言 `'_auto_queue_of(meta)' in body` ->
            只要注释里提一句就**假通过**

        ★ 改用 `_srcutil.code_of()`（剥注释 + 剥 docstring）。
        ★ 报告还建议"两份守卫合并成一份" —— 已在两边都注明彼此,
          保留两份是因为**跨端**（这一份测 `/queue/candidates`, 另一份
          测同一端点的**过滤器**）观察角度不同。
        """
        from _srcutil import code_of
        body = code_of(REPO / 'module' / 'server' / 'schema_router.py',
                       'async def get_queue_candidates')
        assert 'if command in queued' not in body, (
            '候选端点仍在排除"已在队列"的任务 —— '
            '用户要求可以重复添加相同的任务')
        assert '_auto_queue_of(' in body, \
            '仍应排除"自动进队列"的任务（它们靠 build_queue 补齐）'

    def test_queued_task_still_in_candidates(self, live):
        """★ 端到端: 已在队列的任务**仍应**出现在候选里（可以再加一次）。"""
        import asyncio
        from module.server.schema_router import get_queue_candidates

        queued = live.queued_commands()
        got = asyncio.new_event_loop().run_until_complete(
            get_queue_candidates('恋鸟树'))
        names = {c['command'] for c in got.get('candidates', [])}
        both = names & queued
        # 只要队列里有一个 `auto_queue=False` 的任务, 它就该出现在候选里
        from module.config import task_catalog as TC
        manual_queued = {t for t in queued
                         if (TC.get_spec(t) is not None
                             and not TC.get_spec(t).auto_queue_effective)}
        if not manual_queued:
            pytest.skip('队列里没有次数任务, 无法验证')
        assert manual_queued & names, (
            f'这些已在队列的次数任务没出现在候选里: {sorted(manual_queued)} —— '
            f'用户无法重复添加它们')


class TestDuplicateEntriesKeepPosition:
    """★ 障碍 2: 重复条目必须**各占一个队列位置**。

    ## ★★ 第二轮复审（待办 #4）: 删掉 3 条测已删代码的测试 ★★

    | 被删的测试 | 为什么 |
    |---|---|
    | `test_list_order_uses_entry_positions` | 调 `TaskScheduler.schedule()` —— 那个类**生产 0 调用**, 已随 `scheduler.py` 删除 |
    | `test_list_order_source_no_task_order` | 读 `module/config/scheduler.py` 的源码 —— **文件都没了** |

    ★ 而"重复条目各占一个位置"这个**真正的不变量**现在由
    `Config._order_by_queue()` 负责（它按 `entry_id` 逐条分配）——
    守卫在 `test_entry_scoped_state.py` 与 `test_entry_id.py`。
    ★ 下面两条**保留**: 它们只依赖 `RunList` 自己, 与调度器死活无关。
    """

    def test_duplicates_are_preserved_in_run_list(self):
        """`RunList` 本身必须**允许**重复条目（不去重）。

        ★ 这是"重复条目"能工作的**地基** —— 用户 ⑧ 明确要"可以重复添加
        同一个任务"。
        """
        from module.config.run_list import RunEntry, RunList
        rl = RunList([
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='RealmRaid'),
        ])
        assert len(rl.entries) == 2, 'RunList 把重复条目吃掉了'

    def test_task_order_still_dedups_for_legacy(self):
        """`task_order()`（旧字段）**仍然**去重 —— 那是它的既有契约, 不改。

        ⚠ 但**队列顺序不再用它来定位**（`_order_by_queue` 改按条目遍历）。
        ★ 保留这条是为了钉住"旧字段的语义**故意不变**"（读旧配置要用）。
        """
        from module.config.run_list import RunEntry, RunList
        rl = RunList([
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='RealmRaid'),
            RunEntry(kind='task', task='Delegation'),
        ])
        assert rl.task_order() == ['RealmRaid', 'Delegation']
