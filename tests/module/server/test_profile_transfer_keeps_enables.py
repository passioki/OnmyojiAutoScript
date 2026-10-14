# -*- coding: utf-8 -*-
"""★ 守卫：**跨配置转移**配置页时，★ **不许改写目标配置的任务启停**（台账 `N9-8`）。

## ★★ 用户原话（[10-14] 记录第 8 条）

> "**从别的配置中复制执行顺序配置页时，复制后，自身的周期任务被添加了进来，
>   意味着和复制的相比多了自身的周期任务，这不符合复制的语义。**"

## ★★ 复现（[10-14] 实测）

```
A 配置: enable=True = ['orochi']
B 配置: enable=True = ['abyss_shadows']
把 A 的页 transfer 到 B 并切过去之后:
  B 的 enable=True = ['orochi']        ← ★ 被源的快照整片覆盖
  B 的队列显示     = ['RealmRaid'] + ['Orochi']   ← ★ "多出来的周期任务"
```

## ★ 为什么是 bug

★ ① 端点自己写着「**不激活**新页 —— 否则会把目标配置**正在用的队列换掉**」，
  而 `scheduler.enable` **恰恰会换掉**目标能跑什么（周期任务 `enable=True`
  ⇒ `auto_queue` ⇒ **自动进队列**）。
★ ② **任务启停是【账号级】设置**：同配置内切页**本来就不改**它；
  跨配置却整片覆盖 ⇒ 语义不一致。
★ ③ 用户要的"复制的语义" = **把那一页的顺序拿过来**，
  ★ 不是"把我的任务配置也换成对方的"。

## ★ 修法

★ `script_router.post_queue_profile_transfer()` 在**深拷贝之后**，
  把快照里每个任务的 `enable` **剥掉** ⇒ 目标自己的启停原样保留。
★ `queue` / `global` / `target` / `priority` / `expected_minutes` **照旧复制**。
★ **同配置**的"复制这一页…"（`post_queue_profile`）**不动**（既有行为）。
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

SRC = '__n98_src__'
DST = '__n98_dst__'
SRC_P = REPO / 'config' / f'{SRC}.json'
DST_P = REPO / 'config' / f'{DST}.json'

#: ★ A 配置开着的任务（用于复现"源的任务被带进目标"）
SRC_ON = 'orochi'
#: ★ B 配置自己开着的任务（用于复现"目标的被覆盖掉"）
DST_ON = 'abyss_shadows'


def _mk(name: str, enabled_key: str) -> None:
    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    opt = tmpl['script']['optimization']
    opt['run_list'] = [{'kind': 'task', 'task': 'RealmRaid',
                        'target': 0, 'entry_id': 'e-realmraid'}]
    opt['period_backfilled'] = True
    for k, v in tmpl.items():
        if isinstance(v, dict) and isinstance(v.get('scheduler'), dict):
            v['scheduler']['enable'] = (k == enabled_key)
    (REPO / 'config' / f'{name}.json').write_text(
        json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')


def _enabled_tasks(name: str) -> list:
    from module.config.config import Config
    c = Config(name)
    return sorted(k for k, v in c.model.model_dump().items()
                  if isinstance(v, dict) and isinstance(v.get('scheduler'), dict)
                  and v['scheduler'].get('enable'))


def _snapshot_of(name: str, pid: str) -> dict:
    from module.config.config import Config
    from module.server.schema_router import _profiles_store
    store = _profiles_store(Config(name), auto_create=False)
    item = next((it for it in (store.get('items') or [])
                 if isinstance(it, dict) and str(it.get('id')) == pid), None)
    assert item is not None, f'{name} 里应有页 {pid}'
    return item.get('snapshot') or {}


@pytest.fixture()
def two_configs():
    """造 A/B 两份独立配置，并保证清理（★ 绝不碰用户账号配置）。"""
    cwd_before = os.getcwd()
    os.chdir(REPO)
    try:
        _mk(SRC, SRC_ON)
        _mk(DST, DST_ON)
        # ★ 让两个配置各有一页（自动建"页1"）
        from module.config.config import Config
        from module.server.schema_router import _profiles_store
        for nm in (SRC, DST):
            _profiles_store(Config(nm))
        yield
    finally:
        os.chdir(cwd_before)
        for p in (SRC_P, DST_P):
            try:
                p.unlink()
            except OSError:
                pass


def _transfer(from_config: str, to_config: str, pid: str, name=None):
    from module.server.script_router import post_queue_profile_transfer
    data = {'from_config': from_config, 'to_config': to_config,
            'profile_id': pid}
    if name:
        data['name'] = name
    return asyncio.run(post_queue_profile_transfer(data))


# ─────────────────────────── ① 核心：转移后目标的启停不许被改
def test_transfer_does_not_touch_target_task_enables(two_configs):
    """★★★ 核心（N9-8）：★ 转移 + 切到新页之后，★ **目标的启停必须原样**。

    ★ 实测过的错误行为：★ 目标变成 `['orochi']`（= 源的任务），
      而它自己的 `abyss_shadows` **被关掉了** ⇒ ★ 用户看到"多出周期任务"。
    """
    from module.server.schema_router import _apply_snapshot
    assert _enabled_tasks(DST) == [DST_ON], '前置：目标原本只开着自己那个'

    res = _transfer(SRC, DST, 'p1', name='从A来的')
    assert res.get('ok') is True, f'转移应成功，实际：{res}'
    new_pid = str(res.get('created'))

    # ★ 模拟用户在新页上点"切过去"
    from module.config.config import Config
    dst = Config(DST)
    _apply_snapshot(dst, _snapshot_of(DST, new_pid))
    dst.save()

    assert _enabled_tasks(DST) == [DST_ON], (
        '★★ 转移后目标的启停必须原样保留 —— 否则源配置的周期任务会凭空'
        '出现在目标里（并把它自己的任务关掉）。'
        f'实际：{_enabled_tasks(DST)}')


# ─────────────────────────── ② 快照里不许有 enable
def test_transferred_snapshot_has_no_enable(two_configs):
    """★ 落进目标的那份快照里，★ **每个任务都不该有 `enable` 键**。"""
    res = _transfer(SRC, DST, 'p1')
    assert res.get('ok') is True, f'转移应成功，实际：{res}'
    snap = _snapshot_of(DST, str(res.get('created')))
    sched = snap.get('scheduler')
    assert isinstance(sched, dict) and sched, '前置：快照应含 scheduler 段'
    with_enable = [k for k, v in sched.items()
                   if isinstance(v, dict) and 'enable' in v]
    assert not with_enable, (
        f'★ 转移用的快照里不该再有 `enable`（否则切页时会覆盖目标启停）。'
        f'实际仍带 enable 的：{with_enable[:8]}')


# ─────────────────────────── ③ 该复制的仍然要复制
def test_transfer_still_copies_queue_and_global(two_configs):
    """★ 反向守卫：★ **队列与全局开关必须照旧复制**（别把修法做过头）。

    ★ 用户要的"复制的语义" = ★ **把那一页的顺序拿过来** ⇒
      ★ 队列（`queue`）与全局开关（`global`）**必须还在**。
    """
    res = _transfer(SRC, DST, 'p1')
    assert res.get('ok') is True
    snap = _snapshot_of(DST, str(res.get('created')))
    assert snap.get('queue'), '★ 队列必须复制过来（那是这一页的核心）'
    assert isinstance(snap.get('global'), dict), '★ 全局开关必须复制过来'

    from module.server.schema_router import _apply_snapshot
    from module.config.config import Config
    dst = Config(DST)
    _apply_snapshot(dst, snap)
    dst.save()
    tasks = [e.task for e in Config(DST).build_run_list()
             if getattr(e, 'kind', '') == 'task']
    assert tasks == ['RealmRaid'], f'★ 队列应原样复制，实际 {tasks}'


# ─────────────────────────── ④ 目标自己的页不许被动
def test_transfer_does_not_activate_target(two_configs):
    """★ 端点自己声明的取舍：★ **跨配置不激活新页**（不许换掉目标在用的队列）。"""
    from module.config.config import Config
    from module.server.schema_router import _profiles_store
    before = str((_profiles_store(Config(DST), auto_create=False) or {}
                  ).get('active_id'))
    res = _transfer(SRC, DST, 'p1')
    assert res.get('ok') is True
    assert res.get('activated') is False, '★ 跨配置转移**不许**激活新页'
    after = str((_profiles_store(Config(DST), auto_create=False) or {}
                 ).get('active_id'))
    assert after == before, f'★ 当前页不许变（{before} -> {after}）'
