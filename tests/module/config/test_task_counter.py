# -*- coding: utf-8 -*-
"""战斗计数持久化(task_state.get_count/add_count/reset_count)的测试。

背景(线上反馈 2026-10-08)
------------------------
"中断后重启任务, count 计数就重置了, 记忆好像没有生效"。

`BaseTask.current_count` 原本只存在内存里(而且每个任务还在 run() 开头把它重置为 0),
于是进程重启 / 任务被中断 / 崩溃后 restart 都会让它归零 ——
"我今天要打 N 次"这类固定任务会从头再打, 永远打不满 N。

这里把它落到与"完成记忆/次数"同一个状态文件, 并按周期自动清零。
"""
import json
from datetime import datetime, time

import pytest

from module.config import task_state


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_file = tmp_path / '.task_state.json'
    monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state_file))
    yield state_file
    monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)


NOW = datetime(2026, 10, 8, 12, 0)
TASK = 'FallenSun'


class TestBasicCount:
    def test_absent_returns_zero(self):
        assert task_state.get_count('acc', TASK, period='daily', now=NOW) == 0

    def test_add_and_get(self):
        assert task_state.add_count('acc', TASK, 1, period='daily', now=NOW) == 1
        assert task_state.add_count('acc', TASK, 1, period='daily', now=NOW) == 2
        assert task_state.get_count('acc', TASK, period='daily', now=NOW) == 2

    def test_add_multiple(self):
        assert task_state.add_count('acc', TASK, 5, period='daily', now=NOW) == 5

    def test_negative_delta_does_not_go_below_zero(self):
        """负数增量会被夹到 0, 不允许在状态文件里留下脏值。"""
        task_state.add_count('acc', TASK, 3, period='daily', now=NOW)
        assert task_state.add_count('acc', TASK, -10, period='daily', now=NOW) == 0
        assert task_state.get_count('acc', TASK, period='daily', now=NOW) == 0

    def test_per_account_isolation(self):
        task_state.add_count('a', TASK, 1, period='daily', now=NOW)
        task_state.add_count('b', TASK, 7, period='daily', now=NOW)
        assert task_state.get_count('a', TASK, period='daily', now=NOW) == 1
        assert task_state.get_count('b', TASK, period='daily', now=NOW) == 7

    def test_per_task_isolation(self):
        task_state.add_count('acc', 'FallenSun', 3, period='daily', now=NOW)
        task_state.add_count('acc', 'Orochi', 9, period='daily', now=NOW)
        assert task_state.get_count('acc', 'FallenSun', period='daily', now=NOW) == 3
        assert task_state.get_count('acc', 'Orochi', period='daily', now=NOW) == 9


class TestPeriodReset:
    def test_resets_on_new_day(self):
        """daily 周期: 跨过 0 点(默认重置点)后计数归零。"""
        task_state.add_count('acc', TASK, 4, period='daily', now=NOW)
        next_day = datetime(2026, 10, 9, 0, 30)
        assert task_state.get_count('acc', TASK, period='daily', now=next_day) == 0

    def test_same_day_keeps(self):
        task_state.add_count('acc', TASK, 4, period='daily', now=NOW)
        later = datetime(2026, 10, 8, 23, 30)
        assert task_state.get_count('acc', TASK, period='daily', now=later) == 4

    def test_respects_custom_reset_at(self):
        """reset_at=06:00 时, 05:00 仍属前一天, 07:00 才算新周期。"""
        reset = time(6, 0)
        task_state.add_count('acc', TASK, 4, period='daily',
                             reset_at=reset, now=NOW)
        assert task_state.get_count('acc', TASK, period='daily',
                                    reset_at=reset,
                                    now=datetime(2026, 10, 9, 5, 0)) == 4
        assert task_state.get_count('acc', TASK, period='daily',
                                    reset_at=reset,
                                    now=datetime(2026, 10, 9, 7, 0)) == 0

    def test_add_after_reset_starts_from_zero(self):
        task_state.add_count('acc', TASK, 4, period='daily', now=NOW)
        next_day = datetime(2026, 10, 9, 1, 0)
        assert task_state.add_count('acc', TASK, 1, period='daily',
                                    now=next_day) == 1

    def test_none_period_never_resets(self):
        """period='none' 表示不按周期清零(只累计)。"""
        task_state.add_count('acc', TASK, 4, period='none', now=NOW)
        far = datetime(2027, 1, 1, 0, 0)
        assert task_state.get_count('acc', TASK, period='none', now=far) == 4


class TestResetCount:
    def test_reset_clears(self):
        task_state.add_count('acc', TASK, 5, period='daily', now=NOW)
        task_state.reset_count('acc', TASK)
        assert task_state.get_count('acc', TASK, period='daily', now=NOW) == 0

    def test_reset_only_named_task(self):
        task_state.add_count('acc', TASK, 5, period='daily', now=NOW)
        task_state.add_count('acc', 'Orochi', 3, period='daily', now=NOW)
        task_state.reset_count('acc', TASK)
        assert task_state.get_count('acc', 'Orochi', period='daily', now=NOW) == 3

    def test_reset_unknown_is_safe(self):
        task_state.reset_count('nobody', 'nothing')     # 不应抛异常


class TestDegradation:
    """任何异常都不应影响任务本身。"""

    def test_corrupted_state_returns_zero(self, isolated_state):
        isolated_state.write_text('{ 坏 JSON', encoding='utf-8')
        assert task_state.get_count('acc', TASK, period='daily', now=NOW) == 0

    def test_corrupted_state_add_does_not_raise(self, isolated_state):
        isolated_state.write_text('[1,2,3]', encoding='utf-8')
        task_state.add_count('acc', TASK, 1, period='daily', now=NOW)   # 不抛

    def test_garbage_count_value_returns_zero(self, isolated_state):
        isolated_state.write_text(
            json.dumps({'acc': {TASK.lower(): {'count': 'abc'}}}),
            encoding='utf-8')
        assert task_state.get_count('acc', TASK, period='daily', now=NOW) == 0


class TestStateShape:
    def test_state_is_plain_json_serializable(self, isolated_state):
        task_state.add_count('acc', TASK, 2, period='daily', now=NOW)
        data = json.loads(isolated_state.read_text(encoding='utf-8'))
        item = data['acc'][TASK.lower()]
        assert item['count'] == 2
        assert 'count_key' in item
        assert 'count_updated' in item

    def test_count_coexists_with_completion_memory(self, isolated_state):
        """计数与"完成记忆"写的是同一个分桶里的不同字段, 互不覆盖。"""
        task_state.record_success('acc', TASK, period='daily')
        task_state.add_count('acc', TASK, 2, period='daily', now=NOW)
        item = json.loads(isolated_state.read_text(encoding='utf-8'))['acc'][TASK.lower()]
        assert item['count'] == 2
        assert item['last_success']           # 完成记忆仍在
        assert task_state.is_completed_in_period('acc', TASK, 'daily')
