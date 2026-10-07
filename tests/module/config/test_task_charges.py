# -*- coding: utf-8 -*-
"""验证充能式挑战次数机制(经验妖怪 / 金币妖怪)。

游戏事实
--------
经验妖怪 / 金币妖怪的挑战次数每 12 小时恢复 1 次, 最多累积 2 次。

改造前的实现是"一次运行内连打 2 场"(while count < 2), 这在需要组队时是错的:
两场背靠背, 队友第二次对不上; 而且"存 2 次"本意是允许攒着, 不是一口气用完。

本机制把次数纳入状态, 使任务能:
  * 没有次数时不打, 而是排到下次充能后再做;
  * 每次运行按 charge_consume 消耗次数;
  * 把存量次数分摊到一天里(12 小时 1 次), 而不是背靠背。
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


T0 = datetime(2026, 10, 7, 12, 0, 0)


class TestChargeAccounting:
    def test_initial_full(self):
        """首次使用时按满次数处理(不因为没记录就不让打)。"""
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0) == 2

    def test_consume_one(self):
        remain = task_state.consume_charge('cfg', 'T', max_charges=2,
                                           recover_hours=12, now=T0)
        assert remain == 1
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0) == 1

    def test_consume_both_then_empty(self):
        assert task_state.consume_charge('cfg', 'T', max_charges=2,
                                         recover_hours=12, now=T0) == 1
        assert task_state.consume_charge('cfg', 'T', max_charges=2,
                                         recover_hours=12, now=T0) == 0
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0) == 0

    def test_cannot_consume_when_empty(self):
        """没有次数时不得消耗(返回 0), 且状态不变。"""
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        assert task_state.consume_charge('cfg', 'T', max_charges=2,
                                         recover_hours=12, now=T0) == 0
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0) == 0

    def test_recovers_after_12_hours(self):
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        later = T0 + timedelta(hours=12, minutes=1)
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=later) == 1

    def test_recovers_full_after_24_hours(self):
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        later = T0 + timedelta(hours=24, minutes=1)
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=later) == 2

    def test_not_recovered_before_12_hours(self):
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        earlier = T0 + timedelta(hours=11, minutes=30)
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=earlier) == 0

    def test_cap_is_respected(self):
        """上限 2: 即使过了很久也不会超过 2。"""
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        much_later = T0 + timedelta(days=10)
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=much_later) == 2

    def test_partial_recovery_accumulates(self):
        """消耗 2 次、过 18 小时 -> 恢复 1 次(第 12 小时那次)。"""
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        later = T0 + timedelta(hours=18)
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=later) == 1

    def test_sequential_consumption_across_time(self):
        """
        模拟一天: 12:00 打 2 场 -> 用尽; 次日 00:01 恢复 1 次 -> 可再打 1 场;
        次日 12:01 再恢复 1 次 -> 又可打 1 场。共 4 场/天。
        """
        played = 0
        now = T0
        for _ in range(4):
            avail = task_state.get_charges('cfg', 'T', max_charges=2,
                                           recover_hours=12, now=now)
            if avail > 0:
                task_state.consume_charge('cfg', 'T', max_charges=2,
                                          recover_hours=12, now=now)
                played += 1
                if avail > 1:
                    continue          # 还有存量, 立刻再打一场
            now = task_state.next_charge_time('cfg', 'T', max_charges=2,
                                              recover_hours=12, now=now)
            now = max(now, T0 + timedelta(seconds=1)) if now == T0 else now
            now = now + timedelta(seconds=1)
            if now > T0 + timedelta(days=2):
                break
        assert played == 4, f'一天(24h)应可打 4 场(初始2+恢复2), 实际 {played}'


class TestNextChargeTime:
    def test_now_when_charges_available(self):
        assert task_state.next_charge_time('cfg', 'T', max_charges=2,
                                           recover_hours=12, now=T0) == T0

    def test_returns_next_recovery_not_whole_interval(self):
        """
        用尽后应返回"下一格充能"的时刻(约 12 小时后),
        而不是"存量补满"的时刻(那是 24 小时后)。
        """
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        nxt = task_state.next_charge_time('cfg', 'T', max_charges=2,
                                          recover_hours=12, now=T0)
        delta = (nxt - T0).total_seconds() / 3600
        assert 11.9 < delta <= 12.1, f'应约 12 小时后, 实际 {delta:.2f}h'

    def test_accounts_for_elapsed_time(self):
        """已过 10 小时时, 下一格应在约 2 小时后。"""
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        now = T0 + timedelta(hours=10)
        nxt = task_state.next_charge_time('cfg', 'T', max_charges=2,
                                          recover_hours=12, now=now)
        delta = (nxt - now).total_seconds() / 3600
        assert 1.9 < delta <= 2.1, f'应约 2 小时后, 实际 {delta:.2f}h'

    def test_never_in_the_past(self):
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0)
        now = T0 + timedelta(hours=30)
        nxt = task_state.next_charge_time('cfg', 'T', max_charges=2,
                                          recover_hours=12, now=now)
        assert nxt >= now


class TestChargeDegradation:
    def test_corrupted_file_returns_full(self, isolated_state):
        """状态损坏时按满次数处理, 保证任务照常运行。"""
        isolated_state.write_text('{ 坏 JSON', encoding='utf-8')
        assert task_state.get_charges('cfg', 'T', max_charges=2,
                                      recover_hours=12, now=T0) == 2

    def test_unwritable_does_not_raise(self, monkeypatch):
        monkeypatch.setenv('OAS_TASK_STATE_FILE', 'Z:\\no\\such\\dir\\x.json')
        # 不应抛异常; 消耗失败时按成功处理以便任务继续
        task_state.consume_charge('cfg', 'T', max_charges=2,
                                  recover_hours=12, now=T0)

    def test_configs_isolated(self):
        task_state.consume_charge('acc1', 'T', max_charges=2,
                                  recover_hours=12, now=T0)
        assert task_state.get_charges('acc1', 'T', max_charges=2,
                                      recover_hours=12, now=T0) == 1
        assert task_state.get_charges('acc2', 'T', max_charges=2,
                                      recover_hours=12, now=T0) == 2


class TestChargeConfig:
    @pytest.mark.parametrize('mod_name,cls_name,group', [
        ('tasks.ExperienceYoukai.config', 'ExperienceYoukai', 'experience_youkai'),
        ('tasks.GoldYoukai.config', 'GoldYoukai', 'gold_youkai'),
    ])
    def test_charge_fields_exist_with_game_defaults(self, mod_name, cls_name, group):
        """默认值必须与游戏一致: 最多 2 次、每 12 小时恢复 1 次。"""
        cls = getattr(__import__(mod_name, fromlist=[cls_name]), cls_name)
        obj = cls()
        conf = getattr(obj, group)
        assert conf.charge_max == 2
        assert conf.charge_recover_hours == 12.0
        assert conf.charge_consume >= 1
        assert conf.charge_enable is True

    @pytest.mark.parametrize('mod_name,cls_name,group', [
        ('tasks.ExperienceYoukai.config', 'ExperienceYoukai', 'experience_youkai'),
        ('tasks.GoldYoukai.config', 'GoldYoukai', 'gold_youkai'),
    ])
    def test_i18n_has_charge_text(self, mod_name, cls_name, group):
        import xml.etree.ElementTree as ET
        from pathlib import Path
        repo = Path(__file__).resolve().parents[3]
        root = ET.parse(repo / 'module' / 'config' / 'i18n' / 'zh_CN.xml').getroot()
        src = {m.findtext('source') for m in root.iter('message')}
        for key in ('charge_enable_help', 'charge_max_help',
                    'charge_recover_hours_help', 'charge_consume_help'):
            assert key in src, f'zh_CN.xml 缺少 {key}'


class TestKekkaiNotAffected:
    """
    结界寄养(KekkaiActivation)自己 OCR 卡牌剩余时间并 set_next_run(target=...)，
    重挂周期由卡牌决定(可能 6 小时), 因此**不应**给它设置 period,
    否则会因"本周期已完成"而漏挂。
    """

    def test_default_period_is_none(self):
        from tasks.Component.config_scheduler import Scheduler, TaskPeriod
        assert Scheduler().period == TaskPeriod.NONE

    def test_none_period_never_skips(self):
        """period=none 时 is_completed_in_period 恒为 False -> 不会被跳过。"""
        task_state.record_success('cfg', 'KekkaiActivation', 'none')
        assert task_state.is_completed_in_period('cfg', 'KekkaiActivation',
                                                'none') is False
