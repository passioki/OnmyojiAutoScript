# -*- coding: utf-8 -*-
"""★★★ 「暂停调度」真正生效 —— 守卫测试 ★★★

## 用户报告与确认

> "目前的**暂停调度并没有实现**"
> 确认: **1a**（多数任务没检查点）+ 粒度 **2i**（跑完本场战斗就停）
> 覆盖方案: **A**（框架级兜底, 用户确认）

## 实测出的根因（本文件钉住它）

`run_general_battle()` 里本来**有**安全点, 它 `return True` 并置位
`self._pause_requested`。**但**:

1. ★ **50 处调用点丢弃了返回值**（写成 `self.run_general_battle(...)`,
   没有 `=`/`if`/`return`）-> 信号被**无声忽略**
2. ★ 只有 **15/54** 个任务调用了 `should_stop_battle_loop()`
3. ★ `_pause_requested` **全项目只被写、从不被读**

**后果**: 点「暂停调度」后大多数任务**完全不响应**, 一直跑到自己结束。

## 修法（两条腿, 本文件都守护）

* ★ **任务级安全点**: 把"命中"从 `return True`（靠调用方读）改成
  **抛 `TaskPaused`**（必然中断）。
  * `BaseTask.raise_if_paused()` —— 任务侧统一入口
  * `run_general_battle()` 也抛（兜底那 50 处丢弃返回值的调用点）
  * `script.py` 的 `run()` 接住（那里任务收尾的 `finally` 照常执行）
  * `TaskPaused` 继承 **`BaseException`** —— 任务里的 `except Exception` 吞不掉
* ★ **框架级兜底（A 方案）**: 在 `screenshot()` 上加检查 ——
  一处改动覆盖 **54/54**（每个任务循环都会截图）。
  三道闸: 模式闸（只 battle）/ 排除闸（组队类）/ 临界区闸。
"""
import os
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
            '★ `BaseTask.raise_if_paused()` 是任务侧的中断入口')

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
        src = code_only(REPO / 'script.py')
        i = src.index('except TaskPaused')
        seg = src[i:i + 1500]
        for bad in ('exit(', 'sys.exit', 'os._exit', 'raise SystemExit'):
            assert bad not in seg, (
                f'★ `except TaskPaused` 里不该 `{bad}` —— 那会让「继续」失效')


class TestGeneralBattleIsCovered:
    """★ 走 `GeneralBattle` 的 33 个任务由**共享层**覆盖。"""

    @staticmethod
    def _tasks():
        d = REPO / 'tasks'
        return sorted([x for x in d.iterdir()
                       if x.is_dir() and (x / 'script_task.py').exists()])

    def test_general_battle_raises(self):
        body = code_of(REPO / 'tasks/Component/GeneralBattle/general_battle.py',
                       'def run_general_battle')
        assert 'raise_if_paused' in body, (
            '★ `run_general_battle()` 的安全点必须**抛异常**而不是 '
            '`return True` —— 实测 50 处调用点丢弃了返回值')

    def test_no_task_calls_should_stop_battle_loop_directly(self):
        """★ 任务侧统一用 `raise_if_paused()`, 不再自己 `if ...: break`。"""
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
        gb = code_of(REPO / 'tasks/Component/GeneralBattle/general_battle.py',
                     'def run_general_battle')
        assert 'raise_if_paused' in gb
        users = []
        for t in self._tasks():
            blob = ''.join(f.read_text(encoding='utf-8', errors='replace')
                           for f in t.rglob('*.py'))
            if 'GeneralBattle' in blob:
                users.append(t.name)
        assert len(users) >= 20, (
            '★ 走 GeneralBattle 的任务数异常（' + str(len(users)) + '）'
            ' —— 覆盖面统计可能失效了')


