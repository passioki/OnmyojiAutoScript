# -*- coding: utf-8 -*-
"""★★ C6 出口 / C7 结果 —— 流程控制面（`docs/DESIGN-SPEC.md` §1.19）。

## 为什么要有这个模块

★ 实测（SPEC §1.19-三）：★ 8 个任务里"为什么停下来"和"算不算成功"
  **全都写在 `break` 旁边的那一行 `success = ...`** ⇒
  * ★ 同一个"停下来"在不同任务里**含义不同**
    （★ `RyouToppa` 就把"清票完成"写成了 `success = False`，见 SPEC §4.5-㉜）
  * ★ **资源耗尽（没票）** 这一态**在类型系统里没有名字** ⇒ 谁都可以把它写成失败

## ★★ 用户裁定（[10-14]，逐字）

> "**没票算成功，本来就是清票，票没有了就不用清了。**"

★ ⇒ `Exit.RESOURCE_EMPTY` 必须映射到 **`Outcome.EXHAUSTED`**，而 `EXHAUSTED` **算成功**。

## ★ 用法（任务侧）

```python
from module.flow import Exit, Outcome, finish

exit_ = Exit.RESOURCE_EMPTY if not self.has_ticket() else Exit.COUNT_DONE
outcome = finish(exit_)            # ★ 唯一映射点
success = outcome.is_success       # ★ 收尾交给 set_next_run(success=...)
```
★ **P0 只加不改**：本模块**纯数据类型**，不改任何现有任务的行为。
"""
from enum import Enum

__all__ = ['Exit', 'Outcome', 'finish', 'EXIT_TEXT_ZH', 'OUTCOME_TEXT_ZH']


class Exit(Enum):
    """★★ C6：**为什么停下来**（★ 8 类，来自 8 张流程图的实测归纳 · SPEC §1.19-二-C6）。

    ★ 每一类**都能在真实任务里找到出处**（见各行注释）——
      ★ 没有凭空发明的类别。
    """

    PAUSED = 'paused'
    #: ★ 用户点「暂停调度」/ 别的行 `[▶]`（`base_task.py:686 raise_if_paused`）

    COUNT_DONE = 'count_done'
    #: ★ 次数打满（`bind_counter()` 定的 `limit_count`）

    TIME_DONE = 'time_done'
    #: ★ 时间到（`time_limit` ← `expected_minutes`）

    RESOURCE_EMPTY = 'resource_empty'
    #: ★★ 资源耗尽（没票）—— ★ **用户裁定：算成功**（`RealmRaid:198` / `RyouToppa:198`）

    STATE_LOST = 'state_lost'
    #: ★ 状态丢失（★ `Orochi:186/385 is_room_dead()` —— 房间没了）

    DEP_FAILED = 'dep_failed'
    #: ★ 依赖失败（★ `Orochi:197/204` 邀请不到队友 · `AutoCheckinBigGod:69/75/84` adb/frida/APP 不可用）

    ALREADY_DONE = 'already_done'
    #: ★ 目标已被满足（★ `AreaBoss:165` 已上榜 · `AutoCheckinBigGod:142` 没有可领的）

    ABORTED = 'aborted'
    #: ★ 异常中断（★ `GameStuckError` / `GameTooManyClickError` 等，见 `module/exception.py`）


#: ★ 出口的中文说明（★ 上界面 / 上日志用；★ 与 `Exit` 一一对应）
EXIT_TEXT_ZH = {
    Exit.PAUSED: '用户暂停（本轮结束）',
    Exit.COUNT_DONE: '次数已打满',
    Exit.TIME_DONE: '本次时间已到',
    Exit.RESOURCE_EMPTY: '资源已用完（没票了）',
    Exit.STATE_LOST: '状态丢失（房间/队伍没了）',
    Exit.DEP_FAILED: '依赖不可用（队友/ADB/APP）',
    Exit.ALREADY_DONE: '目标已被满足（已上榜/已领完）',
    Exit.ABORTED: '异常中断',
}


