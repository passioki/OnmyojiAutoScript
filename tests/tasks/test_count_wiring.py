# -*- coding: utf-8 -*-
"""防回归: 所有"可计数"任务都必须走**统一次数入口**。

## 为什么需要这条测试

改造前"次数"是**双轨**的:

* 界面有 `scheduler.target` 输入框 —— 但**全仓无人读取**（空壳）
* 真正生效的是各任务配置里的字段 —— 但**界面改不到**

更糟的是各任务**各写各的**:

| 写法 | 后果 |
|---|---|
| `self.current_count = 0` | 毁掉磁盘恢复 —— 重启后从头再打, 永远打不满 N |
| 直接读 `xxx_config.limit_count` | 界面上的次数输入框无效 |
| 从不调 `bind_counter()` | `commit_count()` 是空操作 -> 计数**根本不落盘** |

改造后统一为:

    self.bind_counter()                    # 恢复计数 + 设定 limit_count
    # 或(分段计数的任务, 如 BondlingFairyland 的 handoff 模式):
    self.limit_count = self.effective_target() or 0

本测试**读源码**检查这条约定, 这样以后加新任务时忘了接线会立刻红。
"""
import re
from pathlib import Path

import pytest

from module.config import task_catalog as TC

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / 'tasks'

#: 允许保留 `self.current_count = 0` 的任务, 及原因。
#:
#: ★ 这些是**分段计数**的任务 —— "一人打一半"的双人/多人流程里,
#:   下半场要**从 0 重新计数**, 清零是刻意行为, 不能换成 `bind_counter()`
#:   (那会把上半场的计数带进来)。
ALLOW_EXPLICIT_RESET = {
    'BondlingFairyland':
        'handoff 双人模式分两段, 下半场刻意从 0 重新计数',
}

#: 允许直接读配置字段的任务, 及原因。
ALLOW_DIRECT_READ = {
    # 分段计数的任务用 effective_target() 而非 bind_counter(),
    # 但仍需在读上限处用 self.limit_count —— 所以这里应为空。
}


def countable_sources() -> list:
    """所有可计数任务的源码文件。"""
    out = []
    for meta in TC.all_meta():
        if not meta.countable:
            continue
        d = TASKS / meta.task
        if not d.exists():
            continue
        out.append((meta, d))
    return out


def test_meta_has_countable_tasks():
    """前提: 确实存在可计数任务(否则下面的检查会空转, 变成假绿)。"""
    got = [m for m in TC.all_meta() if m.countable]
    assert len(got) >= 10, f'可计数任务太少({len(got)}), 元数据可能坏了'


def test_countable_tasks_use_unified_entry():
    """
    每个可计数任务都要出现 `bind_counter()` 或 `effective_target()`。

    没有它 -> 任务自己读配置 -> 界面上的次数输入框无效, 且计数不落盘。
    """
    missing = []
    for meta, d in countable_sources():
        text = '\n'.join(
            f.read_text(encoding='utf-8') for f in sorted(d.glob('*.py')))
        if 'bind_counter' in text or 'effective_target' in text:
            continue
        missing.append(meta.task)
    assert not missing, (
        f'这些可计数任务没有走统一次数入口(bind_counter/effective_target): '
        f'{missing}\n'
        f'-> 它们会直接读配置, 界面上的"次数"改不动, 且计数不落盘。'
        f'请在 run() 开头加 `self.bind_counter()`。')


@pytest.mark.parametrize('meta,task_dir', countable_sources(),
                         ids=lambda x: x.task if hasattr(x, 'task') else '')
def test_no_unjustified_count_reset(meta, task_dir):
    """
    不允许把 `current_count` 无条件清零 —— 那会毁掉磁盘恢复。

    ★ 这是"进程重启后从头再打, 永远打不满 N"的直接原因。
    """
    if meta.task in ALLOW_EXPLICIT_RESET:
        pytest.skip(f'已知且合理: {ALLOW_EXPLICIT_RESET[meta.task]}')
    bad = []
    for f in sorted(task_dir.glob('*.py')):
        for i, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            s = line.strip()
            if s.startswith('#'):
                continue
            if re.search(r'self\.current_count\s*=\s*0\b', s):
                bad.append(f'{f.name}:{i}')
    assert not bad, (
        f'{meta.task} 里把 current_count 清零了: {bad}\n'
        f'-> 会毁掉磁盘恢复。改用 `self.bind_counter()`。\n'
        f'   若确实是分段计数(如 handoff 模式), 把它加进 '
        f'ALLOW_EXPLICIT_RESET 并写明原因。')


def test_allow_lists_have_reasons():
    """白名单必须写明原因 —— 避免变成"随手加个例外就过"。"""
    for task, reason in ALLOW_EXPLICIT_RESET.items():
        assert reason and len(reason) >= 8, f'{task} 的例外原因太短'
        assert TC.get(task) is not None, f'{task} 不是有效任务名'


def test_bind_counter_exists_on_base_task():
    """统一入口本身必须存在, 且能设定 limit_count。"""
    from tasks.base_task import BaseTask

    assert hasattr(BaseTask, 'bind_counter')
    assert hasattr(BaseTask, 'effective_target')
    assert hasattr(BaseTask, 'commit_count')
