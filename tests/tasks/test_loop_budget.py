# -*- coding: utf-8 -*-
"""`BaseTask._loop_budget` / `_loop_budget_tick` 的行为测试。

这两个原语的作用是把"条件永不成立的 while 1"转成可控的 TaskEnd, 因此测试重点不是
正常路径, 而是三种必须成立的性质:

1. 无点击且判定条件恒不成立时, 超时后抛 TaskEnd, 不会无限循环。
2. 持续点击但界面毫无变化时, 达到点击上限后抛 TaskEnd。这一条是 Device 看门狗
   覆盖不到的场景: click() 会经由 handle_control_check() 重置卡死计时器。
3. 正常有进展时不误杀: 每轮都有点击就不该触发超时。
"""
import time

import pytest

from module.exception import TaskEnd
from tasks.base_task import BaseTask


class _BudgetHarness(BaseTask):
    """只借用 BaseTask 的预算原语, 不触碰 config/device。"""

    def __init__(self):
        pass


@pytest.fixture()
def harness():
    return _BudgetHarness()


def test_timeout_without_any_progress_raises_task_end(harness):
    """条件恒不成立且从不点击 => 超时后必须抛 TaskEnd。"""
    budget = harness._loop_budget('unit: no progress', timeout=0.2, max_clicks=None)
    rounds = 0
    with pytest.raises(TaskEnd):
        while 1:
            rounds += 1
            harness._loop_budget_tick(budget)
            if rounds > 1000:
                pytest.fail('未触发超时, 循环未被兜底')
            time.sleep(0.02)
    assert rounds < 1000


def test_click_limit_despite_progress_raises_task_end(harness):
    """一直点击但界面无变化 => 达到上限即抛 TaskEnd, 不等超时。"""
    budget = harness._loop_budget('unit: click spam', timeout=60, max_clicks=5)
    with pytest.raises(TaskEnd) as exc:
        for _ in range(100):
            harness._loop_budget_tick(budget, clicked=True)
    assert 'click spam' in str(exc.value)


def test_progress_resets_timeout_and_does_not_false_positive(harness):
    """每轮都有点击 => 不应被超时误杀。"""
    budget = harness._loop_budget('unit: healthy progress', timeout=0.3, max_clicks=50)
    for _ in range(20):
        time.sleep(0.05)
        harness._loop_budget_tick(budget, clicked=True)


def test_shared_budget_accumulates_clicks_across_calls(harness):
    """同一预算对象跨多次调用累计点击数, 用于把嵌套循环算进同一份配额。"""
    budget = harness._loop_budget('unit: shared', timeout=60, max_clicks=3)
    harness._loop_budget_tick(budget, clicked=True)
    harness._loop_budget_tick(budget, clicked=True)
    assert budget['clicks'] == 2
    with pytest.raises(TaskEnd):
        harness._loop_budget_tick(budget, clicked=True)


def test_budget_is_isolated_between_instances(harness):
    """不同预算对象互不影响。"""
    a = harness._loop_budget('unit: a', timeout=0.1, max_clicks=2)
    b = harness._loop_budget('unit: b', timeout=0.1, max_clicks=2)
    harness._loop_budget_tick(a, clicked=True)
    assert a['clicks'] == 1
    assert b['clicks'] == 0
