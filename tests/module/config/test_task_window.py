# -*- coding: utf-8 -*-
"""开放时段：游戏机制事实写在 `tasks/*/meta.py`, 不在任务代码里硬编码。

## 背景

此前 **16 个任务**把开放时段硬编码在自己的 `script_task.py` 里, 例:

    DemonRetreat/script_task.py:33   current_day_of_week = current_date.weekday()
    DemonRetreat/script_task.py:42   days_until_saturday = 5 - current_day_of_week
    DemonRetreat/script_task.py:48   self.custom_next_run(..., time_delta=days_until_saturday)

问题:
  1. **两套机制** —— 调度器有 `AvailabilityWindow`（默认全关）, 任务里又自己判一次
  2. 时段是**游戏机制**, 不该散落在任务逻辑里
  3. `raise TaskEnd` 让任务"跑一次就退", 调度器只能靠 `custom_next_run` 猜下次

现在: 时段写在 `meta.py` 的 `TaskSpec.window` 里, 由调度器统一裁决。

## 本测试覆盖

1. `window` 字段存在, 且支持**单段与多段**（Hunt 一天有两段）
2. 已搬过来的 7 个任务确实带 window, 且时段与代码事实一致
3. `TaskSpec.in_window()` / `next_opening()` 对多段正确
4. **`Restart` 没有被错误地写成"允许"两段** —— 它要的是"排除周三维护",
   而 `AvailabilityWindow` 只能表达"允许", 所以它不该进 meta
"""
import sys
from datetime import datetime, time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from module.config import task_catalog as TC                      # noqa: E402
from module.config.availability import AvailabilityWindow         # noqa: E402

# 周一=0 … 周日=6
DAY = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
# 2026-10-05 是周一
MON = datetime(2026, 10, 5)


def at(day_offset: int, hour: int, minute: int = 0) -> datetime:
    return (MON.replace(hour=hour, minute=minute)
            + __import__('datetime').timedelta(days=day_offset))


class TestWindowField:
    """`TaskSpec.window` 的基本能力。"""

    def test_field_exists(self):
        import dataclasses
        names = [f.name for f in dataclasses.fields(TC.TaskSpec)]
        assert 'window' in names
        assert 'windows' not in names, '不该有两个字段（window + windows）'

    def test_single_window(self):
        spec = TC.TaskSpec(
            task='X', name_zh='X',
            window=AvailabilityWindow(True, time(19, 0), time(20, 0), days=(5,)))
        assert len(spec.windows_effective) == 1
        assert spec.in_window(at(5, 19, 30)) is True    # 周六 19:30
        assert spec.in_window(at(5, 18, 0)) is False    # 周六 18:00
        assert spec.in_window(at(0, 19, 30)) is False   # 周一 19:30

    def test_multi_window(self):
        """★ Hunt 一天有两段不连续的开放时间, 必须支持。"""
        spec = TC.TaskSpec(
            task='X', name_zh='X',
            window=[
                AvailabilityWindow(True, time(6, 0), time(23, 0), days=(0, 1, 2, 3)),
                AvailabilityWindow(True, time(17, 0), time(23, 0), days=(4, 5, 6)),
            ])
        assert len(spec.windows_effective) == 2
        assert spec.in_window(at(0, 7)) is True         # 周一 07:00（早场）
        assert spec.in_window(at(0, 5)) is False        # 周一 05:00
        assert spec.in_window(at(4, 18)) is True        # 周五 18:00（晚场）
        assert spec.in_window(at(4, 10)) is False       # 周五 10:00
        assert spec.in_window(at(6, 20)) is True        # 周日 20:00

    def test_next_opening_picks_earliest(self):
        spec = TC.TaskSpec(
            task='X', name_zh='X',
            window=[
                AvailabilityWindow(True, time(6, 0), time(23, 0), days=(0,)),
                AvailabilityWindow(True, time(17, 0), time(23, 0), days=(4,)),
            ])
        # 周一 05:00 -> 最近的开放是周一 06:00
        assert spec.next_opening(at(0, 5)).hour == 6
        assert spec.next_opening(at(0, 5)).weekday() == 0

    def test_no_window_means_unrestricted(self):
        spec = TC.TaskSpec(task='X', name_zh='X')
        assert spec.window_describe == '不限时段'
        assert spec.in_window(at(3, 3, 33)) is True     # 任何时刻都可以
        assert spec.next_opening(at(3, 3)) == at(3, 3)


