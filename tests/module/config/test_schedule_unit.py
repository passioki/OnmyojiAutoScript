# -*- coding: utf-8 -*-
"""★ [10-15] `L3-0 / R1-a`：调度单元（`module/config/schedule_unit.py`）的守卫。

## 这组守卫守什么（★ 三条，缺一不可）

1. ★ **映射可逆**：`period <-> expire` 必须是一一对应（★ 否则"统一"就是假的）；
2. ★ **零行为变更**：`is_due()` / `record_outcome()` 必须**只转调**既有实现，
   ★ 且参数**逐项正确**（★ 用 monkeypatch 断言"调了谁、传了什么"）；
3. ★★ **临时任务"重启重打"是 session 过期策略的副作用** ——
   ★ 换一次 `session_start` 后**必须重新可跑**（★ 这条证明了 L1-a 断点续跑
   不需要单独修，改为 `expire` 参数即可）。

★ 铁律：★ 新守卫必须**注入验证真红**（见 `dev_tools/_probes/inject_schedule_unit.py`）。
"""
import pytest

from module.config import schedule_unit as SU
from module.config import task_state as TS

CFG = '__schedule_unit_test__'


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    try:
        TS.clear(CFG)
    except Exception:
        pass


# ───────────────────────────────────────────── ① 映射可逆
@pytest.mark.parametrize('period,expire', [
    ('none', SU.SESSION),      # ★ 临时任务
    ('daily', SU.DAILY),
    ('weekly', SU.WEEKLY),
    ('monthly', SU.MONTHLY),
    # ★ 历史字段可能是枚举字符串（meta.py 用 Period.DAILY）
    ('Period.DAILY', SU.DAILY),
    (' period.weekly ', SU.WEEKLY),
])
def test_expire_period_mapping(period, expire):
    assert SU.expire_for_period(period) == expire


@pytest.mark.parametrize('period', ['none', 'daily', 'weekly', 'monthly'])
def test_mapping_is_bijective(period):
    """★ 可逆：`period -> expire -> period` 必须回到原值。"""
    expire = SU.expire_for_period(period)
    assert SU.period_for_expire(expire) == period


def test_unknown_period_raises():
    """★ 不认识的 period 必须**响亮报错**（★ 不许静默当 none）。"""
    with pytest.raises(ValueError, match='period'):
        SU.expire_for_period('yearly')


# ───────────────────────────────────────────── ② 值对象
def test_unit_key_prefers_entry_id_then_task():
    """★ 键口径：★ entry_id 优先、否则任务名、统一小写（★ 与 `_state_key` 同口径）。"""
    assert SU.ScheduleUnit('Orochi').key == 'orochi'
    assert SU.ScheduleUnit('Orochi', entry_id='E1').key == 'e1'
    assert SU.ScheduleUnit('Orochi', entry_id='  E1  ').key == 'e1'
    assert SU.ScheduleUnit('Orochi', entry_id='').key == 'orochi'


def test_reserved_expire_is_loudly_rejected():
    """★ `never` 是 R1-b 的保留值 ⇒ **现在必须吵**，★ 不许静默当 session。"""
    with pytest.raises(ValueError, match='R1-b'):
        SU.ScheduleUnit('Orochi', expire='never')


def test_empty_task_is_rejected():
    with pytest.raises(ValueError):
        SU.ScheduleUnit('   ')


def test_unit_for_accepts_legacy_period():
    """★ 迁移期唯一入口：从历史 `period` + `entry_id` 造单元。"""
    u1 = SU.unit_for('Rest', period='none')
    assert u1.expire == SU.SESSION and not u1.is_periodic
    u2 = SU.unit_for('Orochi', period='daily', entry_id='E9')
    assert u2.expire == SU.DAILY and u2.is_periodic and u2.entry_id == 'E9'


def test_describe_is_readable():
    assert '周期' in SU.ScheduleUnit('Orochi', expire='daily').describe()
    assert '临时' in SU.ScheduleUnit('Rest').describe()


