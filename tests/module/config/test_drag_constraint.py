# -*- coding: utf-8 -*-
"""S6-4/S6-5 守卫: **拖动约束** + `priority_mode` 端点。

用户原话:
> "拖动只在同类别内生效是在选了**定时优先**或者**固定任务优先**时, 如果选了
>  **列表自定义**, 那么全都可以拖动次序。你理解下, 也就是**三个选项:
>  定时任务优先、固定任务优先、自定义**"
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

CFG = '恋鸟树'
T = {'kind': 'task', 'task': 'MetaDemon'}    # timed
F = {'kind': 'task', 'task': 'Orochi'}       # fixed


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope='module', autouse=True)
def _cwd():
    """★ `write_json` 用 `Path.cwd()` —— 不 `chdir` 会写错地方。"""
    old = os.getcwd()
    os.chdir(REPO)
    yield
    os.chdir(old)


@pytest.fixture()
def sr():
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.server import schema_router as SR
    return SR


@pytest.fixture()
def restore_mode(sr):
    """★ 备份 + **必定还原**（我在实时配置上做过测试 —— 必须还原）。"""
    before = _run(sr.get_priority_mode(CFG))['current']
    yield
    _run(sr.put_priority_mode(CFG, {'priority_mode': before}))


class TestPriorityModeEndpoint:
    def test_get_three_choices(self, sr):
        r = _run(sr.get_priority_mode(CFG))
        vals = [c['value'] for c in r['choices']]
        assert vals == ['timed_first', 'fixed_first', 'custom'], vals

    def test_labels_are_chinese_user_words(self, sr):
        """★ 界面名要对上用户说的三个词。"""
        r = _run(sr.get_priority_mode(CFG))
        labels = {c['value']: c['label'] for c in r['choices']}
        assert labels['timed_first'] == '定时任务优先'
        assert labels['fixed_first'] == '固定任务优先'
        assert labels['custom'] == '自定义'

    def test_drag_flag_matches_mode(self, sr, restore_mode):
        """★ `drag_within_group_only`: 只有 `custom` 是 False。"""
        for mode, want in (('timed_first', True), ('fixed_first', True),
                           ('custom', False)):
            _run(sr.put_priority_mode(CFG, {'priority_mode': mode}))
            got = _run(sr.get_priority_mode(CFG))
            assert got['current'] == mode, got
            assert got['drag_within_group_only'] is want, (mode, got)

    def test_put_rejects_bad_value(self, sr):
        r = _run(sr.put_priority_mode(CFG, {'priority_mode': 'nonsense'}))
        assert r.get('error'), r

    def test_put_sets_explicit_flag(self, sr, restore_mode):
        """★★ PUT 必须置 `priority_mode_explicit` —— 否则下次加载会被迁移覆盖。"""
        _run(sr.put_priority_mode(CFG, {'priority_mode': 'fixed_first'}))
        from module.server.main_manager import mm
        cfg = mm.config_cache(CFG)
        assert bool(cfg.model.script.optimization.priority_mode_explicit) is True


class TestDragConstraint:
    """★★ 拖动约束: `custom` 自由; 另两模式**同段内**。"""

    def test_custom_allows_cross_group(self, sr, restore_mode):
        _run(sr.put_priority_mode(CFG, {'priority_mode': 'custom'}))
        for ents in ([T, F], [F, T]):
            r = _run(sr.put_run_list(CFG, ents))
            assert not r.get('drag_blocked'), (ents, r)

    def test_timed_first_blocks_fixed_before_timed(self, sr, restore_mode):
        _run(sr.put_priority_mode(CFG, {'priority_mode': 'timed_first'}))
        r = _run(sr.put_run_list(CFG, [F, T]))
        assert r.get('drag_blocked') is True, r
        assert '跨类别' in str(r.get('error')), r

    def test_timed_first_allows_timed_before_fixed(self, sr, restore_mode):
        _run(sr.put_priority_mode(CFG, {'priority_mode': 'timed_first'}))
        r = _run(sr.put_run_list(CFG, [T, F]))
        assert not r.get('drag_blocked'), r

    def test_fixed_first_blocks_timed_before_fixed(self, sr, restore_mode):
        _run(sr.put_priority_mode(CFG, {'priority_mode': 'fixed_first'}))
        r = _run(sr.put_run_list(CFG, [T, F]))
        assert r.get('drag_blocked') is True, r

    def test_fixed_first_allows_fixed_before_timed(self, sr, restore_mode):
        _run(sr.put_priority_mode(CFG, {'priority_mode': 'fixed_first'}))
        r = _run(sr.put_run_list(CFG, [F, T]))
        assert not r.get('drag_blocked'), r


class TestSchemaExposesMode:
    def test_global_fields_has_priority_mode(self):
        """★ 「全局设置」面板必须暴露 `priority_mode`（**前端据此渲染下拉**）。

        ⚠ 构造器叫 `_global_fields`（我第一版猜成 `build_optional_schema`,
          结果测试被 skip —— **假通过**。已改正, 不再 skip）。
        """
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server import schema_router as S
        opt = S._global_fields(CFG)
        assert 'priority_mode' in opt, f'缺 priority_mode; 现有 {list(opt)}'
        item = opt['priority_mode']
        assert item['current'] in ('timed_first', 'fixed_first', 'custom')
        # ★ 前端要靠 `choices` 里的这个标记决定**能否跨类别拖动**
        assert all('drag_within_group_only' in c for c in item['choices'])

    def test_old_fields_not_exposed_as_choices(self):
        """★ 旧的 `timed_priority` 不再作为**可选项**暴露（已并入三模式）。"""
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server import schema_router as S
        opt = S._global_fields(CFG)
        assert 'timed_priority' not in opt, '旧字段不该再出现在全局设置里'
