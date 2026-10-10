# -*- coding: utf-8 -*-
"""执行队列：`auto_queue` / 队列自动补齐 / 移除=停用 / 添加候选。

## 用户确认的模型（这是本文件的规格来源）

| # | 分类 | 判定 | 位置 |
|---|---|---|---|
| 0 | 正在运行 | WebSocket `runningTask` | 队列第 0 行, 不可拖 |
| 1/2 | 待运行 | `queued == True` | 队列主体, 可拖 |
| 3 | **启用但不会运行** | `enable && !queued` | **只在【添加任务】里** |
| 4 | 未启用 | `!enable` | 只在任务列表里 |

进入队列的两条路径:
* **自动**: `auto_queue == True`（定时类）—— 启用后自动进队列
* **手动**: 次数任务经【添加任务】加入

移除队列 = **同时停用**（否则自动任务会被重新补回来）。
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from module.config import task_catalog as TC          # noqa: E402
from module.config.config_model import convert_to_underscore  # noqa: E402


# ---------------------------------------------------------------- 元数据
class TestAutoQueueMetadata:
    """`auto_queue` 是任务类别属性, 落在各 `meta.py` 里。"""

    def test_every_spec_declares_auto_queue_explicitly(self):
        """★ 54 个任务**都必须显式声明** —— 不许靠推导。

        为什么要显式: 推导规则在 `TaskSpec` 里只能看 `category`, 而
        `countable = category in COUNTABLE_CATEGORIES and bool(count_field)`
        —— 某个 FIXED 任务若没有 `count_field`, 推导会判错。
        显式落值就不会有这种偏差。
        """
        specs = TC._load_specs()
        assert len(specs) == 54, f'期望 54 个任务, 实际 {len(specs)}'
        missing = sorted(t for t, s in specs.items() if s.auto_queue is None)
        assert not missing, f'这些 meta.py 没写 auto_queue（靠推导, 不可靠）: {missing}'

    def test_auto_queue_matches_countable(self):
        """★ 与 `countable` 必须**零矛盾**（用户确认的判定依据）。"""
        idx, _ = TC._load()
        if isinstance(idx, list):
            idx = {m.task: m for m in idx}
        specs = TC._load_specs()

        bad = []
        for task, spec in specs.items():
            meta = idx.get(task)
            if meta is None:
                continue
            if spec.auto_queue_effective == bool(meta.countable):
                bad.append((task, spec.auto_queue_effective, meta.countable))
        assert not bad, (
            f'{len(bad)} 个任务的 auto_queue 与 countable 矛盾: {bad}')

    def test_counts_are_14_and_40(self):
        """实测分布: 14 个次数任务（False）+ 40 个定时类（True）。"""
        specs = TC._load_specs()
        manual = [t for t, s in specs.items() if not s.auto_queue_effective]
        auto = [t for t, s in specs.items() if s.auto_queue_effective]
        assert len(manual) == 14, f'次数任务应为 14 个, 实际 {len(manual)}: {sorted(manual)}'
        assert len(auto) == 40, f'定时类应为 40 个, 实际 {len(auto)}'

    def test_the_fourteen_count_tasks(self):
        """钉住这 14 个（用户逐个核对过）。"""
        specs = TC._load_specs()
        manual = {t for t, s in specs.items() if not s.auto_queue_effective}
        expected = {
            'BondlingFairyland', 'EternitySea', 'EvoZone', 'Exploration',
            'FallenSun', 'GoryouRealm', 'HeroTest', 'Hyakkiyakou', 'Orochi',
            'OtherWorldTwilight', 'RealmRaid', 'RyouToppa', 'SixRealms',
            'Sougenbi',
        }
        assert manual == expected, (
            f'差异: 多了 {sorted(manual - expected)}, 少了 {sorted(expected - manual)}')

    def test_exploration_is_manual(self):
        """探索 = 次数任务（用户明确问过）。"""
        spec = TC.get_spec('Exploration')
        assert spec is not None
        assert spec.auto_queue_effective is False, '探索应是次数任务（不自动进队列）'

    def test_timed_tasks_are_auto(self):
        for task in ('DemonEncounter', 'AreaBoss', 'Delegation',
                     'ExperienceYoukai', 'GoldYoukai', 'WantedQuests'):
            spec = TC.get_spec(task)
            assert spec is not None, f'{task} 没有 meta.py'
            assert spec.auto_queue_effective is True, f'{task} 应自动进队列'


# ---------------------------------------------------------------- 队列构建
class TestBuildQueue:
    """`build_queue()` = 用户编排 + 自动补齐; **不回写**。"""

    @pytest.fixture()
    def config(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_user_entries_come_first_in_order(self, config):
        """★ 用户编排的必须**优先**且**保持顺序**（用户确认"疑点1 = a"）。"""
        user = [getattr(e, 'task', None) for e in config.build_run_list()]
        queue = [getattr(e, 'task', None) for e in config.build_queue()]
        assert queue[:len(user)] == user, (
            f'用户编排的顺序被打乱了: 用户 {user}, 队列前 {len(user)} 项 {queue[:len(user)]}')

    def test_auto_tasks_are_appended(self, config):
        """自动任务**追加在后面**（不插队）。"""
        user = {getattr(e, 'task', None) for e in config.build_run_list()}
        queue = [getattr(e, 'task', None) for e in config.build_queue()]
        appended = [t for t in queue if t not in user]
        assert appended, '一个自动任务都没补齐 —— build_queue 没生效'
        # 追加的都在最后（即第一个追加项之后不应再出现用户项）
        if appended:
            first = queue.index(appended[0])
            assert all(t in appended for t in queue[first:]), \
                '自动补齐的任务中间夹了用户编排项'

    def test_queue_membership_includes_auto(self, config):
        """`queued_commands()` = 用户编排 + **已启用**的自动任务。

        ★★ ② 修（2026-10-10）: 自动任务必须**按 `enable` 过滤** ★★

        用户反馈: "执行队列-执行顺序页面, 这里出现了很多**未启用**的任务"。

        **实测根因**: 旧实现 `out.update(self.auto_queue_tasks())` **没有**
        `enable` 判断, 于是 41 个"队列成员"里混进 23 个未启用的; 而权威的
        `build_queue()`（它**有** `_task_enabled` 过滤）只有 19 条。

        **同一个知识（"队列成员"）在两处定义, 其中一处漏了 `enable`**
        —— 台账 §10.8"单一数据源"要防的那类 bug。

        所以断言改成:
        * **已启用**的自动任务 -> 在队列里
        * **未启用**的自动任务 -> **不在**队列里
        """
        queued = config.queued_commands()
        enabled_auto = [t for t in config.auto_queue_tasks()
                        if config._task_enabled(t)]
        for task in enabled_auto:
            assert task in queued, f'已启用的自动任务 {task} 应在队列成员里'

        # ★ 未启用的自动任务**不该**出现（这就是 ② 的修复点）
        disabled_auto = [t for t in config.auto_queue_tasks()
                         if not config._task_enabled(t)]
        bad = [t for t in disabled_auto if t in queued]
        assert not bad, (
            f'② 回归: 未启用的自动任务出现在了队列成员里: {bad[:8]}')


    def test_count_tasks_only_when_ordered(self, config):
        """次数任务只有被编排了才算在队列里。"""
        idx, _ = TC._load()
        if isinstance(idx, list):
            idx = {m.task: m for m in idx}
        queued = config.queued_commands()
        user = {getattr(e, 'task', None) for e in config.build_run_list()}

        for task, meta in idx.items():
            spec = TC.get_spec(task)
            if spec is None or spec.auto_queue_effective:
                continue           # 只看次数任务
            if task in user:
                assert task in queued
            # 不在 run_list 的次数任务 —— 不该出现（除非它还没被启用时的编排）
            # 注意: RealmRaid/RyouToppa 在别的账号可能被编排, 这里只保证"没编排就不在"
            if task not in user:
                assert task not in queued, (
                    f'次数任务 {task} 没被编排, 却在队列里')

    def test_build_run_list_not_mutated_by_build_queue(self, config):
        """★ `build_queue()` 不能改到用户编排的列表（派生结果不回写）。"""
        before = config.build_run_list().to_list()
        config.build_queue()
        after = config.build_run_list().to_list()
        assert before == after, 'build_queue 副作用改到了 run_list'


# ---------------------------------------------------------------- 端点
class TestQueueEndpoints:
    """`/queue/remove`（移除=停用）与 `/queue/candidates`（添加候选）。"""

    def test_remove_endpoint_disables_task(self):
        """★ 回归守卫: 移除必须**同时停用**。

        否则自动进队列的任务会被 `build_queue()` 重新补回来,
        "移除"变成无效操作。
        """
        src = (REPO / 'module' / 'server' / 'schema_router.py').read_text(
            encoding='utf-8')
        i = src.find('async def post_queue_remove')
        assert i > 0, '缺少 /queue/remove 端点'
        j = src.find('async def', i + 10)
        body = src[i:j]
        assert 'sch.enable = False' in body, \
            '移除队列时没有停用任务 —— 自动任务会被重新补回来'
        assert 'save_run_list' in body, '移除时没从 run_list 删掉条目'

    def test_candidates_endpoint_filters_correctly(self):
        """候选 = `enable && !auto_queue && !queued`。"""
        src = (REPO / 'module' / 'server' / 'schema_router.py').read_text(
            encoding='utf-8')
        i = src.find('async def get_queue_candidates')
        assert i > 0, '缺少 /queue/candidates 端点'
        j = src.find('async def', i + 10)
        body = src[i:j]
        assert "sch.get('enable')" in body, '候选没过滤"未启用"'
        assert '_auto_queue_of' in body, '候选没排除"自动进队列"的任务'
        assert 'queued' in body, '候选没排除"已在队列"的任务'

    def test_candidates_live(self):
        """实测候选列表 —— 用**相对断言**, 不钉具体任务名。

        ## 为什么改成相对断言

        原版硬编码了"这三个必须启用 / 这三个必须未启用":

            assert {'RealmRaid', 'RyouToppa', 'Hyakkiyakou'} <= names
            for off in ('Orochi', 'FallenSun', 'Exploration'):
                assert off not in names

        这些断言会随**用户配置变化**而失效（`Orochi`/`FallenSun`/`Exploration`
        后来被启用了 -> 测试假失败）。真正要钉的是**规则**:

            候选 == 全部任务里「enable && !auto_queue && !queued」的那些

        所以这里自己按同一个规则算一遍, 再与后端端点比对。
        """
        import asyncio
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        from module.server.schema_router import (
            _auto_queue_of, _meta_of_key, get_queue_candidates)

        got = asyncio.new_event_loop().run_until_complete(
            get_queue_candidates('恋鸟树'))
        assert 'error' not in got, got.get('error')
        cands = got['candidates']
        names = {c['command'] for c in cands}

        # 按规则自己算一遍。★ 必须用 `model_dump()` + `_meta_of_key()`,
        #   因为配置节点的键是**压缩小写**（`goryou_realm`）而 catalog 的键是
        #   驼峰（`GoryouRealm`）—— `_meta_of_key()` 就是做这个归一化的
        #   （`TC.get()` 容忍下划线/小写）。用 `TC.get_spec(key)` 直接查
        #   会**全部 miss** -> 算出空集（踩过）。
        #
        # ★★ 2026-10-10: 规则**改了** —— 不再排除 `queued` ★★
        #
        #   用户要求"**可以重复添加相同的任务**"（变相实现多次跑）,
        #   所以候选 = `enable && !auto_queue`（**不看 `queued`**）。
        #   原来这里排除 `queued` 的算法已失效 -> 本测试假失败。
        cfg = mm.config_cache('恋鸟树')
        expected = set()
        for key, value in cfg.model.model_dump().items():
            if not isinstance(value, dict):
                continue
            sch = value.get('scheduler')
            if not isinstance(sch, dict) or not sch.get('enable'):
                continue
            meta = _meta_of_key(key)
            if meta is None:
                continue
            if _auto_queue_of(meta):
                continue
            expected.add(meta.task)

        assert names == expected, (
            f'候选与规则不符\n  端点多出: {sorted(names - expected)}\n'
            f'  端点缺少: {sorted(expected - names)}')

        # 规则的不变量, 逐条钉住
        model = cfg.model.model_dump()
        for c in cands:
            meta = _meta_of_key(c['name'])
            assert meta is not None, f"候选 {c['name']} 无法归一到 catalog"
            assert not _auto_queue_of(meta), \
                f"候选 {c['command']} 是自动进队列的任务"
            assert model[c['name']]['scheduler']['enable'], \
                f"候选 {c['command']} 未启用"
        # ★ 「已在队列」**不再**是排除条件
        queued = cfg.queued_commands()
        assert names & queued or not queued, (
            '候选里一个"已在队列"的任务都没有 —— '
            '用户要求可以重复添加相同的任务')

        # 自动进队列的**永远**不该出现
        for key, value in model.items():
            if not isinstance(value, dict):
                continue
            meta = _meta_of_key(key)
            if meta is not None and _auto_queue_of(meta) \
                    and value.get('scheduler', {}).get('enable'):
                assert meta.task not in names, \
                    f'自动进队列的 {meta.task} 不该在候选里'


# ---------------------------------------------------------------- 接线
class TestWiring:
    """队列必须**真的**接进调度, 否则自动补齐只是摆设。"""

    def test_scheduler_uses_build_queue(self):
        """★ `update_scheduler` 必须用 `build_queue()`, 不是 `build_run_list()`。"""
        src = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')
        i = src.find('def update_scheduler')
        assert i > 0
        j = src.find('\n    def ', i + 10)
        body = src[i:j]
        assert 'self.build_queue()' in body, (
            'update_scheduler 还在用 build_run_list —— 自动补齐不会生效, '
            'auto_queue 任务启用后仍不会进队列')

    def test_overview_exposes_queue_fields(self):
        """`/overview` 必须给前端 `queued` 与 `auto_queue`。"""
        src = (REPO / 'module' / 'server' / 'schema_router.py').read_text(
            encoding='utf-8')
        assert "'auto_queue': _auto_queue_of(meta)" in src
        assert "'queued': command in queued_commands" in src
        assert 'queued_commands = config.queued_commands()' in src, \
            'overview 没有预先算队列成员（逐个判断会重复解析 N 次）'

    def test_overview_live_classification(self):
        """实测: 启用任务应分成"在队列"与"启用但不在队列（次数任务）"。"""
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.schema_router import build_overview

        rows = build_overview('恋鸟树')['tasks']
        en = [r for r in rows if r.get('enable')]
        queued = [r for r in en if r.get('queued')]
        not_queued = [r for r in en if not r.get('queued')]

        assert queued, '没有任务在队列里 —— 自动补齐没生效?'
        # 启用但不在队列的, **必须**都是次数任务（auto_queue=False）
        for r in not_queued:
            assert r['auto_queue'] is False, (
                f"{r['command']} 是自动进队列的却没进队列 —— 分类或补齐有问题")
        # 自动进队列且已启用的, **必须**都在队列里
        for r in en:
            if r['auto_queue']:
                assert r['queued'], (
                    f"{r['command']} auto_queue=True 且已启用, 却不在队列里")

    def test_auto_queue_helper_falls_back_to_countable(self):
        """`_auto_queue_of` 在任务没写 meta.py 时要退回 `countable`。"""
        src = (REPO / 'module' / 'server' / 'schema_router.py').read_text(
            encoding='utf-8')
        i = src.find('def _auto_queue_of')
        assert i > 0
        j = src.find('\ndef ', i + 10)
        body = src[i:j]
        assert 'countable' in body, '缺少 countable 兜底（没 meta.py 的任务会判错）'
