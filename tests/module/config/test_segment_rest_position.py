# -*- coding: utf-8 -*-
"""`Config._tag_and_place_rest(rl)` -- 打段名 + 休息**保持用户位置**。

## ★★★ P-2（用户裁定）: 休息**不再**恒排最后 ★★★

用户原话:
> "休息**也是任务**, 只不过可以选择插入定时任务。"
> "休息当然就是**挡住后边的**, 本质为了**防封**, **符合预期**。"

### 曾经错在哪

本文件原来叫 `TestRestAlwaysLast`, docstring 里写着
"用户确认: 任意拖，但「休息」条目仍强制排最后" ——
★ **那句话不是用户的裁定**, 是某次简化时写下的临时约束被误记成长期规则。
用户已明确澄清, 所以:

* 后端 `_tag_and_place_rest` **只打段名**, 一个字都不动顺序
* `place_rest_last()` 保留名字但**直通**（两个端点还在调它）

### 仍然保留的（★ 不要误删）

* 休息**阻塞列表**（`RunList.blocking_entry()` 返回第一个 `REST`）——
  拖到中间时它后面的任务会等到休息结束才跑。★ 这是用户**明确要的**防封效果
* `rest_interleave`（"休息时可穿插定时任务"）—— 独立能力, 见
  `Config.can_interleave_timed` / `pick_interleave_candidate`

### 为什么"不改变任务之间的相对顺序"仍要被钉住

这是"**拖动永远自由**"的根基: 若本方法会重排任务, 用户拖出来的顺序
就**永远显示不出来**（正是用户抱怨的"拖了没用"）。
★ 所以本文件既钉"任务不被重排", 也钉"**休息也不被重排**"。
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

# 判据是 `period`（用户裁定: 有周期记忆 -> timed(周期); 否则 fixed(临时)）
#   * `KekkaiActivation`  period=DAILY  -> timed
#   * `Exploration`       period=NONE   -> fixed
T_TASK, F_TASK = 'KekkaiActivation', 'Exploration'
REST10 = {'kind': 'rest', 'minutes': 10}


@pytest.fixture()
def cfg():
    """用**临时配置名**，绝不碰真实配置。"""
    import json
    import server  # noqa: F401
    from module.config.config import Config

    os.chdir(REPO)
    name = '__seg_rest__'
    p = REPO / 'config' / f'{name}.json'
    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization']['run_list'] = []
    p.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    try:
        yield Config(name)
    finally:
        try:
            p.unlink()
        except OSError:
            pass


def _snap(rl):
    return [(getattr(getattr(e, 'kind', None), 'value', ''),
             getattr(e, 'task', '') or getattr(e, 'minutes', 0),
             getattr(e, 'group', '')) for e in rl.entries]


def _seg(cfg, entries):
    from module.config.run_list import RunList
    rl = RunList.from_list(entries)
    cfg._tag_and_place_rest(rl)
    return _snap(rl)


def _kinds(got):
    return [k for k, _, _ in got]


def _tasks(got):
    return [t for k, t, _ in got if k == 'task']


class TestRestKeepsUserPosition:
    """★★ P-2: 休息**保持在用户放的位置**（不再被挪到最后）★★"""

    def test_rest_in_middle_stays_in_middle(self, cfg):
        got = _seg(cfg, [
            {'kind': 'task', 'task': F_TASK},
            REST10,
            {'kind': 'task', 'task': T_TASK},
        ])
        assert _kinds(got) == ['task', 'rest', 'task'], got

    def test_rest_first_stays_first(self, cfg):
        """★ 用户把休息拖到**最前**也一样保留（旧实现会挪到最后）。"""
        got = _seg(cfg, [REST10, {'kind': 'task', 'task': F_TASK}])
        assert _kinds(got) == ['rest', 'task'], got
        assert _tasks(got) == [F_TASK], '任务顺序不该被动'

    def test_rest_last_stays_last(self, cfg):
        got = _seg(cfg, [{'kind': 'task', 'task': F_TASK}, REST10])
        assert _kinds(got) == ['task', 'rest'], got

    def test_multiple_rests_keep_their_slots(self, cfg):
        """★ 多个 rest 各就各位，且**它们之间**保序。"""
        got = _seg(cfg, [
            {'kind': 'rest', 'minutes': 10},
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'rest', 'minutes': 20},
            {'kind': 'task', 'task': T_TASK},
        ])
        assert _kinds(got) == ['rest', 'task', 'rest', 'task'], got
        assert [t for k, t, _ in got if k == 'rest'] == [10, 20], got

    def test_chained_rests_stay_together(self, cfg):
        got = _seg(cfg, [
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'rest', 'minutes': 1},
            {'kind': 'rest', 'minutes': 2},
            {'kind': 'task', 'task': T_TASK},
        ])
        assert _kinds(got) == ['task', 'rest', 'rest', 'task'], got

    def test_only_rest_stays(self, cfg):
        got = _seg(cfg, [REST10])
        assert _kinds(got) == ['rest']

    def test_empty(self, cfg):
        assert _seg(cfg, []) == []

    def test_single_task_untouched(self, cfg):
        got = _seg(cfg, [{'kind': 'task', 'task': F_TASK}])
        assert _tasks(got) == [F_TASK], got


class TestPlaceRestLastIsNowNoOp:
    """★★ P-2: `place_rest_last()` 保留名字但**不再挪位** ★★"""

    def test_noop_keeps_order(self, cfg):
        from module.config.run_list import RunList
        entries = [REST10, {'kind': 'task', 'task': F_TASK}]
        rl = RunList.from_list(entries)
        before = _kinds(_snap(rl))
        cfg.place_rest_last(rl)
        after = _kinds(_snap(rl))
        assert before == after == ['rest', 'task'], (before, after)

    def test_noop_returns_the_list(self, cfg):
        from module.config.run_list import RunList
        rl = RunList.from_list([REST10])
        out = cfg.place_rest_last(rl)
        assert out is not None and len(out.entries) == 1


class TestRestStillBlocks:
    """★ 休息的**功能**（阻塞列表, 防封）必须保留 —— 只是不再有排序约束。"""

    def test_rest_is_the_blocker(self, cfg):
        from module.config.run_list import RunList
        rl = RunList.from_list([{'kind': 'task', 'task': F_TASK}, REST10])
        b = rl.blocking_entry()
        assert b is not None
        assert getattr(getattr(b, 'kind', None), 'value', '') == 'rest'

    def test_task_is_not_a_blocker(self, cfg):
        from module.config.run_list import RunList
        rl = RunList.from_list([{'kind': 'task', 'task': F_TASK}])
        assert rl.blocking_entry() is None

    def test_blocker_is_first_rest_when_multiple(self, cfg):
        """★ 多个 rest 时, 阻塞的是**第一个**（与"可自由拖动"天然吻合）。"""
        from module.config.run_list import RunList
        rl = RunList.from_list([
            {'kind': 'rest', 'minutes': 7},
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'rest', 'minutes': 9},
        ])
        b = rl.blocking_entry()
        assert b is not None and b.minutes == 7, getattr(b, 'minutes', None)


class TestOnlyTagsGroups:
    """打 `group` 段名, **不改**任何条目的位置。"""

    def test_group_assigned_per_segment(self, cfg):
        got = _seg(cfg, [{'kind': 'task', 'task': T_TASK},
                         {'kind': 'task', 'task': F_TASK}])
        assert [(k, g) for k, _, g in got] == [
            ('task', 'timed'), ('task', 'fixed')], got

    def test_rest_has_no_group(self, cfg):
        """`rest` 不参与分段 —— `group` 为空（它没有类别）。"""
        got = _seg(cfg, [{'kind': 'task', 'task': F_TASK}, REST10])
        for kind, _, group in got:
            if kind == 'rest':
                assert group == '', f'rest 被打段名: {group!r}'

    def test_relative_order_of_tasks_never_changes(self, cfg):
        entries = [
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'task', 'task': T_TASK},
            {'kind': 'task', 'task': 'Exploration'},
            {'kind': 'task', 'task': 'Nian'},
            {'kind': 'task', 'task': 'SixRealms'},
        ]
        got = _seg(cfg, entries)
        assert _tasks(got) == [e['task'] for e in entries], (
            f'任务被重排了（拖动就不自由了）: {got}')

    def test_timed_after_fixed_is_kept(self, cfg):
        entries = [{'kind': 'task', 'task': F_TASK},
                   {'kind': 'task', 'task': T_TASK}]
        assert _tasks(_seg(cfg, entries)) == [F_TASK, T_TASK]
        entries = [{'kind': 'task', 'task': T_TASK},
                   {'kind': 'task', 'task': F_TASK}]
        assert _tasks(_seg(cfg, entries)) == [T_TASK, F_TASK]

    def test_all_same_segment_order_kept(self, cfg):
        entries = [{'kind': 'task', 'task': t}
                   for t in ('Orochi', 'Exploration', 'SixRealms')]
        got = _seg(cfg, entries)
        assert _tasks(got) == ['Orochi', 'Exploration', 'SixRealms'], got

    def test_repeated_iteration_is_idempotent(self, cfg):
        """连跑两次结果相同（纯函数式派生步骤）。"""
        from module.config.run_list import RunList
        entries = [REST10, {'kind': 'task', 'task': T_TASK},
                   {'kind': 'task', 'task': F_TASK}]
        rl = RunList.from_list(entries)
        cfg._tag_and_place_rest(rl)
        first = _snap(rl)
        cfg._tag_and_place_rest(rl)
        second = _snap(rl)
        assert first == second == [('rest', 10, ''),
                                   ('task', T_TASK, 'timed'),
                                   ('task', F_TASK, 'fixed')], (first, second)
