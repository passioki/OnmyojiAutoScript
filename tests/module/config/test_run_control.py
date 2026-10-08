# -*- coding: utf-8 -*-
"""运行控制（暂停 / 休息 / 延后）的测试。

## 背景

此前 OAS **没有暂停机制**。唯一的"停止"是硬杀进程:
`script_process.py`: `terminate()` -> 0.7 秒后 `kill()`, 会卡在半途
(战斗中 / 组队房间中)。`script.py` 里 `stop_event` 的检查**被注释掉了**,
且该变量从未赋值 —— 原作者想做但没做完。

## 三个控件(用户确认的语义, docs/architecture.md §6.1)

| 控件 | 语义 |
|---|---|
| **⏸ 暂停调度** | **跑完当前这场战斗(到安全点)**后不再开新任务 |
| **⏭ 本轮跑完再停** | 本任务本轮跑完(打满目标次数)再停 |
| **▶ 继续调度** | 恢复 |

**不提供「立即停」** —— 会卡在半途, 不安全。

## 休息 vs 延后(两个概念, 不是"作用范围"参数)

| 条目 | 影响 |
|---|---|
| **休息** | 全局 —— 定时任务也停 |
| **延后** | 只推迟**列表**推进, 定时任务照常 |

★ 设计过程中曾错误地引入"休息作用范围(SELF/WHOLE_LIST)"参数 ——
那是把"条目"和"动作"混在一起。
"""
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture()
def rc(monkeypatch, tmp_path):
    """
    每个用例用**独立的状态文件**, 互不污染。

    通过 `OAS_TASK_STATE_FILE` 环境变量切换(与 task_state 的既有机制一致)。
    """
    state = tmp_path / '.task_state.json'
    monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state))
    # task_state 在导入时读环境变量, 需要重新加载模块
    import importlib
    from module.config import task_state, run_control
    importlib.reload(task_state)
    importlib.reload(run_control)
    yield run_control
    # 清理: 恢复默认(其它测试用真状态文件时不被影响)
    monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)
    importlib.reload(task_state)
    importlib.reload(run_control)


class TestPause:
    def test_default_running(self, rc):
        assert rc.is_paused() is False
        assert rc.pause_mode() == rc.PAUSE_NONE
        st = rc.state()
        assert st['paused'] is False
        assert st['can_run'] is True

    def test_request_battle_pause(self, rc):
        st = rc.request_pause(rc.PAUSE_BATTLE)
        assert st['paused'] is True
        assert st['pause_mode'] == 'battle'
        assert st['can_run'] is False
        assert rc.is_paused() is True

    def test_request_round_pause(self, rc):
        st = rc.request_pause(rc.PAUSE_ROUND)
        assert st['pause_mode'] == 'round'
        assert '本轮' in st['pause_mode_label']

    def test_reason_recorded(self, rc):
        st = rc.request_pause(rc.PAUSE_BATTLE, reason='手动测试')
        assert st['pause_reason'] == '手动测试'

    def test_resume_clears(self, rc):
        rc.request_pause(rc.PAUSE_BATTLE)
        st = rc.resume()
        assert st['paused'] is False
        assert st['can_run'] is True
        assert rc.pause_mode() == rc.PAUSE_NONE
        assert rc.is_paused() is False

    def test_resume_when_not_paused_is_safe(self, rc):
        st = rc.resume()
        assert st['paused'] is False

    def test_invalid_mode_rejected(self, rc):
        with pytest.raises(ValueError):
            rc.request_pause('immediate')
        with pytest.raises(ValueError):
            rc.request_pause('')

    def test_pause_at_recorded(self, rc):
        st = rc.request_pause(rc.PAUSE_BATTLE)
        assert st['pause_at']
        datetime.fromisoformat(st['pause_at'])


class TestRest:
    def test_not_resting_by_default(self, rc):
        assert rc.in_rest() is False
        assert rc.rest_until() is None
        assert rc.state()['rest_until'] is None

    def test_rest_blocks_dispatch(self, rc):
        st = rc.rest(minutes=30)
        assert st['rest_until'] is not None
        # 休息期间不能派发任务 —— 即使是定时任务
        assert st['can_run'] is False
        assert rc.in_rest() is True

    def test_rest_remaining_positive(self, rc):
        st = rc.rest(minutes=10)
        assert st['rest_remaining'] > 9 * 60
        assert st['rest_remaining'] <= 10 * 60

    def test_cancel_rest(self, rc):
        rc.rest(minutes=30)
        st = rc.rest(minutes=0)
        assert st['rest_until'] is None
        assert rc.in_rest() is False

    def test_expired_rest_is_not_resting(self, rc):
        """已过期的休息不应再阻挡调度(用过去时刻模拟)。"""
        past = datetime.now() - timedelta(minutes=5)
        rc.rest(until=past)
        assert rc.in_rest() is False
        assert rc.state()['can_run'] is True

    def test_rest_until_explicit(self, rc):
        future = datetime.now() + timedelta(hours=2)
        st = rc.rest(until=future)
        assert st['rest_until']
        assert rc.in_rest() is True


