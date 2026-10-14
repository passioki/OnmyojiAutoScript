# -*- coding: utf-8 -*-
"""★ C1 准入判据 —— 流程控制面（`docs/DESIGN-SPEC.md` §1.19-C1）。

## 为什么要有这个模块

★ 实测（SPEC §1.19-一）：★ 用户说的"**该任务是否该执行**"其实是**两层**：

| 层 | 现在在哪 | 状态 |
|---|---|---|
| ★ **① 调度层准入**（7 个门）| ★ 全在 `module/config/config.py`（`:1811 enable` · `:1820 类别` · `:1946 窗口` · `:1927 到点` · `:2141 完成记忆` · `:1829 冷却` · `:2530 队列`）| ✅ 已集中 |
| ★ **② 任务内前置**（票/资源/界面状态）| ★ 散落在各任务里，**写法各异** | ❌ 无统一抽象 |

★ 而且它**有三种结局**（★ 这是最要紧的一点）：

```
★ 跑      → 继续
★ 跳过    → 本轮什么都不做，**但不是失败**
★ 推迟    → ★★ "现在不能跑，等 X 点再来" —— ★ 现在没有这一态
             ⇒ ★ 只能靠 `success = False` 让调度器 1 小时后再试
               （★ 但那就把它**记成了失败** ⇒ 形状不对）
```

## ★ P0 只加不改

★ 本模块**纯数据类型 + 协议**，★ 不改 `config.py` 的 7 个门，★ 也不改任何任务的判断。
★ 任务侧**愿意用就用**（P1~P2 再逐个接入）。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = ['Verdict', 'Precondition']


@dataclass(frozen=True)
class Verdict:
    """★★ C1：一条"准入判据"的结论 —— **三态**：跑 / 跳过 / 推迟。

    ★ 为什么 `frozen=True`：★ 判据结论是**值**，不是对象状态
      （★ 免得有人在任务里改它 ⇒ 同一条判据两次结论不同 ⇒ 难查）。

    ## ★ 三个构造器（★ 覆盖三种结局）

    | 构造器 | 语义 | 调度层该怎么处理 |
    |---|---|---|
    | `Verdict.run()` | ★ 可以跑 | ★ 继续 |
    | `Verdict.skip(reason)` | ★ 本轮不跑（**不是失败**）| ★ 记 reason，★ **别进失败冷却** |
    | `Verdict.defer(until, reason)` | ★★ **到 `until` 再来** | ★★ 把 `next_run` 推到 `until`（★ 现在只能靠 `success=False`）|
    """

    ok: bool
    #: ★ 现在能不能跑

    reason: str = ''
    #: ★★ 为什么（★ **要能直接上界面/日志** —— 例："没票了""本周已完成"）

    defer_until: datetime | None = None
    #: ★★ 推迟到什么时候（★ 仅 `defer` 时有值；★ `ok=False` 时为 `None`）

    # ---------------------------------------------------------------- 构造器
    @classmethod
    def run(cls) -> 'Verdict':
        """★ 可以跑。"""
        return cls(ok=True)

    @classmethod
    def skip(cls, reason: str = '') -> 'Verdict':
        """★ 本轮不跑（★ **不是失败**）。"""
        return cls(ok=False, reason=str(reason or ''))

    @classmethod
    def defer(cls, until: datetime, reason: str = '') -> 'Verdict':
        """★★ 推迟到 `until`（★ 这一态以前**没有名字**）。"""
        if not isinstance(until, datetime):
            raise TypeError(f'defer(until=...) 必须是 datetime，收到 '
                            f'{type(until).__name__}: {until!r}')
        return cls(ok=False, reason=str(reason or ''), defer_until=until)

    # ---------------------------------------------------------------- 便捷
    @property
    def is_deferred(self) -> bool:
        """★ 是不是"推迟"（★ 而不是"跳过"）—— ★ 调度层据此推 `next_run`。"""
        return (not self.ok) and self.defer_until is not None

    def __bool__(self) -> bool:
        """★ 让判据能直接当条件用：`if verdict:` ⇒ ★ 只在 `ok` 时为真。"""
        return bool(self.ok)


@runtime_checkable
class Precondition(Protocol):
    """★ C1：一个"准入判据"（★ 任务**声明**判据，而不是把判断散在 `run()` 里）。

    ★ 实现约定：
      * ★ **不许抛异常**（★ 判据读不到数据 ⇒ `Verdict.skip('读不到 X')`）
      * ★ `reason` 必须是人话（★ 它会出现在界面上）
    """

    def check(self) -> Verdict:
        """★ 返回本判据的结论。"""
        ...
