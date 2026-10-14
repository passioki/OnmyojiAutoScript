# -*- coding: utf-8 -*-
"""★★ 守卫：**任务自定义状态**（C10 · SPEC §1.19-C10 · 台账 §D.6 `N9-10`）。

## ★ 为什么要这条

★ 实测（SPEC §1.19-C10 的缺口）：★ `task_state.py` 原有 38 个函数里，
  ★ **没有一个是给"任务自己想存点东西"用的** ⇒
  ★ 新任务想记"今天刷了几次""上次成功是什么时候"，只能**自己往
    `.task_state.json` 里塞**（★ 绕过锁与既有字段 ⇒ 迟早撞车）。

## ★ 为什么必须**两级**（条目 / 任务）

★ 周期任务的 `entry_id` 是 **`None`**（★ 实测：台账 `N9-7` 的三层真因之一）
  ⇒ ★ 只做"条目级"的话，**周期任务根本存不了**。

## ★ 怎么保证不空转

★ 全部是**运行时往返**（写 → 读），★ 不是查源码；
★★ 且额外断言：★ **不许踩坏既有字段**（`runs` / `total_runs` 还在）
  —— ★ 这是"往同一个 json 里塞东西"最容易出的事故。
"""
import json
import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

from module.config import task_state as TS  # noqa: E402

#: ★ 专用配置名（★ 绝不碰用户的账号配置）
CFG = '__guard_custom_state_cfg__'
EID = 'gold_youkai@2026-10-14 21:00:00'
TASK = 'gold_youkai'


@pytest.fixture(autouse=True)
def _clean():
    """★ 前置 + 后置都清（★ 免得留下残留影响别的用例 / 用户排障）。"""
    TS.clear(config_name=CFG)
    yield
    TS.clear(config_name=CFG)


def test_state_file_is_the_shared_one():
    """★ 前置：★ 自定义状态必须落在**同一个**状态文件里（不是另造一套）。"""
    assert str(TS._state_file()).endswith('.task_state.json'), (
        f'★ 状态文件变了：{TS._state_file()} —— 本守卫的落盘判据要跟着改')


# ────────────────────────────── 条目级
def test_entry_state_round_trip():
    """★★ 条目级：写进去、读出来。"""
    assert TS.get_entry_state(CFG, EID, 'n94_last_ok', '缺省') == '缺省', \
        '★ 没写过时应当返回 default'
    assert TS.set_entry_state(CFG, EID, 'n94_last_ok', '2026-10-14 21:30') is True
    assert TS.get_entry_state(CFG, EID, 'n94_last_ok') == '2026-10-14 21:30'


def test_set_state_does_not_clobber_existing_keys():
    """★★★ 最要紧的一条：★ 写自定义状态**不许踩坏** `runs` / `total_runs`。

    ★ 依据：★ 它们与自定义状态**住同一个 json 条目**里 ⇒
      ★ 谁写的时候图省事整条替换，★ 就把"次数"抹了（★ 那是**判据**用的字段）。
    """
    TS.bump_entry_runs(CFG, EID, 3)                      # ★ 先埋一个真实字段
    assert TS.get_entry_runs(CFG, EID) == 3
    assert TS.set_entry_state(CFG, EID, 'note', 'hi') is True
    assert TS.get_entry_runs(CFG, EID) == 3, (
        '★★★ 自定义状态把 `runs` 踩坏了 —— 那是**判据**字段（`entry_target_reached` 要用）')
    assert TS.get_entry_state(CFG, EID, 'note') == 'hi'


# ────────────────────────────── 任务级（周期任务用）
def test_task_state_round_trip():
    """★★ 任务级：★ 周期任务 `entry_id` 为 `None` ⇒ ★ 必须能按任务名存。"""
    assert TS.get_task_state(CFG, TASK, 'k', '缺省') == '缺省'
    assert TS.set_task_state(CFG, TASK, 'k', 7) is True
    assert TS.get_task_state(CFG, TASK, 'k') == 7


def test_entry_and_task_scopes_are_isolated():
    """★★ 两级**互不串味**（★ 同一个 key 名在两处应当是两份数据）。"""
    TS.set_entry_state(CFG, EID, 'same', 'entry')
    TS.set_task_state(CFG, TASK, 'same', 'task')
    assert TS.get_entry_state(CFG, EID, 'same') == 'entry'
    assert TS.get_task_state(CFG, TASK, 'same') == 'task'


def test_two_entries_do_not_share_state():
    """★★ 同一任务的**两条条目**各自独立（★ 与 §1.14-E1"条目级独立"同一原则）。"""
    eid2 = 'gold_youkai@2026-10-14 22:00:00'
    TS.set_entry_state(CFG, EID, 'n', 1)
    TS.set_entry_state(CFG, eid2, 'n', 2)
    assert TS.get_entry_state(CFG, EID, 'n') == 1
    assert TS.get_entry_state(CFG, eid2, 'n') == 2


# ────────────────────────────── 边界与鲁棒
def test_empty_scope_or_key_is_refused():
    """★ 空 `entry_id` / 空 key ⇒ ★ 不写、读默认（**不许**建出无名的容器）。"""
    assert TS.set_entry_state(CFG, '', 'k', 1) is False
    assert TS.set_entry_state(CFG, EID, '', 1) is False
    assert TS.get_entry_state(CFG, '', 'k', '缺省') == '缺省'


def test_non_serializable_value_is_refused_and_file_stays_valid():
    """★★ 不可 JSON 序列化的值 ⇒ ★ 返回 `False`，★ **且状态文件仍能解析**。

    ★ 为什么要这条：★ 状态文件是**全调度共用**的 ⇒ ★ 写坏它 = 整个调度读不出记忆。
    """
    assert TS.set_entry_state(CFG, EID, 'bad', object()) is False
    raw = TS._state_file().read_text(encoding='utf-8')
    json.loads(raw)      # ★ 能解析 = 没写坏
    assert TS.get_entry_state(CFG, EID, 'bad', '缺省') == '缺省'


def test_state_survives_reload():
    """★ 落盘（★ 不是只留内存）：★ 重新读文件也要在。"""
    TS.set_entry_state(CFG, EID, 'persisted', [1, 2, 3])
    data = json.loads(TS._state_file().read_text(encoding='utf-8'))
    custom = (((data.get(CFG) or {}).get(TS.ENTRIES_KEY) or {})
              .get(EID) or {}).get(TS.CUSTOM_KEY) or {}
    assert custom.get('persisted') == [1, 2, 3], (
        f'★ 没落盘到 `<config>/__entries__/<eid>/custom`：{data.get(CFG)}')
