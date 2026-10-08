# -*- coding: utf-8 -*-
"""battle completion 兜底逻辑的回归测试。

背景(线上实测)
--------------
日轮之陨组队时, member 打完一场后卡在 completion 阶段:
  * 日志停在 `Battle completion process`, 之后 60 秒完全静默
  * 期间没有任何点击记录, 最后被 device 的卡死看门狗抛 GameStuckError
  * 结果是**整局任务被判卡死并重启游戏** → member 掉线 → 队长邀请等超时

两个改进在这里锁定:
  1. 进入 completion 只记一次日志; 兜底点击每 3 次打一条诊断(之前完全静默,
     出问题时无从知道当时屏幕有没有目标图)。
  2. 兜底点击有上限, 达到上限就按"结束"放行退出本场 —— 主动收尾的代价,
     远小于让看门狗把整局任务判死。
"""
import time
from dataclasses import dataclass

import pytest

from tasks.Component.GeneralBattle.battle_wait import (
    HookSignal,
    OptionCompletionDefault,
    OptionSuccessDefault,
    PerBattleCompletion,
    _COMPLETION_FALLBACK_MAX_CLICKS,
)


# ---------------------------------------------------------------------------
# 最小替身: 只实现 completion 用到的接口, 不碰设备/图像
# ---------------------------------------------------------------------------
class _FakeDevice:
    def __init__(self):
        self.clicks = []

    def click(self, x=None, y=None, control_name=None):
        self.clicks.append((x, y, control_name))


class _FakeRuleClickExclude:
    """固定返回同一个坐标, 便于断言点击次数。"""

    def __init__(self):
        self.n = 0

    def coord(self):
        self.n += 1
        return (100 + self.n, 200)


class _FakeOwner:
    """替代 ScriptTask: completion 只需要 device。"""

    def __init__(self):
        self.device = _FakeDevice()
        self.appear_calls = []
        self.appear_result = False

    def appear(self, rule, **kwargs):
        self.appear_calls.append(rule)
        return self.appear_result


def _force_timer_ready(state):
    """把真实的 Timer(8) 拨到"已到期"。

    必须用真实 Timer —— completion 里有 `isinstance(state.fallback_timer, Timer)`
    守卫, 假对象会触发裸 `raise`(变成 RuntimeError)。
    Timer.reached() 判断 `time.time() - self._current > self.limit`,
    因此把 _current 推到 1 小时前即可稳定到期。
    """
    from module.base.timer import Timer
    assert isinstance(state.fallback_timer, Timer), '应为真实 Timer'
    state.fallback_timer._current = time.time() - 3600
    state.fallback_timer._reach_count = 0


@dataclass
class _Pub:
    class _PerTask:
        count: int = 0

    per_task: object = None

    def __post_init__(self):
        if self.per_task is None:
            self.per_task = _Pub._PerTask()


@dataclass
class _Pri:
    per_battle: object = None
    options: object = None


def _make(options=None, state=None):
    owner = _FakeOwner()
    pub = _Pub()
    pri = _Pri(per_battle=state or PerBattleCompletion(),
               options=options or OptionCompletionDefault())
    return owner, pub, pri


def _run(owner, pub, pri, n=1):
    """调用 completion 处理函数 n 次, 返回最后一次结果。"""
    from tasks.Component.GeneralBattle.battle_wait import BattleWait

    handler = BattleWait._bw_completion_default
    result = None
    for _ in range(n):
        result = handler(owner, pub=pub, pri=pri)
    return result


class TestCheckImgsNone:
    """check_imgs 为 None = 不做进一步确认, 应立即算结束。"""

    def test_returns_done_immediately(self):
        owner, pub, pri = _make()
        assert _run(owner, pub, pri) == HookSignal.DONE

    def test_counts_task(self):
        owner, pub, pri = _make()
        _run(owner, pub, pri)
        assert pub.per_task.count == 1

    def test_no_click(self):
        owner, pub, pri = _make()
        _run(owner, pub, pri)
        assert owner.device.clicks == []

    def test_logs_only_once(self, caplog):
        """进入 completion 只应记一次 'Battle completion process'。

        旧实现每轮循环都打这行, 日志会刷屏; 现在按 entered_at 去重。
        """
        owner, pub, pri = _make(options=OptionCompletionDefault(check_imgs=[]))
        with caplog.at_level('INFO'):
            _run(owner, pub, pri, n=5)
        n = sum('Battle completion process' in r.message for r in caplog.records)
        assert n == 1, f'应只记一次, 实际 {n} 次'


