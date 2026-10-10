# -*- coding: utf-8 -*-
"""★★★ S7 补: **界面三个口径必须一致** + **排序要避开"当前跑不了"的任务** ★★★

## 用户原话（实机验收）

> "排序不对啊！我发现有个问题是：执行顺序下边的任务统计数量显示：
>  **定时任务2条，固定任务14条**，但是我看到的是任务上的标签显示的几乎都是
>  **紫色的定时，红色的次数只有四个**。
>  而且有个**不在开放时段内的秘闻副本也参与了定时排前面的排序，排到了最前边**"

## 两个 bug（同一批代码里）

### ① 界面对"这个任务属于哪一段"有**三个口径**

| 界面位置 | 原来读的字段 | 语义 |
|---|---|---|
| 「执行顺序」下的分段条 | `priority_group` | ★ **有效分段**（权威）|
| 任务表格的「类型」列 | `category_label`（← `TaskMeta.category`）| **声明**类别 |
| 队列行的色条 / 标签 | `auto_queue` | 会不会**自动进队列** |

★ 实测 `恋鸟树` 16 条队列里 **10 条**声明 `timed` 而有效分段是 `fixed`
（`Delegation`/`DemonEncounter`/`AreaBoss`/`GoldYoukai`/`RichMan`/…）
-> 界面**同时**说它"是定时"又说"按 fixed 排", 看起来**自相矛盾**。

★ 修法: 后端加 `priority_group_label`（与 `priority_group` **同源**）,
  前端三处**都用它**。

### ② 排序不看"能不能跑"

`Secret`（秘闻副本, 窗口"周一 08:00-23:59"）在**非开放时段**仍被当成
"定时段第一条"排到**最前** —— 可它**根本跑不了**, 顶在最前面只是把
能跑的任务全挤到后面。

★ 修法: `sort_run_list` 的 rank 从 2 档变 4 档（能跑的优先）, 见
  `Config.sort_run_list` 的 "当前跑不了的排到后面" 那一段。
"""
import logging
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

CFG = '__cat_label__'
P = REPO / 'config' / f'{CFG}.json'


import pytest  # noqa: E402


@pytest.fixture(scope='module')
def live():
    os.chdir(REPO)
    import server  # noqa: F401
    from module.server.main_manager import mm
    return mm.config_cache('恋鸟树')


class TestOverviewGivesAuthoritativeLabel:
    """★ 后端必须给出**权威的段标签**, 前端才有得可用。"""

    def test_fields_present(self, live):
        from module.server import schema_router as SR
        ov = SR.build_overview('恋鸟树')
        rows = ov.get('tasks') or []
        assert rows, '总览没有任务行'
        for r in rows:
            for k in ('priority_group', 'priority_group_label',
                      'in_window_now'):
                assert k in r, f'{r.get("command")} 缺字段 {k}'

    def test_label_matches_group(self, live):
        """★★ 核心: `priority_group_label` 必须与 `priority_group` **同源**。"""
        from module.server import schema_router as SR
        ov = SR.build_overview('恋鸟树')
        for r in (ov.get('tasks') or []):
            want = {'timed': '定时', 'fixed': '固定'}.get(
                r['priority_group'])
            assert want is not None, f'未知 priority_group: {r["priority_group"]}'
            assert r['priority_group_label'] == want, (
                f'{r["command"]}: group={r["priority_group"]} 但 '
                f'label={r["priority_group_label"]!r} —— 两个字段必须同源')

    def test_declared_category_may_differ_but_label_follows_group(self, live):
        """★★ 正是用户看到的矛盾: 声明 `timed` 而有效分段 `fixed`。

        ★ 断言**标签跟的是 group（有效分段）, 不是 category（声明）**。
        """
        from module.server import schema_router as SR
        ov = SR.build_overview('恋鸟树')
        rows = ov.get('tasks') or []
        mismatch = [r for r in rows
                    if r.get('category') == 'timed'
                    and r.get('priority_group') == 'fixed']
        if not mismatch:
            pytest.skip('当前没有"声明 timed 但有效分段 fixed"的任务 —— '
                        '这不是失败, 是没测到')
        for r in mismatch:
            assert r['priority_group_label'] == '固定', (
                f'★ {r["command"]}: 声明 timed / 有效 fixed, '
                f'标签却给 {r["priority_group_label"]!r} —— '
                f'界面会和分段条自相矛盾（用户报的正是这个）')

    def test_counts_agree_within_queued(self, live):
        """★★ 分段条统计 == 标签统计（用户报的矛盾点）。"""
        from collections import Counter

        from module.server import schema_router as SR
        ov = SR.build_overview('恋鸟树')
        queued = [r for r in (ov.get('tasks') or []) if r.get('queued')]
        if not queued:
            pytest.skip('队列为空 —— 没测到')
        by_group = Counter(r['priority_group'] for r in queued)
        by_label = Counter(r['priority_group_label'] for r in queued)
        assert by_label.get('定时', 0) == by_group.get('timed', 0), (
            f'★ 分段条说定时 {by_group.get("timed", 0)} 条, '
            f'标签却有 {by_label.get("定时", 0)} 枚 —— 口径不一致')
        assert by_label.get('固定', 0) == by_group.get('fixed', 0), (
            f'★ 分段条说固定 {by_group.get("fixed", 0)} 条, '
            f'标签却有 {by_label.get("固定", 0)} 枚 —— 口径不一致')


