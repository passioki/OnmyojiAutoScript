"""SwitchOnmyoji must have a bounded exit path.

Both loops in `SwitchOnmyoji.switch_role` used to be unconditional `while True`.
When the onmyoji/hero tab cannot be reached (stale asset coordinates after a
game UI update, emulator showing a different page, ...), they kept clicking
forever until the global `GameStuckError` watchdog fired roughly two minutes
later, discarding all context about what actually went wrong.

These tests pin the exit conditions: a loop that never finds its target has to
raise a named, catchable `ScriptError` instead of spinning, and the happy path
must keep working unchanged.
"""
import pytest

from module.base.timer import Timer
from module.exception import ScriptError
from tasks.Component.SwitchOnmyoji.config import Onmyoji
from tasks.Component.SwitchOnmyoji.switch_onmyoji import SwitchOnmyoji


class ScriptedSwitch(SwitchOnmyoji):
    """Double that replays a fixed sequence of `appear` results.

    `screenshot` and every click are no-ops, so the test exercises the real
    loop control flow of `switch_role` without a Config, a Device or a game.
    """

    def __init__(self, appear_results, timeout=5):
        """
        :param timeout: 超时守卫的秒数。

        ★★ **默认不能用 0** —— 这是个踩过的坑 ★★

        `Timer.reached()` 的判断是 `time.time() - current > limit`，
        所以 `limit=0` 意味着**只要时钟走过任何一个 tick 就算超时**。

        于是"健康流程"的测试会跑在 **0 秒边界**上:
        平时能过（调用之间没跨过时钟 tick），但一旦机器有负载 /
        被调度器抢占，就会抛 `ScriptError` —— **flaky**。

        （现象: `test_switch_role_still_switches_when_the_flow_is_healthy`
          在全量跑时偶发失败，单独跑却总是通过。）

        所以:
        * **期望成功**的用例用默认 `timeout=5`（远大于测试耗时，守卫不会误触发）
        * **期望超时**的用例显式传 `timeout=0`（那正是被测行为）
        """
        # deliberately skip BaseTask.__init__: it needs a real Config/Device
        self._appear_results = list(appear_results)
        self._appear_calls = 0
        self.switch_clicks = 0
        self.battle_clicks = 0
        self.ui_clicks = 0
        self.SWITCH_TAB_TIMEOUT = timeout
        self.SWITCH_BATTLE_TIMEOUT = timeout

    def _next_appear(self, button):
        self._appear_calls += 1
        if not self._appear_results:
            return False
        return self._appear_results.pop(0)

    def screenshot(self):
        pass

    def appear(self, button, interval=None, **kwargs):
        return self._next_appear(button)

    def appear_then_click(self, button, interval=None, **kwargs):
        self.switch_clicks += 1
        return True

    def click(self, button, interval=None, **kwargs):
        self.battle_clicks += 1
        return True

    def ui_click(self, button1, button2, interval=None, **kwargs):
        self.ui_clicks += 1
        return True


def test_switch_role_raises_when_battle_list_never_appears():
    # ★ 显式 `timeout=0` —— 这个用例**就是要测超时**,
    #   所以用 0 让守卫立刻触发（而不是干等 5 秒）。
    task = ScriptedSwitch(appear_results=[], timeout=0)

    with pytest.raises(ScriptError):
        task.switch_role(role=None, battle_dict={'x': object()}, check_img=object())


def test_switch_role_raises_when_check_icon_never_appears():
    # battle icon visible, confirm icon never does
    # ★ 同上: 这个用例测的是**第二个**循环的超时。
    task = ScriptedSwitch(appear_results=[True], timeout=0)

    with pytest.raises(ScriptError):
        task.switch_role(role=Onmyoji.KAGURA, battle_dict={Onmyoji.KAGURA: object()}, check_img=object())


def test_switch_role_still_switches_when_the_flow_is_healthy():
    # appear order: battle icon, then confirm icon -> no extra clicks needed
    #
    # ★ 用**默认 timeout=5**, 不要用 0 ——
    #   0 会让"健康流程"的用例跑在 0 秒边界上而**偶发失败**（flaky）。
    #   详见 `ScriptedSwitch.__init__` 的 docstring。
    task = ScriptedSwitch(appear_results=[True, True])

    task.switch_role(role=Onmyoji.KAGURA, battle_dict={Onmyoji.KAGURA: object()}, check_img=object())

    assert task.switch_clicks == 0
    assert task.battle_clicks == 0
    assert task.ui_clicks == 0


def test_switch_role_clicks_the_battle_icon_when_confirm_icon_is_absent():
    # appear order: battle icon, not-confirm, battle icon -> ui_click back path
    # ★ 默认 timeout=5（同上, 这是"期望成功"的路径）
    task = ScriptedSwitch(appear_results=[True, False, True])

    task.switch_role(role=Onmyoji.KAGURA, battle_dict={Onmyoji.KAGURA: object()}, check_img=object())

    assert task.switch_clicks == 0
    assert task.ui_clicks == 1


def test_timeouts_are_not_shared_between_instances():
    a = ScriptedSwitch(appear_results=[])
    b = ScriptedSwitch(appear_results=[])

    assert a.SWITCH_TAB_TIMEOUT is not None
    assert b.SWITCH_TAB_TIMEOUT is not None


def test_default_timeout_is_not_zero():
    """
    ★ 回归守卫: 默认超时**不能是 0**。

    `Timer.reached()` 是 `time.time() - current > limit` ——
    `limit=0` 意味着"走过任何时钟 tick 就算超时",
    于是"健康流程"的用例跑在 0 秒边界上而**偶发失败**。

    （这就是 `test_switch_role_still_switches_when_the_flow_is_healthy`
      全量跑偶发红、单独跑总是绿的原因。）
    """
    assert ScriptedSwitch(appear_results=[]).SWITCH_TAB_TIMEOUT > 0
    assert ScriptedSwitch(appear_results=[]).SWITCH_BATTLE_TIMEOUT > 0
