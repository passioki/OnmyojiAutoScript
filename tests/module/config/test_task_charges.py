# -*- coding: utf-8 -*-
"""验证按**固定时刻**刷新的挑战次数机制(经验妖怪 / 金币妖怪 / 石距)。

游戏事实
--------
这些玩法的挑战次数在**每天的固定时刻**刷新(0 点与 12 点), 最多储存 2 次。
关键: 这是"固定时刻"而不是"间隔 12 小时" ——
    若在 01:00 用掉一次, 下一次是**当天 12:00** 刷新, 而不是 13:00。
用固定时刻建模更准确, 也更利于多账号在同一个刷新点对齐组队。

改造前的实现是"一次运行内连打 2 场"(while count < 2):
  * 没有次数概念, 次数用尽后仍会去开房;
  * 两场背靠背, 与"存 2 次、按刷新点来做"的本意相反, 组队时队友对不上。
"""
from datetime import datetime, timedelta

import pytest

from module.config import task_state


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_file = tmp_path / '.task_state.json'
    monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state_file))
    yield state_file
    monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)


# 2026-10-07 12:00 -- 正好在一个刷新点上
NOON = datetime(2026, 10, 7, 12, 0, 0)
SLOTS = '0,12'


class TestSlotParsing:
    def test_parse_standard(self):
        assert task_state.parse_slots('0,12') == (0, 12)

    def test_parse_with_spaces_and_fullwidth_comma(self):
        assert task_state.parse_slots(' 0 ， 12 ') == (0, 12)

    def test_parse_single(self):
        assert task_state.parse_slots('12') == (12,)

    def test_parse_three(self):
        assert task_state.parse_slots('0,8,16') == (0, 8, 16)

    def test_dedup_and_sort(self):
        assert task_state.parse_slots('12,0,12') == (0, 12)

    def test_invalid_falls_back_to_default(self):
        assert task_state.parse_slots('abc') == (0, 12)
        assert task_state.parse_slots('') == (0, 12)
        assert task_state.parse_slots(None) == (0, 12)
        assert task_state.parse_slots('99') == (0, 12)

    def test_accepts_list(self):
        assert task_state.parse_slots([0, 12]) == (0, 12)


class TestSlotTimes:
    """_slot_times 给出最近 N 个刷新点(由新到旧)。"""

    def test_at_noon(self):
        t = task_state._slot_times((0, 12), NOON, 2)
        assert t == [datetime(2026, 10, 7, 12, 0), datetime(2026, 10, 7, 0, 0)]

    def test_early_morning_crosses_day(self):
        """01:00 时最近的两个刷新点是 今天00:00 与 昨天12:00。"""
        now = datetime(2026, 10, 7, 1, 0)
        t = task_state._slot_times((0, 12), now, 2)
        assert t == [datetime(2026, 10, 7, 0, 0), datetime(2026, 10, 6, 12, 0)]

    def test_late_evening(self):
        now = datetime(2026, 10, 7, 23, 0)
        t = task_state._slot_times((0, 12), now, 2)
        assert t == [datetime(2026, 10, 7, 12, 0), datetime(2026, 10, 7, 0, 0)]

    def test_never_in_future(self):
        now = datetime(2026, 10, 7, 5, 30)
        for t in task_state._slot_times((0, 12), now, 3):
            assert t <= now


class TestChargeAccounting:
    def test_initial_full(self):
        """首次使用时按满次数处理(不因为没记录就不让打)。"""
        assert task_state.get_charges('cfg', 'T', 2, SLOTS, NOON) == 2

    def test_consume_one(self):
        assert task_state.consume_charge('cfg', 'T', 2, SLOTS, NOON) == 1
        assert task_state.get_charges('cfg', 'T', 2, SLOTS, NOON) == 1

    def test_consume_both_then_empty(self):
        assert task_state.consume_charge('cfg', 'T', 2, SLOTS, NOON) == 1
        assert task_state.consume_charge('cfg', 'T', 2, SLOTS, NOON) == 0
        assert task_state.get_charges('cfg', 'T', 2, SLOTS, NOON) == 0

    def test_cannot_consume_when_empty(self):
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', 2, SLOTS, NOON)
        assert task_state.consume_charge('cfg', 'T', 2, SLOTS, NOON) == 0
        assert task_state.get_charges('cfg', 'T', 2, SLOTS, NOON) == 0

    def test_consumption_is_reflected_in_state(self):
        """消耗会写入状态: count 递减, 并记录槽位与消耗时刻。"""
        task_state.consume_charge('cfg', 'T', 2, SLOTS, NOON)
        rec = task_state._read_all()['cfg']['t']['charges']
        assert rec['count'] == 1
        assert 'last_slot' in rec, '应记录槽位号'
        assert rec.get('last_consume'), '应记录消耗时刻'
        task_state.consume_charge('cfg', 'T', 2, SLOTS, NOON)
        rec = task_state._read_all()['cfg']['t']['charges']
        assert rec['count'] == 0


