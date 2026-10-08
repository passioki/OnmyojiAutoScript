# -*- coding: utf-8 -*-
"""任务的"资源规则"(Resource) —— 把游戏知识从 54 个配置界面收归一处。

## 为什么需要它

旧状态: "多久能跑一次"散落在**五个字段**里, 且每个任务用哪些字段还不一样:

    success_interval / charge_slots / charge_max / charge_consume / limit_count

于是"想知道某任务现在能不能跑"要读好几处, 且充能类只能靠另一套代码旁路实现。

新状态: 每个任务一条 `Resource`。**一个概念一个词**(设计原则 1),
**游戏知识只存在一处**(原则 2)。

## 三种补充方式, 覆盖全部 54 个任务

| 补充方式 | 语义 | 例 |
|---|---|---|
| `interval` | 距上次运行满 N 时间后, 补满容量 | 逢魔之时: 每 1 小时可做 1 次 |
| `slots` | 在**固定时刻**补满容量 | 金币妖怪: 0 点 +1、12 点 +1, 上限 2 |
| `window` | 只在**活动期**内可做 | 超鬼王: 活动开了才能打 |

三者本质相同 —— 都是"什么时候有资源" —— 所以是**同一个 `Resource` 的三种形态**,
而不是三套并列机制。

## 与旧字段的对应

    Resource(interval=(0,1,0), capacity=1)    <-  success_interval=1h
    Resource(slots=((0,0),(12,0)), capacity=2) <- charge_slots='0,12' + charge_max=2
    Resource(capacity=50)                     <- limit_count=50  (周期=每日, 由 period 给)

注意最后一行: 旧代码用 **两个** 字段(`success_interval=1d` + `limit_count=50`)
表达"每天打 50 次"; 新模型一个 `Resource` 就够。
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Literal


class Period(str, Enum):
    """容量重置周期。仅在 refill 为 `none` 时有意义。"""

    NONE = 'none'          # 不重置(只靠 interval/slots 补充)
    DAILY = 'daily'        # 每天 0 点(或 reset_at)重置
    WEEKLY = 'weekly'      # 每周一 0 点重置


@dataclass(frozen=True)
class Resource:
    """
    任务的可运行资源。

    语义模型:
        有一个容量 `capacity` 的"池子"; 池子按 `refill` 规则补充;
        每次运行消耗 `consume`; 池子里够 `consume` 就能跑。

    字段:
        capacity: 池子容量(能连续跑几次)
        consume:  每次运行消耗几格(通常 1)
        refill:   补充方式 —— 'interval'(按间隔) | 'slots'(按时刻) | 'none'
        interval: (天, 时, 分) —— refill='interval' 时使用
        slots:    ((时, 分), ...) —— refill='slots' 时使用
        period:   周期重置(周期到时池子回满); Period.NONE 表示不重置
        reset_at: 周期边界时刻(游戏每日重置点), 默认 0 点

    例:
        日轮之陨(每天 50 次)   Resource(capacity=50)                      # period 默认 DAILY
        逢魔之时(每小时 1 次)   Resource(capacity=1, interval=(0, 1, 0), period=NONE)
        金币妖怪(0/12 点各1次)  Resource(capacity=2, refill='slots', slots=((0,0),(12,0)), period=NONE)
        超鬼王(活动期)          Resource(refill='window', period=NONE)
    """

    capacity: int = 1
    consume: int = 1
    refill: Literal['interval', 'slots', 'none', 'window'] = 'none'
    interval: tuple = (0, 0, 0)          # (days, hours, minutes)
    slots: tuple = ()                    # ((hour, minute), ...)
    period: Period = Period.DAILY
    reset_at: time = time(0, 0)

    # ------------------------------------------------------------------ 校验
    def __post_init__(self):
        if self.capacity < 1:
            raise ValueError(f'capacity 必须 >= 1, 实际 {self.capacity}')
        if self.consume < 1:
            raise ValueError(f'consume 必须 >= 1, 实际 {self.consume}')
        if self.consume > self.capacity:
            raise ValueError(
                f'consume({self.consume}) 不能大于 capacity({self.capacity}), '
                f'否则永远跑不起来')
        if self.refill not in ('interval', 'slots', 'none', 'window'):
            raise ValueError(f'未知 refill: {self.refill!r}')
        if self.refill == 'interval' and not any(self.interval):
            raise ValueError("refill='interval' 需要非零的 interval")
        if self.refill == 'slots' and not self.slots:
            raise ValueError("refill='slots' 需要非空的 slots")
        # slots 必须有序且合法
        for s in self.slots:
            if len(s) != 2 or not (0 <= s[0] <= 23) or not (0 <= s[1] <= 59):
                raise ValueError(f'非法 slot: {s!r}')

    # ------------------------------------------------------------ 便捷属性
    @property
    def interval_timedelta(self) -> timedelta:
        d, h, m = (list(self.interval) + [0, 0, 0])[:3]
        return timedelta(days=d, hours=h, minutes=m)

    @property
    def is_periodic(self) -> bool:
        """是否按周期重置容量(固定任务的"每天打 N 次")。"""
        return self.period != Period.NONE

    @property
    def is_activity_gated(self) -> bool:
        """是否受活动期限制(限时活动)。"""
        return self.refill == 'window'

    # ------------------------------------------------------------ 周期边界的纯函数
    def period_start(self, now: datetime) -> datetime:
        """
        当前周期的起点。

        daily: 以 reset_at 为界(如 reset_at=00:00 则今天 0 点);
        weekly: 以 reset_at 为界, 且周一为一周之始。
        """
        anchor = now.replace(hour=self.reset_at.hour, minute=self.reset_at.minute,
                             second=0, microsecond=0)
        if now < anchor:
            anchor -= timedelta(days=1)
        if self.period == Period.WEEKLY:
            anchor -= timedelta(days=anchor.weekday())   # 回退到周一
        return anchor

    def next_period_start(self, now: datetime) -> datetime:
        """下一个周期起点。"""
        start = self.period_start(now)
        if self.period == Period.WEEKLY:
            return start + timedelta(days=7)
        if self.period == Period.DAILY:
            return start + timedelta(days=1)
        return start

    # ------------------------------------------------------------ slots 相关的纯函数
    def next_slot(self, now: datetime) -> datetime:
        """下一个补充时刻(严格大于 now)。"""
        if not self.slots:
            raise ValueError('next_slot 需要非空 slots')
        ordered = sorted(self.slots)
        for h, m in ordered:
            cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand > now:
                return cand
        # 今天已过完所有 slot -> 明天的第一个
        h, m = ordered[0]
        return (now + timedelta(days=1)).replace(
            hour=h, minute=m, second=0, microsecond=0)

    def prev_slot(self, now: datetime) -> datetime:
        """上一个补充时刻(<= now)。"""
        if not self.slots:
            raise ValueError('prev_slot 需要非空 slots')
        ordered = sorted(self.slots)
        for h, m in reversed(ordered):
            cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand <= now:
                return cand
        h, m = ordered[-1]
        return (now - timedelta(days=1)).replace(
            hour=h, minute=m, second=0, microsecond=0)

    def slots_between(self, start: datetime, end: datetime,
                      include_end: bool = True) -> int:
        """
        统计 `start < slot` 且 `slot <= end`(include_end=True)
        或 `slot < end`(include_end=False)的补充时刻个数。

        **为什么需要 `include_end` 参数**: 两种调用场景的边界语义相反 ——

        * 统计"锚点到现在补充了几次": `start` 是**已结算点**(该时刻的补充已计入
          当前额度), 要排除; `end` 是当前时刻, 若恰在 slot 上则**该补充已发生**,
          要包含。
        * 判断"某时刻是否已补充": 同上。

        曾用单一的 `[start, end)` 语义, 导致调用方在 `start` 上加 1 微秒来回避
        锚点重复计数 —— 结果把 `end` 侧恰好落在 slot 上的那次也排除了
        (如 `(00:00, 12:00)` 数到 0 次, 使额度要等到 12:00 之后才生效)。
        显式参数比隐式 hack 清楚。
        """
        if not self.slots or end <= start:
            return 0
        # 从 start **之后**的第一个 slot 开始
        cur = self.next_slot(start)
        count = 0
        while cur < end or (include_end and cur == end):
            count += 1
            cur = self.next_slot(cur)
            if count > 100000:      # 防御: 异常时间跨度不应无限循环
                break
        return count

    # ------------------------------------------------------------ 工厂: 从旧字段推导
    @classmethod
    def from_legacy(cls, *, success_interval: str = None,
                    charge_slots: str = None, charge_max=None,
                    charge_consume=None, count_default=None,
                    category: str = None) -> 'Resource':
        """
        从旧的分散字段推导出 `Resource`。

        这是**迁移的桥梁**: 让新模型能在不改动旧配置的前提下先跑起来对账。
        """
        # 限时活动: 活动期判定交给探针; 额度每日回满 1 次
        # (注意: 不能给 capacity=0 —— 那会让任务永远跑不起来。
        #  也不能给 period=NONE —— 那额度用掉就再也补不回来。)
        if category == 'limited':
            return cls(capacity=1, refill='window', period=Period.DAILY)

        # 充能类: slots
        if charge_slots:
            slots = []
            for part in str(charge_slots).split(','):
                part = part.strip()
                if not part:
                    continue
                if ':' in part:
                    h, m = part.split(':')[:2]
                else:
                    h, m = part, '0'
                slots.append((int(h), int(m)))
            return cls(
                capacity=int(charge_max or max(1, len(slots))),
                consume=int(charge_consume or 1),
                refill='slots',
                slots=tuple(sorted(slots)),
                period=Period.NONE,
            )

        # interval 形态
        iv = _parse_interval(success_interval)
        cap = int(count_default) if count_default else 1
        if iv and any(iv):
            days, hours, minutes = iv
            # 整天的间隔 -> 用周期(每天/每周); 不足一天 -> 用 interval
            if hours == 0 and minutes == 0 and days >= 1:
                period = Period.WEEKLY if days >= 7 else Period.DAILY
                return cls(capacity=cap, period=period)
            return cls(capacity=cap, refill='interval', interval=iv,
                       period=Period.NONE)
        return cls(capacity=cap, period=Period.DAILY)


def _parse_interval(s):
    """'01 00:00:00' / '00:03:00' -> (days, hours, minutes)。"""
    if not s:
        return None
    import re
    s = str(s).strip()
    m = re.match(r'(\d+)\s+(\d+):(\d+):(\d+)', s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r'(\d+):(\d+):(\d+)', s)
    if m:
        return 0, int(m.group(1)), int(m.group(2))
    return None
