# -*- coding: utf-8 -*-
"""菜单「移出队列」的**两类语义** —— 用户 2026-10-10 明确修正。

## 用户原话

> "执行队列中移除后自动停用只针对定时任务, 固定任务移除后应该返回添加任务的池子里。"

## 规则

| 任务类型 | `auto_queue` | 移除后 |
|---|---|---|
| **定时任务** | `True` | 出队列 **且 `enable=false`** |
| **固定/次数任务** | `False` | **只出队列**, `enable` 保持 -> 回到【添加任务】池子 |

## 为什么定时任务必须停用

自动进队列的任务只要 `enable=true` 就会被 `Config.build_queue()` **重新补进队列**,
只从 `run_list` 删掉是**无效操作**（下次刷新它又回来了）。

## 为什么次数任务不能停用

它们不在自动补齐范围内, 出队列后不会被补回来。若也停用, 用户想再跑就得先回
任务列表启用 —— 多余步骤, 且用户明确要求"返回添加任务的池子里"。

★ 我此前写成"**无条件停用**" —— 那是**错的**, 本测试钉住修正后的行为。
"""
import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture()
def live():
    """真实账号配置 + **自动还原** `enable` 状态（测试不能改用户配置）。"""
    import logging
    logging.disable(logging.CRITICAL)
    import server  # noqa: F401
    from module.server.main_manager import mm

    cfg = mm.config_cache('恋鸟树')
    backup = {}
    for key in cfg.model.model_dump():
        node = getattr(cfg.model, key, None)
        sch = getattr(node, 'scheduler', None) if node is not None else None
        if sch is not None:
            backup[key] = sch.enable
    yield cfg
    # 还原
    for key, val in backup.items():
        node = getattr(cfg.model, key, None)
        sch = getattr(node, 'scheduler', None) if node is not None else None
        if sch is not None:
            sch.enable = val
    try:
        cfg.save()
    except Exception:
        pass


def _remove(script: str, task: str) -> dict:
    from module.server.schema_router import post_queue_remove
    return asyncio.new_event_loop().run_until_complete(
        post_queue_remove(script, {'task': task}))


def _disk_enable(task_key: str) -> bool:
    """直接从**磁盘文件**读某个任务的 `enable`。

    ⚠ **不能**用 `mm.config_cache()` 再读 —— 它可能返回**缓存实例**,
      而端点在内部用的可能是**另一个** `Config` 对象。
      实测踩过: 端点返回 `enable=False`、磁盘也是 `false`,
      但测试里持有的 `cfg.model` 仍是旧值 -> **假失败**。
    """
    import json
    from pathlib import Path

    cfg_file = Path(__file__).resolve().parents[3] / 'config' / '恋鸟树.json'
    data = json.loads(cfg_file.read_text(encoding='utf-8'))
    return bool(data[task_key]['scheduler']['enable'])


class TestRemovalSemantics:
    def test_timed_task_is_disabled(self, live):
        """★ 定时任务（`auto_queue=True`）-> 出队列 **且停用**。

        `GoldYoukai` 是 `auto_queue=True`（充能型定时任务）。
        """
        from module.config import task_catalog as TC
        spec = TC.get_spec('GoldYoukai')
        assert spec is not None and spec.auto_queue_effective is True, \
            'GoldYoukai 应该是 auto_queue=True（测试前提）'
        # 先启用, 确保起点是 True
        live.model.gold_youkai.scheduler.enable = True
        live.save()

        got = _remove('恋鸟树', 'GoldYoukai')
        assert got.get('ok') is True, got
        assert got['auto_queue'] is True
        assert got['enable'] is False, (
            '定时任务移出后必须停用, 否则会被 build_queue() 立刻补回来')
        assert _disk_enable('gold_youkai') is False, \
            '磁盘上的 enable 也得是 False（端点改的是另一个 Config 实例, 必须查磁盘）'

    def test_count_task_keeps_enabled(self, live):
        """★ 次数任务（`auto_queue=False`）-> **只出队列, 不停用**。

        `RealmRaid` 是 `auto_queue=False`（个人突破, 次数任务）。
        """
        from module.config import task_catalog as TC
        spec = TC.get_spec('RealmRaid')
        assert spec is not None and spec.auto_queue_effective is False, \
            'RealmRaid 应该是 auto_queue=False（测试前提）'
        live.model.realm_raid.scheduler.enable = True
        live.save()

        got = _remove('恋鸟树', 'RealmRaid')
        assert got.get('ok') is True, got
        assert got['auto_queue'] is False
        assert got['enable'] is True, (
            '次数任务移出后**不该**停用 —— 用户要求它"返回添加任务的池子里"')
        assert _disk_enable('realm_raid') is True

    def test_count_task_still_in_candidates_after_removal(self, live):
        """★ 端到端: 次数任务移出后应**出现在【添加任务】候选里**。"""
        import asyncio as aio

        from module.config import task_catalog as TC
        from module.server.schema_router import get_queue_candidates

        live.model.realm_raid.scheduler.enable = True
        live.save()
        got = _remove('恋鸟树', 'RealmRaid')
        assert got.get('ok') is True, got

        cands = aio.new_event_loop().run_until_complete(
            get_queue_candidates('恋鸟树'))
        names = {c['command'] for c in cands.get('candidates', [])}
        assert 'RealmRaid' in names, (
            f'移出后 RealmRaid 应回到【添加任务】候选里, 实际候选: {sorted(names)}')
        spec = TC.get_spec('RealmRaid')
        assert spec.auto_queue_effective is False

    def test_timed_task_NOT_in_candidates_after_removal(self, live):
        """反向: 定时任务移出后（已停用）**不该**出现在候选里。"""
        import asyncio as aio

        from module.server.schema_router import get_queue_candidates

        live.model.gold_youkai.scheduler.enable = True
        live.save()
        got = _remove('恋鸟树', 'GoldYoukai')
        assert got.get('ok') is True, got

        cands = aio.new_event_loop().run_until_complete(
            get_queue_candidates('恋鸟树'))
        names = {c['command'] for c in cands.get('candidates', [])}
        assert 'GoldYoukai' not in names, \
            '停用的任务不该出现在候选里（候选要求 enable=True）'

    def test_message_differs_by_kind(self, live):
        """提示文案要**分类**（用户要求可见的反馈）。"""
        live.model.gold_youkai.scheduler.enable = True
        live.model.realm_raid.scheduler.enable = True
        live.save()
        timed = _remove('恋鸟树', 'GoldYoukai')
        count = _remove('恋鸟树', 'RealmRaid')
        assert '停用' in timed['message'] or '启用' in timed['message'], \
            f'定时任务的提示该提到停用, 实际: {timed["message"]}'
        assert '添加任务' in count['message'], \
            f'次数任务的提示该提到【添加任务】, 实际: {count["message"]}'