class TestFixedClockRefresh:
    """
    核心: 刷新发生在**固定时刻**, 不是"用掉后 12 小时"。
    """

    def test_used_at_0100_recovers_at_same_day_1200(self):
        """
        01:00 用掉一次 -> 当天 12:00 即可再打(而不是 13:00)。
        这是与"间隔模型"最关键的差别。
        """
        t0100 = datetime(2026, 10, 7, 1, 0)
        # 01:00 时最近两个刷新点是 07日00:00 与 06日12:00, 先用掉两次
        task_state.consume_charge('cfg', 'T', 2, SLOTS, t0100)
        task_state.consume_charge('cfg', 'T', 2, SLOTS, t0100)
        assert task_state.get_charges('cfg', 'T', 2, SLOTS, t0100) == 0

        # 当天 12:00 刷新 -> 可打
        assert task_state.get_charges('cfg', 'T', 2, SLOTS,
                                      datetime(2026, 10, 7, 12, 0)) == 1
        # 11:59 还没刷新
        assert task_state.get_charges('cfg', 'T', 2, SLOTS,
                                      datetime(2026, 10, 7, 11, 59)) == 0

    def test_next_charge_time_is_next_clock_slot(self):
        """13:00 用尽 -> 下次是次日 00:00, 不是 13:00+12h。"""
        t1300 = datetime(2026, 10, 7, 13, 0)
        task_state.consume_charge('cfg', 'T', 2, SLOTS, t1300)
        task_state.consume_charge('cfg', 'T', 2, SLOTS, t1300)
        nxt = task_state.next_charge_time('cfg', 'T', 2, SLOTS, t1300)
        assert nxt == datetime(2026, 10, 8, 0, 0)

    def test_next_charge_time_early_morning(self):
        """01:00 用尽 -> 下次是当天 12:00。"""
        t0100 = datetime(2026, 10, 7, 1, 0)
        task_state.consume_charge('cfg', 'T', 2, SLOTS, t0100)
        task_state.consume_charge('cfg', 'T', 2, SLOTS, t0100)
        nxt = task_state.next_charge_time('cfg', 'T', 2, SLOTS, t0100)
        assert nxt == datetime(2026, 10, 7, 12, 0)

    def test_next_charge_time_when_available_is_now(self):
        assert task_state.next_charge_time('cfg', 'T', 2, SLOTS, NOON) == NOON

    def test_next_charge_time_never_in_past(self):
        for hour in (0, 1, 6, 12, 13, 23):
            now = datetime(2026, 10, 7, hour, 30)
            task_state.clear()
            for _ in range(2):
                task_state.consume_charge('cfg', 'T', 2, SLOTS, now)
            nxt = task_state.next_charge_time('cfg', 'T', 2, SLOTS, now)
            assert nxt > now, f'{now} 时算出的下次刷新 {nxt} 不在未来'

    def test_recovers_one_per_slot(self):
        """两个刷新点之间只恢复 1 次(不是按小时连续恢复)。"""
        t0000 = datetime(2026, 10, 7, 0, 0)
        task_state.consume_charge('cfg', 'T', 2, SLOTS, t0000)
        task_state.consume_charge('cfg', 'T', 2, SLOTS, t0000)
        # 00:01~11:59 之间始终为 0
        for h in (0, 3, 6, 9, 11):
            assert task_state.get_charges('cfg', 'T', 2, SLOTS,
                                          datetime(2026, 10, 7, h, 30)) == 0

    def test_cap_is_respected(self):
        """上限 2: 即使隔了很多天也不会超过 2。"""
        t0000 = datetime(2026, 10, 7, 0, 0)
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', 2, SLOTS, t0000)
        much_later = datetime(2026, 10, 20, 15, 0)
        assert task_state.get_charges('cfg', 'T', 2, SLOTS, much_later) == 2

    def test_first_two_days_gives_five_challenges(self):
        """
        从空状态起算的两天: 共 5 次。
        原因: 初始存量 2 次, 加上 4 个刷新点(每天 0/12 点)各恢复 1 次,
        但刷新点恢复时会受"上限 2"约束, 因此不是简单的 2+4=6:
            第1个刷新点 -> 存量2, 打1次后刷新又补到2 -> 仍剩1
            第2个刷新点 -> 打1次后刷新 -> 剩1
            第3、4个刷新点 -> 各打1次
        合计 2(初始可用) + 3 = 5。
        """
        played = 0
        for day in (7, 8):
            for hour in (0, 12):
                now = datetime(2026, 10, day, hour, 5)
                while task_state.get_charges('cfg', 'T', 2, SLOTS, now) > 0:
                    task_state.consume_charge('cfg', 'T', 2, SLOTS, now)
                    played += 1
        assert played == 5, f'实际 {played}'

    def test_steady_state_is_two_per_day(self):
        """
        稳态下每天恰好 2 次 —— 与游戏"0 点/12 点各恢复 1 次"一致。

        做法: 每个刷新点检查并消耗到 0, 统计"该刷新点能打几次"。
        刚耗尽后若跨越了多个刷新点, 会按"每点 +1"累计(封顶 2), 这是规格要求;
        从第二天起进入稳态, 每个刷新点恰有 1 次。
        """
        base = datetime(2026, 10, 7, 1, 0)
        for _ in range(2):
            task_state.consume_charge('cfg', 'T', 2, SLOTS, base)
        assert task_state.get_charges('cfg', 'T', 2, SLOTS, base) == 0

        # 从 10/8 00:05 起进入稳态: 之后每个刷新点恰有 1 次可打
        playable = []
        for day, hour in [(8, 0), (8, 12), (9, 0), (9, 12), (10, 0), (10, 12)]:
            now = datetime(2026, 10, day, hour, 5)
            avail = task_state.get_charges('cfg', 'T', 2, SLOTS, now)
            playable.append((day, hour, avail))
            while task_state.get_charges('cfg', 'T', 2, SLOTS, now) > 0:
                task_state.consume_charge('cfg', 'T', 2, SLOTS, now)
        # 首个点可能带走"结转存量", 从第二个点开始必须恒为 1
        after_first = [a for _, _, a in playable[1:]]
        assert after_first == [1, 1, 1, 1, 1], f'稳态每点应恰 1 次, 实际 {playable}'


