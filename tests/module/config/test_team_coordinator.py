# -*- coding: utf-8 -*-
"""跨账号组队协同(team_coordinator)的测试。

设计要点
--------
各账号的"剩余次数"本来就按配置名分桶存在同一个状态文件里, 因此协同不需要另建
状态文件 —— 只要再加一个心跳就能判断"对方在不在线"和"对方还剩几次"。

决策规则:
    对方离线     -> START(没人可等, 按自己能力做)
    对方有次数   -> START(双方都能打, 此刻一起做最合适)
    对方次数为 0 -> DEFER(等对方恢复; 等超过一个周期则强行 START, 防死锁)
    读不到/异常  -> START(绝不因为协同把任务卡住)
"""
import json
from datetime import datetime, timedelta

import pytest

from module.config import task_state, team_coordinator as TC


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_file = tmp_path / '.task_state.json'
    monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state_file))
    yield state_file
    monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)


SLOTS = '0,12'
NOW = datetime(2026, 10, 7, 12, 5)
TASK = 'GoldYoukai'


def online(config, at=NOW):
    task_state.write_heartbeat(config, {'at': at.isoformat()})


def deplete(config, at=NOW, n=2, slots=SLOTS):
    for _ in range(n):
        task_state.consume_charge(config, TASK, 2, slots, at)


# ---------------------------------------------------------------------------
# 心跳
# ---------------------------------------------------------------------------
class TestHeartbeat:
    def test_offline_without_heartbeat(self):
        assert task_state.is_online('B', now=NOW) is False

    def test_online_after_write(self):
        online('B')
        assert task_state.is_online('B', now=NOW) is True

    def test_timeout(self):
        online('B', at=NOW)
        later = NOW + timedelta(seconds=task_state.DEFAULT_HEARTBEAT_TIMEOUT + 1)
        assert task_state.is_online('B', now=later) is False

    def test_custom_timeout(self):
        online('B', at=NOW)
        assert task_state.is_online('B', timeout=1,
                                    now=NOW + timedelta(seconds=5)) is False

    def test_heartbeat_does_not_pollute_config_buckets(self):
        """心跳要单独存放, 不要出现在配置分桶里(否则会被当成一个账号)。"""
        online('B')
        data = task_state._read_all()
        assert task_state.HEARTBEAT_KEY in data
        assert 'b' not in {k.lower() for k in data if k != task_state.HEARTBEAT_KEY}

    def test_heartbeat_corrupted_returns_offline(self):
        online('B')
        data = task_state._read_all()
        data[task_state.HEARTBEAT_KEY]['B']['at'] = 'not-a-time'
        task_state._write_all(data)
        assert task_state.is_online('B', now=NOW) is False


# ---------------------------------------------------------------------------
# 读取对方次数
# ---------------------------------------------------------------------------
class TestPeerCharges:
    def test_full_when_no_record(self):
        assert task_state.peer_charges('B', TASK, 2, SLOTS, NOW) == 2

    def test_reflects_consumption(self):
        deplete('B', n=1)
        assert task_state.peer_charges('B', TASK, 2, SLOTS, NOW) == 1

    def test_zero_after_depletion(self):
        deplete('B', n=2)
        assert task_state.peer_charges('B', TASK, 2, SLOTS, NOW) == 0

    def test_recovers_at_next_slot(self):
        """
        在 12:05 用尽后:
          次日 00:05 -> 跨过 10/7 12:00 与 10/8 00:00 两个槽位中的 1 个 -> 1 次
          次日 12:05 -> 再跨 1 个 -> 2 次(封顶)
        """
        deplete('B', n=2)
        assert task_state.peer_charges(
            'B', TASK, 2, SLOTS, datetime(2026, 10, 8, 0, 5)) == 1
        assert task_state.peer_charges(
            'B', TASK, 2, SLOTS, datetime(2026, 10, 8, 12, 5)) == 2

    def test_infers_slots_from_record(self):
        """不传 slots 时应能从记录里推断。"""
        deplete('B', n=2)
        assert task_state.peer_charges('B', TASK, 2, None, NOW) == 0


