# -*- coding: utf-8 -*-
"""★★★ [10-15] **L3-0 / R1-a：调度单元（ScheduleUnit）** —— 周期任务 / 临时任务的统一语义模型。

## 为什么需要它（用户裁定）

> ★★ **用户原话（逐字）**：
> > "**L3的周期任务和临时任务在底层实现上是否能够统一架构来表达。
> >   这样每次创建新的任务只需要用一种架构就行。对L2也会有影响**"

★ 依据：`docs/GRIND-REDUCTION.md` §3.3（用户已裁定：**L3-0 提到 L2 之前，R1 先做**）。

## ★★ 现状：同一件事有**两套平行实现**，★ 而且**存储布局也不同**

| | ★ 周期任务（`period != none`）| ★ 临时任务（`period == none`）|
|---|---|---|
| 记账 | `task_state.record_success()`（`:189`）| `task_state.mark_entry_completed()`（`:994`）|
| 过期判定 | `task_state.is_completed_in_period()`（`:219`）| `task_state.get_entry_completed()`（`:891`）|
| ★ 存储位置 | ★ `data[config][<key>]` = `{last_success, period, period_key}` | ★ `data[config][ENTRIES_KEY][eid]` = `{completed, completed_session, …}` |
| 过期作用域 | 日 / 周 / 月（`period_key`）| **本次启动**（`completed_session == session_start`）|

★★ ⇒ ★ **两者的差异可以完全参数化成一个 `expire` 字段**：
`session`（= 临时）· `daily` / `weekly` / `monthly`（= 周期）；★ `never` / `<时间戳>` 是**保留值**（R1-b 接线）。

## ★★★ R1-a 的边界（★ 本文件**只做三件事，绝不改行为**）

1. ★ **值对象** `ScheduleUnit`（**纯数据、零 IO**）；
2. ★ **可逆映射** `expire <-> period`（★ 有守卫证明可逆）；
3. ★ **委托**：`record_outcome()` / `is_due()` **只转调既有实现** ⇒
   ★ **零行为变更**（★ 这是"先建等价层、再翻方向"的标准做法）。
   ★ **R1-b** 才把方向翻过来：让旧函数变成本模块的**薄别名**，
     并把 `config.py` / `script.py` 的调用点切过来 —— **届时才可能改变行为，必须另做等价性验证**。

★ **不许**在本文件里读写 `task_state` 的存储、不许改 `_write_all` 的布局 —— ★ 那是 R1-b 的事。
"""
from dataclasses import dataclass

from module.config import task_state as TS

#: ★ 过期作用域：`session` = 临时任务（★ 重启即失效）
SESSION = 'session'
#: ★ 过期作用域：周期任务
DAILY = 'daily'
WEEKLY = 'weekly'
MONTHLY = 'monthly'

#: ★ 周期作用域集合（★ 只有它们走"按 period_key"那套）
PERIODIC = (DAILY, WEEKLY, MONTHLY)

#: ★ R1-b 才接线的保留值（★ 现在就**响亮报错**，不静默当 session 处理）
RESERVED = ('never',)

#: ★ 本刀支持的 expire 全集
SUPPORTED = (SESSION, DAILY, WEEKLY, MONTHLY)

#: ★ `period` 字段的历史取值（`meta.py` 用它）
_PERIOD_TO_EXPIRE = {
    'none': SESSION, '': SESSION, None: SESSION,
    DAILY: DAILY, WEEKLY: WEEKLY, MONTHLY: MONTHLY,
}
_EXPIRE_TO_PERIOD = {
    SESSION: 'none', DAILY: DAILY, WEEKLY: WEEKLY, MONTHLY: MONTHLY,
}


def _norm(value) -> str:
    """★ 统一小写去空白（★ `period` 在 meta.py 里可能是 `Period.DAILY` 的字符串形式）。"""
    if value is None:
        return ''
    text = str(value).strip().lower()
    # ★ 兼容 `Period.DAILY` / `period.daily` 这类枚举字符串
    if '.' in text:
        text = text.rsplit('.', 1)[-1]
    return text


def expire_for_period(period) -> str:
    """★ `period`（历史字段）→ `expire`（统一字段）。

    ★ `none` ⇒ `session`（= 临时任务）；★ `daily/weekly/monthly` ⇒ 同名。
    """
    key = _norm(period)
    if key in _PERIOD_TO_EXPIRE:
        return _PERIOD_TO_EXPIRE[key]
    raise ValueError(
        f'★ 不认识的 period={period!r}（只支持 none/daily/weekly/monthly）—— '
        f'★ 若这是新周期类型，请同时更新 `expire_for_period()` 与 R1 的 `period_key()`')