class TestCustomSlots:
    def test_single_daily_slot(self):
        """只有 0 点刷新时, 每天只能打 1 次。"""
        now = datetime(2026, 10, 7, 10, 0)
        task_state.consume_charge('cfg', 'T', 1, '0', now)
        assert task_state.get_charges('cfg', 'T', 1, '0', now) == 0
        assert task_state.next_charge_time('cfg', 'T', 1, '0', now) == \
            datetime(2026, 10, 8, 0, 0)

    def test_three_slots(self):
        now = datetime(2026, 10, 7, 8, 0)
        assert task_state.get_charges('cfg', 'T', 3, '0,8,16', now) == 3
        task_state.consume_charge('cfg', 'T', 3, '0,8,16', now)
        assert task_state.get_charges('cfg', 'T', 3, '0,8,16', now) == 2


class TestChargeDegradation:
    def test_corrupted_file_returns_full(self, isolated_state):
        """状态损坏时按满次数处理, 保证任务照常运行。"""
        isolated_state.write_text('{ 坏 JSON', encoding='utf-8')
        assert task_state.get_charges('cfg', 'T', 2, SLOTS, NOON) == 2

    def test_unwritable_does_not_raise(self, monkeypatch):
        monkeypatch.setenv('OAS_TASK_STATE_FILE', 'Z:\\no\\such\\dir\\x.json')
        task_state.consume_charge('cfg', 'T', 2, SLOTS, NOON)

    def test_configs_isolated(self):
        task_state.consume_charge('acc1', 'T', 2, SLOTS, NOON)
        assert task_state.get_charges('acc1', 'T', 2, SLOTS, NOON) == 1
        assert task_state.get_charges('acc2', 'T', 2, SLOTS, NOON) == 2

    def test_used_slots_do_not_grow_forever(self):
        """状态记录必须保持 O(1) 大小, 不能随消耗次数增长。"""
        now = datetime(2026, 10, 7, 0, 0)
        for i in range(60):
            t = now + timedelta(hours=12 * i)
            task_state.consume_charge('cfg', 'T', 2, SLOTS, t)
        rec = task_state._read_all()['cfg']['t']['charges']
        # 现在只存 count / last_slot / slots / last_consume, 与消耗次数无关
        assert set(rec.keys()) <= {'count', 'last_slot', 'slots', 'last_consume'}
        import json as _json
        assert len(_json.dumps(rec)) < 400, f'记录过大: {rec}'