class Outcome(Enum):
    """★★ C7：**这一轮算成功吗**（★ 三态 · SPEC §1.19-二-C7）。

    ★ 为什么必须是**三态**（不是 `bool`）：
      ★ "资源用完"既不是"做完"，也不是"失败" —— 它是**做不了**。
      ★ 把它压成 `bool` ⇒ ★ 只能二选一 ⇒ ★ `RyouToppa` 选了"失败"就错了。
    """

    DONE = 'done'
    #: ★ 正常做完

    FAILED = 'failed'
    #: ★ 真失败（★ 会进失败冷却）

    EXHAUSTED = 'exhausted'
    #: ★★ 资源用完 —— ★ **语义 = 成功**（★ 用户裁定）

    @property
    def is_success(self) -> bool:
        """★ 能不能拿去 `set_next_run(success=...)`。

        ★★ 这是"三态 → 二态"的**唯一**出口：
          ★ `DONE` / `EXHAUSTED` ⇒ `True`；★ `FAILED` ⇒ `False`。
        ★ 依据：★ 用户裁定"没票算成功" + ★ 8 个任务的既有行为
          （★ 暂停/打满/时间到/已上榜 都**不改 `success`**）。
        """
        return self is not Outcome.FAILED

    @property
    def is_exhausted(self) -> bool:
        """★ 是不是"资源用完"（★ 用于日志/界面区分"打满了"与"没票了"）。"""
        return self is Outcome.EXHAUSTED


#: ★ 结果的中文说明
OUTCOME_TEXT_ZH = {
    Outcome.DONE: '已完成',
    Outcome.FAILED: '失败',
    Outcome.EXHAUSTED: '资源已用完（本轮结束）',
}

#: ★★ 出口 → 结果 的**唯一映射表**（★ 改语义只改这里）
_FAILED_EXITS = frozenset({
    Exit.STATE_LOST,      # ★ 房间没了 = 失败（Orochi 既有行为）
    Exit.DEP_FAILED,      # ★ 依赖不可用 = 失败（Orochi / AutoCheckinBigGod 既有行为）
    Exit.ABORTED,         # ★ 异常中断 = 失败
})

_EXHAUSTED_EXITS = frozenset({
    Exit.RESOURCE_EMPTY,  # ★★ 用户裁定："没票算成功"
})


def finish(exit_: Exit) -> Outcome:
    """★ C6 → C7：把"为什么停"翻译成"算不算成功"（★ **唯一映射点**）。

    ★ 判据（★ 三条，全部来自**任务既有行为** + **用户裁定**，不是我发明）：

    | 出口 | 结果 | 依据 |
    |---|---|---|
    | `RESOURCE_EMPTY` | ★ `EXHAUSTED`（★ **算成功**）| ★★ 用户 [10-14] 裁定"没票算成功" |
    | `STATE_LOST` / `DEP_FAILED` / `ABORTED` | ★ `FAILED` | ★ `Orochi` 房间没了/邀请失败 = `success False`；★ 异常 = 失败 |
    | 其余（`PAUSED`/`COUNT_DONE`/`TIME_DONE`/`ALREADY_DONE`）| ★ `DONE` | ★ 8 个任务实测：这些出口**都不改 `success`**（保持 True）|

    :param exit_: 本次循环的出口
    :return: 三态结果
    """
    if not isinstance(exit_, Exit):
        # ★ 响亮失败：★ 免得有人传字符串（那会静默落进"其余 ⇒ DONE"）
        raise TypeError(f'finish() 只接受 Exit，收到 {type(exit_).__name__}: {exit_!r}')
    if exit_ in _FAILED_EXITS:
        return Outcome.FAILED
    if exit_ in _EXHAUSTED_EXITS:
        return Outcome.EXHAUSTED
    return Outcome.DONE
