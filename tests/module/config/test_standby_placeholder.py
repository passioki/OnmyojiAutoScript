# -*- coding: utf-8 -*-
"""★ 守卫：`Config.get_next()` 在「**队列全完成**」时**必须返回待命占位**，
★ 不许抛 `RequestHumanTakeover`（否则**整个调度循环死掉**）。

## ★★★ 这条守的是**用户两次报过的同一个 bug** ★★★

### 第一次（10-12）—— 用户原话

> "**循环虚设**！！！跑到最后一列后出现以下日志：
>  `CRITICAL No task waiting or pending`"

### 第二次（10-13 实机日志，`记录/20261013-关于循环和周期任务.txt:37-41`）

```
INFO     | 队列里没有可跑的条目（本轮全完成/未到点） -> **待命**（不抛 CRITICAL）
WARNING  | 构造待命占位失败(KeyError: 'Restart')      ← ★★ 真因就在这一行
CRITICAL | No task waiting or pending
CRITICAL | Please enable at least one task
ERROR    | Run script 恋鸟树 error  ➜ RequestHumanTakeover  ➜ 脚本进程退出
```

### ★★ 真因（代码级，已实测）

★ 待命分支这样造占位：

```python
_placeholder = Function('Restart', {'scheduler': {...}})   # config.py:4485
```

★ `Function.__init__` 会调 **`ConfigModel.type(key)`**（`config.py:89`），
  它实现为 **`ConfigModel.__annotations__[key]`**（`config_model.py:314`）
  ⇒ ★ **键必须小写**（`'restart'`）。
★ 实测：`Function('Restart', …)` ⇒ ★ **`KeyError: 'Restart'`**；
  `Function('restart', …)` ⇒ `command='Restart'` ✅
  ⇒ 被 `except` 吞成 warning（`config.py:4492`）⇒ 落到末尾
  ⇒ ★★ **`raise RequestHumanTakeover`** ⇒ `script.py:1130` 的 `while 1` 退出。

## ★★ 这条守卫**怎么保证不空转**（★ 我在这里连续空转了两次，记下来）

★ `get_next()` 有**两条**出路，只有第二条会走占位分支：

```
① `pending_task` 非空 ⇒ 返回 pending 第一条（★ 与占位**无关**）
② `pending` 空 ⇒ 看 `waiting_task`：
     非空 ⇒ 返回 waiting[0]
     为空 ⇒ ★ **待命占位分支**（★ bug 就在这里）
```

★ **我踩的两个坑**（都让守卫"pass 但什么都没守"）：
  1. ★ 只造"空 `run_list` 的配置" ⇒ 但模板里 **`Restart` 是 `enable=True`**
     ⇒ ★ 实测 `pending_task = ['Restart']` ⇒ ★ 走**出路①** ⇒ 空转
  2. ★ 在外部设 `cfg.pending_task = []` ⇒ ★ **无效**！因为
     `get_next()` **第一行就 `self.update_scheduler()`**（`config.py:4351`）
     ⇒ ★ 会**重算并覆盖**这两个列表（★ 实测：设了 waiting 非空，进去又变 `[]`）

★ ⇒ ★ **正确做法：`monkeypatch` 把 `update_scheduler` 打桩**，
  然后**精确**设 `pending_task=[]` + `waiting_task=[]` —— 这才是实机那一刻。

## ★ 覆盖的内容

| # | 断言 | 依据 |
|---|---|---|
| ① | ★★ **全完成 ⇒ `get_next()` 返回占位，绝不抛 `RequestHumanTakeover`** | §1.3-P2 · §1.5-C4 |
| ② | ★ 占位的 `command` 必须是**真任务名**（`tasks/<command>/meta.py` 存在）| `script.py:1139` / `:1156` |
| ③ | ★ 占位必须是 `Function`（**不是 `str` / `None`**）| `Function` 未实现 `__eq__` |
| ④ | ★ 反向：`waiting_task` **非空**时必须返回它（不许误判待命）| 防"把待命分支提前"的走偏修法 |
| ⑤ | ★ 反向：`pending_task` **非空**时必须返回它 | `config.py:4353-4373` |
"""
import copy
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

CFG = '__standby_placeholder_cfg__'
P = REPO / 'config' / f'{CFG}.json'


@pytest.fixture()
def cfg(monkeypatch):
    """造一份**可用**配置，并★ **把 `update_scheduler` 打桩**（见模块 docstring 坑 2）。

    ★ 打桩后 `pending_task` / `waiting_task` **完全由用例决定**
      ⇒ ★ 才能精确复现"待命"那一刻。
    """
    import server  # noqa: F401  （★ 必须先 import，ConfigModel 才自动发现配置类）
    from module.config.config import Config

    cwd_before = os.getcwd()
    try:
        os.chdir(REPO)
        tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
            encoding='utf-8'))
        opt = tmpl['script']['optimization']
        opt['run_list'] = []
        opt['period_backfilled'] = True
        P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')

        c = Config(CFG)
        c.update_scheduler()                 # ★ 先跑一次真的，拿到真实条目
        monkeypatch.setattr(type(c), 'update_scheduler',
                            lambda self: None, raising=True)
        yield c
    finally:
        os.chdir(cwd_before)
        try:
            P.unlink()
        except OSError:
            pass


def _make_idle(c):
    """把 `Config` 置成**"待命"状态**（= 实机日志那一刻）。"""
    c.pending_task = []
    c.waiting_task = []
    c.task = None
    return c


