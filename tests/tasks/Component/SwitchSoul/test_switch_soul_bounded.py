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
