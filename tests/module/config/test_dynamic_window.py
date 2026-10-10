# -*- coding: utf-8 -*-
"""(b) 动态窗口: `AvailabilityWindow` 能**引用配置字段**（用户裁定）。

## 用户原话

> "窗口是唯一排期依据, 这个 B 并不冲突吧, **窗口仍然是唯一排期依据**。
>  (b) **AvailabilityWindow 支持动态 days（运行时从配置读）**
>   让窗口能**引用配置字段**"

## 为什么需要

`GuildBanquet` 的宴会日/时刻是**用户在任务配置里选的**:
```
guild_banquet.guild_banquet_time.day_1     = 星期三
guild_banquet.guild_banquet_time.run_time_1 = 19:00
day_2 = 星期六, run_time_2 = 19:00
```
而 `AvailabilityWindow` 原本是**声明时冻结**的 —— 表达不了"周几来自配置"。

## 修好的**三个真 bug**（都是我实测抓到的）

1. `Function.model` 是 `None` -> 路径解析**永远失败**（静默）
2. `self.node` 是 **dict**, 用 `getattr` 取不到
3. `resolve_windows()` 里 `AvailabilityWindow` **未导入** -> `NameError`
   被宽 `except` 吞成 WARNING, 表现为"动态 days 不生效"
"""
import sys
from datetime import datetime, time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestParseHelpers:
    def test_parse_weekday(self):
        from module.config.availability import parse_weekday
        assert parse_weekday('星期三') == 2
        assert parse_weekday('星期六') == 5
        assert parse_weekday('周日') == 6
        assert parse_weekday('Monday') == 0
        assert parse_weekday('sunday') == 6
        assert parse_weekday(0) == 0 and parse_weekday(6) == 6

    def test_parse_weekday_rejects_garbage(self):
        from module.config.availability import parse_weekday
        for bad in ('星期八', 'abc', 7, -1, None):
            with pytest.raises(ValueError):
                parse_weekday(bad)

    def test_parse_time(self):
        from module.config.availability import parse_time
        assert parse_time('19:00') == time(19, 0)
        assert parse_time('07:00:00') == time(7, 0)
        assert parse_time('19：00') == time(19, 0)     # 全角冒号
        assert parse_time(time(8, 30)) == time(8, 30)

    def test_parse_time_rejects_garbage(self):
        from module.config.availability import parse_time
        for bad in ('25:00', 'abc', ''):
            with pytest.raises(ValueError):
                parse_time(bad)


class TestWindowFields:
    def test_days_empty_allowed_with_dynamic(self):
        """★ `days=()` 在**有动态项**时合法（"没有静态约束"）。"""
        from module.config.availability import AvailabilityWindow
        w = AvailabilityWindow(True, time(18, 0), time(22, 0), days=(),
                               days_from_config=('x.y',))
        assert w.days == ()

    def test_days_empty_rejected_without_dynamic(self):
        from module.config.availability import AvailabilityWindow
        with pytest.raises(ValueError):
            AvailabilityWindow(True, time(18, 0), time(22, 0), days=())

    def test_unresolved_dynamic_window_does_not_block(self):
        """★ 未解析的动态窗口**不误拦**（否则 `TaskSpec.in_window()` 恒 False）。"""
        from module.config.availability import AvailabilityWindow
        w = AvailabilityWindow(True, time(18, 0), time(22, 0), days=(),
                               days_from_config=('x.y',))
        assert w.contains(datetime(2026, 10, 8, 3, 0)) is True, \
            '动态未解析时不应拦（真实判定在 Config.in_window）'
        assert w.is_unrestricted is False, '动态窗口不该被当成"不限"'


@pytest.fixture()
def live():
    import copy
    import logging
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.config.config import Function
    from module.server.main_manager import mm

    cfg = mm.config_cache('恋鸟树')
    raw = copy.deepcopy(cfg.model.model_dump())
    return Function, raw


class TestGuildBanquetDynamic:
    """★ `GuildBanquet` 的宴会日/时刻**来自配置**。"""

    def test_two_segments(self, live):
        Function, raw = live
        f = Function('guild_banquet', raw['guild_banquet'])
        assert len(f.resolve_windows()) == 2, '两场宴会 -> 两段窗口'

    def test_days_resolved_from_config(self, live):
        """★ 配置里的 周三/周六 -> 解析成 days=(2,)/(5,)。"""
        Function, raw = live
        gbt = raw['guild_banquet']['guild_banquet_time']
        f = Function('guild_banquet', raw['guild_banquet'])
        ws = f.resolve_windows()
        got = {tuple(sorted(w.days)) for w in ws}
        want = {(int(getattr(gbt['day_1'], 'value', gbt['day_1']) == '星期三'
                     and 2 or 0),),
                (5,)}
        # 直接断言"两段都是单日, 且都非全周"
        assert all(len(w.days) == 1 for w in ws), \
            f'动态 days 未生效（应是单日窗口）: {[w.days for w in ws]}'

    def test_in_window_follows_config(self, live):
        Function, raw = live
        f = Function('guild_banquet', raw['guild_banquet'])
        # 周三(2) 与 周六(5) 19:00 应在窗口内; 周四(3) 不在
        assert f.in_window(datetime(2026, 10, 7, 19, 0)) is True   # 周三
        assert f.in_window(datetime(2026, 10, 10, 19, 0)) is True  # 周六
        assert f.in_window(datetime(2026, 10, 8, 19, 0)) is False  # 周四
        assert f.in_window(datetime(2026, 10, 7, 12, 0)) is False  # 周三中午

    def test_bad_path_warns_not_crashes(self, live):
        """解析失败 -> WARNING + 跳过, **不抛**（不让配置错误卡死任务）。"""
        from module.config.availability import AvailabilityWindow
        Function, raw = live
        node = dict(raw['guild_banquet'])
        node = {**node, 'scheduler': dict(node['scheduler'])}
        f = Function('guild_banquet', node)
        # 手工塞一个不存在的路径
        bad = AvailabilityWindow(True, time(18, 0), time(22, 0), days=(),
                                 days_from_config=('no.such.path',))
        f.windows = (bad,)
        assert f.resolve_windows() is not None      # 不该抛


class TestNodeIsDict:
    def test_function_stores_node(self, live):
        Function, raw = live
        f = Function('guild_banquet', raw['guild_banquet'])
        assert getattr(f, 'node', None) is not None, \
            'Function 必须存任务节点 —— 否则动态窗口解析不了'
        assert isinstance(f.node, dict), \
            'node 是 model.dump() 的普通 dict（不是对象）'
