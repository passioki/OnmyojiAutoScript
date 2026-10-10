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


class TestPriorityModeHint:
    """③: 说清「调度优先级」的**拖动范围**（用户 2026-10-10 反馈的 ③）。

    ★★ S6 变化 ★★

    原来这里断言「需选『列表优先』才生效」—— 那是**两个重叠下拉**时代的
    提示（用户抱怨"两个下拉语义重叠"）。

    用户裁定（S6）: "**三个选项: 定时任务优先、固定任务优先、自定义**" ——
    两个下拉已合并成 `priority_mode`, 提示也改成**拖动范围**的说明。
    """

    def test_drag_scope_hint_present(self):
        src = (OASX / 'lib/views/tasks/task_list_view.dart').read_text(
            encoding='utf-8')
        # ★ 说清"当前模式下能怎么拖" —— 正是用户 ③ 的诉求
        assert '只能同类别内拖动' in src, \
            '缺"只能同类别内拖动"的提示（用户 ③ 的诉求）'
        assert '可自由拖动' in src, \
            '缺"可自由拖动"的提示（自定义模式）'
        assert 'priority_mode' in src, \
            '前端应读后端给的 `priority_mode`（不硬编码）'

    def test_backend_returns_drag_flag(self):
        """★ 后端要给出 `drag_within_group_only` —— 前端据此决定拖动范围。

        ## ★ 第二轮复审修复: 必须**剥注释**再断言

        原来直接 `assert 'drag_within_group_only' in src` —— 复审员实测
        `schema_router.py` 的 **docstring 里就有这个词**, 于是把三处真代码
        全删掉**这条仍然通过**。★ 正是本仓反复踩的"守卫匹配到自己的说明文字"。
        """
        from _srcutil import code_only
        src = code_only(REPO / 'module' / 'server' / 'schema_router.py')
        assert 'drag_within_group_only' in src, \
            '后端未给出拖动范围标记'

    def test_legacy_fields_no_longer_read_for_ordering(self):
        """★★ S6: 旧的 `timed_priority` **不再参与排序** ★★

        ## 为什么这条断言反过来了

        原来这里断言"`timed_priority` 的读取点在 `_order_by_timed_priority` 内"
        —— 那是**旧设计**（两个下拉语义重叠）。

        用户裁定（S6）: "**三个选项**: 定时任务优先、固定任务优先、自定义" ——
        所以旧字段已并入 `priority_mode`, `_order_by_timed_priority()` 也**已删除**
        （它是死代码）。

        ★ 现在断言的是**反向**事实:
          * `_order_by_timed_priority` **不存在**了
          * 排段由 `priority_mode` / `_segment_queue()` 负责
        """
        from _srcutil import code_only
        src = code_only(REPO / 'module' / 'config' / 'config.py')
        assert 'def _order_by_timed_priority' not in src, \
            '旧排序函数应已删除（S6 三模式取代）'
        assert 'def _segment_queue' in src, \
            '应有 `_segment_queue()` 负责按 priority_mode 排段'
        assert 'priority_mode' in src
