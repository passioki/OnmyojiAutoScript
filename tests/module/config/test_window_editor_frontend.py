# -*- coding: utf-8 -*-
"""S4 前端: 窗口列表编辑器（存在性 + 契约守卫）。"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OASX = Path(r'D:\OAS-dev\OASX-src')


def _src(rel):
    return (OASX / rel).read_text(encoding='utf-8')


class TestWindowEditorExists:
    def test_file_exists(self):
        assert (OASX / 'lib/views/args/window_editor.dart').is_file(), \
            '缺窗口列表编辑器 —— 用户裁定"设置多个 window"'

    def test_is_part_of_args_view(self):
        """★ 它是 `args_view.dart` 的 `part`（`part of` 指令必须有）。

        踩过: 直接 `import` 一个 `part` 文件会报 `part_of_non_part`。
        """
        src = _src('lib/views/args/window_editor.dart')
        assert "part of 'args_view.dart';" in src

    def test_args_view_declares_part(self):
        src = _src('lib/views/args/args_view.dart')
        assert "part './window_editor.dart';" in src

    def test_renders_for_windows_field(self):
        """★ `windows` 字段必须走**专用编辑器**（原生表单渲染不了 List）。"""
        src = _src('lib/views/args/args_view.dart')
        assert "model.name == 'windows'" in src, \
            'args_view 未把 `windows` 交给专用编辑器'
        assert 'WindowEditor(' in src


class TestWindowEditorFeatures:
    def _src(self):
        return _src('lib/views/args/window_editor.dart')

    def test_has_add_and_delete(self):
        src = self._src()
        assert '添加窗口' in src, '缺"添加窗口"（用户要"设置多个 window"）'
        assert 'Icons.delete_outline' in src, '缺删除按钮'

    def test_has_period_dropdown(self):
        src = self._src()
        for k in ("'daily'", "'weekly'", "'monthly'"):
            assert k in src, f'周期下拉缺 {k}'
        assert '每天' in src and '每周' in src and '每月' in src

    def test_has_days_and_dom(self):
        src = self._src()
        assert "'days'" in src and "'days_of_month'" in src

    def test_saves_via_put_windows(self):
        """★ 保存走**整单替换** `PUT .../windows`（最可靠）。"""
        src = self._src()
        assert 'putTaskWindows' in src

    def test_uses_entry_id_like_identity(self):
        """★ 每条窗口带 `id`（"身份不是位置"）。"""
        src = self._src()
        assert "'id'" in src
        assert 'ValueKey' in src, '行要有 key（按 id）, 否则重排后状态会串'

    def test_explanations_are_tooltips(self):
        """★ 说明走 `Tooltip`（用户要求"括号改悬停"）。"""
        src = self._src()
        assert 'Tooltip' in src
        assert '一天跑两次' in src, '应说明"一天跑两次 = 两个窗口"'


class TestApiClient:
    def _src(self):
        return _src('lib/api/api_client.dart')

    def test_five_methods(self):
        src = self._src()
        for m in ('getTaskWindows', 'putTaskWindows', 'addTaskWindow',
                  'updateTaskWindow', 'deleteTaskWindow'):
            assert m in src, f'api_client 缺 {m}'

    def test_endpoints_match_backend(self):
        """★ 前后端**路径一致**（用户要求"前后端要同步改"）。

        ⚠ 断言里要匹配 Dart 的字符串插值 `$task` —— 用 **raw 字符串**
          避免 Python 把 `\\$` 当转义（我第一版就写错了，假失败）。
        """
        src = self._src()
        assert r'/tasks/$task/windows' in src, \
            'api_client 的窗口路径与后端不一致'


class TestArgumentModelHasName:
    def test_name_field_added(self):
        """★ `ArgumentModel` 必须有 `name`（判断字段类型用）。

        原来只有 `title`, 而 `title` 是中文展示名 —— 不能用来判断类型。
        """
        src = _src('lib/controller/args/args_controller.dart')
        assert 'final String name;' in src
        assert r"name: '${json['name'] ?? ''}'" in src, \
            'fromJson 未设置 name'

    def test_title_uses_title_not_name(self):
        """★ `fromJson` 里 `title` 应取 `json['title']`（原实现错用了 `name`）。"""
        src = _src('lib/controller/args/args_controller.dart')
        assert r"title: '${json['title'] ?? json['name'] ?? ''}'" in src, \
            'title 应从 json["title"] 取（原来错用了 name）'
