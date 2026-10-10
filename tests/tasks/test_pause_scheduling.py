# -*- coding: utf-8 -*-
"""★★★ 「暂停调度」真正生效 —— 守卫测试 ★★★

## 用户报告与确认

> "目前的**暂停调度并没有实现**"
> 确认: **1a**（那 39 个任务没检查点）+ 粒度 **2i**（跑完本场战斗就停）

## 实测出的根因（本文件钉住它）

`run_general_battle()` 里本来**有**安全点, 它 `return True` 并置位
`self._pause_requested`。**但**:

1. ★ **50 处调用点丢弃了返回值**（写成 `self.run_general_battle(...)`,
   没有 `=`/`if`/`return`）-> 信号被**无声忽略**
2. ★ 只有 **15/54** 个任务调用了 `should_stop_battle_loop()`
3. ★ `_pause_requested` **全项目只被写、从不被读**

**后果**: 点「暂停调度」后大多数任务**完全不响应**, 一直跑到自己结束。

## 修法（本文件守护）

★ 把"安全点命中"从 **`return True`（靠调用方读）** 改成
  **抛 `TaskPaused`（必然中断）** —— 不依赖调用方是否读返回值。

* `BaseTask.raise_if_paused()` —— 唯一的中断入口
* `script.py` 的 `run()` 接住（那里任务收尾的 `finally` 照常执行）
* `TaskPaused` 继承 **`BaseException`** —— 任务里的 `except Exception`
  吞不掉它（否则又变成"点了没用"）
"""
import os
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from _srcutil import code_of, code_only  # noqa: E402


class TestTaskPausedIsUncatchableByBroadHandlers:
    def test_inherits_base_exception(self):
        """★ 必须继承 `BaseException`, 否则会被任务里的 `except Exception` 吞掉。"""
        from module.exception import TaskPaused
        assert issubclass(TaskPaused, BaseException), (
            '★ `TaskPaused` 必须继承 `BaseException` —— 任务代码里有大量 '
            '`except Exception` 兜底容错, 继承 `Exception` 会被它们吞掉, '
            '暂停就又"点了没用"了')
        assert not issubclass(TaskPaused, Exception), (
            '★ 不能同时是 `Exception` 的子类（那就又会被 `except Exception` 接住）')

    def test_broad_handler_does_not_swallow_it(self):
        """★ 实证: 一个 `except Exception` 块**接不住**它。"""
        from module.exception import TaskPaused
        caught_by_broad = False
        try:
            try:
                raise TaskPaused()
            except Exception:          # noqa: BLE001  —— 模拟任务里的兜底
                caught_by_broad = True
        except TaskPaused:
            pass
        assert caught_by_broad is False, (
            '★ `except Exception` 竟然接住了 `TaskPaused`')


class TestRaiseIfPausedIsTheOnlyGate:
    def test_method_exists_and_raises(self):
        from tasks.base_task import BaseTask
        assert hasattr(BaseTask, 'raise_if_paused'), (
            '★ `BaseTask.raise_if_paused()` 是唯一的中断入口')

    def test_body_raises_task_paused(self):
        body = code_of(REPO / 'tasks/base_task.py', 'def raise_if_paused')
        assert 'TaskPaused' in body and 'raise' in body, (
            '★ `raise_if_paused()` 必须真的 `raise TaskPaused`')

    def test_should_stop_battle_loop_is_pure(self):
        """★ `should_stop_battle_loop()` 保持**纯判据**（不抛）——
        这样它还能被单独调用/测试。"""
        body = code_of(REPO / 'tasks/base_task.py',
                       'def should_stop_battle_loop')
        assert 'raise ' not in body, (
            '★ `should_stop_battle_loop()` 不该 raise —— 抛异常统一由 '
            '`raise_if_paused()` 负责（单一入口好审计）')


