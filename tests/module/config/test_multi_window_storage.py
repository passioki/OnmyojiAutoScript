# -*- coding: utf-8 -*-
"""S3: **多窗口**结构化存储（`Scheduler.windows`）+ 废弃 `window_slots`。

## 用户裁定

> "不是 window slots, 而是**设置多个 window**！slots 不是已经废弃了吗,
>  请**通读代码、设计文档并更新记忆**！**前后端要同步改**！"
> "一天跑两次 = **两个窗口**"

## 我此前记错的两件事（已纠正）

| 我的错误说法 | 代码事实 |
|---|---|
| "靠 `window_slots` 就能表达多个时刻" | `window_slots` 是**我自己发明的绕法**, 用户**从未认可** |
| "多 window 已实现" | 只对一半成立: `TaskSpec.window` 支持多段, **但用户配置只有 `window_start`/`window_end` 两个单值** |

**新增**: `Scheduler.windows: List[TaskWindow]`
**删除**: `window_enable` / `window_start` / `window_end` / `window_days` /
`window_period` / `window_dom` / **`window_slots`**
"""
import sys
from datetime import datetime, time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestFieldModel:
    def test_windows_is_user_visible(self):
        from tasks.Component.config_scheduler import Scheduler
        props = Scheduler.model_json_schema()['properties']
        assert 'windows' in props
        assert not props['windows'].get('internal')

    def test_no_single_value_window_fields(self):
        from tasks.Component.config_scheduler import Scheduler
        fields = set(Scheduler.model_fields)
        for dead in ('window_enable', 'window_start', 'window_end',
                     'window_days', 'window_period', 'window_dom',
                     'window_slots'):
            assert dead not in fields, f'{dead} 应已删除（单一数据源）'

    def test_task_window_field_count_is_small(self):
        """★ 单个窗口只有 7 个字段 —— 前端好编辑。"""
        from tasks.Component.config_scheduler import TaskWindow
        assert len(TaskWindow.model_fields) == 7, sorted(TaskWindow.model_fields)


class TestMigrationFromSingleValue:
    """★ 旧单值 / `window_slots` -> `windows` 列表（幂等）。"""

    def test_slots_migrate_to_multiple_windows(self):
        """★★ `window_slots='12:00,20:00'` -> **两个窗口**。"""
        from tasks.Component.config_scheduler import apply_recommended_windows
        node_map = {
            'restart': {'scheduler': {'window_enable': True,
                                      'window_slots': '12:00,20:00'}},
        }
        changed = apply_recommended_windows(node_map)
        assert 'restart' in changed
        ws = node_map['restart']['scheduler']['windows']
        assert len(ws) == 2, f'应折成两个窗口, 实际 {ws}'
        assert ws[0]['start'] == '12:00:00'
        assert ws[1]['start'] == '20:00:00'

    def test_single_value_migrates_to_one_window(self):
        from tasks.Component.config_scheduler import apply_recommended_windows
        node_map = {
            'restart': {'scheduler': {
                'window_enable': True, 'window_start': '09:00:00',
                'window_end': '17:00:00', 'window_period': 'weekly',
                'window_days': '4,5,6', 'window_dom': ''}},
        }
        apply_recommended_windows(node_map)
        ws = node_map['restart']['scheduler']['windows']
        assert len(ws) == 1, ws
        assert ws[0]['start'] == '09:00:00'
        assert ws[0]['days'] == '4,5,6'
        assert ws[0]['period'] == 'weekly'

    def test_old_fields_removed_after_migration(self):
        """★ 迁移后旧字段**必须删掉**（否则两个来源）。"""
        from tasks.Component.config_scheduler import apply_recommended_windows
        node_map = {
            'restart': {'scheduler': {'window_enable': True,
                                      'window_slots': '12:00'}},
        }
        apply_recommended_windows(node_map)
        sch = node_map['restart']['scheduler']
        for dead in ('window_enable', 'window_slots', 'window_start',
                     'window_end', 'window_days', 'window_period',
                     'window_dom'):
            assert dead not in sch, f'{dead} 迁移后应删除'

    def test_idempotent(self):
        """★ 已有 `windows` -> 不再改动（不能每次启动都覆盖用户设置）。"""
        from tasks.Component.config_scheduler import apply_recommended_windows
        node_map = {'restart': {'scheduler': {'windows': [
            {'id': 'mine', 'start': '01:00:00', 'end': '02:00:00'}]}}}
        changed = apply_recommended_windows(node_map)
        assert 'restart' not in changed
        assert node_map['restart']['scheduler']['windows'][0]['id'] == 'mine'

    def test_every_window_has_unique_id(self):
        from tasks.Component.config_scheduler import apply_recommended_windows
        node_map = {'restart': {'scheduler': {}}}
        apply_recommended_windows(node_map)
        ws = node_map['restart']['scheduler']['windows']
        ids = [w['id'] for w in ws]
        assert all(ids), '每个窗口必须有 id（身份不是位置）'
        assert len(set(ids)) == len(ids), f'id 重复: {ids}'


class TestLiveConfig:
    """★ 实测用户配置（用户表示配置可随意改）。"""

    @pytest.fixture()
    def cfg(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_restart_has_two_windows(self, cfg):
        """★★ `restart` = **两个窗口**（一天两次领体力）。"""
        ws = cfg.model.restart.scheduler.windows
        assert len(ws) == 2, (
            f'restart 应有两个窗口（12-14 / 20-22）, 实际 {len(ws)}')
        starts = sorted(w.start.hour for w in ws)
        assert starts == [12, 20], starts

    def test_ryou_toppa_has_no_config_window(self, cfg):
        """★★ `ryou_toppa` **不该**在配置里有窗口（用户裁定 A: 全天可跑）★★

        ## 用户原话

        > "寮突破 window **设置混乱、不生效**而且**不再开放时间段**"

        ## 根因（两套窗口定义打架）

        那个**一次性推荐窗口迁移**（`RECOMMENDED_WINDOWS`）曾给
        `ryou_toppa` 写入 `07:00-09:00`, 而 `meta.py` 声明的是
        `00:00-23:59`（**全天**）。

        ★ `Function.window` 的优先级是 **配置 > meta** -> 迁移值
          **永久压住**了 meta -> 寮突破每天只有 2 小时能跑。

        ★ 用户选 **A（全天可跑, 跟 meta）** -> 已从推荐表移除 +
          清掉配置里的残留, 所以现在**配置里应当是空的**
          （由 meta 的全天窗口兜底）。

        ⚠ 这条测试**必须**这么写: 断言"有 1 个 07:00 窗口"就是给那个 bug
          上锁（旧版正是如此 —— 它会让修复**测不过**）。
        """
        ws = cfg.model.ryou_toppa.scheduler.windows
        assert len(ws) == 0, (
            '★ 寮突破配置里不该有窗口 —— 它会压住 meta 的全天窗口 '
            f'(实际 {len(ws)} 个: '
            + str([(w.start, w.end) for w in ws]) + ')')

    def test_no_old_fields_on_disk_objects(self, cfg):
        s = cfg.model.restart.scheduler
        for dead in ('window_enable', 'window_slots', 'window_start'):
            assert not hasattr(s, dead), f'{dead} 还在模型上'

    def test_in_window_two_segments(self, cfg):
        from module.config.config import Function
        raw = cfg.model.model_dump()
        f = Function('restart', raw['restart'])
        assert f.in_window(datetime(2026, 10, 7, 13, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 21, 0)) is True
        assert f.in_window(datetime(2026, 10, 7, 16, 0)) is False
