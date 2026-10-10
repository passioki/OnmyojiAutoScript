# -*- coding: utf-8 -*-
"""⑥(b): `window_slots`（每日固定时刻）—— 表达"一天跑几次"的第 4 种语义。

## 为什么需要它

用户的三条裁定（台账 §21.1 / §20.2）**互相约束**:
1. 窗口只回答"这个时间**可不可以**跑"
2. "跑几次"由**次数**（一轮打几场）或**重复条目**（跑几轮）体现
3. 排期**只用窗口**

但 `Restart` 的语义是"**每天 12:00 与 20:00 各领一次体力**":
* **不是窗口**（那是"可不可以"）
* **不是次数**（那是"一轮打几场"）
* **不是重复条目**（那会跑两轮完整任务, 但体力只在 12/20 点补充）

-> 它是**第 4 种**语义 = "**一天几个固定时刻**"。

## 设计

`scheduler.window_slots = '12:00,20:00'` -> 每个时刻生成一个**窗口段**
（该时刻 -> +120 分钟）, 于是"一天两次"由**窗口开放次数**自然表达。

★ 与 `window_start`/`window_end` **互斥**（填了 slots 就用 slots）。
"""
import sys
from datetime import datetime, time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _fn(restart=True, **over):
    """用真实任务的键构造 `Function`（合成名会 `KeyError` —— 踩过）。"""
    import copy
    import logging
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.config.config import Function
    from module.server.main_manager import mm

    cfg = mm.config_cache('恋鸟树')
    raw = copy.deepcopy(cfg.model.model_dump())
    key = 'restart'
    d = copy.deepcopy(raw[key])
    s = d['scheduler']
    s.update({
        'window_enable': True, 'window_period': 'daily', 'window_dom': '',
        'window_start': time(0, 0), 'window_end': time(23, 59),
        'window_slots': '',
    })
    s.update(over)
    return Function(key, d), cfg


class TestWindowSlotsField:
    def test_field_exists_and_visible(self):
        from tasks.Component.config_scheduler import Scheduler
        assert 'window_slots' in Scheduler.model_fields
        props = Scheduler.model_json_schema()['properties']
        assert not props['window_slots'].get('internal'), \
            'window_slots 必须**用户可见可改**'

    def test_help_translated(self):
        import json
        d = json.loads(
            (REPO / 'module' / 'config' / 'i18n' / 'zh-CN.json')
            .read_text(encoding='utf-8'))
        assert d.get('window_slots_help'), 'window_slots_help 缺译文'


class TestSlotsProduceSegments:
    def test_two_slots_two_segments(self):
        """★ `'12:00,20:00'` -> **两段**窗口。"""
        f, _ = _fn(window_slots='12:00,20:00')
        assert len(f.windows) == 2, [w.describe() for w in f.windows]
        desc = ' '.join(w.describe() for w in f.windows)
        assert '12:00' in desc and '20:00' in desc

    def test_in_window_follows_slots(self):
        """★ "一天两次"由**窗口开放次数**表达 —— 只有那两个时段能跑。"""
        f, _ = _fn(window_slots='12:00,20:00')
        expect = {
            11: False, 12: True, 13: True, 14: False,
            15: False, 19: False, 20: True, 21: True, 22: False,
        }
        for h, want in expect.items():
            got = f.in_window(datetime(2026, 10, 7, h, 0))
            assert got is want, f'{h:02d}:00 期望 {want}, 实际 {got}'

    def test_empty_slots_falls_back_to_start_end(self):
        """★ 空 slots -> 用 `window_start`/`window_end`（不混用）。"""
        f, _ = _fn(window_slots='', window_start=time(17, 0),
                   window_end=time(23, 0))
        assert len(f.windows) == 1
        assert f.windows[0].describe() == '每天 17:00-23:00'

    def test_bad_slots_ignored(self):
        """乱码项被忽略, 有效项保留（不让配置错误卡死任务）。"""
        f, _ = _fn(window_slots='12:00,abc,25:00')
        assert len(f.windows) == 1, [w.describe() for w in f.windows]
        assert f.windows[0].start == time(12, 0)

    def test_duplicate_slots_deduped(self):
        f, _ = _fn(window_slots='12:00,12:00')
        assert len(f.windows) == 1


class TestRestartMigrated:
    def test_no_custom_next_run_at_all(self):
        """★ 用户最终裁定: **彻底删除**自排期, 不留兼容兜底。

        用户原话:
          "删 custom_next_run, **用户没配窗口, 代表着这个只能按照排序依次执行**"
          "能重构就重构, **不要做冗余代码适配**"
        """
        import re
        src = (REPO / 'tasks' / 'Restart' / 'script_task.py').read_text(
            encoding='utf-8')
        code = re.sub(r'"""[\s\S]*?"""', '', src)
        code = '\n'.join(l.split('#', 1)[0] for l in code.split('\n'))
        assert 'custom_next_run' not in code, \
            'Restart 仍有自排期 —— 用户要求彻底删除'

    def test_settles_with_set_next_run(self):
        import re
        src = (REPO / 'tasks' / 'Restart' / 'script_task.py').read_text(
            encoding='utf-8')
        assert "set_next_run(task='Restart'" in src, \
            'Restart 应通过 set_next_run 结算（由窗口决定下次）'


class TestRemainingCustomNextRun:
    """★ **`custom_next_run` 已全库清零**（用户最终裁定）。"""

    def test_zero_custom_next_run_repo_wide(self):
        """★★ 起点 **10 处** -> 现在 **0 处**（用户: "删 custom_next_run"）。"""
        import re
        left = {}
        for p in (REPO / 'tasks').rglob('script_task.py'):
            src = re.sub(r'"""[\s\S]*?"""',
                         '', p.read_text(encoding='utf-8'))
            n = sum(1 for l in src.split('\n')
                    if 'custom_next_run' in l.split('#', 1)[0])
            if n:
                left[p.parent.name] = n
        assert not left, (
            f'还有任务在用任务内自排期: {left}\n'
            f'用户裁定: "删 custom_next_run, 用户没配窗口, 代表着这个只能'
            f'按照排序依次执行"')

    def test_helper_still_exists_for_other_uses(self):
        """★ `custom_next_run` **方法本身**保留（`base_task` 的 API）。

        删的是**调用**, 不是 API —— 以后若有真实"绝对时刻"需求仍可用
        （用户裁定第 ⑥ 条: "任务用 interval 还是真实日期时间"）。
        """
        from tasks.base_task import BaseTask
        assert hasattr(BaseTask, 'custom_next_run'), \
            'BaseTask.custom_next_run 被删了 —— 只该删调用, 不该删 API'
