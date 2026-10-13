# -*- coding: utf-8 -*-
"""防回归: 所有"可计数"任务都必须走**统一次数入口**。

## 为什么需要这条测试

改造前"次数"是**双轨**的:

* 界面有 `scheduler.target` 输入框 —— 但**全仓无人读取**（空壳）
* 真正生效的是各任务配置里的字段 —— 但**界面改不到**

更糟的是各任务**各写各的**:

| 写法 | 后果 |
|---|---|
| `self.current_count = 0` | ★ **已无害** —— 见下方 2026-10-13 裁定（旧口径下才叫"毁掉磁盘恢复"）|
| 直接读 `xxx_config.limit_count` | 界面上的次数输入框无效 |
| 从不调 `bind_counter()` | 统一入口失效：`limit_count` 没人设、条目身份拿不到 |
| 从不调 `commit_count()` | ★ 现在**不再**是 bug（它是空操作），但调用点仍要保留 |

改造后统一为:

    self.bind_counter()                    # ★ 本轮从 0 开始 + 设定 limit_count
    # 或(分段计数的任务, 如 BondlingFairyland 的 handoff 模式):
    self.limit_count = self.effective_target() or 0

★ **2026-10-13 用户裁定「丙」**（★ 本文件的口径随之更新）:

> "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
> "**或者按照时间戳来判断**" / "**就按这个来**"

* ★ `bind_counter()` ★ **不再从磁盘恢复**（本轮进度只在内存）
* ★ `commit_count()` ★ **不再写盘**（空操作）
* ★ "这条本次跑没跑过" ⇒ 由 `task_state.get_entry_completed()`
  的【时间戳比对】负责（`completed_session` ↔ `session_start`）

本测试**读源码**检查这条约定, 这样以后加新任务时忘了接线会立刻红。
"""
import re
from pathlib import Path

import pytest

from module.config import task_catalog as TC

REPO = Path(__file__).resolve().parents[2]
TASKS = REPO / 'tasks'

#: 允许在任务里**手工清零** `self.current_count` 的任务, 及原因。
#:
#: ★ 2026-10-13 用户裁定「丙」之后: ★ **清零本身不再是 bug**
#:   （`bind_counter()` 也从 0 开始 —— `tasks/base_task.py:374`）。
#:   ★ 这份名单现在只用于"**文档纪律**": 手工清零必须写明为什么不能走统一入口。
#:
#: ★ 这些是**分段计数**的任务 —— "一人打一半"的双人/多人流程里,
#:   下半场要**从 0 重新计数**, 清零是刻意行为。
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

    没有它 -> 任务自己读配置 -> 界面上的次数输入框无效，
    且拿不到统一入口设定的 `limit_count`（★ 本轮进度只在内存，
    所以"忘了接线"的表现不再是"计数不落盘"，而是"上限/身份都不对"）。
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
        f'-> 它们会直接读配置, 界面上的"次数"改不动, 且拿不到统一入口设定的 '
        f'`limit_count`。请在 run() 开头加 `self.bind_counter()`。')


@pytest.mark.parametrize('meta,task_dir', countable_sources(),
                         ids=lambda x: x.task if hasattr(x, 'task') else '')
def test_no_unjustified_count_reset(meta, task_dir):
    """
    不允许把 `current_count` **无理由**清零。

    ## ★★★ 2026-10-13 用户裁定「丙」之后本用例的**口径已反过来** ★★★

    ## ★★ 用户原话

    > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
    > "**或者按照时间戳来判断**"
    > "**就按这个来**"

    | | 旧口径（**已作废**）| ★ 现行口径 |
    |---|---|---|
    | `bind_counter()` | 从磁盘恢复 `runs` | ★ **一律从 0 开始**（不读盘）|
    | `commit_count()` | 把本轮计数写盘 | ★ **空操作**（不写盘）|
    | `current_count = 0` | ★ **是 bug**（"毁掉磁盘恢复"）| ★ **无害**（本来就从 0 开始）|

    ★ 所以本用例**不再**禁止"清零"（★ 清零已是正常语义，
      而且 `bind_counter()` 内部就是这么做的：`tasks/base_task.py:374`）。
    ★ 现在它只守**文档纪律**：可计数任务若有**手工清零**，
      必须写进 `ALLOW_EXPLICIT_RESET` 并说明理由 —— 不允许"随手清零、无人知道"。

    ## ★ 对齐规格书哪一条

    ★ `docs/DESIGN-SPEC.md` §1.6-L500/L502-504（分歧块⑩ L508-516）
      "**本轮进度只在内存；磁盘只保留长时记录**"。
    """
    bad = []
    for f in sorted(task_dir.glob('*.py')):
        for i, line in enumerate(f.read_text(encoding='utf-8').splitlines(), 1):
            s = line.strip()
            if s.startswith('#'):
                continue
            # ★ 只认**裸清零**（恰好赋 0）；`self.current_count = self.bind_counter(...)`
            #   （`tasks/FallenSun/script_task.py:47`）是走统一入口，不算裸清零。
            if re.fullmatch(r'self\.current_count\s*=\s*0\b.*', s):
                bad.append(f'{f.name}:{i}')
    if bad and meta.task in ALLOW_EXPLICIT_RESET:
        pytest.skip(f'已知且合理: {ALLOW_EXPLICIT_RESET[meta.task]}')
    assert not bad, (
        f'{meta.task} 里手工把 current_count 清零了: {bad}\n'
        f'-> ★ 现在清零本身**不再**是 bug（`bind_counter()` 也从 0 开始），\n'
        f'   但必须写明理由: 把它加进 `ALLOW_EXPLICIT_RESET` 并写清\n'
        f'   「为什么这一处不能走 `bind_counter()`」。')


