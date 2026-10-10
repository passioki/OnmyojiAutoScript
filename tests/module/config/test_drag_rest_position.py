# -*- coding: utf-8 -*-
"""★ 第二轮复审自查发现的 bug: **后端 `_check_drag_allowed` 不管 `rest` 的位置**。

## 现象

用户裁定: "**拖动只在同类别内生效**"。`rest`（休息）条目**不属于任何段**,
所以「跑完这些再休息」意味着它应当**垫最后** —— 把它拖到中间会**挡住**
后面所有任务。

| 端 | 行为 |
|---|---|
| **前端** `_sameGroupReorder` | `rest` -> rank **2** → 拖到中间 **被拦**（`run`? 见下）|
| **后端** `_check_drag_allowed` | `[e for e in rl.entries if e.task]` **跳过 rest**, 只看任务条目的段序 → **放行** |

★ 于是: 前端拦住了, 但**若前端没拦**（例如 `custom` 之外的情形、或前端有 bug）
  后端**不会兜底** —— 与"后端是最终防线"的设计相悖。

## 先复现（本测试当前应当**失败**）
"""
import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

import pytest

R = Path(r'D:\OAS-dev\OnmyojiAutoScript')
if str(R) not in sys.path:
    sys.path.insert(0, str(R))
logging.disable(logging.CRITICAL)

CFG = '恋鸟树'
P = R / 'config' / f'{CFG}.json'


@pytest.fixture()
def cfg():
    os.chdir(R)
    import server  # noqa: F401
    from module.server.main_manager import mm
    c = mm.config_cache(CFG)
    before = c.priority_mode()
    yield c
    try:
        c.model.script.optimization.priority_mode = before
        c.model.script.optimization.priority_mode_explicit = True
    except Exception:
        pass


def _blocked(cfg, entries):
    from module.config.run_list import RunList
    from module.server import schema_router as SR
    rl = RunList.from_list(entries)
    return SR._check_drag_allowed(cfg, rl)


T = {'kind': 'task', 'task': 'MetaDemon'}      # timed
F = {'kind': 'task', 'task': 'Orochi'}         # fixed
REST = {'kind': 'rest', 'minutes': 10}


class TestRestPositionIsChecked:
    """★ `rest` 被拖到**任务前面/中间** -> 后端应当**拦**。"""

    def test_rest_before_tasks_blocked(self, cfg):
        cfg.model.script.optimization.priority_mode = 'timed_first'
        blocked, reason = _blocked(cfg, [REST, T, F])
        assert blocked, (
            f'★★ 后端放行了「rest 在任务之前」—— 但 rest 该恒排最后\n'
            f'   （前端会拦, 后端不兜底 -> "用户拖了没效果"）\n'
            f'   实际: blocked={blocked} reason={reason!r}')

    def test_rest_between_tasks_blocked(self, cfg):
        cfg.model.script.optimization.priority_mode = 'timed_first'
        blocked, reason = _blocked(cfg, [T, REST, F])
        assert blocked, (
            f'★★ 后端放行了「rest 夹在两个任务之间」\n'
            f'   实际: blocked={blocked} reason={reason!r}')

    def test_rest_at_end_allowed(self, cfg):
        """★ rest 在**最后**是合法的 —— 不能被误拦。"""
        cfg.model.script.optimization.priority_mode = 'timed_first'
        blocked, reason = _blocked(cfg, [T, F, REST])
        assert not blocked, f'rest 在最后被误拦: {reason!r}'

    def test_custom_allows_any_rest_position(self, cfg):
        """★ `custom` -> rest 位置**也由用户定**（用户裁定"全都可以拖"）。"""
        cfg.model.script.optimization.priority_mode = 'custom'
        for ents in ([REST, T, F], [T, REST, F], [T, F, REST]):
            blocked, reason = _blocked(cfg, ents)
            assert not blocked, f'custom 下 rest 被拦: {ents} -> {reason!r}'

    def test_only_rest_is_fine(self, cfg):
        cfg.model.script.optimization.priority_mode = 'timed_first'
        blocked, reason = _blocked(cfg, [REST])
        assert not blocked, reason
