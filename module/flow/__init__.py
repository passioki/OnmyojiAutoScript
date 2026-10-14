# -*- coding: utf-8 -*-
"""★★ 流程控制面（Flow Control）—— `docs/DESIGN-SPEC.md` §1.19。

> ★★ **用户原话（[10-14]）**：
> > "**看了这些流程图，请抽象一下，实现这些流程，需要哪些抽象层面的控制。**"

★ 本包 = **§1.19 那 11 个控制面里，先落地的 4 个"纯数据类型"**（★ P0 · **只加不改**）：

| 控制面 | 本包文件 | 类型 |
|---|---|---|
| ★ **C1 准入** | `precondition.py` | `Verdict`（跑 / 跳过 / ★ **推迟**）· `Precondition` 协议 |
| ★ **C4 判断** | `match.py` | `Match`（ok / score / roi / text）|
| ★ **C6 出口** | `outcome.py` | `Exit`（★ **8 类具名出口**）|
| ★ **C7 结果** | `outcome.py` | `Outcome`（★ **三态**）· `finish()`（★ **唯一映射点**）|

★ **为什么先落这四个**：★ 它们**不改任何现有行为**，
  ★ 却能把 SPEC §1.19-四 的三个红灯**从"靠人记"变成"类型保证"**：

```
★ 红灯 1 出口语义靠自觉  ⇒ ★ 现在必须写 `Exit.XXX`，★ 再经 finish() 出结果
★ （红灯 2 收尾 / 红灯 3 暂停检查点 属 C2/C8/C9，★ P1~P2 做）
```

★ **C10 记忆**（`entry_state`）落在 `module/config/task_state.py`
  —— ★ 因为它**要用既有的落盘 + 锁**（★ 不另造一套）。
"""
from module.flow.match import Match
from module.flow.outcome import (
    EXIT_TEXT_ZH,
    OUTCOME_TEXT_ZH,
    Exit,
    Outcome,
    finish,
)
from module.flow.precondition import Precondition, Verdict

__all__ = [
    # C1
    'Verdict', 'Precondition',
    # C4
    'Match',
    # C6 / C7
    'Exit', 'Outcome', 'finish', 'EXIT_TEXT_ZH', 'OUTCOME_TEXT_ZH',
]