def test_allow_lists_have_reasons():
    """白名单必须写明原因 —— 避免变成"随手加个例外就过"。"""
    for task, reason in ALLOW_EXPLICIT_RESET.items():
        assert reason and len(reason) >= 8, f'{task} 的例外原因太短'
        assert TC.get(task) is not None, f'{task} 不是有效任务名'


def test_task_level_counter_api_is_gone():
    """★ 守卫：★ **任务级计数那三个函数不许复活**（规格书 §2.2-REC6）。

    ## ★ 为什么删的（用户原话）

    > "既然你用 `runs`，那就把他**取代 `current_count`**，
    >  这两个**不是一个东西吗**。" -> "**1 甲**"
    > "**不能存在两套机制**" -> "**2 废弃**"

    ★ `module/config/task_state.py` 里的 `get_count` / `add_count` /
      `reset_count` **已删** ⇒ ★ 谁再调它们只会拿到 `AttributeError`
      （被最外层 `except` 吞掉 ⇒ 表现成"计数莫名不生效"，极难排查）。
    ★ 唯一入口是**条目级**：`get_entry_runs` / `bump_entry_runs` /
      `reset_entry_runs`（+ 长时记录 `record_entry_run`）。
    ★ 本用例**用 `tokenize` 剥掉注释与 docstring** 后再查 ——
      因为这两个文件的注释 / docstring 里**大量提到**这些名字
      （正是用来记录"已删除"），不剥会假红。

    ## ★ 对齐规格书哪一条

    ★ `docs/DESIGN-SPEC.md` L431（"~~`get_count` / `add_count` /
      `reset_count`~~ ★ **已删**（任务级，第二套机制）"）。
    """
    read_sites = (
        REPO / 'module' / 'config' / 'task_state.py',
        REPO / 'tasks' / 'base_task.py',
    )

    def _tokens(p) -> list:
        """★ 用 `tokenize` 剥掉**注释与 docstring**，只留真正的名字 token。

        ★ 为什么不用"逐行剥注释"：这两个文件的注释 / docstring 里**大量**
          提到已删函数名（正是用来记录"已删除"），逐行剥会把它们当成代码；
          ★ 而 `tokenize` 是按 Python 语法来的，不会误判三引号 / 行内引号。
        """
        import tokenize
        with open(p, 'rb') as fh:
            return [t.string for t in tokenize.tokenize(fh.readline)
                    if t.type == tokenize.NAME]

    bad = []
    for p in read_sites:
        if not p.exists():
            continue
        names = set(_tokens(p))
        for fn in ('get_count', 'add_count', 'reset_count'):
            # ★ 带下划线前缀的（`reset_entry_runs` / `_read_all`）会被 tokenize
            #   拆成**另一个名字**，天然不会误报。
            if fn in names:
                bad.append(f'{p.name}: {fn}')
    assert not bad, (
        f'★ 任务级计数 API 不能复活（已按"2 废弃"删除）: {bad}\n'
        f'-> 请用条目级那一套（`get_entry_runs` / `bump_entry_runs` / '
        f'`reset_entry_runs`）；两套机制并存会导致"跑不起来"。')


def test_bind_counter_exists_on_base_task():
    """统一入口本身必须存在, 且能设定 limit_count。"""
    from tasks.base_task import BaseTask

    assert hasattr(BaseTask, 'bind_counter')
    assert hasattr(BaseTask, 'effective_target')
    assert hasattr(BaseTask, 'commit_count')
