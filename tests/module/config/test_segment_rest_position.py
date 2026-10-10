# -*- coding: utf-8 -*-
"""T12: `rest`（休息）条目在**队列分段**里的位置 —— 原来完全没有测试。

## 审计发现（T12）

`Config._segment_queue()` 给 `rest` 条目算 `rank = 2`（**恒排最后**）,
但**没有任何测试观察它**:

* `test_queue_is_authority.py` 的 `_queue()` **把 rest 过滤掉了**
  （`if getattr(e, 'task', None)`）—— 于是 rest 在队列里的位置
  **从未被任何断言看过**
* `test_run_list.py` 只测 `RunList` 层（`replace_all` 能插任意位置）,
  不是 `_segment_queue()` 的行为

## 为什么这个位置很重要

`rest` 条目是"**跑完这些之后歇一会儿**"。如果它被排到中间,
**后面所有任务都会被它挡住** —— 那是用户一眼能看出的严重体验问题。

## 覆盖

* 三种模式下 `rest` 都必须在**最后**
* `rest` 不参与分段标签（`group` 为空）
* 同段内用户顺序不被 `_segment_queue` 打乱
* 空队列 / 只有 rest / 只有一条任务 —— 边界
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

CFG = '恋鸟树'
T_TASK, F_TASK = 'MetaDemon', 'Orochi'      # T=timed, F=fixed


@pytest.fixture()
def cfg():
    os.chdir(REPO)
    import server  # noqa: F401
    from module.server.main_manager import mm
    c = mm.config_cache(CFG)
    before = c.priority_mode()
    yield c
    # ★ 备份 + 必定还原（我在实时配置上做过测试 —— 必须还原）
    try:
        c.model.script.optimization.priority_mode = before
        c.model.script.optimization.priority_mode_explicit = True
    except Exception:
        pass


def _seg(cfg, entries):
    """用 `_segment_queue()` 给一份 `RunList` 排序, 返回 (kind, task/分钟, group)。"""
    from module.config.run_list import RunList
    rl = RunList.from_list(entries)
    cfg._segment_queue(rl)
    out = []
    for e in rl.entries:
        kind = getattr(getattr(e, 'kind', None), 'value', '')
        out.append((kind, getattr(e, 'task', '') or getattr(e, 'minutes', 0),
                    getattr(e, 'group', '')))
    return out


REST10 = {'kind': 'rest', 'minutes': 10}


class TestRestAlwaysLast:
    """★★ `rest` 在 `timed_first` / `fixed_first` 下**恒排最后** ★★

    ## ★ T12 修正: **`custom` 下不排**（我第一版写错了）

    我第一版把三种模式一起断言"rest 恒最后" —— **2 条失败**, 因为
    `_segment_queue()` 在 `custom` 时**直接返回**, rest **不**被挪走。

    ★ 哪个对? **两个都对, 取决于模式**:
      * `timed_first` / `fixed_first` -> 段序由**模式**决定, 而 rest
        **不属于任何段** -> 只能**垫最后**（否则挡住后面所有任务）
      * `custom` -> 用户裁定"**全都可以拖动次序**" ——
        rest 的位置**也是用户拖出来的**, 必须尊重

    ★ 我原来的代码注释写"rest **始终**排在最后" —— **与实现不符**。
      已改注释, 并在这里**显式**覆盖两种行为。
    """

    @pytest.mark.parametrize('mode', ['timed_first', 'fixed_first'])
    def test_rest_after_all_tasks(self, cfg, mode):
        cfg.model.script.optimization.priority_mode = mode
        got = _seg(cfg, [
            {'kind': 'task', 'task': F_TASK},
            REST10,
            {'kind': 'task', 'task': T_TASK},
        ])
        kinds = [k for k, _, _ in got]
        assert kinds[-1] == 'rest', (
            f'[{mode}] rest 没排在最后 -> {got}\n'
            f'★ rest 排中间会把后面所有任务都挡住')

    @pytest.mark.parametrize('mode', ['timed_first', 'fixed_first'])
    def test_rest_not_between_tasks(self, cfg, mode):
        cfg.model.script.optimization.priority_mode = mode
        got = _seg(cfg, [
            REST10,
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'task', 'task': T_TASK},
        ])
        idx = [i for i, (k, _, _) in enumerate(got) if k == 'rest']
        assert idx == [len(got) - 1], f'[{mode}] rest 在下标 {idx}: {got}'

    def test_custom_keeps_rest_where_user_put_it(self, cfg):
        """★ `custom` -> rest **留在用户放的位置**（不强制挪到最后）。"""
        cfg.model.script.optimization.priority_mode = 'custom'
        got = _seg(cfg, [
            REST10,
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'task', 'task': T_TASK},
        ])
        assert [k for k, _, _ in got] == ['rest', 'task', 'task'], (
            f'custom 下 rest 被挪走了: {got} —— '
            f'用户裁定"全都可以拖动次序", 不该动他排的休息位置')

    def test_chained_rests_all_at_end(self, cfg):
        cfg.model.script.optimization.priority_mode = 'timed_first'
        got = _seg(cfg, [
            REST10,
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'rest', 'minutes': 20},
            {'kind': 'task', 'task': T_TASK},
        ])
        kinds = [k for k, _, _ in got]
        assert kinds[:2] == ['task', 'task'], f'任务没被提到前面: {got}'
        assert kinds[2:] == ['rest', 'rest'], f'rest 没都在最后: {got}'


class TestRestNotSegmented:
    @pytest.mark.parametrize('mode', ['timed_first', 'fixed_first', 'custom'])
    def test_rest_has_no_group(self, cfg, mode):
        """★ `rest` **不参与分段** —— `group` 应为空（它没有类别）。"""
        cfg.model.script.optimization.priority_mode = mode
        got = _seg(cfg, [{'kind': 'task', 'task': F_TASK}, REST10])
        for kind, _, group in got:
            if kind == 'rest':
                assert group == '', (
                    f'[{mode}] rest 被打了段名 {group!r} —— '
                    f'它不该参与分段（`priorityGroupOf` 也不该给它段名）')

    def test_rest_does_not_break_segment_order(self, cfg):
        """★ 中间夹一个 rest, 不影响两个任务段的先后。"""
        cfg.model.script.optimization.priority_mode = 'timed_first'
        got = _seg(cfg, [
            {'kind': 'task', 'task': F_TASK},
            REST10,
            {'kind': 'task', 'task': T_TASK},
        ])
        tasks = [(k, g) for k, _, g in got if k == 'task']
        assert tasks == [('task', 'timed'), ('task', 'fixed')], (
            f'分段顺序不对: {tasks}')


class TestStabilityWithinSegment:
    """★ 段**内**用户顺序不被 `_segment_queue` 打乱（稳定排序）。"""

    def test_user_order_kept_inside_segment(self, cfg):
        cfg.model.script.optimization.priority_mode = 'timed_first'
        # 三个 fixed, 用户顺序 Orochi -> Exploration -> SixRealms
        got = _seg(cfg, [
            {'kind': 'task', 'task': 'Orochi'},
            {'kind': 'task', 'task': 'Exploration'},
            {'kind': 'task', 'task': 'SixRealms'},
        ])
        assert [t for _, t, _ in got] == ['Orochi', 'Exploration', 'SixRealms']

    def test_custom_keeps_full_user_order(self, cfg):
        """★★ `custom` **完全不动** —— 用户拖的顺序直接生效。"""
        cfg.model.script.optimization.priority_mode = 'custom'
        entries = [
            {'kind': 'task', 'task': 'Orochi'},      # fixed
            {'kind': 'task', 'task': T_TASK},        # timed
            {'kind': 'task', 'task': 'Exploration'},  # fixed
        ]
        got = _seg(cfg, entries)
        assert [t for _, t, _ in got] == ['Orochi', T_TASK, 'Exploration'], (
            f'custom 模式下被重排了: {got}')


class TestBoundaries:
    """★ 边界: 空队列 / 只有 rest / 只有一条任务。"""

    def test_empty(self, cfg):
        assert _seg(cfg, []) == []

    def test_only_rest(self, cfg):
        got = _seg(cfg, [REST10])
        assert [k for k, _, _ in got] == ['rest']

    def test_single_task(self, cfg):
        """★ 只有一条任务 —— 三种模式结果**必须一样**
        （没有"段间"可排, 最容易掩盖分段 bug 的情形）。"""
        outs = []
        for mode in ('timed_first', 'fixed_first', 'custom'):
            cfg.model.script.optimization.priority_mode = mode
            outs.append([t for _, t, _ in _seg(
                cfg, [{'kind': 'task', 'task': F_TASK}])])
        # ⚠ 我第一版写成 `== [[F_TASK]]`（多包了一层）—— 必然失败。
        assert outs[0] == outs[1] == outs[2] == [F_TASK], outs

    def test_all_same_segment(self, cfg):
        """★ 全是同一段 —— 两种模式应给**相同**结果（同段内顺序 = 用户顺序）。"""
        entries = [{'kind': 'task', 'task': t}
                   for t in ('Orochi', 'Exploration', 'SixRealms')]
        cfg.model.script.optimization.priority_mode = 'timed_first'
        a = [t for _, t, _ in _seg(cfg, entries)]
        cfg.model.script.optimization.priority_mode = 'fixed_first'
        b = [t for _, t, _ in _seg(cfg, entries)]
        assert a == b == [e['task'] for e in entries], (a, b)