class TestMigratedTasks:
    """已搬到 `meta.py` 的 7 个任务, 时段必须与**代码事实**一致。"""

    MIGRATED = {
        # 任务: (描述要包含的片段, 至少一个"应在窗口内"的时刻, 至少一个"应在窗口外"的时刻)
        'AbyssShadows': ('周五', (4, 19, 5), (0, 19, 5)),      # 周五六日 19:00
        'DemonRetreat': ('周六', (5, 19, 30), (0, 19, 30)),    # 仅周六
        'Dokan': ('周一', (0, 19, 30), (4, 19, 30)),           # 周一~周四
        'Hunt': ('周一', (0, 7, 0), (0, 5, 0)),                # 早晚两段
        'MysteryShop': ('周三', (2, 12, 0), (0, 12, 0)),       # 周三 + 周六
        'Secret': ('周一', (0, 9, 0), (1, 9, 0)),              # 仅周一
        'GuildBanquet': ('每天', (0, 18, 30), (0, 5, 0)),      # 每天 18-22
    }

    def test_all_migrated_have_window(self):
        specs = TC._load_specs()
        missing = [t for t in self.MIGRATED if t not in specs]
        assert not missing, f'这些任务没有 meta.py: {missing}'
        no_window = [t for t in self.MIGRATED if specs[t].window is None]
        assert not no_window, f'这些任务还没搬时段: {no_window}'

    @pytest.mark.parametrize('task', sorted(MIGRATED))
    def test_window_matches_code_fact(self, task):
        desc_frag, inside, outside = self.MIGRATED[task]
        spec = TC.get_spec(task)
        assert spec is not None

        assert desc_frag in spec.window_describe, (
            f'{task} 的时段描述 {spec.window_describe!r} 不含 {desc_frag!r}')

        assert spec.in_window(at(*inside)) is True, (
            f'{task} 在 {DAY[inside[0]]} {inside[1]:02d}:{inside[2]:02d} 应在窗口内; '
            f'实际时段 {spec.window_describe}')
        assert spec.in_window(at(*outside)) is False, (
            f'{task} 在 {DAY[outside[0]]} {outside[1]:02d}:{outside[2]:02d} 应在窗口外; '
            f'实际时段 {spec.window_describe}')

    def test_hunt_has_two_windows(self):
        spec = TC.get_spec('Hunt')
        assert len(spec.windows_effective) == 2, (
            'Hunt 一天有两段（周一~周四早场 / 周五~周日 晚场）, 必须用多段')

    def test_abyss_shadows_covers_friday_saturday_sunday(self):
        spec = TC.get_spec('AbyssShadows')
        days = set()
        for w in spec.windows_effective:
            days |= set(w.days)
        assert days == {4, 5, 6}, f'狭间暗域应只在周五六日开放, 实际 {sorted(days)}'

    def test_dokan_excludes_weekend(self):
        spec = TC.get_spec('Dokan')
        days = set()
        for w in spec.windows_effective:
            days |= set(w.days)
        assert days == {0, 1, 2, 3}, f'道馆应只在周一~周四, 实际 {sorted(days)}'


class TestNoWrongApproximation:
    """★ 防止用 `AvailabilityWindow` **错误地**表达"排除"。"""

    def test_restart_has_no_window(self):
        """`Restart` 的需求是"**避开**周三 06:00-08:00 维护"。

        `AvailabilityWindow` 只能表达"允许"某时段, **不能表达"排除"**。
        写成 `[00:00-06:00, 08:00-23:59]` 并**不能**排除周三整天 ——
        第二段在任何一天都成立, 于是窗口等于"全天", 是**假迁移**。

        它的"维护期顺延"留在代码里（那是"运行中任务被延后", 不是
        "任务什么时候开放"）。本测试钉住这个判断, 防止后人"顺手"加错。
        """
        spec = TC.get_spec('Restart')
        assert spec is not None
        assert spec.window is None, (
            'Restart 不该有 window —— AvailabilityWindow 表达不了"排除周三维护", '
            '硬写会得到"全天开放"的假结果')
