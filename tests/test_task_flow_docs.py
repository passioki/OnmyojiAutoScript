# -*- coding: utf-8 -*-
"""★ 守卫：「逐任务流程图」不许**漏登记**（台账 `N9-5` · 用户 [10-14] 第 5 条）。

## ★★ 用户原话

> "**对每一个任务的代码逻辑，画出流程图，用于理解代码。**"

## ★ 这条守卫**不要求**"55 个任务全都画完"（那是工作量，不是正确性）

★ 它要求的是：★ **每个任务都在 `docs/flows/README.md` 里有一条登记** ——
  ★ **要么**已有 `docs/flows/<Name>.md`（状态 ✅），
  ★ **要么**在待补表里（状态 ⬜ + 一句理由）。

## ★ 为什么这样设计（而不是"必须都存在"）

* ★ "必须都存在" ⇒ ★ 55 张图没画完之前，守卫**一直红** ⇒
  ★ 红久了的守卫**等于没有**（本项目已有"空转守卫"的教训，见台账 §C.3）。
* ★ "必须登记" ⇒ ★ **新增任务时忘了登记就变红** —— ★ 那才是真正会漏的地方
  （★ 加任务的人**一定**会跑测试，但不一定会想起补文档）。

## ★ 覆盖的内容

| # | 断言 |
|---|---|
| ① | ★ 索引文件存在，且含"待补台账"表 |
| ② | ★★ **每个 `tasks/<Name>/` 都在索引里有一条**（★ 这就是"不许漏登记"）|
| ③ | ★ 标了 ✅ 的，`docs/flows/<Name>.md` **必须真的存在**（不许"登记了却没图"）|
| ④ | ★ 每条待补记录**必须带一句理由**（★ 防"只知道没做、不知道为什么"）|
"""
import logging
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

FLOWS = REPO / 'docs' / 'flows'
INDEX = FLOWS / 'README.md'
TASKS = REPO / 'tasks'


def _task_dirs() -> list:
    """`tasks/` 下**有 `script_task.py`** 的目录名（= 一个任务）。"""
    out = []
    for p in sorted(TASKS.iterdir()):
        if not p.is_dir():
            continue
        if (p / 'script_task.py').exists():
            out.append(p.name)
    return out


@pytest.fixture(scope='module')
def index_text() -> str:
    assert INDEX.exists(), (
        f'★ 缺少索引文件 {INDEX} —— 用户要求"对每一个任务画出流程图"'
        '（[10-14] 记录第 5 条），至少要有索引 + 待补台账')
    return INDEX.read_text(encoding='utf-8')


def test_index_has_backlog_table(index_text):
    """★ 索引里必须有"待补台账"表（否则"没画的"就无处登记）。"""
    assert '待补台账' in index_text, (
        '★ 索引里必须有「待补台账」段 —— 未完成的图要**显式登记**，'
        '★ 不许"悄悄没有"')


def test_every_task_is_registered(index_text):
    """★★★ 核心：★ **每个任务都必须在索引里出现一次**（漏了 ⇒ 变红）。

    ★ 这条守的是"**新增任务时忘了登记**"—— ★ 加任务的人会跑测试，
      但不一定会想起补文档。
    """
    missing = [d for d in _task_dirs() if f'`{d}`' not in index_text]
    assert not missing, (
        '★★★ 这些任务在 `docs/flows/README.md` 的台账里**没有登记**：\n  '
        + ', '.join(missing)
        + '\n★ 请在待补台账里补一行（★ 已有图 ⇒ 标 ✅；★ 没有 ⇒ 标 ⬜ + 一句理由）')


def test_completed_entries_have_a_file(index_text):
    """★ 标了 ✅ 的任务，`docs/flows/<Name>.md` **必须真的存在**。

    ★ 防"登记了却没图"（★ 那比不登记更糟：读者以为有）。
    """
    # ★ 只检查"带 ✅ 且带反引号任务名"的行
    bad = []
    for line in index_text.split('\n'):
        if '✅' not in line:
            continue
        for name in re.findall(r'`([A-Za-z][A-Za-z0-9]*)`', line):
            if not (TASKS / name / 'script_task.py').exists():
                continue        # ★ 不是任务名（例如 `Component` 之类）
            if not (FLOWS / f'{name}.md').exists():
                bad.append(name)
    assert not bad, (
        '★ 这些任务在索引里标了 ✅，但 `docs/flows/<Name>.md` **不存在**：\n  '
        + ', '.join(sorted(set(bad))))


def test_backlog_rows_explain_why(index_text):
    """★ 每条待补记录都要有**一句理由**（★ 不同任务的理由不一样）。

    ★ 判据：★ 待补行里 `⬜` 之后必须还有**实质文字**（不只是状态符号）。
    """
    rows = [l for l in index_text.split('\n')
            if l.startswith('|') and '⬜' in l]
    assert rows, '前置：待补台账里应有记录'
    thin = []
    for r in rows:
        cells = [c.strip() for c in r.strip('|').split('|')]
        # ★ 最后一格 = 理由；★ 去掉状态符号后应还有内容
        why = cells[-1].replace('⬜', '').replace('**', '').strip()
        if len(why) < 4:
            thin.append(r[:80])
    assert not thin, (
        '★ 这些待补记录没写理由（"为什么还没画"）：\n  ' + '\n  '.join(thin)
        + '\n★ 要求：每条待补都要有一句**具体**理由（不是空着）')
