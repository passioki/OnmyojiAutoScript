# -*- coding: utf-8 -*-
"""S1 + F3 修: 僵尸节点清理 + **队列外任务泄漏进 pending**。

## 本轮实测发现的两个真 bug

### bug A: 僵尸配置节点（用户要求清理）

`tasks/OrochiMoans/` 只有 `assets.py` + `config.py` —— **缺 `meta.py`**
（-> 没类别、没窗口）, **也缺 `script_task.py`**（-> 跑不了）。
它在 4 个配置里各留了一个 `orochi_moans` 的 `scheduler` 节点。

★ **我第一版把它做错了两遍**:
1. 判据只有"有 `config.py` 但缺 `meta.py`" -> 把 **`Script`** 与
   **`GlobalGame`** 也当僵尸**删掉了**。它们是
   `config_model.EXTRA_GLOBAL` 里的**必需配置节点**（继承 `BaseModel`,
   **本来就不该有 `meta.py`**）-> 删掉等于丢了脚本/全局设置。
   **已从 `config/template.json`（git 跟踪）恢复。**
2. 我把函数插到了 `@lru_cache(maxsize=1)` 与 `def _load_specs()` **之间**
   -> 装饰器被我的函数抢走 -> `reload_specs()` 报
   `AttributeError: 'function' object has no attribute 'cache_clear'`。
   （与台账 §26 记的 `@dataclass` 同类错误。）

### bug B: `schedule_rule=Filter` 时**队列外任务照样跑**

实测（`戀鳥樹`）: `pending` 里多出 **8 个**不在队列里的任务 ——
`Orochi` / `FallenSun` / `EternitySea` / `Exploration` /
`BondlingFairyland` / `GoryouRealm` / `Hyakkiyakou` / `Sougenbi`,
全是 `enable=True` 但**用户没加进队列**的 `auto_queue=False` 任务。

**根因**: `_order_by_timed_priority()` **只排序、不剔除**（它假定调用方
已经过滤过）。`List` 分支有 `_order_by_queue()` 剔除, `Filter`/`Priority`/
`FIFO` 分支**没有** -> 泄漏。这与"**队列是唯一调度依据**"直接冲突
（正是 `test_queue_is_authority.py` 钉的不变量）。

**修**: 非 LIST 分支也**先** `_order_by_queue()` 过滤。
另外**去掉**重复调用与 `_order_by_timed_priority()` —— 后者会**重排**,
让"pending 是队列的保序子序列"不成立（= 用户拖的顺序失效）。

**实测**:
```
修前: queue(19) pending(22) 泄漏 8 个
修后: queue(19) pending(14) 泄漏 无  保序子序列 True
```
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestQueueIsAuthorityForAllRules:
    """★★ bug B: **任何** `schedule_rule` 下队列都必须是唯一依据。"""

    @pytest.fixture()
    def live(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        cfg = mm.config_cache('恋鸟树')
        cfg.update_scheduler()
        return cfg

    def _state(self, cfg):
        """返回 `(queue, pending, waiting, 未启用, 本周期已完成)`。

        ★★ 第二轮复审: 后两项是**新增的** —— 原来只算 `waiting`, 于是
        期望值 `[t for t in q if t not in w]` 在 T1 之后**过时**:
          * T1 让 E3（按条目完成记忆）**无条件生效**
            -> 本周期做过的任务**也会**离开 pending
          * 队列里可能有**未启用**的条目（实测 `MetaDemon` `enable=False`）
            -> 它**既不在 pending 也不在 waiting**
        """
        from module.config.config_model import convert_to_underscore

        q = [e.task for e in cfg.build_queue() if getattr(e, 'task', None)]
        p = [f.command for f in (cfg.pending_task or [])]
        w = {f.command for f in (cfg.waiting_task or [])}
        disabled, done = set(), set()
        for cmd in q:
            try:
                if not cfg._task_enabled(cmd):
                    disabled.add(cmd)
                    continue
                key = convert_to_underscore(cmd)
                tv = cfg.model.model_dump().get(key) or {}
                if cfg._skip_by_period(key, tv, entry_id=None) is True:
                    done.add(cmd)
            except Exception:
                pass
        return q, p, w, disabled, done

    def test_no_leak_under_any_rule(self, live):
        """★ 当前规则（实测是 `Filter`）下也**不该**有队列外任务跑。"""
        q, p, _, _, _ = self._state(live)
        leak = sorted(set(p) - set(q))
        assert not leak, (
            f'这些任务不在队列里却进了 pending: {leak}\n'
            f'（`_order_by_timed_priority()` 只排序不剔除 -> 泄漏; '
            f'非 LIST 分支也必须先 `_order_by_queue()`）')

    def test_ordered_subsequence_under_any_rule(self, live):
        """★ `pending` 必须是"队列剔除 waiting/未启用/本周期已完成"的**保序子序列**。

        `_order_by_timed_priority()` 会**重排** -> 这条会失败（用户拖的顺序失效）。

        ★★ 第二轮复审: 期望值原来只剔除 `waiting` —— T1 让 E3 无条件生效后
        必须**同时**剔除"本周期已完成"与"未启用"的条目。
        """
        q, p, w, disabled, done = self._state(live)
        expected = [t for t in q
                    if t not in w and t not in disabled and t not in done]
        assert p == expected, (
            f'pending 不是队列的保序子序列\n'
            f'  队列        : {q}\n'
            f'  waiting     : {sorted(w)}\n'
            f'  未启用      : {sorted(disabled)}\n'
            f'  本周期已完成: {sorted(done)}\n'
            f'  期望        : {expected}\n'
            f'  实际        : {p}')

    def test_non_list_branch_orders_by_queue(self):
        """★ 源码守卫: 非 LIST 分支必须调用 `_order_by_queue()`。"""
        src = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')
        i = src.find('if self._is_list_rule(_rule):')
        j = src.find('_order_by_manual_run', i)
        seg = src[i:j]
        assert '_order_by_queue' in seg, \
            '非 LIST 分支缺 `_order_by_queue()` -> 队列外任务会泄漏'

    def test_timed_priority_not_used_to_reorder(self):
        """★★ S6: `_order_by_timed_priority()` **已被删除** ★★

        ## 为什么断言升级了

        原来断言"该函数**保留**但**不得**在调度路径里调用"。

        用户裁定（S6）: "**三个选项**: 定时任务优先、固定任务优先、自定义" ——
        它的语义已由 `priority_mode` + `_segment_queue()` 取代, 而它本身是
        **死代码**（实测: 只有定义、无调用）-> **已删除**。

        ★ 所以现在断言**更强**: 它**连定义都不该有**了。
          同时保留"调度路径不许重排 `pending`"这条核心约束（F3 回归守卫）:
          `pending` 必须是 `queue` 的**保序子序列**（设计文档 §W4/Z1）。
        """
        src = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')
        assert 'def _order_by_timed_priority' not in src, \
            '死代码 `_order_by_timed_priority()` 应已删除（S6 三模式取代）'

        i = src.find('def update_scheduler')
        j = src.find('\n    def ', i + 10)
        body = src[i:j]
        # 剥掉注释再查
        code = '\n'.join(l.split('#', 1)[0] for l in body.split('\n'))
        assert '_order_by_timed_priority(' not in code, (
            '调度路径里仍在用 `_order_by_timed_priority()` 重排 -> '
            '用户拖的顺序会被覆盖（F3 回归）')
        # ⚠ 我第一版还加了 `assert 'sorted(' not in code` —— **过严**:
        #   `update_scheduler()` 里**合法地**排 `waiting_task`
        #   （`sorted(waiting_task, key=attrgetter('next_run'))`）。
        #   真正要守的是"**别重排 `pending_task`**", 由下面这条表达。
        assert '_order_by_priority_mode(pending_task)' not in code, (
            '分段排序**不能**在调度路径里重排 `pending` —— '
            '会破坏"pending 是 queue 的保序子序列"不变量（§W4/Z1）。'
            '分段排序应在**队列层** `_segment_queue()` 做。')


class TestZombieCleanupSafe:
    """★ bug A: 僵尸清理**不能**碰必需配置节点。"""

    def test_extra_global_kept(self):
        from module.config.config_model import EXTRA_GLOBAL
        from module.config import task_catalog as TC
        z = TC.zombie_task_keys()
        for name in EXTRA_GLOBAL:
            assert name not in z, f'{name} 被误判为僵尸 -> 会丢配置'

    def test_specs_cache_decorator_intact(self):
        """★ `reload_specs()` 必须能用（装饰器曾被我的函数抢走）。"""
        from module.config import task_catalog as TC
        TC.reload_specs()          # 不该抛 AttributeError
        assert len(TC.all_specs()) > 0