def period_for_expire(expire) -> str:
    """★ `expire` → `period`（★ `expire_for_period()` 的逆映射）。"""
    key = _norm(expire)
    if key in _EXPIRE_TO_PERIOD:
        return _EXPIRE_TO_PERIOD[key]
    raise ValueError(
        f'★ `expire={expire!r}` 不能映射回 `period`（周期侧只支持 '
        f'{sorted(_EXPIRE_TO_PERIOD)}）')


@dataclass(frozen=True)
class ScheduleUnit:
    """★★ 一个**调度单元** —— ★ 周期任务与临时任务**共用**这一个模型。

    ★ 它只有"键 + 过期策略"两件事是调度必需的；★ 其余（次数/窗口/出口）由上层补。

    :param task: ★ 任务名（大驼峰，★ 与 `tasks/<Name>/` 同名）
    :param entry_id: ★ 队列条目 id（★ **空串 = 周期任务/自动补齐**）
    :param expire: ★ 过期作用域，见 `SESSION` / `PERIODIC` / `RESERVED`
    """

    task: str
    entry_id: str = ''
    expire: str = SESSION

    def __post_init__(self):
        if not str(self.task or '').strip():
            raise ValueError('★ ScheduleUnit.task 不能为空')
        key = _norm(self.expire)
        if key in RESERVED:
            raise ValueError(
                f'★ expire={self.expire!r} 是 **R1-b 的保留值**，本刀未接线 —— '
                f'★ 现在支持 {list(SUPPORTED)}（★ 宁可不做，也不静默当 session 处理）')
        if key not in SUPPORTED:
            raise ValueError(
                f'★ 不认识的 expire={self.expire!r}（支持 {list(SUPPORTED)}）')
        object.__setattr__(self, 'expire', key)

    # ── ★ 键：与 `task_state._state_key()` **同口径**（entry_id 优先，否则任务名，统一小写）
    @property
    def key(self) -> str:
        eid = str(self.entry_id or '').strip()
        return (eid if eid else str(self.task)).strip().lower()

    @property
    def is_periodic(self) -> bool:
        return self.expire in PERIODIC

    def describe(self) -> str:
        """★ 一行可读描述（★ 日志/报错用，★ 不许在别处再拼一份）。"""
        kind = '周期' if self.is_periodic else '临时'
        return (f'{self.task}[{kind}·{self.expire}]'
                + (f' entry_id={self.entry_id}' if self.entry_id else ''))


def unit_for(task: str, *, period='none', entry_id: str = '') -> ScheduleUnit:
    """★ 从**历史入参**（`period` + `entry_id`）造一个调度单元（★ 迁移期的唯一入口）。"""
    return ScheduleUnit(task=task, entry_id=entry_id or '',
                        expire=expire_for_period(period))


def record_outcome(config_name: str, unit: ScheduleUnit, *,
                   success: bool = True, reason: str = '') -> bool:
    """★★ 统一记账 —— ★ **只转调既有实现**（★ R1-a 零行为变更）。

    * ★ 周期单元 ⇒ `task_state.record_success()`（按 `period_key` 记）
    * ★ 临时单元 ⇒ `task_state.mark_entry_completed()`（按本次启动时间记）

    :return: ★ 是否记账成功（★ 失败不抛，与既有实现同口径）
    """
    if not success:
        # ★ 失败不记"完成"（★ 失败的具体计数由 `failure_state` 负责，不在这里）
        return False
    if unit.is_periodic:
        TS.record_success(config_name, unit.task, period=unit.expire,
                          entry_id=unit.entry_id or None)
        return True
    return TS.mark_entry_completed(config_name, unit.key, reason=reason)


def is_due(config_name: str, unit: ScheduleUnit) -> bool:
    """★★ 统一"该不该跑" —— ★ **只转调既有实现**（★ R1-a 零行为变更）。

    :return: ★ `True` = 现在**可以跑**（★ 与既有实现同义）
    """
    if unit.is_periodic:
        return not TS.is_completed_in_period(
            config_name, unit.task, period=unit.expire,
            entry_id=unit.entry_id or None)
    return not TS.get_entry_completed(config_name, unit.key)