class TestScriptCatchesItAtTheExecutionBoundary:
    """★ 接住的位置必须是**任务收尾之后**, 否则会卡在半途。"""

    def test_run_catches_task_paused(self):
        src = code_only(REPO / 'script.py')
        assert 'except TaskPaused' in src, (
            '★ `script.py` 的 `run()` 必须接住 `TaskPaused`')

    def test_catch_is_after_the_finally(self):
        """★ `except TaskPaused` 必须在 `_record_task_run` 的 `finally` **之外**
        （即任务收尾已跑完）。"""
        src = code_only(REPO / 'script.py')
        i_run = src.index('def run(self')
        i_catch = src.index('except TaskPaused', i_run)
        i_final = src.index('_record_task_run', i_run)
        assert i_final < i_catch, (
            '★ `except TaskPaused` 必须排在 `_record_task_run` 的 `finally` '
            '之后 —— 否则收尾逻辑会被跳过（卡半途）')

    def test_does_not_exit_the_process(self):
        """★ 暂停是**可恢复**的 —— 不许 `exit()`/`sys.exit()`。

        若在这里结束进程, 用户点「继续」就**没有进程可恢复**了。
        """
        # ⚠ 不用 `code_of(..., 'def run')` —— `script.py` 里有多个 `run`,
        #   会抓到**别的方法**（实测 ValueError: 找不到 'except TaskPaused'）。
        #   这里直接从 `except TaskPaused` 往下取一段。
        src = code_only(REPO / 'script.py')
        i = src.index('except TaskPaused')
        # 取到该 except 块结束（下一个同级 except / 或 1500 字）
        seg = src[i:i + 1500]
        for bad in ('exit(', 'sys.exit', 'os._exit', 'raise SystemExit'):
            assert bad not in seg, (
                f'★ `except TaskPaused` 里不该 `{bad}` —— 那会让「继续」失效')


class TestAllBattleTasksHaveASafePoint:
    """★ 覆盖面守卫: 战斗类任务必须能被打断。"""

    @staticmethod
    def _tasks():
        d = REPO / 'tasks'
        return sorted([x for x in d.iterdir()
                       if x.is_dir() and (x / 'script_task.py').exists()])

    def test_general_battle_raises(self):
        """★ `run_general_battle()` 必须走 `raise_if_paused()`（兜底那 50 处
        丢弃返回值的地方）。"""
        body = code_of(REPO / 'tasks/Component/GeneralBattle/general_battle.py',
                       'def run_general_battle')
        assert 'raise_if_paused' in body, (
            '★ `run_general_battle()` 的安全点必须**抛异常**而不是 '
            '`return True` —— 实测 50 处调用点丢弃了返回值')

    def test_no_task_calls_should_stop_battle_loop_directly(self):
        """★ 任务侧统一用 `raise_if_paused()`, **不再**自己 `if ...: break`

        （原来 27 处 `if self.should_stop_battle_loop(): break`, 那只在
          "调用方恰好读了返回值"时有效。）
        """
        bad = []
        for t in self._tasks():
            for f in t.rglob('*.py'):
                for i, l in enumerate(
                        f.read_text(encoding='utf-8',
                                     errors='replace').split('\n'), 1):
                    c = l.split('#')[0]
                    if 'should_stop_battle_loop' in c and 'def ' not in c:
                        bad.append(f'{f.relative_to(REPO)}:{i}')
        assert not bad, (
            '★ 任务侧不该再直接调 `should_stop_battle_loop()`（应改用 '
            '`raise_if_paused()`）: ' + str(bad[:8]))

    def test_general_battle_callers_are_covered(self):
        """★ 所有走 `GeneralBattle` 的任务都在**共享层**有安全点
        （不需要每个调用点都读返回值）。"""
        gb = code_of(REPO / 'tasks/Component/GeneralBattle/general_battle.py',
                     'def run_general_battle')
        assert 'raise_if_paused' in gb
        # 只要有任务走 GeneralBattle, 就必然被覆盖
        users = []
        for t in self._tasks():
            blob = ''.join(f.read_text(encoding='utf-8', errors='replace')
                           for f in t.rglob('*.py'))
            if 'GeneralBattle' in blob:
                users.append(t.name)
        assert len(users) >= 20, (
            '★ 走 GeneralBattle 的任务数异常（' + str(len(users)) + '）'
            ' —— 覆盖面统计可能失效了')