# ────────────────────────── ① 核心：全完成不许把调度器搞死
def test_get_next_never_raises_when_queue_fully_done(cfg):
    """★★★ 核心（★ 用户 10-12 + 10-13 两次报的同一个 bug）：

    **队列全完成（`pending` 空 + `waiting` 空）⇒ `get_next()` 必须返回待命占位，
    绝不抛 `RequestHumanTakeover`。**

    ★ 为什么这条最重要：★ `RequestHumanTakeover` 会**中断整个调度循环**
      ⇒ ★ 用户体感就是"**循环虚设 / 跑完一轮后调度凭空死掉**"
      ⇒ ★ 界面不再更新、后续到点的周期任务**也不会跑**。
    """
    from module.exception import RequestHumanTakeover

    idle = _make_idle(cfg)
    try:
        task = idle.get_next()
    except RequestHumanTakeover as exc:      # ★★ 10-13 实机日志里那一次
        pytest.fail(
            '★★★ 队列全完成时 `get_next()` 抛了 `RequestHumanTakeover` '
            '—— 这正是"循环虚设 / 跑到最后一列后调度死掉"的根因。\n'
            '★ 检查 `Config.get_next()` 的"待命占位"分支：'
            '`Function(...)` 的第一个参数必须是**小写配置键**\n'
            '  （`ConfigModel.type()` == `__annotations__[key]`；'
            '★ 传 `"Restart"` 会 `KeyError`）。\n'
            f'  （原始异常：{exc!r}）')
    assert task is not None, '★ 待命占位不许是 None（上游拿它当字符串用）'


# ────────────────────────── ② 占位的 `command` 必须是**真任务名**
def test_standby_placeholder_has_real_task_command(cfg):
    """★ 占位必须带一个**真任务名**的 `command`。

    ★ 依据：`script.py:1139` —— `if self.is_first_task and task == 'Restart':`
      ⇒ ★ 上游是**按字符串**比对的；`script.py:1156` 还会把它写进
        `model.running_task` 并发给前端。
    ★ 若 `command` 是 `'Unknown'`（`Function` 的降级分支）⇒
      ★ 前端会显示一个不存在的任务名。
    """
    task = _make_idle(cfg).get_next()
    command = str(getattr(task, 'command', '') or '')
    assert command, '★ 占位必须有 command'
    assert command != 'Unknown', (
        '★ 占位的 command 不许是 `Unknown` —— 那说明 `Function` 走了'
        '降级分支（`data` / `scheduler` 不合法），前端会显示未知任务')
    assert (REPO / 'tasks' / command / 'meta.py').exists(), (
        f'★ 占位的 command={command!r} 不是真任务'
        '（`tasks/<command>/meta.py` 不存在）—— 上游会拿它去'
        '`tasks/<command>/script_task.py`，所以占位只能借用**真实存在**的任务名')


# ────────────────────────── ③ 占位必须是 Function，不是 str
def test_standby_placeholder_is_a_function_object(cfg):
    """★ 占位必须是 `Function` 对象（**不能**返回 `None` 或字符串）。

    ★ 依据：`script.py:1139` 用 `==` 比字符串 —— 而 `Function` **未实现
      `__eq__`** ⇒ ★ 返回字符串会让 `task == 'Restart'` 变成"字符串比字符串"，
        语义会漂（★ 这正是"不许用 `return None` 当修法"的理由）。
    """
    from module.config.config import Function

    task = _make_idle(cfg).get_next()
    assert not isinstance(task, str), (
        '★ 占位不许返回字符串 —— `Function` 未实现 `__eq__`，'
        '★ 上游 `task == "Restart"` 会变成"字符串比字符串"，语义会漂')
    assert isinstance(task, Function), f'★ 占位应是 Function，实际 {type(task)!r}'
    assert getattr(task, 'next_run', None) is not None, '★ 占位必须有 next_run'
    assert getattr(task, 'enable', None) is True, '★ 占位应是 enable=True'


# ────────────────────────── ④ 反向：waiting 非空必须返回它
def test_waiting_task_still_returned_when_present(cfg):
    """★ 反向守卫：★ `waiting_task` **非空**时**不能**走待命占位。

    ★ 为什么要有这条：★ 修"不抛异常"最容易的走偏做法是**把待命分支提前**
      ⇒ ★ 那会让"还有等待中的任务"直接返回占位 ⇒ ★ **调度器彻底不出任务**。
    """
    waited = copy.deepcopy(list(cfg.pending_task))
    assert waited, '前置：本配置应有条目可用（否则本用例无意义）'
    cfg.pending_task = []
    cfg.waiting_task = waited
    cfg.task = None

    task = cfg.get_next()
    assert task is not None
    assert str(getattr(task, 'command', '') or '') == \
        str(getattr(waited[0], 'command', '') or ''), (
        '★ `waiting_task` 非空时 `get_next()` 必须返回其中的条目，'
        '★ 不许直接给"待命占位"（否则调度器就再也不出任务了）')


# ────────────────────────── ⑤ 反向：pending 非空必须返回它
def test_pending_task_still_returned_when_present(cfg):
    """★ 反向守卫：★ `pending_task` **非空**时必须返回它（★ 出路① 不许被改坏）。

    ★ 依据：`config.py:4353-4373`（`pending_task` 一有内容就进它）。
    """
    pend = copy.deepcopy(list(cfg.pending_task))
    assert pend, '前置：本配置应有可派发条目（否则本用例无意义）'
    cfg.pending_task = pend
    cfg.waiting_task = []
    cfg.task = None

    task = cfg.get_next()
    assert str(getattr(task, 'command', '') or '') == \
        str(getattr(pend[0], 'command', '') or ''), (
        '★ `pending_task` 非空时 `get_next()` 必须返回它（出路①）')
