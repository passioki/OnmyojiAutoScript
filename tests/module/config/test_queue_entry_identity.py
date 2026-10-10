# -*- coding: utf-8 -*-
"""⑧⑨ + 拖动丢 id: 队列的**条目身份**必须贯穿前后端。

## 本轮实测到的**三个真 bug**

### ⑨ 后端按任务名删 -> 一删全删
`post_queue_remove` 的注释曾写着"删掉**所有**该任务的条目"。
实测: 两条「个人突破」删一条, **两条都没了**。

### ⑧ 前端 `appendToQueue` **静默拒绝**重复
```dart
if (_entryIndex(command) >= 0) return;   // 点了没反应
```

### 拖动把 `entry_id` **抹掉**
`reorderQueue` 重建 entries 时只写 `kind`/`task`/`minutes` ->
一次拖动就丢掉所有条目身份 -> 后端重新生成 id ->
**按条目追踪（C）的完成状态全部失效**。
"""
import asyncio
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OASX = Path(r'D:\OAS-dev\OASX-src')


class TestBackendPreciseRemoval:
    @pytest.fixture()
    def live(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        cfg = mm.config_cache('恋鸟树')
        return cfg, mm

    def test_entry_id_removes_only_one(self, live):
        """★★ ⑨ 核心: 带 `entry_id` **只删一条**。"""
        from module.config.run_list import RunEntry, RunList
        from module.server import schema_router as SR

        cfg, mm = live
        backup = cfg.model.script.optimization.run_list
        try:
            rl = RunList()
            rl.add(RunEntry(kind='task', task='RealmRaid'))
            rl.add(RunEntry(kind='task', task='RealmRaid'))
            cfg.save_run_list(rl)

            got = [(e.task, e.entry_id) for e in
                   mm.config_cache('恋鸟树').build_run_list()]
            ids = [i for t, i in got if t == 'RealmRaid']
            assert len(ids) == 2, f'应有两条同名: {got}'

            res = asyncio.run(SR.post_queue_remove(
                '恋鸟树', {'task': 'RealmRaid', 'entry_id': ids[0]}))
            assert res.get('ok') is True, res
            assert res.get('removed_entries') == 1, res

            left = [e.task for e in
                    mm.config_cache('恋鸟树').build_run_list()]
            assert left.count('RealmRaid') == 1, (
                f'应只剩 1 条 RealmRaid, 实际 {left}（一删全删的回归）')
        finally:
            cfg.model.script.optimization.run_list = backup
            cfg.save()

    def test_unknown_entry_id_errors_not_silent(self, live):
        """★ 找不到 id 必须**报错**, 不能静默"成功"（否则界面像没反应）。"""
        from module.server import schema_router as SR
        cfg, _ = live
        backup = cfg.model.script.optimization.run_list
        try:
            res = asyncio.run(SR.post_queue_remove(
                '恋鸟树', {'task': 'RealmRaid', 'entry_id': 'no-such-id'}))
            assert res.get('error'), f'应报错, 实际 {res}'
        finally:
            cfg.model.script.optimization.run_list = backup
            cfg.save()

    def test_missing_entry_id_keeps_legacy_behaviour(self, live):
        """★ 不带 `entry_id` -> 删该任务**全部**（向后兼容）。"""
        from module.config.run_list import RunEntry, RunList
        from module.server import schema_router as SR
        cfg, mm = live
        backup = cfg.model.script.optimization.run_list
        try:
            rl = RunList()
            rl.add(RunEntry(kind='task', task='RealmRaid'))
            rl.add(RunEntry(kind='task', task='RealmRaid'))
            cfg.save_run_list(rl)
            asyncio.run(SR.post_queue_remove('恋鸟树', {'task': 'RealmRaid'}))
            left = [e.task for e in
                    mm.config_cache('恋鸟树').build_run_list()]
            assert 'RealmRaid' not in left, left
        finally:
            cfg.model.script.optimization.run_list = backup
            cfg.save()


class TestFrontendCarriesEntryId:
    def _src(self, rel):
        return (OASX / rel).read_text(encoding='utf-8')

    def test_append_allows_duplicates(self):
        """★★ ⑧: `appendToQueue` **不该**再静默拒绝重复。"""
        src = self._src('lib/controller/task_list/task_list_controller.dart')
        i = src.find('appendToQueue')
        assert i > 0
        body = src[i:i + 700]
        assert '_entryIndex(command) >= 0' not in body, (
            'appendToQueue 仍在拒绝重复添加（⑧ 的根因）')

    def test_reorder_preserves_entry_id(self):
        """★★ 拖动必须**保留 `entry_id`**（否则条目身份被抹掉）。"""
        src = self._src('lib/controller/task_list/task_list_controller.dart')
        i = src.find('void reorderQueue')
        assert i > 0
        body = src[i:i + 2000]
        assert 'entry_id' in body, (
            'reorderQueue 重建 entries 时丢了 entry_id —— '
            '一次拖动就会让按条目追踪失效')

    def test_api_client_accepts_entry_id(self):
        src = self._src('lib/api/api_client.dart')
        i = src.find('removeFromQueue')
        assert 'entryId' in src[i:i + 900], \
            'api_client.removeFromQueue 应接受 entryId'

    def test_panel_passes_entry_id(self):
        src = self._src('lib/views/tasks/queue_panel.dart')
        assert 'entryId:' in src, 'queue_panel 调用移除时应传 entryId'
