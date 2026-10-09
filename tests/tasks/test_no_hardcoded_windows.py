# -*- coding: utf-8 -*-
"""4-F: 任务内的**硬编码时段**必须删除, 统一由调度器按 `meta.py` 的 window 裁决。

## 为什么

此前任务把"什么时候开放"写在自己的 `script_task.py` 里, 例:

    DemonRetreat/script_task.py:
        current_day_of_week = current_date.weekday()   # 0=周一
        if current_day_of_week == 5: pass              # 只有周六
        else:
            days_until_saturday = 5 - current_day_of_week   # 或 +7
            self.custom_next_run(..., time_delta=days_until_saturday)
            raise TaskEnd

问题:
  1. **两套机制** —— 调度器有 `AvailabilityWindow`, 任务里又自己判一次
  2. 时段是**游戏机制**, 散落在任务逻辑里; 新增活动要改多处
  3. `raise TaskEnd` 让任务"跑一次就退", 调度器只能靠 `custom_next_run` 猜

现在: 时段写在 `meta.py` 的 `TaskSpec.window`, 由 `Config._align_to_window()`
统一裁决（4-A/4-C 已做）。

## 本测试覆盖

1. `DemonRetreat` 已清理干净（无 `custom_next_run` / `days_until` / `weekday()`）
2. `meta.py` 的 window 与旧逻辑**语义一致**（周六 19:00-20:00）
3. 清理后的排期与旧逻辑**结果相同**（等价性回归）
4. 反向守卫: 清理过的文件里**不该**再出现第二套时段判断
"""
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# ⚠ 本文件在 `tests/tasks/`, 比其他 `tests/module/config/` 的测试**浅一层** ——
#   所以是 `parents[2]` 而不是 `parents[3]`。
#   （踩过: 写成 parents[3] 会得到 `D:\OAS-dev`, 报 FileNotFoundError。）
REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# 已清理的任务（随进度增加）
CLEANED = ('DemonRetreat',)

# 触发"第二套机制"的关键词（在 script_task.py 里出现即为漏改）
FORBIDDEN = ('custom_next_run', 'days_until')


def code_only(text: str) -> str:
    """剥掉注释（`#` 整行/行内）—— 否则"说明我删了什么"的注释会被误判。"""
    out = []
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('#'):
            continue
        i = line.find('  # ')
        if i != -1:
            line = line[:i]
        out.append(line)
    return '\n'.join(out)


class TestNoSecondMechanism:
    """★ 清理过的任务里**不该**再有第二套时段判断。"""

    @pytest.mark.parametrize('task', CLEANED)
    def test_no_custom_next_run(self, task):
        src = code_only((REPO / 'tasks' / task / 'script_task.py')
                        .read_text(encoding='utf-8'))
        leaked = [k for k in FORBIDDEN if k in src]
        assert not leaked, (
            f'{task}/script_task.py 里仍有第二套排期机制: {leaked}\n'
            f'（时段应统一由 meta.py 的 TaskSpec.window + _align_to_window 裁决）')

    @pytest.mark.parametrize('task', CLEANED)
    def test_no_weekday_branch_for_scheduling(self, task):
        """★ 不该用 `weekday()` 决定**能不能跑**。

        `weekday()` 本身不是禁品（有时用来选 boss / 选区域, 如
        `DemonEncounter` 按星期选鬼王）。禁止的是"用它决定跑不跑" ——
        那种分支一定会伴随 `custom_next_run` 或 `raise TaskEnd`。
        这里检查: 若出现 `weekday()` 与 `TaskEnd` 紧邻, 即视为漏改。
        """
        src = code_only((REPO / 'tasks' / task / 'script_task.py')
                        .read_text(encoding='utf-8'))
        if 'weekday()' not in src:
            return
        # 有 weekday 就该有正当用途 —— 与 TaskEnd 同段出现即可疑
        for m in re.finditer(r'weekday\(\)', src):
            tail = src[m.start():m.start() + 400]
            assert 'raise TaskEnd' not in tail, (
                f'{task}: `weekday()` 附近有 `raise TaskEnd` —— '
                f'像是"不在时段就退出"的第二套机制（应删, 交给调度器）')


class TestDemonRetreatEquivalence:
    """★ 等价性: 清理后的排期与旧逻辑**结果相同**。

    旧逻辑（手工算到周六）:
        days_until_saturday = 5 - weekday      (周一到周五)
                            = 5 - weekday + 7  (周日)
        target = (now + days_until_saturday).replace(hour=19, minute=0)
        next_run = target

    新逻辑:
        next_run = align_to_window(now + success_interval)
    """

    @pytest.fixture()
    def config(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_window_is_saturday_evening(self):
        from module.config import task_catalog as TC
        spec = TC.get_spec('DemonRetreat')
        assert spec is not None and spec.window is not None, '缺 window'
        days = set()
        for w in spec.windows_effective:
            days |= set(w.days)
        assert days == {5}, f'应只在周六开放, 实际 {sorted(days)}'
        assert '周六' in spec.window_describe

    @pytest.mark.parametrize('day_offset,label', [
        (0, '周一'), (2, '周三'), (6, '周日'),
    ])
    def test_non_saturday_aligns_to_saturday(self, config, day_offset, label):
        """非周六 -> 对齐到周六（旧的 `days_until_saturday` 逻辑）。"""
        # 2026-10-05 是周一
        now = datetime(2026, 10, 5, 10, 0) + timedelta(days=day_offset)
        got = config._align_to_window('demon_retreat', now)
        assert got.weekday() == 5, f'{label} 应推到周六, 实际 {got}'
        assert (got.hour, got.minute) == (19, 0), f'应是 19:00, 实际 {got}'
        assert got > now, '不能往前推'

    def test_saturday_success_goes_to_next_saturday(self, config):
        """周六跑完 -> 下周六（不能排到明天）。"""
        now = datetime(2026, 10, 10, 19, 30)      # 周六
        got = config._align_to_window(
            'demon_retreat', (now + timedelta(days=1)).replace(microsecond=0))
        assert got.weekday() == 5 and got.day == 17, \
            f'应推到 10-17（下周六）, 实际 {got}'

    def test_old_and_new_agree(self, config):
        """★ 直接比对旧算法与新算法的结果。"""
        for day_offset in range(7):
            now = datetime(2026, 10, 5, 10, 0) + timedelta(days=day_offset)
            wd = now.weekday()
            # 旧: 手工算到周六
            if wd == 5:
                continue
            delta = (5 - wd) if wd < 5 else (5 - wd + 7)
            old = (now + timedelta(days=delta)).replace(
                hour=19, minute=0, second=0, microsecond=0)
            # 新
            new = config._align_to_window('demon_retreat', now)
            assert new == old, (
                f'weekday={wd}: 旧算法 {old} vs 新算法 {new} —— 不等价')