class TestCheckImgsMiss:
    """给了 check_imgs 但全不命中 → 走兜底点击。"""

    def test_sets_entered_at(self):
        owner, pub, pri = _make(options=OptionCompletionDefault(check_imgs=['x']))
        state = pri.per_battle
        assert state.entered_at == 0.0
        _run(owner, pub, pri)
        assert state.entered_at > 0.0

    def test_returns_continue_before_timer(self):
        owner, pub, pri = _make(options=OptionCompletionDefault(check_imgs=['x']))
        assert _run(owner, pub, pri) == HookSignal.CONTINUE
        assert owner.device.clicks == [], '8s 未到不应点击'

    def test_click_after_timer(self):
        owner, pub, pri = _make(options=OptionCompletionDefault(check_imgs=['x']))
        _run(owner, pub, pri)                 # 建立真实的 Timer(8)
        _force_timer_ready(pri.per_battle)
        _run(owner, pub, pri)
        assert len(owner.device.clicks) == 1
        assert pri.per_battle.fallback_clicks == 1

    def test_appear_checked_for_each_img(self):
        owner, pub, pri = _make(
            options=OptionCompletionDefault(check_imgs=['a', 'b', 'c']))
        _run(owner, pub, pri)
        assert owner.appear_calls == ['a', 'b', 'c']


class TestFallbackSafetyValve:
    """兜底点击次数上限 —— 防止与卡死看门狗互相触发。"""

    def test_gives_up_after_max_clicks(self):
        owner, pub, pri = _make(options=OptionCompletionDefault(check_imgs=['x']))
        _run(owner, pub, pri)
        _force_timer_ready(pri.per_battle)

        # 前 MAX 次仍然只是点击
        for _ in range(_COMPLETION_FALLBACK_MAX_CLICKS):
            r = _run(owner, pub, pri)
            assert r == HookSignal.CONTINUE
            _force_timer_ready(pri.per_battle)
        assert pri.per_battle.fallback_clicks == _COMPLETION_FALLBACK_MAX_CLICKS

        # 第 MAX+1 次放弃兜底, 按结束处理
        r = _run(owner, pub, pri)
        assert r == HookSignal.DONE, '超过上限应放行退出, 而不是无限兜底'
        assert pub.per_task.count == 1

    def test_valve_is_before_watchdog(self):
        """安全阀必须早于 device 的 60s 看门狗触发。

        兜底间隔 8s: 6 次约 48s, 留有余量。
        """
        assert _COMPLETION_FALLBACK_MAX_CLICKS * 8 < 60, (
            f'{_COMPLETION_FALLBACK_MAX_CLICKS} 次 × 8s 应小于看门狗 60s')

    def test_diagnostic_logged(self, caplog):
        """每 3 次兜底点击应有一条诊断日志(含停留时长/命中情况)。"""
        owner, pub, pri = _make(options=OptionCompletionDefault(check_imgs=['x', 'y']))
        _run(owner, pub, pri)
        _force_timer_ready(pri.per_battle)
        with caplog.at_level('WARNING'):
            for _ in range(3):
                _run(owner, pub, pri)
                _force_timer_ready(pri.per_battle)
        msgs = [r.message for r in caplog.records
                if 'Battle completion fallback' in r.message]
        assert msgs, '应打诊断日志'
        assert '已停留' in msgs[0]
        assert 'check_imgs=2' in msgs[0]


class TestStateDefaults:
    def test_new_fields_have_defaults(self):
        """新增字段必须有默认值, 否则 reset_per_battle 构造会失败。"""
        s = PerBattleCompletion()
        assert s.entered_at == 0.0
        assert s.fallback_clicks == 0

    def test_options_default_is_none_check_imgs(self):
        assert OptionCompletionDefault().check_imgs is None
        assert OptionCompletionDefault().excludes == []
