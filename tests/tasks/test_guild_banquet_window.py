# -*- coding: utf-8 -*-
"""⑥ 继续: `GuildBanquet` 的 `custom_next_run` **已换成窗口**（用户裁定 (a)）。

## 背景

`GuildBanquet` 原来有个 `plan_next_run()`:
```python
today = datetime.now().weekday()
if today < self.banquet_day_1:
    self.custom_next_run(..., time_delta=self.banquet_day_1 - today)
elif self.banquet_day_1 <= today < self.banquet_day_2:
    self.custom_next_run(..., time_delta=self.banquet_day_2 - today)
elif self.banquet_day_2 <= today:
    self.custom_next_run(..., time_delta=7 - today + self.banquet_day_1)
```
它按**用户配置的宴会日**（`run_time.day_1` / `day_2`, 周三/周六）手工算
"下次哪天几点" —— 那是"**任务内自排期**", 与"**队列顺序 + 窗口**"是两套机制。

## 现在

* `plan_next_run()` **已删除**
* 结算处改为 `set_next_run(success=True)` —— 由**任务窗口**决定下次
* 宴会日/时段改由**用户可见的窗口字段**表达:
  `window_period=每周` + `window_days`（周三/周六）+ `window_start/end`

★ 这不丢失表达能力: `weekday()` 判断本来就是把"宴会日"硬编码进代码,
  现在它变成**用户可配的窗口**（`window_period='weekly'` + `window_days`）。
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TASK = REPO / 'tasks' / 'GuildBanquet' / 'script_task.py'


def _code(text: str = None) -> str:
    """剥掉注释与 docstring —— 否则"说明我删了什么"的注释会被误判。

    ★ 这条纪律（台账 §10.7）我已在多处踩过, 这里一开始就剥。
    """
    src = text if text is not None else TASK.read_text(encoding='utf-8')
    src = re.sub(r'"""[\s\S]*?"""', '', src)
    out = []
    for line in src.split('\n'):
        s = line.split('#', 1)[0]
        if s.strip():
            out.append(s)
    return '\n'.join(out)


class TestGuildBanquetUsesWindow:
    def test_no_custom_next_run(self):
        code = _code()
        assert 'custom_next_run' not in code, (
            'GuildBanquet 仍在自排期 —— 应改用窗口（见 §24）')

    def test_plan_next_run_removed(self):
        code = _code()
        assert 'plan_next_run' not in code, (
            '`plan_next_run()` 应已删除')

    def test_settlement_uses_set_next_run(self):
        """★ 结算处应调 `set_next_run(success=True)`（由窗口决定下次）。"""
        code = _code()
        assert "set_next_run(task='GuildBanquet'" in code.replace('"', "'"), \
            '结算处应调用 set_next_run'
        assert 'success=True' in code, '成功路径应标记 success=True'

    def test_still_ends_task(self):
        """只改排期, 不该把任务结束逻辑弄丢。"""
        assert 'raise TaskEnd' in _code()

    def test_banquet_days_now_expressible_by_window(self):
        """★ 宴会日（周三/周六）现在能用**窗口**表达（#1 的字段模型）。"""
        from module.config.availability import AvailabilityWindow
        from tasks.Component.config_scheduler import WindowPeriod
        assert WindowPeriod.WEEKLY.value == 'weekly'
        # 周三=2, 周六=5
        w = AvailabilityWindow(True, __import__('datetime').time(18, 0),
                               __import__('datetime').time(22, 0),
                               days=(2, 5))
        assert '周三' in w.describe() and '周六' in w.describe()


class TestOtherTasksStillUsingCustomNextRun:
    """★ **如实记录**还剩哪些（不用它假装完成）。"""

    def test_remaining_count(self):
        """当前剩 `Restart`(3) 与 `RyouToppa`(2) —— 共 5 处。

        两者都是"**一天跑几次**"的语义（领体力 12:00/20:00；寮突破次日 7:00）,
        而**窗口只回答"这个时间可不可以跑"**（用户裁定 §21.1）——
        所以它们**不能在当前模型下被窗口取代**。见台账 §24。
        """
        hits = []
        for p in (REPO / 'tasks').rglob('script_task.py'):
            code = _code(p.read_text(encoding='utf-8'))
            n = code.count('custom_next_run')
            if n:
                hits.append((p.parent.name, n))
        names = {n for n, _ in hits}
        assert 'GuildBanquet' not in names, 'GuildBanquet 不该再自排期'
        assert names <= {'Restart', 'RyouToppa'}, (
            f'出现了预期外的自排期任务: {sorted(names)} —— '
            f'请更新台账 §24 并确认是否该迁移')