class TestSortAvoidsOutOfWindowTasks:
    """★ 用户: "不在开放时段内的秘闻副本…排到了最前边"。"""

    @pytest.fixture()
    def tmp_cfg(self):
        import json
        os.chdir(REPO)
        from module.config import task_catalog as TC
        from module.config.config_model import convert_to_underscore
        # 找一个 timed 段任务 + 一个 fixed 段任务
        names = list(TC.all_specs())
        timed = [n for n in names if TC.get_spec(n).priority_group == 'timed']
        fixed = [n for n in names if TC.get_spec(n).priority_group == 'fixed']
        assert timed and fixed, '任务太少'
        # ★ 找一个**当前不在窗口**的任务（若没有就 skip）
        out = [n for n in timed if not TC.get_spec(n).in_window()]
        if not out:
            pytest.skip('当前没有"不在窗口"的 timed 任务 —— 没测到')
        entries = ([{'kind': 'task', 'task': out[0], 'entry_id': 'oow'}]
                   + [{'kind': 'task', 'task': t, 'entry_id': f't{i}'}
                      for i, t in enumerate(
                          [x for x in timed if x != out[0]][:1])]
                   + [{'kind': 'task', 'task': f, 'entry_id': f'f{i}'}
                      for i, f in enumerate(fixed[:2])])
        tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
            encoding='utf-8'))
        tmpl['script']['optimization']['run_list'] = entries
        for e in entries:
            node = tmpl.get(convert_to_underscore(e['task']))
            if isinstance(node, dict) and isinstance(node.get('scheduler'),
                                                     dict):
                node['scheduler']['enable'] = True
        P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
        try:
            from module.config.config import Config
            yield Config(CFG), out[0]
        finally:
            try:
                P.unlink()
            except OSError:
                pass

    def test_out_of_window_timed_goes_after_in_window_timed(self, tmp_cfg):
        """★★ 核心: 不在窗口的 timed 任务**不能**排到在窗口的 timed 前面。"""
        cfg, oow = tmp_cfg
        assert cfg.sort_run_list('timed') is True
        from module.config.config import Config
        seq = [getattr(e, 'task', '') for e in Config(CFG).build_run_list()]
        assert seq, '排序后 run_list 为空'
        # 不在窗口的那个**不应**是第一个
        assert seq[0] != oow, (
            f'★ 不在开放时段的 {oow} 被排到了最前 —— 用户报的正是这个')
        # 且它应该在**所有能跑的 timed 任务之后**
        assert seq.index(oow) > 0

    def test_rest_still_last(self, tmp_cfg):
        """★ 排序不能破坏"休息恒最后"。"""
        import json

        from module.config.config import Config
        _cfg, _ = tmp_cfg
        d = json.loads(P.read_text(encoding='utf-8'))
        d['script']['optimization']['run_list'].append(
            {'kind': 'rest', 'minutes': 5})
        P.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
        # ★ 必须在**写完 rest 之后**重新构造 Config ——
        #   `tmp_cfg` 给的那个实例是**写之前**建的, 它的内存里没有 rest。
        #   （我第一版就没重建, 于是断言看到的是旧内容 -> 假失败。）
        fresh = Config(CFG)
        assert fresh.sort_run_list('timed') is True
        entries = Config(CFG).build_run_list().entries
        assert getattr(entries[-1], 'task', '') in ('', None), \
            f'★ 排序把 rest 弄走了 —— 它必须恒在最后（实际末条: ' \
            f'{getattr(entries[-1], "task", "")!r}）'


class TestFrontendUsesOneSourceOnly:
    """★ 前端**不许**再拿 `category_label` / `auto_queue` 当"分段"用。"""

    OASX = Path(r'D:\OAS-dev\OASX-src')

    def _code(self, rel):
        from _srcutil import code_only
        return code_only(self.OASX / rel)

    def test_task_row_uses_priority_group_label(self):
        src = self._code('lib/views/tasks/task_row_view.dart')
        assert 'priorityGroupLabelOf' in src, (
            '★ 任务表格的「类型」列应读 `priorityGroupLabelOf()` '
            '（后端 `priority_group_label`）')
        assert "task['category_label']" not in src, (
            '★ 它又回去读 `category_label` 了 —— 那是**声明**类别, '
            '会和分段条自相矛盾（用户报的正是这个）')

    def test_queue_panel_uses_priority_group_label(self):
        src = self._code('lib/views/tasks/queue_panel.dart')
        assert 'priorityGroupLabelOf' in src, (
            '★ 队列行的类别标签应读 `priorityGroupLabelOf()`')
        # 色条也不能再按 auto_queue 分
        assert 'isAutoTask ?\n' not in src.replace(' ', ''), \
            '★ 色条又按 `auto_queue` 分了 —— 那是第三个口径'

    def test_controller_exposes_the_label(self):
        src = self._code('lib/controller/task_list/task_list_controller.dart')
        assert 'String priorityGroupLabelOf(' in src
        assert "t['priority_group_label']" in src, (
            '★ 标签必须读后端的 `priority_group_label`, 前端不自己编')

    def test_sort_rank_has_four_tiers(self):
        """★ 后端排序必须是 4 档（能跑/不能跑 × 本段/它段）。"""
        from _srcutil import code_of
        body = code_of(REPO / 'module' / 'config' / 'config.py',
                       'def sort_run_list')
        assert 'in_window' in body, (
            '★ 排序必须看"能不能跑"（用户报的"不在窗口的排到最前"）')
        for r in ('return 0 if runnable else 1', 'return 2 if runnable else 3'):
            assert r in body, f'★ 缺 rank 分支: {r}'
        assert 'return 9' in body, '★ rest 恒最后那档不能丢'
