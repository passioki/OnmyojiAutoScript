# -*- coding: utf-8 -*-
"""★★★ 「等待到点」必须真有依据（用户报的真 bug）★★★

## 用户原话

> "**契灵之境为什么显示等待到点**? 这个是次数任务, 不应该有
>  [还未到点]这种[拥有 window 的任务类]的属性啊"

## 实测根因（三层, 前两条都已修）

1. ★ `next_run_after(strict=True)` 对**全天窗口**（`00:00-23:59`）
   算出的是"**下一次**窗口开放" = **明天 00:00**
   （`next_opening(strict=True)` 先跳到 `next_closing` 今天 23:59,
    再找下一次开放）-> 排期把任务推到明天。
   ✅ 修在 `next_run_after`（`is_unrestricted` 特判 -> 返回 `when`）
2. ★ 坏值**已经落盘**（`RealmRaid` = 明天 00:00, `MemoryScrolls` = 明天 22:21）,
   而 `update_scheduler` 只**读** `next_run` 不重算
   -> 光修算法不够, 界面仍显示"等待到点"。
   ✅ 修在 `fix_stale_next_run_once()`（一次性, 幂等）
3. ★ **受限**窗口（如逢魔 `17:00-23:00`）的 `next_run` 落在未来是**正确**的
   -> 那些**绝不能**动（否则会把"还没到点"的任务提前放出去）。
"""
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

from _srcutil import code_of  # noqa: E402


@pytest.fixture(scope='module')
def cfg():
    os.chdir(REPO)
    import server  # noqa: F401
    from module.server.main_manager import mm
    return mm.config_cache('恋鸟树')


class TestFullDayWindowIsNotDeferred:
    """★ 全天窗口的 `next_run_after` 必须是"现在", 不是"明天"。"""

    def test_unrestricted_returns_now(self, cfg):
        now = datetime.now().replace(microsecond=0)
        for task in ('RealmRaid', 'MemoryScrolls', 'RyouToppa'):
            got = cfg.next_run_after(task, after=now, strict=True)
            delta = got - now
            assert abs(delta) <= timedelta(minutes=1), (
                f'★ {task} 是**全天窗口**（00:00-23:59）, `next_run_after` '
                f'应返回"现在", 实际 {got}（+{delta}）—— '
                f'这正是"等待到点"的成因')

    def test_restricted_window_still_deferred(self, cfg):
        """★ 受限窗口**必须**仍被推到下次开放（不能修过头）。"""
        now = datetime.now().replace(microsecond=0)
        got = cfg.next_run_after('DemonEncounter', after=now, strict=True)
        # 逢魔每天 17:00-23:00; 从"现在"起算的下次开放必定 > 现在
        assert got > now, (
            f'★ DemonEncounter 的窗口是 17:00-23:00（受限）, '
            f'下次开放必须晚于现在, 实际 {got}')

    def test_source_uses_is_unrestricted(self):
        """★ 源码必须用 `is_unrestricted` 特判（且是 **property** 不是方法）。"""
        body = code_of(REPO / 'module/config/config.py', 'def next_run_after')
        assert 'is_unrestricted' in body, (
            '★ `next_run_after` 必须有全天窗口特判')
        assert 'is_unrestricted()' not in body, (
            '★ `is_unrestricted` 是 **property（bool）**, 加 () 会 '
            '`TypeError: bool object is not callable`（我踩过）')


class TestStaleNextRunIsRepaired:
    """★ 落盘的坏 `next_run` 必须被一次性修正（否则光修算法没用）。"""

    def test_no_waiting_for_time_in_live_config(self, cfg):
        """★★ 实测: `/overview` 里**不该**再出现「等待到点」。"""
        from module.server import schema_router as SR
        rows = SR.build_overview('恋鸟树').get('tasks') or []
        bad = [(r['command'], r.get('period'))
               for r in rows if r.get('reason') == '等待到点']
        assert not bad, (
            '★ 仍有任务显示「等待到点」: ' + str(bad) + '\n'
            '  （它们的窗口此刻应当是开放的, 却因为坏 next_run 被归入 waiting）')

    def test_reason_is_empty_for_open_full_day_tasks(self, cfg):
        """★ 全天窗口 + 窗口开着 -> `reason` 该是空的（= 可跑）。"""
        from module.server import schema_router as SR
        rows = {r['command']: r for r in
                (SR.build_overview('恋鸟树').get('tasks') or [])}
        for task in ('RealmRaid', 'MemoryScrolls'):
            r = rows.get(task)
            if r is None:
                continue
            if r.get('enable') is not True:
                continue
            assert r.get('in_window') is True, r
            assert not r.get('reason'), (
                f'★ {task}: 全天窗口开着, reason 不该是 {r.get("reason")!r}')

    def test_repair_skips_restricted_windows(self):
        """★ 修正**不得**动受限窗口的未来 `next_run`（那是正确的）。"""
        body = code_of(REPO / 'module/config/config.py',
                       'def fix_stale_next_run_once')
        assert 'is_unrestricted' in body, (
            '★ 修正只该处理"全是全天窗口"的任务')
        assert 'continue' in body, '★ 必须有跳过分支（受限窗口不动）'

    def test_repair_is_idempotent(self, cfg):
        """★ 幂等: 第二次跑无改动。"""
        assert cfg.fix_stale_next_run_once() is False, (
            '★ 修正应当幂等（修完 next_run 不再是未来 -> 无改动）')

    def test_hooked_in_init(self):
        """★ 必须挂在 `Config.__init__` 上（用户不用手动触发）。

        ⚠ 不能用 `code_of(..., 'def __init__')` —— `config.py` 里有**多个**
          `__init__`（`Function.__init__` 在前）-> 会抓到错的那个。
          ★ 改用原始源码断言"迁移调用"的**相邻顺序**。
        """
        raw = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')
        assert 'self.fix_stale_next_run_once()' in raw, (
            '★ 修正必须在配置加载时自动跑 —— 否则老配置永远显示"等待到点"')
        i_period = raw.index('self.migrate_task_period_once()')
        i_fix = raw.index('self.fix_stale_next_run_once()')
        assert i_period < i_fix, (
            '★ `fix_stale_next_run_once` 应跟在其它一次性迁移之后')
