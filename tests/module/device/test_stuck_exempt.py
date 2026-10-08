# -*- coding: utf-8 -*-
"""device 战斗豁免(持续豁免)的测试。

线上实测背景(2026-10-08, 伴生树/恋鸟树 两个账号时序完全一致)
-----------------------------------------------------------
    11:20:05.623  Add stuck record: BATTLE_STATUS_S
    11:20:14.683  Click (667,237) @ random_click     <- 战斗中的防封随机点击
    11:21:14.892  Wait too long | Waiting for set()   <- 正好 60s 后

`click()` -> `handle_control_check()` -> `stuck_record_clear()`(device.py),
所以**任何一次点击都会把普通豁免清掉**。战斗期间本流程自己会频繁随机点击
(见 battle_wait.py 的 _bw_randomclick_default), 于是"每轮重新声明"这种写法
在单场战斗内部**执行不到**, 豁免在第一次随机点击后永久失效 -> 正常战斗被
误判卡死 -> 重启游戏 -> 掉线 -> 队长邀请等待超时。

因此引入"持续豁免"(hold_stuck_exempt): 它跨过 stuck_record_clear() 存活,
只在真正离开该状态时由 release_stuck_exempt() 撤销。
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))


class _Stub:
    """只加载 Device 的豁免相关方法, 不构造真实设备。"""

    from module.device.device import Device
    stuck_record_add = Device.stuck_record_add
    stuck_record_clear = Device.stuck_record_clear
    keep_stuck_exempt = Device.keep_stuck_exempt
    hold_stuck_exempt = Device.hold_stuck_exempt
    release_stuck_exempt = Device.release_stuck_exempt
    stuck_unlimited_wait_list = Device.stuck_unlimited_wait_list
    stuck_long_wait_list = Device.stuck_long_wait_list

    def __init__(self):
        from module.base.timer import Timer
        self.detect_record = set()
        self.stuck_record_late = set()
        self.stuck_timer = Timer(60, count=60).start()
        self.stuck_timer_long = Timer(300, count=300).start()

    def app_is_running(self) -> bool:
        return True

    def click(self):
        """模拟一次点击: 走的就是 handle_control_check 的清理逻辑。"""
        self.stuck_record_clear()


@pytest.fixture
def dev():
    return _Stub()


class TestPlainExemptionIsFragile:
    """说明为什么普通豁免不够 —— 这是根因的最小复现。"""

    def test_click_wipes_plain_exemption(self, dev):
        dev.stuck_record_add('BATTLE_STATUS_S')
        assert 'BATTLE_STATUS_S' in dev.detect_record
        dev.click()                                   # 战斗中的一次随机点击
        assert dev.detect_record == set(), (
            '普通豁免会被点击清掉 —— 这正是线上卡死的原因')

    def test_click_does_not_wipe_held_exemption(self, dev):
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        dev.click()
        assert 'BATTLE_STATUS_S' in dev.detect_record, (
            '持续豁免必须跨过点击存活')


class TestHoldExempt:
    def test_hold_declares(self, dev):
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        assert dev.stuck_record_late == {'BATTLE_STATUS_S'}
        assert 'BATTLE_STATUS_S' in dev.detect_record

    def test_hold_is_idempotent(self, dev):
        for _ in range(5):
            dev.hold_stuck_exempt('BATTLE_STATUS_S')
        assert dev.stuck_record_late == {'BATTLE_STATUS_S'}

    def test_survives_many_clicks(self, dev):
        """战斗期间会点很多次, 豁免必须一直有效。"""
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        for _ in range(20):
            dev.click()
            assert 'BATTLE_STATUS_S' in dev.detect_record

    def test_survives_other_clear_calls(self, dev):
        """其它任务代码误调 stuck_record_clear 也不该取消持续豁免。"""
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        dev.stuck_record_clear()
        assert 'BATTLE_STATUS_S' in dev.detect_record


class TestReleaseExempt:
    def test_release_removes(self, dev):
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        dev.release_stuck_exempt('BATTLE_STATUS_S')
        assert dev.stuck_record_late == set()
        assert 'BATTLE_STATUS_S' not in dev.detect_record

    def test_release_makes_watchdog_work_again(self, dev):
        """释放后必须恢复普通的卡死检测能力, 否则看门狗会永久失效。"""
        from module.device.device import Device
        from module.exception import GameStuckError

        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        dev.release_stuck_exempt('BATTLE_STATUS_S')
        dev.click()                                   # 清掉瞬时状态
        assert dev.detect_record == set()

        # 让 60s 计时器到期(需要 _reach_count > count)
        dev.stuck_timer._current -= 3600
        dev.stuck_timer._reach_count = dev.stuck_timer.count + 1
        with pytest.raises(GameStuckError):
            Device.stuck_record_check(dev)

    def test_release_unknown_is_safe(self, dev):
        dev.release_stuck_exempt('NOT_HELD')          # 不应抛异常
        assert dev.detect_record == set()

    def test_release_only_affects_named(self, dev):
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        dev.hold_stuck_exempt('PREPARE_BEFORE_BATTLE')
        dev.release_stuck_exempt('BATTLE_STATUS_S')
        assert dev.stuck_record_late == {'PREPARE_BEFORE_BATTLE'}
        assert 'PREPARE_BEFORE_BATTLE' in dev.detect_record


class TestWatchdogSemantics:
    def test_held_exemption_suppresses_watchdog(self, dev):
        from module.device.device import Device
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        dev.click()                                   # 战斗中随机点击
        dev.stuck_timer._current -= 3600
        dev.stuck_timer._reach_count = dev.stuck_timer.count + 1
        assert Device.stuck_record_check(dev) is False, (
            '持有持续豁免时不得判定卡死')

    def test_watchdog_reads_held_set_not_only_detect_record(self, dev):
        """
        **关键回归**: 看门狗必须直接检查持续豁免集合, 不能只看 detect_record。

        线上实测(2026-10-08, 第一次带 hold 的版本仍卡死):
            battle_wait.py:1128  Start battle process        <- hold_stuck_exempt 执行
            device.py:0234       Wait too long | Waiting for set()  <- detect_record 为空!
        原因: detect_record 只在 stuck_record_clear() 里由 stuck_record_late 重建;
        若点击后没有再触发 clear, detect_record 一直为空, 看门狗就读不到豁免。
        """
        from module.device.device import Device
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        # 直接把 detect_record 清空, 模拟"点击后尚未再触发 clear"的状态
        dev.detect_record = set()
        assert dev.stuck_record_late == {'BATTLE_STATUS_S'}
        dev.stuck_timer._current -= 3600
        dev.stuck_timer._reach_count = dev.stuck_timer.count + 1
        assert Device.stuck_record_check(dev) is False, (
            'detect_record 虽空, 但持续豁免仍在 —— 不得判定卡死')

    def test_battle_status_in_unlimited_list(self):
        from module.device.device import Device
        assert 'BATTLE_STATUS_S' in Device.stuck_unlimited_wait_list

    def test_release_then_watchdog_can_fire(self, dev):
        """释放持续豁免后, 看门狗必须恢复工作(不能永久豁免)。"""
        from module.device.device import Device
        from module.exception import GameStuckError
        dev.hold_stuck_exempt('BATTLE_STATUS_S')
        dev.release_stuck_exempt('BATTLE_STATUS_S')
        dev.detect_record = set()
        dev.stuck_timer._current -= 3600
        dev.stuck_timer._reach_count = dev.stuck_timer.count + 1
        dev.stuck_timer_long._current -= 4000
        dev.stuck_timer_long._reach_count = dev.stuck_timer_long.count + 1
        with pytest.raises(GameStuckError):
            Device.stuck_record_check(dev)
