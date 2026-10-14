# -*- coding: utf-8 -*-
"""★★ 守卫：流程控制面（`module/flow/**`）—— SPEC §1.19 的 C1 / C4 / C6 / C7。

## ★ 为什么这四条守卫必须存在

★ SPEC §1.19-四 的**红灯 1** = ★ "**出口语义靠各任务自觉**"
  —— ★ 实测：`success = False` 的次数在 8 个任务里是 `4/1/6/3/0/0/0/4`，
  ★ 而 `AreaBoss` 的出口**返回 `True`/`False`/`None` 三种混用**。
★ ⇒ ★ 本守卫把"**什么出口 ⇒ 什么结果**"钉死成**表**：
  ★ 谁想把 `RESOURCE_EMPTY` 改成失败，**必须改 `finish()`**，
  ★ 而改 `finish()` ⇒ ★ 这里**立刻变红**（★ 用户裁定："没票算成功"）。

## ★★ 怎么保证不空转（本项目铁律：注入破坏后必须真红）

★ 判据**不查源码文本**，而是**调 `finish()` 拿真结果** + ★ 断言**全 8 个出口都有映射**
  + ★ 断言**返回值只能是三种 `Outcome` 之一**（★ 不许有人偷偷塞第四种）。
"""
import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

from module.flow import (  # noqa: E402
    EXIT_TEXT_ZH, OUTCOME_TEXT_ZH, Exit, Match, Outcome, Verdict, finish,
)

#: ★★ 出口 → 期望结果（★ 这张表 = 用户裁定 + 任务既有行为的**固化**）
EXPECTED = {
    Exit.PAUSED: Outcome.DONE,            # ★ 8 任务实测：暂停不改 success
    Exit.COUNT_DONE: Outcome.DONE,        # ★ 打满 = 做完了
    Exit.TIME_DONE: Outcome.DONE,         # ★ 时间到 = 收工（不是失败）
    Exit.RESOURCE_EMPTY: Outcome.EXHAUSTED,  # ★★ 用户裁定："没票算成功"
    Exit.STATE_LOST: Outcome.FAILED,      # ★ Orochi 房间没了 = 失败
    Exit.DEP_FAILED: Outcome.FAILED,      # ★ 邀请不到队友 / adb 不可用 = 失败
    Exit.ALREADY_DONE: Outcome.DONE,      # ★ 已上榜/已领完 = 目标已被满足
    Exit.ABORTED: Outcome.FAILED,         # ★ 异常中断 = 失败
}


# ────────────────────────────────── C6 出口
def test_exit_has_exactly_eight_kinds():
    """★ C6：出口必须是**具名的 8 类**（SPEC §1.19-C6；★ 少一类就说明有人删了语义）。"""
    assert len(list(Exit)) == 8, (
        f'★ 出口应为 8 类，实际 {len(list(Exit))} 类：'
        f'{[e.name for e in Exit]}\n'
        '★ 依据 SPEC §1.19-C6（8 类出口来自 8 张流程图的实测归纳）')


def test_every_exit_has_chinese_text():
    """★ 每个出口都要有中文说明（★ 它要上界面/日志 —— 不许留 `paused` 这种英文给用户看）。"""
    missing = [e.name for e in Exit if not EXIT_TEXT_ZH.get(e)]
    assert not missing, f'★ 这些出口没有中文说明：{missing}'


# ────────────────────────────────── C7 结果（★ 红灯 1 的钉子）
@pytest.mark.parametrize('exit_,expected', list(EXPECTED.items()),
                         ids=[e.name for e in EXPECTED])
def test_exit_maps_to_expected_outcome(exit_, expected):
    """★★★ 核心：★ 每个出口 → 结果的映射必须与**裁定 + 既有行为**一致。"""
    got = finish(exit_)
    assert got is expected, (
        f'★★★ {exit_.name} 的结果应为 {expected.name}，实际 {got.name}\n'
        '★ 若你是有意改语义 ⇒ ★ 请**同时改 SPEC §1.19-C7 与 §4.5**，'
        '★ 并说明依据（★ 尤其 `RESOURCE_EMPTY`：★ 用户裁定"没票算成功"）')


