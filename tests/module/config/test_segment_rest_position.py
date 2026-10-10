# -*- coding: utf-8 -*-
"""`Config._tag_and_place_rest(rl)` —— **打段名 + 把「休息」挪到最后**。

## ★★★ 这一版是"架构简化"之后重写的 ★★★

用户原话（**唯一依据**）:

> "我觉得……这个**固定任务优先和定时任务优先以及不能跨类别拖动太蠢了**。
>  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
>  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有意义的
>  不能跨类别拖动以及**单独的调度优先级**。"

所以:

* 执行顺序 = **`run_list` 的顺序本身**。这个方法**不按任何模式排段** ——
  它只做两件事: ① 给条目打 `group` 段名（**显示用**）② 把 `rest` 挪到最后。
* 「定时排前面 / 固定排前面」是**一次性动作**（`Config.sort_run_list(by)`）,
  **不是模式** —— 那个能力的测试在 `test_queue_sort.py`。

## 为什么 `rest` 恒最后是**唯一**保留的硬约束

`rest` 条目会**阻塞列表**（跑完前面的才继续）。排在中间会把它后面的任务
**全挡住**。用户确认: "任意拖，但「休息」条目仍强制排最后"。

★ 而且它是**归一化**（挪到最后）**不是拒绝** —— 用户拖到哪都接受。

## 为什么"不改变任务之间的相对顺序"必须被钉住

这是"**拖动永远自由**"的根基: 若这个方法会重排任务, 用户拖出来的顺序
就**永远显示不出来**（正是用户抱怨的"拖了没用"）。
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

# ★★★ 测试用的两个样本任务（★ 用户裁定改了分类判据后换过）★★★
#
# 用户裁定:
# > "按照**有没有设置周期记忆**, `period` 不限时是**固定**（固定任务改名为
# >  **临时任务**）, 其他是**定时**（定时任务名字改为**周期任务**）"
#
# ★ 所以判据是 **`period`**, 不再是 `category`:
#   * `T_TASK` 必须是 `period != none`（= **周期任务**）
#   * `F_TASK` 必须是 `period == none`（= **临时任务**）
#
# ⚠ 原来写的是 `T_TASK, F_TASK = 'MetaDemon', 'Orochi'` —— 而 **`Orochi`
#   的 `period=DAILY`**, 新判据下它是**周期任务**, 于是本文件多条断言
#   （"F 在 T 前面"之类）**全部失效**。这就是"分类规则改了, 测试样本也得换"。
#
# ★ 两个都选**全天窗口**的, 免得窗口外的任务被 `sort_run_list` 的特殊
#   排序影响（那是另一个文件的职责）。
#   * `KekkaiActivation`  period=DAILY  -> timed（周期）
#   * `Exploration`       period=NONE   -> fixed（临时）
T_TASK, F_TASK = 'KekkaiActivation', 'Exploration'
REST10 = {'kind': 'rest', 'minutes': 10}


@pytest.fixture()
def cfg():
    """★ 用**临时配置名** —— 绝不碰 `config/恋鸟树.json` 等真实配置。

    `_tag_and_place_rest()` 本身只操作传进来的 `RunList`（不读不写配置）,
    但为了不再重演"测试改用户实时配置"的事故, 这里一律用临时配置。
    """
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
    """把 `RunList` 拍成 `(kind, task 或 minutes, group)` 列表。"""
    return [(getattr(getattr(e, 'kind', None), 'value', ''),
             getattr(e, 'task', '') or getattr(e, 'minutes', 0),
             getattr(e, 'group', '')) for e in rl.entries]


def _seg(cfg, entries):
    """跑 `_tag_and_place_rest()`, 返回 `(kind, task 或 minutes, group)`。"""
    from module.config.run_list import RunList
    rl = RunList.from_list(entries)
    cfg._tag_and_place_rest(rl)
    return _snap(rl)


def _kinds(got):
    return [k for k, _, _ in got]


def _tasks(got):
    return [t for k, t, _ in got if k == 'task']


class TestRestAlwaysLast:
    """★★ `rest` **恒排最后** —— 删掉三模式之后**唯一**的硬约束 ★★"""

    def test_rest_after_all_tasks(self, cfg):
        got = _seg(cfg, [
            {'kind': 'task', 'task': F_TASK},
            REST10,
            {'kind': 'task', 'task': T_TASK},
        ])
        assert _kinds(got)[-1] == 'rest', (
            f'rest 没排在最后 -> {got}\n'
            f'★ rest 排中间会把后面所有任务都挡住')

    def test_rest_not_between_tasks(self, cfg):
        got = _seg(cfg, [
            REST10,
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'task', 'task': T_TASK},
        ])
        idx = [i for i, (k, _, _) in enumerate(got) if k == 'rest']
        assert idx == [len(got) - 1], f'rest 在下标 {idx}: {got}'

    def test_rest_moved_even_if_user_put_it_first(self, cfg):
        """★★ 归一化（**挪**）而不是拒绝 —— 用户拖到哪都接受 ★★

        这条正是与"旧的拖动约束"的**分界**: 旧实现会**拒绝**这种顺序
        （`drag_blocked`）; 现在**接受**并把 rest 挪到最后。
        """
        got = _seg(cfg, [REST10, {'kind': 'task', 'task': F_TASK}])
        assert _kinds(got) == ['task', 'rest'], got
        assert _tasks(got) == [F_TASK], '任务顺序不该被动'

    def test_chained_rests_all_at_end(self, cfg):
        """★ 链式多个 rest —— 全都到最后, 且**它们之间**保序。"""
        got = _seg(cfg, [
            {'kind': 'rest', 'minutes': 10},
            {'kind': 'task', 'task': F_TASK},
            {'kind': 'rest', 'minutes': 20},
            {'kind': 'task', 'task': T_TASK},
        ])
        assert _kinds(got) == ['task', 'task', 'rest', 'rest'], got
        # 稳定排序 -> 10 分钟那个仍在 20 分钟之前
        assert [t for k, t, _ in got if k == 'rest'] == [10, 20], got

    def test_only_rest_stays(self, cfg):
        got = _seg(cfg, [REST10])
        assert _kinds(got) == ['rest']

    def test_empty(self, cfg):
        assert _seg(cfg, []) == []

    def test_single_task_untouched(self, cfg):
        got = _seg(cfg, [{'kind': 'task', 'task': F_TASK}])
        assert _tasks(got) == [F_TASK], got


class TestOnlyTagsGroups:
    """★ 「只打 `group` 段名」+ **不改变任务之间的相对顺序**。"""

    def test_group_assigned_per_segment(self, cfg):
        got = _seg(cfg, [{'kind': 'task', 'task': T_TASK},
                         {'kind': 'task', 'task': F_TASK}])
        assert [(k, g) for k, _, g in got] == [
            ('task', 'timed'), ('task', 'fixed')], got

    def test_rest_has_no_group(self, cfg):
        """★ `rest` **不参与分段** —— `group` 为空（它没有类别）。"""
        got = _seg(cfg, [{'kind': 'task', 'task': F_TASK}, REST10])
        for kind, _, group in got:
            if kind == 'rest':
                assert group == '', f'rest 被打了段名 {group!r}'

    def test_relative_order_of_tasks_never_changes(self, cfg):
        """★★★ **拖动永远自由**的根基: 任务之间的相对顺序**一字不动** ★★★

        用户抱怨的正是"拖了没用"。若这里会按段重排, 用户拖出来的顺序就
        **永远显示不出来**。★ 所以本方法**只打段名, 不排段**。
        """
        entries = [
            {'kind': 'task', 'task': F_TASK},          # fixed
            {'kind': 'task', 'task': T_TASK},          # timed
            {'kind': 'task', 'task': 'Exploration'},   # fixed
            {'kind': 'task', 'task': 'Nian'},          # timed
            {'kind': 'task', 'task': 'SixRealms'},     # fixed
        ]
        got = _seg(cfg, entries)
        assert _tasks(got) == [e['task'] for e in entries], (
            f'任务被重排了（拖动就不自由了）: {got}')

    def test_timed_after_fixed_is_kept(self, cfg):
        """★ 反向也成立: **定时段在后**时同样不重排（没有"定时优先"）。"""
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
        """★ 连跑两次结果相同（它是纯函数式的派生步骤）。"""
        from module.config.run_list import RunList
        entries = [REST10, {'kind': 'task', 'task': T_TASK},
                   {'kind': 'task', 'task': F_TASK}]
        rl = RunList.from_list(entries)
        cfg._tag_and_place_rest(rl)
        first = _snap(rl)
        cfg._tag_and_place_rest(rl)
        second = _snap(rl)
        assert first == second == [('task', T_TASK, 'timed'),
                                   ('task', F_TASK, 'fixed'),
                                   ('rest', 10, '')], (first, second)