# ───────────────────────────────────────────── ③ 零行为变更：委托参数逐项核对
def test_is_due_periodic_delegates_and_inverts(monkeypatch):
    seen = {}

    def fake(config_name, task, period, reset_at=None, entry_id=None):
        seen.update(config=config_name, task=task, period=period,
                    entry_id=entry_id)
        return True                      # ★ 已完成 ⇒ is_due 应为 False

    monkeypatch.setattr(TS, 'is_completed_in_period', fake)
    u = SU.ScheduleUnit('Orochi', entry_id='', expire='daily')
    assert SU.is_due(CFG, u) is False
    assert seen == {'config': CFG, 'task': 'Orochi', 'period': 'daily',
                    'entry_id': None}     # ★ 空串必须转成 None（与既有调用同口径）


def test_is_due_session_delegates_and_inverts(monkeypatch):
    seen = {}

    def fake_get(config_name, entry_id):
        seen.update(config=config_name, entry_id=entry_id)
        return False                     # ★ 未完成 ⇒ is_due 应为 True

    monkeypatch.setattr(TS, 'get_entry_completed', fake_get)
    u = SU.ScheduleUnit('Rest', entry_id='E7', expire='session')
    assert SU.is_due(CFG, u) is True
    assert seen == {'config': CFG, 'entry_id': 'e7'}   # ★ 走统一键


def test_record_outcome_periodic_delegates(monkeypatch):
    seen = {}

    def fake_rec(config_name, task, period='none', reset_at=None, entry_id=None):
        seen.update(config=config_name, task=task, period=period,
                    entry_id=entry_id)

    monkeypatch.setattr(TS, 'record_success', fake_rec)
    u = SU.ScheduleUnit('Orochi', expire='weekly')
    assert SU.record_outcome(CFG, u) is True
    assert seen == {'config': CFG, 'task': 'Orochi', 'period': 'weekly',
                    'entry_id': None}


def test_record_outcome_session_delegates(monkeypatch):
    seen = {}

    def fake_mark(config_name, entry_id, reason=''):
        seen.update(config=config_name, entry_id=entry_id, reason=reason)
        return True

    monkeypatch.setattr(TS, 'mark_entry_completed', fake_mark)
    u = SU.ScheduleUnit('Rest', entry_id='E7')
    assert SU.record_outcome(CFG, u, reason='没券了') is True
    assert seen == {'config': CFG, 'entry_id': 'e7', 'reason': '没券了'}


def test_record_outcome_failure_does_not_delegate(monkeypatch):
    """★ 失败**不记完成**，且**不许**调委托（★ 防"失败了还标已完成"）。"""
    called = []
    monkeypatch.setattr(TS, 'record_success',
                        lambda *a, **k: called.append('periodic'))
    monkeypatch.setattr(TS, 'mark_entry_completed',
                        lambda *a, **k: called.append('session'))
    assert SU.record_outcome(CFG, SU.ScheduleUnit('Orochi', expire='daily'),
                             success=False) is False
    assert SU.record_outcome(CFG, SU.ScheduleUnit('Rest'),
                             success=False) is False
    assert called == []


# ───────────────────────────────────────────── ④ 真·往返（不 monkeypatch）
def test_real_roundtrip_periodic():
    """★ 周期单元：记完后 ⇒ 同周期内 `is_due` False，★ 且与旧函数**完全一致**。"""
    u = SU.ScheduleUnit('ProbeDaily', expire='daily')
    assert SU.record_outcome(CFG, u) is True
    assert SU.is_due(CFG, u) is False
    # ★ 零行为变更的硬证据：直接调旧函数，结论必须一样
    assert SU.is_due(CFG, u) == (not TS.is_completed_in_period(
        CFG, 'ProbeDaily', period='daily'))


def test_real_roundtrip_session_expires_on_new_start():
    """★★★ 临时单元：★ **换一次 `session_start` ⇒ 重新可跑**（★ 这就是"重启重打"）。

    ★ 结论：★ L1-a「断点续跑」**不是独立 bug** —— 它是 `expire='session'` 的**策略副作用**。
    ★ 统一后想"重启不重打"，只须把该单元的 `expire` 改成 `daily`/`never`（R1-b 接线）。
    """
    u = SU.ScheduleUnit('ProbeTemp', entry_id='E1', expire='session')
    TS.mark_session_start(CFG)
    assert SU.record_outcome(CFG, u) is True
    assert SU.is_due(CFG, u) is False, '★ 同一 session 内应算已完成'

    TS.mark_session_start(CFG)          # ★ 模拟"后端重启"
    assert SU.is_due(CFG, u) is True, (
        '★ 换 session 后必须重新可跑 —— 这正是"临时任务重启重打"的机制')
