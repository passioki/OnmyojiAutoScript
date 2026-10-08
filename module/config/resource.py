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

from module.config.availability import AvailabilityWindow


class Period(str, Enum):
    """容量重置周期。仅在 refill 为 `none` 时有意义。"""

    NONE = 'none'          # 不重置(只靠 interval/slots 补充)
    DAILY = 'daily'        # 每天 0 点(或 reset_at)重置
    WEEKLY = 'weekly'      # 每周一 0 点重置


@dataclass(frozen=True)
class Recharge:
    """
    池子如何补充 —— 三种**互斥**的方式(一次只用一种)。

    为什么把它独立出来: 早期版本把 `refill` 与 `period` 平铺在 `Resource` 上,
    结果出现 `refill='interval'` 与 `period=WEEKLY` **同时非默认**的组合
    (真八岐大蛇: 每周回满 2 次, 同时"距上次运行 3 天"). 那种状态语义含糊 ——
    读者无法判断"到底哪天能跑"。分层后每种方式**自带**它需要的参数,
    不存在自相矛盾的组合。

    | `kind`     | 含义               | 需要的参数        |
    |------------|--------------------|-------------------|
    | `NONE`     | 只在周期边界回满   | `period`          |
    | `INTERVAL` | 距上次补充 N 时间   | `interval`,`period`+`amount` |
    | `SLOTS`    | 在固定时刻补充      | `slots`,`period`+`amount` |
    | `WINDOW`   | 只在活动期可做      | `period`          |

    `period` + `amount` 对 `INTERVAL`/`SLOTS` 可选: 指定后表示
    "每周期至少回补 `amount` 次"(如真蛇每周 2 次)。
    """

    kind: Literal['none', 'interval', 'slots', 'window'] = 'none'
    interval: tuple = (0, 0, 0)      # (days, hours, minutes), kind=INTERVAL
    slots: tuple = ()                # ((hour, minute), ...), kind=SLOTS
    period: Period = Period.NONE     # 周期边界重置
    amount: int = 1                  # 每次补充/每周期回补几格(增量式)
    refill_to_full: bool = False     # True: 每次补充直接**回满** capacity
    reset_at: time = time(0, 0)

    def __post_init__(self):
        if self.kind not in ('none', 'interval', 'slots', 'window'):
            raise ValueError(f'未知 recharge.kind: {self.kind!r}')
        if self.kind == 'interval' and not any(self.interval):
            raise ValueError("recharge.kind='interval' 需要非零 interval")
        if self.kind == 'slots' and not self.slots:
            raise ValueError("recharge.kind='slots' 需要非空 slots")
        if self.amount < 1:
            raise ValueError(f'amount 必须 >= 1, 实际 {self.amount}')
        for s in self.slots:
            # 严格要求"二元组"。畸形输入(如 `slots=(25,)` —— 少了一层括号)
            # 要给**清晰的 ValueError**, 而不是迭代出整数后抛 TypeError。
            if not isinstance(s, (tuple, list)) or len(s) != 2:
                raise ValueError(
                    f'非法 slot: {s!r} —— 应为 (hour, minute) 二元组, '
                    f'且 slots 需要外层再包一层: slots=((0, 0), (12, 0))')
            h, m = s
            if not (isinstance(h, int) and isinstance(m, int)):
                raise ValueError(f'非法 slot: {s!r} —— 时分必须是整数')
            if not (0 <= h <= 23) or not (0 <= m <= 59):
                raise ValueError(f'非法 slot: {s!r} —— 小时 0-23, 分钟 0-59')

    # ------------------------------------------------------------ 便捷属性
    @property
    def interval_timedelta(self) -> timedelta:
        d, h, m = (list(self.interval) + [0, 0, 0])[:3]
        return timedelta(days=d, hours=h, minutes=m)

    @property
    def is_periodic(self) -> bool:
        return self.period != Period.NONE

    @property
    def is_activity_gated(self) -> bool:
        return self.kind == 'window'

    # ------------------------------------------------------------ 周期边界
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
        """下一个周期起点。period 为 NONE 时返回 now(无周期概念)。"""
        if self.period == Period.NONE:
            return now
        start = self.period_start(now)
        if self.period == Period.WEEKLY:
            return start + timedelta(days=7)
        if self.period == Period.DAILY:
            return start + timedelta(days=1)
        return start

    # ------------------------------------------------------------ slots
    def next_slot(self, now: datetime) -> datetime:
        """下一个补充时刻(严格大于 now)。"""
        if not self.slots:
            raise ValueError('next_slot 需要非空 slots')
        ordered = sorted(self.slots)
        for h, m in ordered:
            cand = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if cand > now:
                return cand
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

        曾用单一的 `[start, end)` 语义, 导致调用方在 `start` 上加 1 微秒来回避
        锚点重复计数 —— 结果把 `end` 侧恰好落在 slot 上的那次也排除了
        (如 `(00:00, 12:00)` 数到 0 次, 使额度要等到 12:00 之后才生效)。
        显式参数比隐式 hack 清楚。
        """
        if not self.slots or end <= start:
            return 0
        cur = self.next_slot(start)
        count = 0
        while cur < end or (include_end and cur == end):
            count += 1
            cur = self.next_slot(cur)
            if count > 100000:      # 防御: 异常时间跨度不应无限循环
                break
        return count

    # ------------------------------------------------------------ 显示
    def describe(self) -> str:
        """人类可读描述, 供界面与日志使用。"""
        if self.kind == 'window':
            return '活动期'
        parts = []
        if self.kind == 'interval':
            d, h, m = self.interval
            txt = (f'{d}天' if d else '') + (f'{h}小时' if h else '') + \
                  (f'{m}分' if m else '')
            parts.append(f'每 {txt} 补 {self.amount}')
        elif self.kind == 'slots':
            parts.append('每天 ' + '、'.join(f'{h:02d}:{m:02d}' for h, m in sorted(self.slots)))
        if self.is_periodic:
            per = '每天' if self.period == Period.DAILY else '每周'
            parts.append(f'{per}重置')
        return '，'.join(parts) if parts else '不限'


@dataclass(frozen=True)
class Resource:
    """
    任务的可运行资源。

    语义模型:
        有一个容量 `capacity` 的"池子"; 池子按 `recharge` 规则补充;
        每次运行消耗 `consume`; 池子里够 `consume` **且**落在 `window` 内才能跑。

    字段:
        capacity: 池子容量(能连续跑几次)
        consume:  每次运行消耗几格(通常 1)
        recharge: 补充规则(见 `Recharge`)
        window:   开放时段(硬约束); None = 不限时段, 由用户在配置里填

    例:
        日轮之陨(每天 50 次)   Resource(capacity=50,
                                       recharge=Recharge(period=Period.DAILY))
        逢魔之时(每小时1次)     Resource(capacity=1,
                                       recharge=Recharge(kind='interval',
                                                         interval=(0, 1, 0)))
        金币妖怪(0/12 点各1次)  Resource(capacity=2,
                                       recharge=Recharge(kind='slots',
                                                         slots=((0,0),(12,0))))
        真八岐大蛇(每周2次)     Resource(capacity=2,
                                       recharge=Recharge(period=Period.WEEKLY,
                                                         amount=2))
        超鬼王(活动期)          Resource(recharge=Recharge(kind='window',
                                                            period=Period.DAILY))
    """

    capacity: int = 1
    consume: int = 1
    recharge: Recharge = None
    window: AvailabilityWindow = None

    def __post_init__(self):
        if self.recharge is None:
            object.__setattr__(self, 'recharge', Recharge())
        if self.capacity < 1:
            raise ValueError(f'capacity 必须 >= 1, 实际 {self.capacity}')
        if self.consume < 1:
            raise ValueError(f'consume 必须 >= 1, 实际 {self.consume}')
        if self.consume > self.capacity:
            raise ValueError(
                f'consume({self.consume}) 不能大于 capacity({self.capacity}), '
                f'否则永远跑不起来')

    # ------------------------------------------------------------ 转发便捷属性
    @property
    def refill(self) -> str:
        """补充方式(转发 `recharge.kind`, 便于调用方少写一层)。"""
        return self.recharge.kind

    @property
    def period(self) -> Period:
        return self.recharge.period

    @property
    def interval(self) -> tuple:
        return self.recharge.interval

    @property
    def interval_timedelta(self) -> timedelta:
        return self.recharge.interval_timedelta

    @property
    def slots(self) -> tuple:
        return self.recharge.slots

    @property
    def reset_at(self) -> time:
        return self.recharge.reset_at

    @property
    def amount(self) -> int:
        """每个周期/每格补充时, 回补几次。"""
        return self.recharge.amount

    @property
    def is_periodic(self) -> bool:
        return self.recharge.is_periodic

    @property
    def is_activity_gated(self) -> bool:
        return self.recharge.is_activity_gated

    @property
    def has_window(self) -> bool:
        """是否配置了开放时段(硬约束)。"""
        return self.window is not None and self.window.enabled

    def period_start(self, now: datetime) -> datetime:
        return self.recharge.period_start(now)

    def next_period_start(self, now: datetime) -> datetime:
        return self.recharge.next_period_start(now)

    def next_slot(self, now: datetime) -> datetime:
        return self.recharge.next_slot(now)

    def prev_slot(self, now: datetime) -> datetime:
        return self.recharge.prev_slot(now)

    def slots_between(self, start: datetime, end: datetime,
                      include_end: bool = True) -> int:
        return self.recharge.slots_between(start, end, include_end)

    def describe(self) -> str:
        return self.recharge.describe()

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
            return cls(capacity=1,
                       recharge=Recharge(kind='window', period=Period.DAILY))

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
                # 充能类的语义是"补充时刻**回满**可用次数", 不是增量加一 ——
                # 金币妖怪 0 点、12 点各把次数补满到 2。
                recharge=Recharge(kind='slots', slots=tuple(sorted(slots)),
                                  refill_to_full=True),
            )

        cap = int(count_default) if count_default else 1
        iv = _parse_interval(success_interval)
        if iv and any(iv):
            days, hours, minutes = iv
            # 只有**恰好**一天/一周才归为周期重置 —— 因为周期意味着
            # "每天 0 点(或每周一)池子回满", 与"隔 N 时间"语义不同。
            # 3 天、3 小时这类间隔必须保留为 interval, 否则会丢掉间隔信息。
            # (踩过: 曾把 days<7 一律归为 daily, 于是真蛇的"每 3 天"变成"每天",
            #  3 小时的斗技变成"每天 1 次", 间隔信息全丢。)
            if hours == 0 and minutes == 0 and days == 1:
                return cls(capacity=cap,
                           recharge=Recharge(period=Period.DAILY))
            if hours == 0 and minutes == 0 and days == 7:
                return cls(capacity=cap,
                           recharge=Recharge(period=Period.WEEKLY))
            return cls(capacity=cap,
                       recharge=Recharge(kind='interval', interval=iv))
        return cls(capacity=cap, recharge=Recharge(period=Period.DAILY))


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