class TestDelay:
    def test_not_delayed_by_default(self, rc):
        assert rc.list_delayed() is False
        assert rc.list_resume_at() is None

    def test_delay_does_not_block_dispatch(self, rc):
        """
        关键区别: **延后只推迟列表推进, 定时任务照常** ——
        因此 `can_run` 仍为 True(与"休息"相反)。
        """
        st = rc.delay(minutes=20)
        assert st['delayed'] is True
        assert rc.list_delayed() is True
        assert st['can_run'] is True, '延后不应阻止定时任务派发'

    def test_cancel_delay(self, rc):
        rc.delay(minutes=20)
        st = rc.delay(minutes=0)
        assert st['delayed'] is False
        assert rc.list_delayed() is False

    def test_expired_delay(self, rc):
        past = datetime.now() - timedelta(minutes=1)
        rc.delay(until=past)
        assert rc.list_delayed() is False

    def test_rest_and_delay_independent(self, rc):
        """两者互不影响 —— 这是"两个条目类型"设计的直接体现。"""
        rc.rest(minutes=10)
        rc.delay(minutes=30)
        st = rc.state()
        assert st['rest_until'] is not None
        assert st['list_resume_at'] is not None
        # 取消休息, 延后仍在
        st = rc.rest(minutes=0)
        assert st['rest_until'] is None
        assert st['delayed'] is True


class TestWaitSeconds:
    def test_zero_when_running(self, rc):
        assert rc.wait_seconds() == 0

    def test_short_poll_when_paused(self, rc):
        rc.request_pause(rc.PAUSE_BATTLE)
        w = rc.wait_seconds()
        assert 0 < w <= 60, '暂停时应短轮询(用户可能随时点继续)'

    def test_bounded_during_rest(self, rc):
        rc.rest(minutes=60)
        w = rc.wait_seconds()
        assert 0 < w <= 300, '休息期间轮询应有上界'


class TestRobustness:
    def test_broken_state_file_does_not_crash(self, monkeypatch, tmp_path):
        """状态文件损坏时应"照常运行", 不能把任务卡死。"""
        bad = tmp_path / '.task_state.json'
        bad.write_text('{ this is not json', encoding='utf-8')
        monkeypatch.setenv('OAS_TASK_STATE_FILE', str(bad))
        import importlib
        from module.config import task_state, run_control
        importlib.reload(task_state)
        importlib.reload(run_control)
        try:
            # 不应抛异常; 且应可运行(不能因为读不到状态就永久暂停)
            assert run_control.state()['can_run'] is True
        finally:
            monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)
            importlib.reload(task_state)
            importlib.reload(run_control)

    def test_clear_all(self, rc):
        rc.request_pause(rc.PAUSE_BATTLE)
        rc.rest(minutes=10)
        rc.delay(minutes=10)
        rc.clear_all()
        st = rc.state()
        assert st['paused'] is False
        assert st['rest_until'] is None
        assert st['delayed'] is False


class TestBaseTaskIntegration:
    """`BaseTask` 侧的两个方法必须存在且默认安全。"""

    def test_methods_exist(self):
        from tasks.base_task import BaseTask
        assert hasattr(BaseTask, 'requested_pause')
        assert hasattr(BaseTask, 'should_stop_battle_loop')

    def test_should_stop_returns_bool_on_clean_state(self, monkeypatch, tmp_path):
        """未暂停时 → False(不打断任何任务)。"""
        state = tmp_path / '.task_state.json'
        monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state))
        import importlib
        from module.config import task_state, run_control
        importlib.reload(task_state)
        importlib.reload(run_control)
        try:
            from tasks.base_task import BaseTask

            class Fake(BaseTask):
                def __init__(self):
                    self._pause_requested = False
                    self.current_count = 0

            assert Fake().should_stop_battle_loop() is False
        finally:
            monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)
            importlib.reload(task_state)
            importlib.reload(run_control)

    def test_pause_battle_stops_even_if_round_incomplete(self, monkeypatch, tmp_path):
        """⏸ 暂停 = 跑完这场就停 —— 即使本轮未打满。"""
        state = tmp_path / '.task_state.json'
        monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state))
        import importlib
        from module.config import task_state, run_control
        importlib.reload(task_state)
        importlib.reload(run_control)
        try:
            run_control.request_pause(run_control.PAUSE_BATTLE)
            from tasks.base_task import BaseTask

            class Fake(BaseTask):
                def __init__(self):
                    self._pause_requested = False
                    self.current_count = 1
                    self.limit_count = 10

            assert Fake().should_stop_battle_loop() is True
        finally:
            monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)
            importlib.reload(task_state)
            importlib.reload(run_control)

    def test_pause_round_continues_until_limit(self, monkeypatch, tmp_path):
        """⏭ 本轮跑完再停 —— 未打满则继续。"""
        state = tmp_path / '.task_state.json'
        monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state))
        import importlib
        from module.config import task_state, run_control
        importlib.reload(task_state)
        importlib.reload(run_control)
        try:
            run_control.request_pause(run_control.PAUSE_ROUND)
            from tasks.base_task import BaseTask

            class Fake(BaseTask):
                def __init__(self, done):
                    self._pause_requested = False
                    self.current_count = done
                    self.limit_count = 5

            assert Fake(2).should_stop_battle_loop() is False, '未打满应继续'
            assert Fake(5).should_stop_battle_loop() is True, '打满应停'
        finally:
            monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)
            importlib.reload(task_state)
            importlib.reload(run_control)
