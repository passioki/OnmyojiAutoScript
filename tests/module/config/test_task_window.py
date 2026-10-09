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


def code_only(text: str) -> str:
    """剥掉注释与文档字符串。

    ★ 必须这么做: "我在注释/文档里说明**原来的错误写法**"会让
      `assert '错误写法' not in src` 这类守卫**误判成失败**。
      这个坑在本会话里已踩过 3 次（`exit(1)` / `save_zh_cn(data)` /
      `putChineseTranslate()` / `_configured_start_times`）。
    """
    import re as _re
    text = _re.sub(r'"""[\s\S]*?"""', '', text)
    text = _re.sub(r"'''[\s\S]*?'''", '', text)
    out = []
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('#') or s.startswith('*'):
            continue
        for marker in ('  # ', ' # '):
            idx = line.find(marker)
            if idx != -1:
                line = line[:idx]
                break
        out.append(line)
    return '\n'.join(out)


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
        'AbyssShadows': ('周五', (4, 19, 5), (0, 19, 5)),      # 周五六日 19:00-20:00
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


class TestWindowAlignment:
    """★ 4-C: `next_run` **必须落在窗口内**（用户要求的 K）。

    此前 `next_run = 开始时间 + success_interval`, **完全没看窗口**。窗口只在
    `update_scheduler()` 里当"闸门"（不在时段内就入 waiting）, 但**不改
    `next_run`**。若间隔不是恰好对齐窗口, `next_run` 会漂移、长期落在窗外
    —— **永远错过**那几分钟的窗口（狭间暗域只有 15 分钟）。
    """

    @pytest.fixture()
    def config(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def _align(self, config, task, when):
        key = ''.join('_' + c.lower() if c.isupper() else c
                      for c in task).lstrip('_')
        return config._align_to_window(key, when)

    def test_inside_window_unchanged(self, config):
        """★ 已在窗口内 -> **必须不变**（否则会把合法时刻推走）。"""
        for h, m in ((19, 5), (19, 30), (19, 45)):
            when = datetime(2026, 10, 9, h, m)   # 2026-10-09 = 周五
            got = self._align(config, 'AbyssShadows', when)
            assert got == when, (
                f'{when} 在狭间暗域窗口（周五六日 19:00-20:00）内, 不该被推走; '
                f'实际推到 {got}')

    def test_outside_window_pushed_to_opening(self, config):
        """不在窗口内 -> 推到**下一次开放**。"""
        got = self._align(config, 'AbyssShadows', datetime(2026, 10, 5, 19, 5))
        assert got.weekday() == 4, f'应推到周五, 实际 {got}（{DAY[got.weekday()]}）'
        assert (got.hour, got.minute) == (19, 0), f'应是 19:00, 实际 {got}'

    def test_saturday_only_task(self, config):
        """DemonRetreat 只在周六 -> 周一 19:30 应推到**本周六**。"""
        got = self._align(config, 'DemonRetreat', datetime(2026, 10, 5, 19, 30))
        assert got.weekday() == 5, f'应推到周六, 实际 {DAY[got.weekday()]}'

    def test_weekday_only_task_pushes_over_weekend(self, config):
        """Dokan 只在周一~周四 -> 周五 19:30 应推到**下周一**。"""
        got = self._align(config, 'Dokan', datetime(2026, 10, 9, 19, 30))
        assert got.weekday() == 0, f'应推到周一, 实际 {DAY[got.weekday()]}'
        assert got.day == 12, f'应是下周一（10-12）, 实际 {got}'

    def test_task_without_window_unchanged(self, config):
        """没有窗口的任务 -> 原样返回（**不改变既有行为**）。"""
        when = datetime(2026, 10, 5, 3, 33)
        assert self._align(config, 'Delegation', when) == when

    def test_alignment_never_moves_backwards(self, config):
        """★ 对齐结果**绝不能早于**输入（否则会立刻重复触发）。"""
        import datetime as _dt
        for task in ('AbyssShadows', 'DemonRetreat', 'Dokan', 'Secret', 'Hunt'):
            for d in range(7):
                for h in (0, 6, 12, 18, 19, 20, 23):
                    when = MON + _dt.timedelta(days=d, hours=h)
                    got = self._align(config, task, when)
                    assert got >= when, (
                        f'{task}: 对齐把时间**往前**推了 {when} -> {got}')

    def test_task_delay_calls_alignment(self):
        """★ 回归守卫: `task_delay()` 必须调用 `_align_to_window()`。"""
        src = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')
        i = src.find('def task_delay')
        assert i > 0
        j = src.find('\n    def ', i + 10)
        body = src[i:j]
        assert '_align_to_window' in body, (
            'task_delay 没有对齐窗口 —— next_run 会漂移到窗口外, '
            '任务永远不会在正确的时段被排到')

    def test_no_configured_override_guessing(self):
        """★ `task_window()` **不该**去猜用户配置字段的语义。

        第一版我写了 `_configured_start_times()` 拿 `custom_run_time_friday`
        等字段去移动窗口, 实测把 `AbyssShadows` 窗口从 19:00-19:15 挪到
        19:30-19:45, **连 19:05 这个本来合法的时刻都被推走了**。

        根因: 那些字段的语义（游戏开始时刻? 应用该跑的时刻?）**从代码里
        看不出唯一答案** —— 拿它移动窗口就是在猜, 而猜错会**静默改变调度**。

        ⚠ 检查前**必须剥掉注释与文档字符串**: 我在 `task_window` 的文档里
          说明了"为什么不用它", 那段文字里就含这个方法名 ——
          不剥会把**说明**误判成**代码**（这个坑我踩过好几次了）。
        """
        src = code_only((REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8'))
        assert '_configured_start_times' not in src, (
            '不该再用配置字段移动窗口（语义不明确, 属于猜测）')
        i = src.find('def task_window')
        j = src.find('\n    def ', i + 10)
        body = src[i:j]
        assert 'spec.windows_effective' in body, \
            'task_window 应直接用 meta 的窗口'


class TestResourceWiring:
    """★ 4-D: `Resource` + `next_available()` **接进调度**（此前从没接过）。

    本会话实测: 在 `config.py` / `script.py` 里搜
    `next_available|Resource|RunState` 得到 **0 处** ——
    `resource.py`(364 行) 与 `scheduler_core.py`(291 行) 早就写好、47 个单测,
    但**从没被调度器调用**。这就是典型的"文档说做完了、代码里没接"。
    """

    @pytest.fixture()
    def config(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def _key(self, task: str) -> str:
        return ''.join('_' + c.lower() if c.isupper() else c
                       for c in task).lstrip('_')

    def test_interval_resource_matches_old_interval(self, config):
        """★ 行为可对齐: `interval` 类任务的 Resource 结果 == 旧的 `+interval`。

        这是"接线没改变既有行为"的证据 —— 若两者不等, 说明我接错了。
        """
        import datetime as _dt
        base = _dt.datetime(2026, 10, 5, 12, 0, 0)
        for task, hours in (('DemonEncounter', 1), ('SoulsTidy', 3),
                            ('Duel', 3), ('WeeklyTrifles', 3)):
            got = config._next_run_from_resource(self._key(task), base)
            want = base + _dt.timedelta(hours=hours)
            assert got == want, (
                f'{task}: Resource 算出 {got}, 旧 interval 是 {want}')

    def test_slots_resource_uses_fixed_times(self, config):
        """★ `slots` 类任务按**固定时刻**算, 不是"加 3 小时"。

        金币妖怪的真实机制是 **0 点 / 12 点各补 1 次**（`slots='0,12'`）。
        旧实现把它压成 `success_interval=3h`, 于是会在 18:00 这种
        **根本不补充**的时刻去跑 —— 白跑一趟。
        """
        import datetime as _dt
        base = _dt.datetime(2026, 10, 5, 12, 0, 0)      # 周一 12:00
        got = config._next_run_from_resource(self._key('GoldYoukai'), base)
        assert got is not None, 'GoldYoukai 应有 Resource 排期'
        # 12:00 之后的下一个 slot 是次日 00:00
        assert (got.hour, got.minute) == (0, 0), (
            f'应按 slot 补到 00:00, 实际 {got}')
        assert got > base

    def test_periodic_resource_not_used(self, config):
        """★ `refill='none' + period` 类**不**走 `next_available`。

        原因: 那类任务的"下次运行"由**完成记忆**在周期边界决定;
        若用 `next_available`（它在"现在可行"时返回 `now`）会变成**热循环**。
        所以 `_next_run_from_resource` 对它返回 `None`, 交给旧逻辑 + 窗口对齐。
        """
        # 找一个 is_periodic 的任务
        from module.config import task_catalog as TC
        target = None
        for t, s in TC._load_specs().items():
            r = getattr(s, 'resource', None)
            if r is not None and getattr(r, 'is_periodic', False) \
                    and getattr(r, 'refill', 'none') == 'none':
                target = t
                break
        if target is None:
            pytest.skip('当前没有 refill=none+period 的任务')
        import datetime as _dt
        got = config._next_run_from_resource(
            self._key(target), _dt.datetime(2026, 10, 5, 12, 0, 0))
        assert got is None, (
            f'{target} 是周期回满类, 不该用 next_available 排期（会热循环）')

    def test_task_delay_prefers_resource(self):
        """★ 回归守卫: `task_delay` 必须**优先**用 Resource。"""
        src = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')
        i = src.find('def task_delay')
        j = src.find('\n    def ', i + 10)
        body = src[i:j]
        assert '_next_run_from_resource' in body, (
            'task_delay 没有用 Resource 排期 —— 新模型仍是死代码')
        # 必须有回退（任务没写 meta.py 时不能崩）
        assert '回退' in body or 'else:' in body, '缺少回退路径'

    def test_resource_wiring_is_real(self):
        """★ 反向守卫: `config.py` 里必须**真的**出现这些名字。

        防止有人"重构"掉接线, 又回到"模块存在但没人调"的状态。
        """
        src = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')
        for name in ('next_available', 'RunState', 'TC.get_spec'):
            assert name in src, f'config.py 里没有 {name} —— Resource 又变成死代码了'


class TestDemonEncounterWindow:
    """★ 台账 9.6「逢魔之时 = 每天 17:00–23:00」终于落进 `meta.py`。

    依据是**任务代码本身**（`script_task.py` 的 `check_time()`）:

        if now.hour < 17:    -> target = 当天 17:30   （太早）
        elif now.hour >= 23: -> target = 次日 17:30   （太晚）
        else: return True                             （可以跑）

    ⚠ 那个方法的 docstring 写的是"17:00到22:00" —— **过时注释**,
      代码实际用 23。**以代码为准**（已核对 L647 / L653）。
    """

    @pytest.fixture()
    def config(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_window_is_17_to_23_daily(self):
        spec = TC.get_spec('DemonEncounter')
        assert spec is not None and spec.window is not None, '缺 window'
        desc = spec.window_describe
        assert '17:00' in desc and '23:00' in desc, f'时段不对: {desc}'
        for w in spec.windows_effective:
            assert set(w.days) == set(range(7)), '应该是每天'

    def test_inside_window_not_pushed(self, config):
        """★ 关键回归: 已在窗口内的时刻**不能**被推走。"""
        for h in (17, 18, 22):
            now = datetime(2026, 10, 5, h, 0)
            got = config._align_to_window('demon_encounter', now)
            assert got == now, f'{h}:00 在窗口内, 却被推到 {got}'

    def test_23_pushes_to_next_day(self, config):
        """23:00 是**开区间**上界 -> 应推到次日 17:00（与 `check_time()` 一致）。"""
        now = datetime(2026, 10, 5, 23, 0)
        got = config._align_to_window('demon_encounter', now)
        assert got.day == 6 and (got.hour, got.minute) == (17, 0), \
            f'23:00 应推到次日 17:00, 实际 {got}'

    def test_before_17_pushes_to_same_day_17(self, config):
        now = datetime(2026, 10, 5, 16, 0)
        got = config._align_to_window('demon_encounter', now)
        assert got.day == 5 and (got.hour, got.minute) == (17, 0), \
            f'16:00 应推到当天 17:00, 实际 {got}'

    def test_check_time_still_uses_new_mechanism(self):
        """★ `check_time()` 用 `set_next_run(target=...)`（**新机制**）,
        不是 `custom_next_run` —— 所以它**不需要删**, 与窗口互补。"""
        src = (REPO / 'tasks' / 'DemonEncounter' / 'script_task.py').read_text(
            encoding='utf-8')
        i = src.find('def check_time')
        assert i > 0, 'check_time 不见了'
        j = src.find('\n    def ', i + 10)
        body = src[i:j]
        assert 'set_next_run' in body, 'check_time 应使用 set_next_run'
        assert 'custom_next_run' not in body, \
            'check_time 不该用旧的 custom_next_run'


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