def test_finish_always_returns_one_of_three_outcomes():
    """★ 结果只能三态（★ 防有人偷偷加第四种或返回 `None`）。"""
    for e in Exit:
        got = finish(e)
        assert isinstance(got, Outcome), f'★ {e.name} 返回了 {got!r}'


def test_resource_empty_is_success_and_named_exhausted():
    """★★★ 用户裁定：★ "没票算成功，本来就是清票，票没有了就不用清了。"

    ★ 这条守的是**语义本身**：★ `RESOURCE_EMPTY` ⇒ `EXHAUSTED` ⇒ **`is_success` 为真**
      ★ 且 **不能**是 `DONE`（★ 要能区分"打满了"与"没票了" —— 否则日志分不清）。
    """
    got = finish(Exit.RESOURCE_EMPTY)
    assert got is Outcome.EXHAUSTED, (
        '★★★ `RESOURCE_EMPTY` 必须映射到 `EXHAUSTED`（用户裁定"没票算成功"）')
    assert got is not Outcome.DONE, (
        '★ 不能直接给 `DONE` —— ★ "资源用完"与"正常做完"要能区分（报表/日志要用）')
    assert got.is_success is True, (
        '★★★ `EXHAUSTED` 必须**算成功**（用户裁定）—— 现在它被判成失败了')
    assert got.is_exhausted is True


def test_only_failed_is_not_success():
    """★ `is_success` 的判据只有一条：★ **不是 `FAILED`**（★ 别再写第二套）。"""
    assert [o.name for o in Outcome if not o.is_success] == ['FAILED']


def test_finish_rejects_non_exit():
    """★ 传字符串必须**响亮失败**（★ 否则会静默落进"其余 ⇒ DONE"）。"""
    with pytest.raises(TypeError):
        finish('resource_empty')


def test_outcome_has_chinese_text():
    """★ 每种结果都要有中文说明。"""
    missing = [o.name for o in Outcome if not OUTCOME_TEXT_ZH.get(o)]
    assert not missing, f'★ 这些结果没有中文说明：{missing}'


# ────────────────────────────────── C1 准入
def test_verdict_three_states():
    """★ C1：三态必须都在（★ 尤其**推迟** —— 这一态以前没有名字）。"""
    run = Verdict.run()
    assert run.ok is True and bool(run) is True
    assert run.defer_until is None and run.is_deferred is False

    skip = Verdict.skip('本周已完成')
    assert skip.ok is False and bool(skip) is False
    assert skip.reason == '本周已完成'
    assert skip.is_deferred is False, '★ `skip` **不是** `defer`（一个不排期，一个要排期）'

    from datetime import datetime, timedelta
    when = datetime.now() + timedelta(hours=1)
    defer = Verdict.defer(when, '没票了')
    assert defer.ok is False and bool(defer) is False
    assert defer.defer_until == when
    assert defer.is_deferred is True, '★ `defer` 必须能被识别出来（调度层据此推 next_run）'


def test_verdict_defer_requires_datetime():
    """★ `defer` 传错类型要响亮失败（★ 免得把字符串算成"到点时间"）。"""
    with pytest.raises(TypeError):
        Verdict.defer('2026-10-15 12:00:00', '没票了')


def test_verdict_is_immutable():
    """★ 判据结论是**值**，不是对象状态（★ 防"同一条判据两次结论不同"）。"""
    v = Verdict.run()
    with pytest.raises(Exception):
        v.ok = False       # type: ignore[misc]


# ────────────────────────────────── C4 判断
def test_match_carries_four_things():
    """★ C4：★ 一次判断要能同时带 **成立/分数/命中框/文本**（现在要四种解包方式）。"""
    hit = Match.hit(score=0.93, roi=(10, 20, 30, 40), text='14/15')
    assert bool(hit) is True
    assert hit.ok is True
    assert hit.score == 0.93
    assert hit.roi == (10, 20, 30, 40)
    assert hit.text == '14/15'


def test_match_miss_keeps_score_but_drops_roi():
    """★ 未命中要**留住分数**（★ 调阈值要看"差多少"），★ 且**不留命中框**（★ 免得点空）。"""
    miss = Match.miss(score=0.41, text='')
    assert bool(miss) is False
    assert miss.score == 0.41
    assert miss.roi is None
