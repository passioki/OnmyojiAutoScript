# -*- coding: utf-8 -*-
"""界面状态汇总(summarize / peers_status)的测试。

背景: 完成记忆与次数此前没有任何 HTTP 出口, 界面无法显示
"本周期是否已完成""还剩几次""对方在不在"。task_status 接口把它们暴露出来,
这里锁定其底层汇总函数的行为。
"""
import os
from datetime import datetime, timedelta

import pytest

from module.config import task_state


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_file = tmp_path / '.task_state.json'
    monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state_file))
    yield state_file
    monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)


NOW = datetime(2026, 10, 7, 12, 5)
SLOTS = '0,12'


class TestSummarize:
    def test_empty_when_nothing_recorded(self):
        s = task_state.summarize('acc1', now=NOW)
        assert s['config'] == 'acc1'
        assert s['global'] == {}
    
    def test_exposes_period_record(self):
        task_state.record_success('acc1', 'DailyTrifles', 'daily')
        s = task_state.summarize('acc1', now=NOW)
        rec = s['global']['dailytrifles']
        assert rec['period'] == 'daily'
        assert rec['period_key'], '应带上周期标识'
        assert rec['last_success'], '应带上完成时间'




    def test_corrupted_state_returns_empty(self, isolated_state):
        isolated_state.write_text('{ 坏 JSON', encoding='utf-8')
        s = task_state.summarize('acc1', now=NOW)
        assert s['global'] == {}


    def test_excludes_self(self):
        task_state.write_heartbeat('me', {'at': NOW.isoformat()})
        task_state.write_heartbeat('other', {'at': NOW.isoformat()})
        names = [p['config'] for p in task_state.peers_status('me', now=NOW)]
        assert 'me' not in names
        assert 'other' in names

    def test_online_flag(self):
        task_state.write_heartbeat('other', {'at': NOW.isoformat()})
        p = task_state.peers_status('me', now=NOW)
        rec = [x for x in p if x['config'] == 'other'][0]
        assert rec['online'] is True

    def test_offline_when_heartbeat_stale(self):
        task_state.write_heartbeat('other', {'at': NOW.isoformat()})
        later = NOW + timedelta(seconds=task_state.DEFAULT_HEARTBEAT_TIMEOUT + 5)
        rec = [x for x in task_state.peers_status('me', now=later)
               if x['config'] == 'other'][0]
        assert rec['online'] is False


    def test_charges_omitted_without_task(self):
        task_state.write_heartbeat('other', {'at': NOW.isoformat()})
        rec = [x for x in task_state.peers_status('me', now=NOW)
               if x['config'] == 'other'][0]
    