class TestChargeConfig:
    @pytest.mark.parametrize('mod_name,cls_name,group', [
        ('tasks.ExperienceYoukai.config', 'ExperienceYoukai', 'experience_youkai'),
        ('tasks.GoldYoukai.config', 'GoldYoukai', 'gold_youkai'),
        ('tasks.Tako.config', 'Tako', 'tako_config'),
    ])
    def test_charge_fields_exist_with_game_defaults(self, mod_name, cls_name, group):
        """默认值必须与游戏一致: 最多 2 次、0 点与 12 点刷新。"""
        cls = getattr(__import__(mod_name, fromlist=[cls_name]), cls_name)
        conf = getattr(cls(), group)
        assert conf.charge_max == 2
        assert task_state.parse_slots(conf.charge_slots) == (0, 12)
        assert conf.charge_consume >= 1
        assert conf.charge_enable is True

    @pytest.mark.parametrize('mod_name,cls_name,group', [
        ('tasks.ExperienceYoukai.config', 'ExperienceYoukai', 'experience_youkai'),
        ('tasks.GoldYoukai.config', 'GoldYoukai', 'gold_youkai'),
        ('tasks.Tako.config', 'Tako', 'tako_config'),
    ])
    def test_zone_name_matches_the_zone_used_in_task(self, mod_name, cls_name, group):
        """zone_name 必须与任务里 check_zones 用的名字对得上, 否则读不到倒计时。"""
        from pathlib import Path

        cls = getattr(__import__(mod_name, fromlist=[cls_name]), cls_name)
        # 注意: 这里要取分组模型**实例**的默认值, 不能用 cls() 直接取属性
        # (cls() 是任务顶层模型, 其 group 属性是 FieldInfo, 内部字段均为空串)
        group_cls = cls.model_fields[group].annotation
        zone = group_cls().zone_name
        assert zone, 'zone_name 不能为空'

        script = mod_name.replace('.config', '.script_task').replace('.', '/') + '.py'
        repo = Path(__file__).resolve().parents[3]
        src = (repo / script).read_text(encoding='utf-8')

        # 场地名可以写死, 也可以是变量(如石距周末切"愤怒的石距"),
        # 因此两种形态都接受: 字面量, 或该名字出现在同一个源文件里且被 check_zones 使用
        literal = f"check_zones('{zone}')" in src
        var_form = f"check_zones({group}.zone_name)" in src
        assert literal or var_form or zone in src, \
            (f'{cls_name} 的 zone_name={zone!r} 在 script_task 中既未作为 '
             f'check_zones 字面量, 也未出现; 会导致读不到倒计时')

    @pytest.mark.parametrize('mod_name,cls_name,group', [
        ('tasks.ExperienceYoukai.config', 'ExperienceYoukai', 'experience_youkai'),
        ('tasks.GoldYoukai.config', 'GoldYoukai', 'gold_youkai'),
        ('tasks.Tako.config', 'Tako', 'tako_config'),
    ])
    def test_i18n_has_charge_text(self, mod_name, cls_name, group):
        import xml.etree.ElementTree as ET
        from pathlib import Path
        repo = Path(__file__).resolve().parents[3]
        root = ET.parse(repo / 'module' / 'config' / 'i18n' / 'zh_CN.xml').getroot()
        src = {m.findtext('source') for m in root.iter('message')}
        for key in ('charge_enable_help', 'charge_max_help',
                    'charge_slots_help', 'charge_consume_help', 'zone_name_help'):
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
        task_state.record_success('cfg', 'KekkaiActivation', 'none')
        assert task_state.is_completed_in_period('cfg', 'KekkaiActivation',
                                                'none') is False
