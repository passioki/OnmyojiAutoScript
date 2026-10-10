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
        assert len(specs) == 55, f'期望 55 个任务, 实际 {len(specs)}'
        missing = sorted(t for t, s in specs.items() if s.auto_queue is None)
        assert not missing, f'这些 meta.py 没写 auto_queue（靠推导, 不可靠）: {missing}'

    def test_auto_queue_matches_countable(self):
        """★ 与 `countable` 必须**零矛盾**（用户确认的判定依据）。"""
        idx, _ = TC._load()
        if isinstance(idx, list):
            idx = {m.task: m for m in idx}
        specs = TC._load_specs()

        # ★★★ `Rest` 是**有意的例外**（用户裁定 乙）★★★
        #
        # 用户原话:
        # > "休息就是临时任务（回庭院待着），只不过可以选择被定时任务插队。"
        #
        # 而在我给出"甲/乙"两个选项后, 用户选 **乙** =
        # ★ 休息**不自动进队列**, 由用户**主动添加**（与改动前的体验一致）。
        #
        # 所以 `Rest` 破了"`auto_queue == NOT countable`"这条不变量:
        #     `Rest`: auto_queue=False（不自动进队列）
        #             countable=False（它不是"打满 N 次"的任务）
        #
        # ★ 这条不变量本来的含义是"**次数任务不自动进队列, 定时任务自动进**"
        #   —— 它描述的是**例行任务**。而休息是**控制类**条目（用户手动安排
        #   "跑到这一行歇一会儿"），不属于这两类。
        # ⚠ 所以这里**显式排除** Rest, 并写明原因 —— 不是放水:
        #   除了它之外**任何一个**任务违反不变量仍然会失败。
        _EXEMPT = {'Rest'}

        bad = []
        for task, spec in specs.items():
            if task in _EXEMPT:
                continue
            meta = idx.get(task)
            if meta is None:
                continue
            if spec.auto_queue_effective == bool(meta.countable):
                bad.append((task, spec.auto_queue_effective, meta.countable))
        assert not bad, (
            f'{len(bad)} 个任务的 auto_queue 与 countable 矛盾: {bad}'
            f'（★ 唯一允许的例外是 {sorted(_EXEMPT)}，理由是用户裁定 乙）')

    def test_counts_are_15_and_40(self):
        """实测分布: **15** 个不自动进队列（False）+ **40** 个自动（True）。

        ★ 原来是 14 + 40 —— 新增 `Rest`（休息）后变成 **15 + 40**。
        ★ `Rest` 在 **manual 边**（`auto_queue=False`）:
          用户裁定 **乙** = 休息**由用户主动添加**, 不自动进队列。
        ★ 注意它**不是次数任务**（`countable=False`）—— 见
          `test_auto_queue_matches_countable` 里对这条例外的说明。
        """
        specs = TC._load_specs()
        manual = [t for t, s in specs.items() if not s.auto_queue_effective]
        auto = [t for t, s in specs.items() if s.auto_queue_effective]
        assert len(manual) == 15, f'应为 15 个, 实际 {len(manual)}: {sorted(manual)}'
        assert len(auto) == 40, f'应为 40 个, 实际 {len(auto)}' 

    def test_the_fifteen_manual_tasks(self):
        """钉住这 15 个（14 个次数任务 + ★ 新增的 `Rest`）。"""
        specs = TC._load_specs()
        manual = {t for t, s in specs.items() if not s.auto_queue_effective}
        expected = {
            'BondlingFairyland', 'EternitySea', 'EvoZone', 'Exploration',
            'FallenSun', 'GoryouRealm', 'HeroTest', 'Hyakkiyakou', 'Orochi',
            'OtherWorldTwilight', 'RealmRaid', 'RyouToppa', 'SixRealms',
            'Sougenbi',
            # ★ 休息: 用户裁定 乙 -> 主动添加, 不自动进队列
            #   （它不是次数任务, 见 test_auto_queue_matches_countable）
            'Rest',
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
        """★★ 用户编排**整段**在队列最前, 且**顺序原样** ★★

        ## 这条断言**反转过三次**, 现在是最终形态

        | 时期 | 队列顺序由谁决定 |
        |---|---|
        | 最初 | 假设"队列前缀 == 用户编排"（**错了**）|
        | S6 | "段序 = **模式**决定, 段内 = 用户决定" |
        | **现在** | **执行顺序 = `run_list` 的顺序本身** —— 没有任何模式 |

        用户裁定把「调度优先级三模式」整簇删掉:

        > "我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
        >  定时任务优先**直接作为一个快捷排序**就好。"

        ★ 所以现在**可以**断言最强的那条: 用户编排（已启用的）就是队列的
          **前缀**, 且**顺序一字不动**; 自动补齐的追加在**后面**
          （见 `build_queue()` 的 docstring: "用户手动排的必须优先"）。
        """
        user = [getattr(e, 'task', None) for e in config.build_run_list()]
        user_on = [t for t in user if t and config._task_enabled(t)]
        queue = [getattr(e, 'task', None) for e in config.build_queue()]

        # ① 全在队列里（未启用的会被剔除 -> 只看已启用的）
        missing = [t for t in user_on if t not in queue]
        assert not missing, (
            f'用户编排（已启用）的条目不在执行队列里: {missing}\n'
            f'  用户(启用) = {user_on}\n  队列 = {queue}')

        # ② ★ 用户编排就是队列**前缀**, 且顺序原样（拖动永远自由）
        assert queue[:len(user_on)] == user_on, (
            f'用户编排没有成为队列前缀（被按段重排了?）:\n'
            f'  用户 = {user_on}\n  队列前 {len(user_on)} 项 = '
            f'{queue[:len(user_on)]}\n'
            f'  ★ 现行设计: 执行顺序 = `run_list` 的顺序本身')

        # ③ 段名仍然是**派生显示值**（不影响顺序）—— 保留这条以防
        #    "段名判据" 被误用成排序判据
        for seg in {config._segment_of(t) for t in user_on}:
            seg_user = [t for t in user_on if config._segment_of(t) == seg]
            seg_queue = [t for t in queue
                         if t and config._segment_of(t) == seg]
            order_in_q = [t for t in seg_queue if t in set(seg_user)]
            assert order_in_q == seg_user, (
                f'[{seg} 段] 用户编排的段内顺序被打乱:\n'
                f'  用户 = {seg_user}\n  队内出现次序 = {order_in_q}\n'
                f'  （★ 现行设计: 执行顺序 = `run_list` 的顺序本身, '
                f'没有任何"模式"能重排它）')

    def test_auto_tasks_are_appended(self, config):
        """★ 自动补齐的条目**必须都已启用**, 且**不与用户条目重复**。

        ⚠ 不说"追加在队列末尾" —— 分段会重排（见上一条说明）。
        """
        user = {t for t in (getattr(e, 'task', None)
                            for e in config.build_run_list())
                if t and config._task_enabled(t)}
        queue = [getattr(e, 'task', None) for e in config.build_queue()]
        appended = [t for t in queue if t not in user]

        # ★★ 实机验收修复: 去掉"**必须有**自动补齐"这个断言 ★★
        #
        # 原文: `assert appended, '一个自动任务都没补齐 —— build_queue 没生效'`
        #
        # ★ 现在**可以合法地为空** —— 因为前端 `reorderQueue` 修好之后,
        #   **用户拖动过的自动任务会被写进 `run_list`**（那正是修复的目标:
        #   原来拖了必弹回）。于是"待补齐"的任务可能**一个都不剩**。
        #   实测本机就是这种情况: `appended == []`。
        # ★ 那**不是** `build_queue()` 没生效, 而是**没有东西需要补**。
        #
        # ★ 所以改成: ① 队列**非空** ② 若**有**待补齐的, 它们必须全部已启用
        #   且不与用户条目重复。
        assert queue, 'build_queue 返回了空队列'
        if not appended:
            pytest.skip(
                '当前**没有**待自动补齐的任务（用户已把自动任务都编排进 '
                '`run_list` 了）—— ★ 这不是失败, 是"无需补齐"')

        # ★ 自动补齐的必须**全部已启用**（未启用的不该进队列）
        disabled_in_queue = [t for t in appended if not config._task_enabled(t)]
        assert not disabled_in_queue, (
            f'队列里有**未启用**的自动任务: {disabled_in_queue}')

        # ★ 用户条目不该被"补齐"成重复
        #
        # ⚠⚠ 我第一版写成 `queue.count(t) == 1` —— **必然假失败**:
        #   用户**可以**在 `run_list` 里放**重复条目**（⑧ 明确确认的用法:
        #   "可以重复添加同一个任务"）。实测 `queue` 里 `RealmRaid` 出现
        #   **2 次** —— 两行**都是用户编排的**, 与自动补齐无关。
        #
        # ★ 正确判据: **`RunEntry` 身份**（`entry_id`）去重后再比, 而不是
        #   按任务名。自动补齐只该补"用户**完全没编排过**"的任务。
        from collections import Counter
        user_ids = {getattr(e, 'entry_id', None)
                    for e in config.build_run_list()
                    if getattr(e, 'task', None)}
        q_entries = config.build_queue()
        auto_like = [getattr(e, 'task', None) for e in q_entries
                     if getattr(e, 'entry_id', None) not in user_ids]
        # 自动补齐的每个任务名, 在**用户条目之外**最多出现一次
        for name, n in Counter(auto_like).items():
            if name in user:
                assert n == 0, (
                    f'{name} 既在用户编排里, 又被自动补齐了 {n} 次 —— '
                    f'自动补齐失去了去重')

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
            # ★★★ `Rest` 是**有意的例外**（用户裁定 乙）★★★
            #
            # `Rest`: `auto_queue=False`（用户主动添加）但 **不是次数任务**。
            # ★ 所以它可能"在 `run_list` 里、却因 `enable=False` 不在队列里"
            #   —— 这是**正确行为**（用户停用了休息 -> 就不该休息）。
            # ⚠ 本条测试的前提是"次数任务被编排 -> 一定在队列里"，
            #   对 `Rest` **不成立**。★ 除它之外任何任务仍按原规则检查。
            if task == 'Rest':
                continue
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
        """候选 = `enable && !auto_queue`（★ **不**排除已在队列的, 见 ⑧）。

        ## ★★ T7: 原来这条有**不可失败的断言 + 反向语义** ★★

        原来的最后一句是 `assert 'queued' in body` ——
        而实现里有一行 `queued = config.queued_commands()`, **于是这个子串
        必然存在**, **无论是否真的用它过滤** -> **永真, 不可失败**。

        ★ 更糟: 它的**语义已经反了**。S6 之后候选**故意不再排除 `queued`**
          （⑧ 用户要求"可以重复添加同一个任务"）, 所以"候选没排除已在队列的
          任务"从**缺陷**变成了**需求**。

        ★ 修法: 剥注释后断言**真实规则**（`enable` + `!auto_queue`）;
          "不排除 queued"用**反向断言**表达（这才是 ⑧ 的守卫）。

        真正的端到端验证在下面的 `test_candidates_live`（相对断言）。
        """
        src = (REPO / 'module' / 'server' / 'schema_router.py').read_text(
            encoding='utf-8')
        i = src.find('async def get_queue_candidates')
        assert i > 0, '缺少 /queue/candidates 端点'
        j = src.find('async def', i + 10)
        # ★ 剥注释 —— 否则会匹配到注释里的说明文字（本项目反复踩过）
        body = '\n'.join(l.split('#', 1)[0] for l in src[i:j].split('\n'))

        assert "sch.get('enable')" in body, '候选没过滤"未启用"'
        assert '_auto_queue_of' in body, '候选没排除"自动进队列"的任务'
        # ★ ⑧ 的反向守卫: 候选**不得**用 `queued` 做排除
        assert 'if command in queued' not in body, (
            '候选又排除了"已在队列"的任务 —— 用户 ⑧ 要求可以重复添加同一任务')

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
            if _auto_queue_of(meta, cfg):
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
            assert not _auto_queue_of(meta, cfg), \
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
        """★★ `update_scheduler` 必须走 `_order_by_queue()` -> `build_queue()` ★★

        ## T1 后的更新

        原来断言"`update_scheduler` 里有 `self.build_queue()`" —— 那是
        `TaskScheduler.schedule(run_list=self.build_queue())` 那一行留下的。

        T1 删掉了 `TaskScheduler.schedule()` 调用（它带来两个真 bug:
        FILTER 白名单吞队列内任务 / 两个排序权威互相牵制）。现在
        `update_scheduler` 的顺序权威是 **`_order_by_queue()`**, 而
        **`_order_by_queue()` 内部用 `build_queue()`**（用户编排 + 自动补齐）。

        ★ 所以这条守卫改成**跟随调用链**——否则会把"正确的 T1 改动"判成回归。
        """
        src = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')

        def code_of(name):
            """取方法体并**剥掉注释** —— ⚠ 否则会匹配到注释里的反面说明。

            我自己就踩了: T1 的注释里写着"**不再调 `TaskScheduler.schedule()`**"
            -> 断言 `not in body` **匹配到自己的注释** -> 假失败。
            （本项目多次踩"守卫匹配到自己的说明文字" —— 见 `codeOnly` 的注释。）
            """
            i = src.find(f'def {name}')
            assert i > 0, f'找不到 {name}'
            j = src.find('\n    def ', i + 10)
            body = src[i:j if j > i else len(src)]
            return '\n'.join(l.split('#', 1)[0] for l in body.split('\n'))

        us = code_of('update_scheduler')
        assert '_order_by_queue(' in us, (
            'update_scheduler 未走 `_order_by_queue()` —— 队列不是顺序权威')
        assert 'TaskScheduler.schedule(' not in us, (
            'T1 后不应再调 `TaskScheduler.schedule()` —— '
            '它会让 FILTER 白名单吞掉队列内任务, 且与队列排序权威互相牵制')

        obq = code_of('_order_by_queue')
        assert 'build_queue()' in obq, (
            '_order_by_queue 未用 `build_queue()` —— 自动补齐不会生效, '
            'auto_queue 任务启用后仍不会进队列')
        assert 'build_run_list()' not in obq, (
            '`_order_by_queue` 只该用 `build_queue()`（含自动补齐）')

    def test_overview_exposes_queue_fields(self):
        """`/overview` 必须给前端 `queued` 与 `auto_queue`。"""
        src = (REPO / 'module' / 'server' / 'schema_router.py').read_text(
            encoding='utf-8')
        # ⚠ 本轮改了签名: `_auto_queue_of(meta)` -> `_auto_queue_of(meta, config)`
        #   （统一判据: 与「周期 / 临时」同源）。★ 断言放宽到前缀, 签名再变也不假失败。
        assert "_auto_queue_of(meta" in src, \
            '`/overview` 必须给前端 `auto_queue`（判据见 `_auto_queue_of`）'
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