# ---------------------------------------------------------------------------
# 决策
# ---------------------------------------------------------------------------
class TestDecide:
    def test_start_when_peer_offline(self):
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert d.action == TC.START
        assert '不在线' in d.reason

    def test_start_when_both_have_charges(self):
        online('B')
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert d.action == TC.START
        assert d.peer == 'B'

    def test_defer_when_peer_depleted(self):
        online('B')
        deplete('B')
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert d.action == TC.DEFER
        assert d.wait_seconds > 0
        assert d.peer == 'B'

    def test_defer_wait_points_to_next_slot(self):
        online('B')
        deplete('B')
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        # 12:05 的下一个刷新点是 12:00? 不是 —— 是当天 12:00 已过, 次日 00:00
        # 实际上 slots=(0,12), 12:05 之后最近的是次日 00:00
        expect = int((datetime(2026, 10, 8, 0, 0) - NOW).total_seconds())
        assert abs(d.wait_seconds - expect) <= 1

    def test_start_when_peer_recovers(self):
        online('B')
        deplete('B')
        later = datetime(2026, 10, 8, 0, 5)
        online('B', at=later)
        d = TC.decide(TASK, 'A', peer='B', now=later)
        assert d.action == TC.START

    def test_start_when_no_peer(self):
        """peer 指定为自己 -> 没有可协同对象 -> START。"""
        d = TC.decide(TASK, 'A', peer='A', now=NOW)
        assert d.action == TC.START

    def test_result_is_loggable(self):
        online('B')
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert 'START' in str(d)


class TestDeadlockGuard:
    """
    防死锁: 若两个账号互相认为对方没次数, 最多互相等一个刷新周期就会各自开始。
    这是不做这条保护时最容易踩的坑。
    """

    def test_defers_first_time(self):
        online('B')
        deplete('B')
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert d.action == TC.DEFER

    def test_starts_after_waiting_one_period(self):
        online('B')
        deplete('B')
        # 模拟 A 已经等了很久(超过一个周期 12h)
        task_state.write_heartbeat('A', {
            'waiting': {TASK.lower(): '2026-10-06T00:00:00'},
            'at': NOW.isoformat()})
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert d.action == TC.START
        assert '超过一个刷新周期' in d.reason

    def test_wait_marker_cleared_after_start(self):
        online('B')
        deplete('B')
        task_state.write_heartbeat('A', {
            'waiting': {TASK.lower(): '2026-10-06T00:00:00'},
            'at': NOW.isoformat()})
        TC.decide(TASK, 'A', peer='B', now=NOW)
        waiting = (task_state.read_heartbeat('A') or {}).get('waiting') or {}
        assert TASK.lower() not in waiting

    def test_wait_marker_kept_while_deferring(self):
        online('B')
        deplete('B')
        TC.decide(TASK, 'A', peer='B', now=NOW)
        waiting = (task_state.read_heartbeat('A') or {}).get('waiting') or {}
        assert TASK.lower() in waiting


class TestDegradation:
    """任何异常都必须退化为 START, 绝不能因为协同把任务卡住。"""

    def test_corrupted_state_starts(self, isolated_state):
        isolated_state.write_text('{ 坏 JSON', encoding='utf-8')
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert d.action == TC.START

    def test_non_dict_state_starts(self, isolated_state):
        isolated_state.write_text('[1,2,3]', encoding='utf-8')
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert d.action == TC.START

    def test_peer_charges_exception_starts(self, monkeypatch):
        online('B')

        def boom(*a, **kw):
            raise RuntimeError('boom')

        monkeypatch.setattr(task_state, 'peer_charges', boom)
        d = TC.decide(TASK, 'A', peer='B', now=NOW)
        assert d.action == TC.START


class TestConfigDiscovery:
    def test_discover_includes_state_buckets(self):
        online('B')
        task_state.consume_charge('C', TASK, 2, SLOTS, NOW)
        names = task_state.discover_configs()
        assert 'B' in names and 'C' in names

    def test_heartbeat_key_not_treated_as_config(self):
        online('B')
        names = task_state.discover_configs()
        assert task_state.HEARTBEAT_KEY not in names

    def test_discover_ignores_template(self, tmp_path):
        (tmp_path / 'template.json').write_text('{}', encoding='utf-8')
        (tmp_path / 'acc1.json').write_text('{}', encoding='utf-8')
        names = task_state.discover_configs(config_dir=str(tmp_path))
        assert 'acc1' in names
        assert 'template' not in names