class TestFrameworkLevelCheckpoint:
    """★★★ A 方案: 框架级兜底（在 `screenshot()` 上检查）★★★

    ## 为什么需要它（用户确认 1a + 选 A）

    实测: 「暂停调度」只对 **33/54** 个任务有效 ——
    剩下 21 个**不使用 `GeneralBattle`** 的任务各自有 1~16 个 `while`,
    ★ 无法机械判定哪个是"工作循环"（我试过"插第一个 while", 抽查发现
      插进了"进界面"的等待循环 -> 会在刚要进门时中断, 收尾跑不到）。

    ★ A 方案: 在 `screenshot()` 这个**公共入口**上加检查 ——
      一处改, **54/54** 覆盖（每个任务循环都会截图）。

    ## 代价与三道闸

    ⚠ `screenshot()` 在**任何**循环里都会被调 -> 比"战斗结束"**更早**中断,
      可能停在界面操作中途。所以必须有三道闸:

    1. **模式闸**: 只在 `PAUSE_BATTLE` 生效。
       ★ `PAUSE_ROUND`（"本轮打满再停"）交给任务自己判断
         （框架层没有 `limit_count`/`current_count` 的知识,
          硬判会**破坏"跑完本轮"的语义**）。
    2. **排除闸**: `PAUSE_FRAMEWORK_EXEMPT` —— 组队类任务
       （中途停下会让**真人队友干等**, 不可回滚）。
    3. **临界区闸**: `pause_blocked()` / `pause_protected()` ——
       任务可临时保护"不可回滚"的片段。
    """

    @staticmethod
    def _fake(task_name='SixRealms'):
        from tasks.base_task import BaseTask

        class _Fake(BaseTask):
            def __init__(self):
                self._pause_block_depth = 0
                self._name = task_name

            def get_task_name(self):
                return self._name

        return _Fake()

    @pytest.fixture(autouse=True)
    def _clean_pause(self):
        from module.config import run_control
        run_control.clear_all()
        yield
        run_control.clear_all()

    def test_not_paused_does_nothing(self):
        self._fake()._pause_check_at_screenshot()      # 不该抛

    def test_paused_battle_raises(self):
        from module.config import run_control
        from module.exception import TaskPaused
        run_control.request_pause(mode='battle')
        with pytest.raises(TaskPaused):
            self._fake()._pause_check_at_screenshot()

    def test_round_mode_is_left_to_the_task(self):
        """★ `PAUSE_ROUND` 框架层**不许**拦 —— 那会破坏"跑完本轮"语义。"""
        from module.config import run_control
        run_control.request_pause(mode='round')
        self._fake()._pause_check_at_screenshot()      # 不该抛

    def test_exempt_tasks_skip_framework_check(self):
        """★ 组队类任务（会让队友干等）必须跳过框架级检查。"""
        from module.config import run_control
        from tasks.base_task import BaseTask
        run_control.request_pause(mode='battle')
        assert BaseTask.PAUSE_FRAMEWORK_EXEMPT, (
            '★ 排除名单不能为空 —— 组队类任务会被中途打断')
        for name in BaseTask.PAUSE_FRAMEWORK_EXEMPT:
            self._fake(name)._pause_check_at_screenshot()   # 不该抛

    def test_critical_section_blocks_then_restores(self):
        """★ 临界区护栏: 区内不拦, 出区恢复拦截。"""
        from module.config import run_control
        from module.exception import TaskPaused
        run_control.request_pause(mode='battle')
        f = self._fake()
        with f.pause_protected():
            assert f.pause_blocked() is True
            f._pause_check_at_screenshot()      # 区内不抛
        assert f.pause_blocked() is False
        with pytest.raises(TaskPaused):
            f._pause_check_at_screenshot()

    def test_critical_section_is_nestable(self):
        from module.config import run_control
        from module.exception import TaskPaused
        run_control.request_pause(mode='battle')
        f = self._fake()
        with f.pause_protected():
            with f.pause_protected():
                f._pause_check_at_screenshot()
            f._pause_check_at_screenshot()      # 内层退出后仍在保护中
        with pytest.raises(TaskPaused):
            f._pause_check_at_screenshot()

    def test_critical_section_restores_on_exception(self):
        """★ 出异常也必须减回去（否则永久失去暂停能力）。"""
        f = self._fake()
        with pytest.raises(ValueError):
            with f.pause_protected():
                raise ValueError('boom')
        assert f.pause_blocked() is False, (
            '★ 临界区计数没回退 —— 该任务将**永久**无法被暂停')

    def test_hooked_into_screenshot(self):
        """★ 必须真的挂在 `screenshot()` 上（否则 A 方案等于没做）。"""
        body = code_of(REPO / 'tasks/base_task.py', 'def screenshot')
        assert '_pause_check_at_screenshot' in body, (
            '★ `screenshot()` 里必须调用暂停检查 —— 那是 A 方案的唯一挂点')

    def test_failure_is_swallowed(self):
        """★ 失败安全: 暂停检查出问题**绝不能**把任务卡死。"""
        body = code_of(REPO / 'tasks/base_task.py',
                       'def _pause_check_at_screenshot')
        assert 'except TaskPaused' in body and 'raise' in body, (
            '★ `TaskPaused` 必须原样抛出（不能被兜底吞掉）')
        assert 'except Exception' in body, (
            '★ 其它异常必须被吞掉并记日志（状态读取失败不该卡死任务）')


class TestEveryTaskHasAPausePath:
    """★ 覆盖率守卫: **没有任务掉队**。"""

    @staticmethod
    def _tasks():
        d = REPO / 'tasks'
        return sorted([x for x in d.iterdir()
                       if x.is_dir() and (x / 'script_task.py').exists()])

    def test_all_tasks_have_a_pause_path(self):
        """每个任务至少有**一条**暂停通路:

        * 走 `GeneralBattle`（共享层抛异常）, **或**
        * 自己调 `raise_if_paused()`, **或**
        * ★ 靠**框架级** `screenshot()` 检查（除排除名单外的全体）

        ★ 前两条覆盖 33 个; 第三条把剩下的（除组队排除名单）全部兜住。
        """
        from tasks.base_task import BaseTask
        exempt = set(BaseTask.PAUSE_FRAMEWORK_EXEMPT)
        uncovered = []
        for t in self._tasks():
            blob = ''.join(f.read_text(encoding='utf-8', errors='replace')
                           for f in t.rglob('*.py'))
            covered = ('GeneralBattle' in blob
                       or 'raise_if_paused' in blob
                       or t.name not in exempt)
            if not covered:
                uncovered.append(t.name)
        assert not uncovered, (
            '★ 这些任务既无战斗安全点、也没调 raise_if_paused、'
            '还在排除名单里 -> 只能等它整轮跑完: ' + str(uncovered[:8]))

    def test_exempt_list_is_documented(self):
        """★ 排除名单必须有**理由注释**（不能是随手加的）。

        ⚠ 必须读**原始源码** —— `code_of()` 会剥掉注释, 而理由正是注释。
        """
        raw = (REPO / 'tasks' / 'base_task.py').read_text(encoding='utf-8')
        i = raw.index('PAUSE_FRAMEWORK_EXEMPT')
        block = raw[i:i + 900]
        for name in ('MysteryShop', 'FindJade', 'Hyakkiyakou'):
            assert name in block, (
                f'★ 排除名单应包含 {name}（实测有真实 invite_friend 调用）')
        assert 'invite' in block.lower(), (
            '★ 排除名单必须写明理由（"会邀请真人队友"）, 否则后来人不敢动')
