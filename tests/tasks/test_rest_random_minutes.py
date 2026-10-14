# -*- coding: utf-8 -*-
"""★ 守卫：休息时长**范围内随机 ±20%**（台账 `N9-3` · 用户 [10-14] 第 3 条）。

## ★★ 用户原话

> "**添加任务的休息时间做成范围内随机上下20%**"

## ★ 规则（本文件钉住的）

| # | 规则 |
|---|---|
| **R1** | ★ 实际休息分钟 = `base × (1 ± 0.20)` 内**均匀随机**，**四舍五入到整数分钟** |
| **R2** | ★ **下限 1 分钟** —— ★ 不许出现"0 分钟休息"（`base=1` 也要休 1 分钟）|
| **R3** | ★ `base <= 0` ⇒ ★ **原样返回**（★ 调用方负责兜底默认 30）|
| **R4** | ★★ **配置里的 `minutes` 不许被改写** —— ★ 随机的只是"这一轮实际睡多久"<br>★ 为什么：★ 若写回配置 ⇒ 切页/重启后**越随机越偏**（游走），且用户看不到自己填的数 |
| **R5** | ★★ **实际睡的是随机后的值**（`script_task.py` 里 `total_s = actual * 60`）|

★ 为什么用 `random.uniform`（均匀）而不是正态：★ 用户说的是
  "**范围内**随机上下 20%" ⇒ ★ 均匀分布**的均值就是 `base`**（不系统性偏长/偏短）。
"""
import ast
import logging
import random
import statistics
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]   # tests/tasks/x.py -> 仓库根
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

from tasks.Rest.script_task import (  # noqa: E402
    REST_JITTER, randomized_rest_minutes)

SRC_P = REPO / 'tasks' / 'Rest' / 'script_task.py'


# ─────────────────────────── R1 边界：必须在 ±20% 内
@pytest.mark.parametrize('base', [1, 5, 30, 60, 120])
def test_stays_within_jitter_band(base):
    """★★ 核心：★ 无论随机多少次，★ 结果必须落在 `base ± 20%` 内（整数）。"""
    low = base * (1 - REST_JITTER)
    high = base * (1 + REST_JITTER)
    seen = set()
    for _ in range(400):
        v = randomized_rest_minutes(base)
        seen.add(v)
        assert isinstance(v, int), f'★ 必须是整数分钟，实际 {v!r}'
        # ★ 四舍五入 ⇒ 允许 1 分钟的取整余量
        assert low - 0.5 <= v <= high + 0.5, (
            f'★ base={base} 的结果 {v} 超出了 ±20% 区间 '
            f'[{low:.1f}, {high:.1f}]（含取整余量）')
    assert len(seen) > 1 or base <= 2, (
        f'★ base={base} 时结果应有变化（"随机"不能退化成固定值）')


# ─────────────────────────── R1 均值：不许系统性偏
def test_mean_is_centered_on_base():
    """★ 均值必须**接近 base**（★ 均匀分布 ⇒ 不系统性偏长/偏短）。

    ⚠ 这是"随机"是否**有意义**的判据：★ 若实现写成"只加不减"
      （`base*(1+rand*0.2)`），均值会偏 **+10%** —— ★ 那与用户说的
      "**上下**20%"不符。
    """
    base = 30
    vals = [randomized_rest_minutes(base) for _ in range(3000)]
    mean = statistics.mean(vals)
    assert abs(mean - base) <= base * 0.05, (
        f'★ 均值应接近 {base}（±5% 内），实际 {mean:.2f} '
        f'—— ★ 检查是否用了"只加不减"的写法')


# ─────────────────────────── R2 下限 1 分钟
@pytest.mark.parametrize('base', [1, 2, 3])
def test_never_below_one_minute(base):
    """★ 下限 1 分钟：★ 小 base 也不许出现 0（0 = 不休息，与用户预期不符）。"""
    for _ in range(400):
        assert randomized_rest_minutes(base) >= 1


# ─────────────────────────── R3 非正数原样返回
@pytest.mark.parametrize('base', [0, -1, -30])
def test_non_positive_returns_as_is(base):
    """★ `base <= 0` ⇒ ★ 原样返回（★ 兜底默认由调用方负责，本函数不猜）。"""
    assert randomized_rest_minutes(base) == base


# ─────────────────────────── R4 源码：配置不许被改写
def test_source_does_not_write_minutes_back():
    """★★ 源码级：★ `randomized_rest_minutes` 只**返回**值，
    ★ **不许**往里传"配置对象"或写回 `scheduler.target`。

    ★ 判据：★ 函数签名只有 `base` / `jitter` 两个参数（都是标量）
      ⇒ ★ 它**没有能力**碰配置（比"搜关键字"可靠）。
    """
    tree = ast.parse(SRC_P.read_text(encoding='utf-8'))
    fn = next((n for n in tree.body
               if isinstance(n, ast.FunctionDef)
               and n.name == 'randomized_rest_minutes'), None)
    assert fn is not None, '★ 应能找到 `randomized_rest_minutes`'
    args = [a.arg for a in fn.args.args]
    assert args == ['base', 'jitter'], (
        f'★ 它只该接标量参数（不许接 config/model）—— 实际 {args}')


# ─────────────────────────── R5 源码：睡的是随机后的值
def test_source_sleeps_the_randomized_value():
    """★★ 源码级：★ `total_s` 必须由**随机后的 `actual`** 算出来。

    ★ 判据（行序 + 内容）：★ 必须先有 `actual = randomized_rest_minutes(minutes)`，
      再有 `total_s = actual * 60`。
    """
    src = SRC_P.read_text(encoding='utf-8')
    lines = [l.split('#')[0] for l in src.split('\n')]
    call_idx = next((i for i, l in enumerate(lines)
                     if 'randomized_rest_minutes(' in l and '=' in l), None)
    total_idx = next((i for i, l in enumerate(lines)
                      if 'total_s =' in l), None)
    assert call_idx is not None, '★ 必须调用 `randomized_rest_minutes`'
    assert total_idx is not None, '★ 应能找到 `total_s =`'
    assert 'actual' in lines[total_idx], (
        f'★ `total_s` 必须由随机后的 `actual` 算出来，实际：'
        f'{lines[total_idx].strip()!r}\n'
        '★ 否则"随机"算了却没用（睡的还是固定值）—— 这正是典型的空转修法')
    assert call_idx < total_idx, '★ 先算随机值，再算总秒数'
