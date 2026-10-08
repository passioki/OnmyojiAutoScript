# -*- coding: utf-8 -*-
"""switch_soul 找阵容循环必须有界(回归测试)。

线上实测(2026-10-08 11:55, 日轮之陨, 恋鸟树)
------------------------------------------
    11:55:46.346  Swipe up to find target team
    11:55:47.398  [SS_TEAM_NAME] ['安魂冢', '真蛇', '安魂冢']
    11:55:47.399  OCR [SS_TEAM_NAME] detected in None
    ... 同一动作每秒重复约 2 次, 持续到 11:56:47 ...
    11:56:47.005  Wait too long | Waiting for set()
    ERROR         GameStuckError -> 重启游戏

原因: `switch_soul_by_name` 里"找目标阵容"与"点中目标阵容"都是 `while 1`,
目标阵容名(日轮)不在列表里时(OCR 失配 / 配置写错 / 该阵容属于别的分组),
会一直滑动或点击, 直到 device 的卡死看门狗把**整局任务**判死并重启游戏。

切换御魂是可选项, 找不到就跳过, 让任务继续跑, 远好于重启游戏。
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

SRC = REPO_ROOT / 'tasks' / 'Component' / 'SwitchSoul' / 'switch_soul.py'


def _code_lines():
    """去掉注释行后的源码行(避免把说明文字当成代码)。"""
    out = []
    for raw in SRC.read_text(encoding='utf-8').splitlines():
        s = raw.strip()
        if s.startswith('#'):
            continue
        out.append(re.sub(r'\s+#.*$', '', s))
    return out


def _function_body(name: str) -> str:
    """取某个方法的函数体文本(到下一个同缩进 def 为止)。"""
    lines = SRC.read_text(encoding='utf-8').splitlines()
    start = None
    for i, l in enumerate(lines):
        if re.match(rf'\s*def {name}\s*\(', l):
            start = i
            break
    assert start is not None, f'未找到 {name}'
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = []
    for l in lines[start + 1:]:
        if l.strip() and (len(l) - len(l.lstrip())) <= indent and \
                re.match(r'\s*(def|class) ', l):
            break
        body.append(l)
    return '\n'.join(body)


class TestBidirectionalScan:
    """
    核心回归: 查找必须"先看当前屏, 再双向扫描"。

    线上实测 2026-10-08 11:55(日轮之陨, 用户确认)：
      阵容列表一屏只显示约 3 个预设, 目标 '日轮' **本来就在列表里、且在最上面**。
      原实现是"先滑再看"且只朝 SWIPE_UP(朝"更靠前"方向翻) 一个方向 ——
      于是第一下就把 '日轮' 推到了可视区上方, 之后永远 OCR 不到,
      循环空转 60s 被卡死看门狗判死并重启游戏。
    """

    def test_check_screen_before_any_swipe(self):
        """当前屏已有目标时, **不得**发生任何滑动。"""
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT))

        from tasks.Component.SwitchSoul.switch_soul import (
            SS_SCAN_MAX_SWIPES, SwitchSoul,
        )

        order = []

        class _Rule:
            def detect_and_ocr(self, image):
                order.append('ocr')
                return [type('R', (), {'ocr_text': '日轮'})()]

        class _Owner:
            device = type('D', (), {'image': None})()

            def screenshot(self):
                order.append('screenshot')

            def swipe(self, *a, **kw):
                order.append('swipe')

            _scan_for_name = SwitchSoul._scan_for_name

        assert _Owner()._scan_for_name(_Rule(), '日轮',
                                       'SWIPE_FWD', 'SWIPE_BWD') is True
        assert 'swipe' not in order, (
            f'当前屏已有目标时不应滑动, 实际动作序列={order}')
        assert order[0] == 'screenshot', f'应先截图, 实际={order}'

    def test_scans_both_directions_when_missing(self):
        """当前屏没有目标时, 必须朝两个方向都找过。"""
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT))

        from tasks.Component.SwitchSoul.switch_soul import (
            SS_SCAN_MAX_SWIPES, SwitchSoul,
        )

        swipes = []

        class _Rule:
            def detect_and_ocr(self, image):
                return [type('R', (), {'ocr_text': '别的'})()]

        class _Owner:
            device = type('D', (), {'image': None})()

            def screenshot(self):
                pass

            def swipe(self, target, *a, **kw):
                swipes.append(target)

            _scan_for_name = SwitchSoul._scan_for_name

        assert _Owner()._scan_for_name(_Rule(), '日轮',
                                       'FWD', 'BWD', swipe_sleep=0) is False
        assert swipes.count('FWD') == SS_SCAN_MAX_SWIPES, '应朝前扫满'
        assert swipes.count('BWD') == SS_SCAN_MAX_SWIPES, (
            '没找到时必须换方向回扫 —— 否则划过头就再也回不来')

    def test_finds_target_when_scrolled_to_far_end(self):
        """
        目标在"反方向"那一端时也能找到 —— 这正是"划过头"的场景。

        模拟: 目标只在朝 BWD 回扫若干次后才出现。
        """
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT))

        from tasks.Component.SwitchSoul.switch_soul import (
            SS_SCAN_MAX_SWIPES, SwitchSoul,
        )

        state = {'swipes': 0}

        class _Rule:
            def detect_and_ocr(self, image):
                # 只有朝 BWD 滑过 3 次后才"看得到"目标
                text = '日轮' if state['swipes'] >= SS_SCAN_MAX_SWIPES + 3 else '别的'
                return [type('R', (), {'ocr_text': text})()]

        class _Owner:
            device = type('D', (), {'image': None})()

            def screenshot(self):
                pass

            def swipe(self, target, *a, **kw):
                state['swipes'] += 1

            _scan_for_name = SwitchSoul._scan_for_name

        assert _Owner()._scan_for_name(_Rule(), '日轮',
                                       'FWD', 'BWD', swipe_sleep=0) is True, (
            '换成双向扫描后, 目标在反方向也应能找到')


class TestScanPacing:
    """
    扫描节奏必须足够慢。

    线上实测(2026-10-08, 用户判断"滑动速度过快"):
      原实现用 `swipe(SWIPE_UP, 0.3)` 且滑完**立刻**截图。0.3 秒的冷却意味着几乎
      不停顿地连滑, 而列表还在惯性滚动 —— 目标可能从未被渲染成一帧静止画面,
      OCR 自然一直读不到。对照同一函数里"滑到列表顶部"那段的
      `swipe(..., 2)` + `sleep(2.5)`(约 4 秒一次)是能正常收敛的。
    """

    def test_settle_delay_after_each_swipe(self):
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT))

        from tasks.Component.SwitchSoul.switch_soul import SwitchSoul

        order = []

        class _Rule:
            def detect_and_ocr(self, image):
                order.append('ocr')
                return [type('R', (), {'ocr_text': '别的'})()]

        class _Owner:
            device = type('D', (), {'image': None})()

            def screenshot(self):
                order.append('screenshot')

            def swipe(self, target, interval=None):
                order.append('swipe')

            _scan_for_name = SwitchSoul._scan_for_name

        import tasks.Component.SwitchSoul.switch_soul as _ss
        # 把 settle 换成一个记录点, 验证"滑动 -> 等待 -> 判读"的顺序
        orig_sleep = _ss.sleep
        try:
            _ss.sleep = lambda s: order.append(f'sleep({s})')
            _Owner()._scan_for_name(_Rule(), '日轮', 'FWD', 'BWD',
                                    swipe_sleep=1.5)
        finally:
            _ss.sleep = orig_sleep

        # 每次 swipe 之后必须紧跟一次 sleep, 再才是 screenshot/ocr
        for i, act in enumerate(order):
            if act == 'swipe':
                nxt = order[i + 1] if i + 1 < len(order) else None
                assert nxt == 'sleep(1.5)', (
                    f'swipe 之后应等待列表停稳再判读, 实际下一个动作={nxt}; '
                    f'序列={order[:12]}')

    def test_slow_swipe_interval_is_passed(self):
        """滑动冷却必须显式传入且明显大于原来的 0.3。"""
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT))

        import tasks.Component.SwitchSoul.switch_soul as _ss

        assert hasattr(_ss, 'SS_SCAN_SWIPE_INTERVAL')
        assert _ss.SS_SCAN_SWIPE_INTERVAL >= 1.0, (
            f'滑动冷却应明显放慢(原实现 0.3), 实际 {_ss.SS_SCAN_SWIPE_INTERVAL}')
        assert hasattr(_ss, 'SS_SCAN_SETTLE')
        assert _ss.SS_SCAN_SETTLE >= 1.0

    def test_interval_actually_passed_to_swipe(self):
        """`_scan_for_name` 必须把冷却值传给 swipe, 而不是用默认(无冷却)。"""
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT))

        from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
        import tasks.Component.SwitchSoul.switch_soul as _ss

        got = []

        class _Rule:
            def detect_and_ocr(self, image):
                return [type('R', (), {'ocr_text': '别的'})()]

        class _Owner:
            device = type('D', (), {'image': None})()

            def screenshot(self):
                pass

            def swipe(self, target, interval=None):
                got.append(interval)

            _scan_for_name = SwitchSoul._scan_for_name

        orig_sleep = _ss.sleep
        try:
            _ss.sleep = lambda s: None
            _Owner()._scan_for_name(_Rule(), '日轮', 'FWD', 'BWD')
        finally:
            _ss.sleep = orig_sleep

        assert got, '应发生过滑动'
        assert all(g == _ss.SS_SCAN_SWIPE_INTERVAL for g in got), (
            f'每次滑动都应传入冷却 {_ss.SS_SCAN_SWIPE_INTERVAL}, 实际={set(got)}')


class TestSwitchSoulByBameIsBounded:
    def test_constants_exist(self):
        text = SRC.read_text(encoding='utf-8')
        assert 'SS_TEAM_FIND_MAX_ATTEMPTS' in text
        assert 'SS_SOUL_SWITCH_TIMEOUT' in text

    def test_no_unbounded_find_loops(self):
        """
        每个 `while 1` 必须至少满足下列之一, 否则就是"会一直转"的写法:

        A) 有显式上界: `for _ in range(...)` 或 `Timer(...)` + `reached()`
        B) 有状态变化收敛判据: 对比"本轮识别结果"与"上一轮"相等即 break
           (滑动找列表的常规写法, 正常流程能退出)

        裸 `while 1` + 仅靠"识别到目标才退出"是最危险的: 目标识别不到就永远出不来
        (线上 2026-10-08 就是这么把整局任务拖到看门狗重启游戏的)。
        """
        body = _function_body('switch_soul_by_name')
        lines = [re.sub(r'\s+#.*$', '', l) for l in body.splitlines()]
        offenders = []
        for i, l in enumerate(lines):
            if l.strip() != 'while 1:':
                continue
            # 取循环体: 到缩进回退为止
            indent = len(lines[i]) - len(lines[i].lstrip())
            chunk = []
            for x in lines[i + 1:]:
                if x.strip() and (len(x) - len(x.lstrip())) <= indent:
                    break
                chunk.append(x)
            text = ' '.join(c.strip() for c in chunk)
            bounded = ('range(' in text and 'MAX_ATTEMPTS' in text) or \
                      bool(re.search(r'\w*timer\w*\.reached\(\)', text, re.I))
            # B) 状态变化收敛: 出现 `== last_...` / `!= last_...` 之类的比较
            converges = bool(re.search(r'==\s*last_\w+', text)) or \
                        bool(re.search(r'last_\w+\s*==', text))
            if not (bounded or converges):
                offenders.append((i, text[:120]))
        assert not offenders, (
            'switch_soul_by_name 里存在"既无上界、又无状态变化收敛"的 while 1, '
            f'目标识别不到时会无限循环直到看门狗重启游戏: {offenders}')

    def test_find_loop_has_explicit_giveup(self):
        """找不到目标阵容时必须明确跳过并留日志, 而不是默默卡住。"""
        body = _function_body('switch_soul_by_name')
        assert '跳过本次切换' in body, '缺少"找不到就跳过"的处理'
        assert "logger.warning" in body

    def test_switch_phase_has_timer(self):
        """切换御魂阶段必须有时间上限。"""
        body = _function_body('switch_soul_by_name')
        assert 'SS_SOUL_SWITCH_TIMEOUT' in body
        assert 'Timer(' in body


class TestCallersTolerateSkip:
    """调用方不检查返回值, 因此"跳过切换"不会破坏上层流程。"""

    def test_callers_do_not_branch_on_result(self):
        calls = []
        for p in (REPO_ROOT / 'tasks').rglob('script_task.py'):
            text = p.read_text(encoding='utf-8')
            for i, l in enumerate(text.splitlines(), 1):
                if 'run_switch_soul' in l and not l.strip().startswith('#'):
                    calls.append((p, i, l.strip()))
        assert calls, '应能找到 run_switch_soul 的调用点'
        for p, i, l in calls:
            assert not re.match(r'\s*(if|while|assert)\b.*run_switch_soul', l), (
                f'{p.name}:{i} 依赖了 run_switch_soul 的返回值; '
                f'当前实现是无返回值的, 跳过切换需要调用方能容忍')
