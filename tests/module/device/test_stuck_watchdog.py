# -*- coding: utf-8 -*-
"""验证看门狗对「战斗状态无限期豁免」与「异常状态仍有时限」的区分。

对应修复: 超鬼王等长战斗(实测 BOSS 血量 82%->7% 仍在推进)此前会在 300 秒处被
判为卡死并触发 Restart。现在战斗类状态(BATTLE_STATUS_S / PREPARE_BEFORE_BATTLE)
无限期豁免, 而 PAUSE / LOGIN_CHECK 仍保留 300 秒时限, 不能因为修长战斗就把
看门狗整体废掉。

测试手法: 直接操纵 detect_record 与两个计时器, 断言 stuck_record_check 的行为。
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from module.base.timer import Timer
from module.device.device import Device
from module.exception import GameStuckError, GameNotRunningError


class _Harness:
    """借用 Device.stuck_record_check, 但不做真实设备初始化。"""

    def __init__(self):
        self.detect_record = set()
        self.stuck_timer = Timer(1).start()
        self.stuck_timer_long = Timer(1).start()
        self._app_running = True

    # 直接绑定 Device 上的真实实现
    stuck_record_check = Device.stuck_record_check
    stuck_record_clear = Device.stuck_record_clear
    stuck_long_wait_list = Device.stuck_long_wait_list
    stuck_unlimited_wait_list = Device.stuck_unlimited_wait_list

    def app_is_running(self):
        return self._app_running


@pytest.fixture()
def harness():
    h = _Harness()
    # 让两个计时器都已到达
    import time
    time.sleep(1.1)
    return h


@pytest.mark.parametrize('state', ['BATTLE_STATUS_S', 'PREPARE_BEFORE_BATTLE'])
def test_battle_state_is_exempt_without_time_limit(harness, state):
    """战斗类状态即使超过 stuck_timer_long 也不应报错。"""
    harness.detect_record = {state}
    assert harness.stuck_record_check() is False, (
        f'{state} 应被无限期豁免, 不应抛 GameStuckError'
    )


def test_pause_still_times_out_when_long_timer_reached(harness):
    """PAUSE 不是战斗类状态: 超过长计时仍应报错, 保证看门狗没被废掉。"""
    harness.detect_record = {'PAUSE'}
    with pytest.raises(GameStuckError):
        harness.stuck_record_check()


def test_login_check_still_times_out_when_long_timer_reached(harness):
    """LOGIN_CHECK 同理, 卡在登录页需要救援。"""
    harness.detect_record = {'LOGIN_CHECK'}
    with pytest.raises(GameStuckError):
        harness.stuck_record_check()


def test_non_whitelisted_state_raises(harness):
    """不在白名单里的状态照旧报错。"""
    harness.detect_record = {'SOME_UNKNOWN_STATE'}
    with pytest.raises(GameStuckError):
        harness.stuck_record_check()


def test_battle_state_exempt_even_with_extra_states(harness):
    """detect_record 同时含战斗状态与异常状态时, 战斗状态优先豁免。

    这是实际会遇到的情况: battle_wait 添加 BATTLE_STATUS_S 后, 期间可能又叠加了
    其它状态。此时按"只要在战斗中就不判卡死"处理, 与 stuck_record_add 的语义一致。
    """
    harness.detect_record = {'BATTLE_STATUS_S', 'PAUSE'}
    assert harness.stuck_record_check() is False


def test_not_running_raises_game_not_running(harness):
    """非白名单状态且游戏已退出时, 应抛 GameNotRunningError 而非 GameStuckError。"""
    harness.detect_record = {'UNKNOWN'}
    harness._app_running = False
    with pytest.raises(GameNotRunningError):
        harness.stuck_record_check()
