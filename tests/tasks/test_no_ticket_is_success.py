# -*- coding: utf-8 -*-
"""★★ 守卫：**"没票" = 本轮【正常结束】（成功）** —— 用户 [10-14] 裁定。

## ★★ 用户原话（逐字）

> "**没票算成功，本来就是清票，票没有了就不用清了。**"

## ★ 为什么要有这条守卫

★ 同一件事在代码里**两套写法**（★ 实测）：

| 任务 | "没票"分支的写法 | 后果 |
|---|---|---|
| `RealmRaid`（样板）| ★ `mark_entry_completed(...)` + **不改 `success`** | ★ 记**成功** ⇒ 收尾 `set_next_run(success=True)` |
| `RyouToppa`（寮突破）| ⚠ 原来 `success = False` | ★ 记**失败** —— ★ 与裁定**相反** |

★ ⚠ 危险点：★ 这不是"难看"，而是**语义反了** ——
  ★ "票清完了"是**做完了**，不是**失败**；★ 记失败会让界面/统计把
  "清票完成"显示成错误，且会触发失败冷却把任务往后推。

## ★★ 判据为什么用 **AST** 而不是"关键词/行序"

★ 本项目已有教训（台账 §C.3「教训-C」）：
  ★ **源码级"比行序/找关键词"的守卫是空转的** ——
    把校验改成 `if False:` 之后，`raise` 字样**还在**，守卫照样绿。
★ 所以这里**解析语法树**，只看 `if not self.<x>():` 这个分支**体里到底有什么**：
  ① ★ 不许出现 `success = <假值>` 的赋值
  ② ★ 必须有 `mark_entry_completed(...)` 调用
  ③ ★ 必须有 `break`
★ 这样"改回 `success = False`"或"删掉上报"都会**真的变红**（★ 已做注入验证）。

## ★ 覆盖范围

★ `RealmRaid`（★ 样板，作为**正向对照**）+ `RyouToppa`（★ 本次修复对象）。
★ 若将来别的任务也走"没票即本轮完成"，★ **请把它加进 `CASES`**。
"""
import ast
import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

#: (任务目录名, `run()` 里那个"还有票吗"的方法名)
CASES = [
    ('RealmRaid', 'check_ticket'),   # ★ 样板（正向对照）
    ('RyouToppa', 'has_ticket'),     # ★ [10-14] 本次修复
]

RULE = '★ 用户 [10-14] 裁定："没票算成功，本来就是清票，票没有了就不用清了。"'


def _module(task: str):
    """★ 取整个模块的语法树。

    ⚠ [10-14] 订正：★ 一开始我只在 `run()` 里找，**`RealmRaid` 找不到** ——
      因为它的主循环在 **`run_2()`** 里（`run()` 只是转发）。
      ⇒ ★ 判据改为**全模块搜索**（★ 任务里 `run`/`run_2`/`run_leader` 都可能放这段）。
    """
    path = REPO / 'tasks' / task / 'script_task.py'
    assert path.is_file(), f'★ 找不到 {path}'
    return path, ast.parse(path.read_text(encoding='utf-8'))


def _no_ticket_block(tree, method: str):
    """找 `if not self.<method>(...):` 这个 `If` 节点（★ 全模块）。"""
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not (isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not)):
            continue
        operand = test.operand
        if not isinstance(operand, ast.Call):
            continue
        fn = operand.func
        if isinstance(fn, ast.Attribute) and fn.attr == method:
            hits.append(node)
    return hits


@pytest.mark.parametrize('task,method', CASES)
def test_no_ticket_branch_is_found(task, method):
    """★ 前置：分支必须找得到（★ 否则后面的断言全是空转）。"""
    _path, tree = _module(task)
    hits = _no_ticket_block(tree, method)
    assert hits, (
        f'★★ 在 {task}/script_task.py 里找不到 '
        f'`if not self.{method}(...):` 分支 ——\n'
        f'★ 要么代码被重构了（请同步更新本守卫的判据），\n'
        f'★ 要么"没票"这条语义被挪走了（那就是**回归**）。\n{RULE}')


@pytest.mark.parametrize('task,method', CASES)
def test_no_ticket_does_not_mark_failure(task, method):
    """★★★ 核心：★ "没票"分支**不许**把 `success` 置假。"""
    _path, tree = _module(task)
    hits = _no_ticket_block(tree, method)
    assert hits
    bad = []
    for block in hits:
        for stmt in ast.walk(block):
            if not isinstance(stmt, ast.Assign):
                continue
            names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            if 'success' not in names:
                continue
            val = stmt.value
            if isinstance(val, ast.Constant) and not val.value:
                bad.append(f'{task} (第 {stmt.lineno} 行)')
    assert not bad, (
        '★★★ "没票"分支把 `success` 置成了假值 —— **与用户裁定相反**：\n  '
        + '\n  '.join(bad) + f'\n{RULE}\n'
        '★ 正确写法（见样板 `RealmRaid/script_task.py:180-200`）：\n'
        "    self.mark_entry_completed('没票了（本轮结束）')\n"
        '    break          # ★ success 保持 True')


@pytest.mark.parametrize('task,method', CASES)
def test_no_ticket_reports_entry_completed(task, method):
    """★★★ 核心：★ "没票"分支**必须上报"本条目本轮已完成"**。

    ★ 为什么必须：★ 不上报 ⇒ 调度层 `_skip_by_completed()` 剔不掉它
      ⇒ ★ 会被**反复派发**（用户体感："清完票还在 40 秒一轮地跑"）。
    """
    _path, tree = _module(task)
    hits = _no_ticket_block(tree, method)
    assert hits
    for i, block in enumerate(hits):
        calls = [n for n in ast.walk(block)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == 'mark_entry_completed']
        assert calls, (
            f'★★★ {task} 的"没票"分支（第 {block.lineno} 行那个 `if`）'
            f'**没有** `mark_entry_completed(...)`：\n{RULE}\n'
            '★ 依据：不上报 ⇒ `_skip_by_completed()` 剔不掉 ⇒ 反复派发')
    # ★ 顺带: 分支必须 break（否则会继续往下跑去打）
    for block in hits:
        assert any(isinstance(n, ast.Break) for n in ast.walk(block)), (
            f'★ {task} 的"没票"分支没有 `break` —— 没票了还往下走会白跑一趟')


@pytest.mark.parametrize('task,method', CASES)
def test_no_ticket_log_text_says_normal_end(task, method):
    """★ 日志文案必须说"本轮正常结束"（★ 别再说"Try again after 1 hour"）。

    ★ 依据：★ 文案与实现相反 ⇒ ★ 后来读日志的人（包括我）会**判错语义**
      （★ 这正是 `RyouToppa` 这条 bug 一直没被发现的原因之一）。
    """
    _path, tree = _module(task)
    hits = _no_ticket_block(tree, method)
    assert hits
    for block in hits:
        texts = [n.value for n in ast.walk(block)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        blob = ' '.join(texts)
        assert '本轮' in blob and ('结束' in blob or '完成' in blob), (
            f'★ {task} 的"没票"分支日志文案没说清"本轮结束/完成"：{blob!r}\n'
            f'{RULE}')
