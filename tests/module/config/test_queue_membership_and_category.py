# -*- coding: utf-8 -*-
"""②③: 队列成员必须过滤 `enable`；队列行要按类别区分。

## ② 用户反馈

> "执行队列-执行顺序页面, 这里出现了很多**未启用**的任务"

**实测根因**: `queued_commands()` 用 `out.update(self.auto_queue_tasks())`
—— `auto_queue_tasks()` 返回**所有** auto_queue 任务（**不看 `enable`**）,
而权威的 `build_queue()` 有 `if not self._task_enabled(task): continue`。

**同一个知识在两处定义, 其中一处漏了 `enable`**（台账 §10.8 要防的）。

实测: `queued_commands()` 41 个（23 个未启用）-> 修后 18 个（0 个未启用）。

## ③ 用户反馈

> "如果是因为次数类只能在次序类里拖动, 定时只能在定时类任务队拖动,
>  那么请用**不同颜色或两个边框**来区分。"
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OASX = Path(r'D:\OAS-dev\OASX-src')


class TestQueuedCommandsFiltersDisabled:
    """★★ ②: `queued_commands()` 必须与 `build_queue()` 用**同一个** enable 过滤。"""

    @pytest.fixture()
    def config(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_no_disabled_auto_task_in_queue(self, config):
        """★ 未启用的自动任务**不该**出现在队列成员里。"""
        queued = config.queued_commands()
        bad = [t for t in config.auto_queue_tasks()
               if not config._task_enabled(t) and t in queued]
        assert not bad, (
            f'② 回归: 未启用的自动任务出现在队列成员里: {bad[:8]}\n'
            f'（`queued_commands()` 必须和 `build_queue()` 一样过滤 enable）')

    def test_enabled_auto_task_is_in_queue(self, config):
        queued = config.queued_commands()
        for t in config.auto_queue_tasks():
            if config._task_enabled(t):
                assert t in queued, f'已启用的 {t} 应在队列里'

    def test_count_matches_build_queue(self, config):
        """★ 两个概念的**规模应一致**（这是"单一数据源"的可观测判据）。

        `build_queue()` 是权威（含休息条目, 条数可能略多）, 但**队列成员**
        不该比它多出"未启用的任务"。
        """
        queued = config.queued_commands()
        q = config.build_queue()
        tasks_in_build = {getattr(e, 'task', None) for e in q
                          if getattr(e, 'task', None)}
        extra = {t for t in queued if t not in tasks_in_build}
        # 允许 `run_list` 里有但 `build_queue()` 没排上的（例如不在窗口）,
        # 但**不允许**未启用的自动任务混进来
        bad = [t for t in extra
               if t in config.auto_queue_tasks()
               and not config._task_enabled(t)]
        assert not bad, f'② 回归: {bad[:8]}'


class TestFrontendCategoryVisuals:
    """③: 队列行要**看得出**「定时」与「次数」。"""

    def _panel(self):
        return (OASX / 'lib/views/tasks/queue_panel.dart').read_text(
            encoding='utf-8')

    def test_has_category_accent(self):
        src = self._panel()
        assert 'accent' in src, '③ 缺类别色条'
        assert 'BorderSide(color: accent, width: 3)' in src, \
            '③ 缺左侧类别色条（定时/次数要能一眼分辨）'

    def test_has_category_label(self):
        src = self._panel()
        assert "'定时'" in src and "'次数'" in src, '③ 缺类别文字标签'

    def test_explains_via_tooltip(self):
        """★ 说明走 Tooltip（用户要求"括号改悬停"）。"""
        src = self._panel()
        i = src.find("isAutoTask ? '定时' : '次数'")
        assert i > 0
        before = src[max(0, i - 1200):i]
        assert 'Tooltip' in before, '③ 类别说明应走 Tooltip, 不写括号'

    def test_container_uses_decoration_not_color(self):
        """★ Flutter 的 `Container` **不能**同时给 `color` 与 `decoration`。"""
        src = self._panel()
        i = src.find('Widget _queueRow')
        body = src[i:i + 2500]
        assert 'decoration: BoxDecoration(' in body
        # 该段里不该再有 `color: bg,` 这种与 decoration 并列的写法
        assert 'color: bg,\n      child:' not in body, \
            'Container 同时给了 color 与 decoration -> 会 assert 崩'


# ★★★ `TestPriorityModeHint` **整类已删除** ★★★
#
# 用户裁定（架构简化）:
# > "我觉得……这个**固定任务优先和定时任务优先以及不能跨类别拖动太蠢了**。
# >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
# >  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有意义的
# >  不能跨类别拖动以及**单独的调度优先级**。"
#
# 所以这一簇东西全没了, 类里那 3 条**全部**依赖已删符号:
#
# | 原测试 | 依赖 |
# |---|---|
# | `test_drag_scope_hint_present` | 前端的「只能同类别内拖动」提示 + `priority_mode` |
# | `test_backend_returns_drag_flag` | 后端 `drag_within_group_only` |
# | `test_legacy_fields_no_longer_read_for_ordering` | `_segment_queue()`（已改名 `_tag_and_place_rest()`）|
#
# ★ 其中"`_order_by_timed_priority` 已删除"这个**反向意图**没有丢:
#   它仍由 `test_queue_no_leak_all_rules.py::test_timed_priority_not_used_to_reorder`
#   守着; 而"拖动永远自由"的根基（`_tag_and_place_rest()` **不改变任务相对顺序**）
#   由 `test_segment_rest_position.py::TestOnlyTagsGroups` 守着。
