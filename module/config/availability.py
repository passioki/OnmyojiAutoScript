# -*- coding: utf-8 -*-
"""任务开放时段(AvailabilityWindow) —— 纯逻辑, 无副作用。

## 为什么需要它

阴阳师里很多玩法**不是随时都能做**, 而是有固定开放时段:

    逢魔之时   每天 17:00 - 23:00
    首领退治   每天某个时段
    狭间暗域   周五/六/日 某个时段
    ...

而此前 OAS **完全没有"开放时段"这个概念**。用户只能靠一个迂回办法绕过:
把 `success_interval` 设得很短(如 1 小时), 让任务**频繁醒来去碰运气** ——
因为软件无法保证"在开放时段内一定会打开该任务"。

这带来两个后果:
  1. `success_interval` 里混进了**用户意图**(轮询节奏), 不再是游戏机制;
     任何拿它当游戏知识读的逻辑都会出错。
  2. 不在时段内时, 任务会白跑一趟(进界面、发现做不了、退出), 浪费时间。

`AvailabilityWindow` 把"游戏什么时候允许"显式建模为**硬约束**,
与"用户想多快轮询"(`interval`)**彻底分开**。

## 设计要点

* **不写死任何时段** —— 时段全部由用户配置, 默认"不限时段"(行为不变)。
* **支持跨午夜** —— 如 `22:00 - 02:00`。
* **支持限定星期** —— 如狭间暗域只有周五/六/日。
* **纯函数** —— 判定与"下一次开放/关闭时刻"都可单测。
* **可自学习** —— 见 `ObservedWindow`: 记录实际跑通的时刻, 反推真实时段,
  与用户配置比对。这样即使初始配置不准, 软件也能自我纠正。
"""
import bisect
from dataclasses import dataclass
from datetime import datetime, time, timedelta
# ★ (b) 动态窗口: `parse_time()` 需要"构造 time"的入口, 但字段名 `time`
#   会遮蔽模块级名字 —— 所以用别名（不改既有 `time(...)` 的用法）。
from datetime import datetime as datetime_cls
from datetime import time as time_cls

# 一星期 7 天, 周一 = 0(与 datetime.weekday() 一致)
ALL_DAYS = (0, 1, 2, 3, 4, 5, 6)
DAY_NAMES = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')


def _minutes(t: time) -> int:
    """时刻 -> 当日第几分钟。"""
    return t.hour * 60 + t.minute


@dataclass(frozen=True)
class AvailabilityWindow:
    """
    任务的开放时段。

    语义:
        只有落在 [start, end) 内(且当天在 `days` 内)才允许运行。
        若 `end <= start`, 视为**跨午夜**窗口, 如 22:00-02:00。

    字段:
        enabled: 是否启用时段限制。**默认 False** —— 即"不限时段",
                 这样新字段不改变既有行为(与 `period` 的处理方式一致)。
        start / end: 起止时刻。
        days: 允许的星期(0=周一)。默认全周。
        days_of_month: 允许的**月内日**(1-31)。**默认空 = 不限**。
                       ★ 用户明确要求"每月以此类推" —— 即 `Period.MONTHLY`
                         的窗口是"当月 1 日 00:00 到 月末 24:00",
                         用 `days_of_month=range(1, 32)` + `days=ALL_DAYS` 表达。
                         空元组 = 不限（**不能**用"空集"表示"都不允许",
                         那样会让任务的窗口永远关闭）。

    例:
        AvailabilityWindow(True, time(17), time(23))                    # 每天 17-23
        AvailabilityWindow(True, time(19), time(21), days=(4, 5, 6))    # 周五六日 19-21
        AvailabilityWindow(True, time(22), time(2))                     # 跨午夜 22-次日2
        AvailabilityWindow(True, time(0), time(23, 59),
                           days_of_month=tuple(range(1, 32)))           # 每月（整月）
    """

    enabled: bool = False
    start: time = time(0, 0)
    end: time = time(23, 59)
    days: tuple = ALL_DAYS
    # ★ 空元组 = 不限月内日（**不是**"都不允许"）
    days_of_month: tuple = ()
    # ★★ 动态 days（用户裁定 (b)）: 运行时从**任务配置**读星期 ★★
    #
    # 值是 `Config` 上的点分路径**元组**, 每项指向一个"星期"字段, 如:
    #     ('guild_banquet.guild_banquet_time.day_1',
    #      'guild_banquet.guild_banquet_time.day_2')
    #
    # `Config.resolve_windows()` 在运行时读成 0-6 的整数, 与静态 `days`
    # **取并集** —— 于是**窗口仍是唯一排期依据**, 只是 `days` 可能
    # **运行时求值**（用户原话: "这个 B 并不冲突"）。
    days_from_config: tuple = ()
    # ★ 同上的**时刻**版: 指向一个 `datetime.time` 字段, 运行时读成 `start`/`end`
    #   值形如 `('guild_banquet.guild_banquet_time.run_time_1',)`
    #   （只放一个路径 -> `start` 用它, `end` = start + 窗口跨度）
    times_from_config: tuple = ()

    def __post_init__(self):
        # ★ 空 `days` 的两种合法情形（否则真的没法判定）:
        #   1. `days_from_config` 非空 -> 运行时才有值（用户裁定 (b)）
        #   2. `days_of_month` 非空 -> 按月内日限（`days` 不参与）
        if not self.days and not self.days_from_config \
                and not self.days_of_month:
            raise ValueError(
                'days 不能为空（除非 days_from_config / days_of_month 非空）; '
                '如需不限时段请把 enabled 设为 False')
        for d in self.days:
            if not (0 <= int(d) <= 6):
                raise ValueError(f'非法星期: {d!r}(应为 0-6, 周一=0)')
        if not any(int(d) != d for d in self.days):     # 全是整数
            object.__setattr__(self, 'days', tuple(sorted({int(d) for d in self.days})))
        # 动态 days: 每项必须是"非空的配置路径字符串"
        if self.days_from_config:
            for pth in self.days_from_config:
                if not isinstance(pth, str) or not pth.strip():
                    raise ValueError(
                        f'days_from_config 的项必须是配置路径字符串, '
                        f'实际 {pth!r}')
            object.__setattr__(
                self, 'days_from_config',
                tuple(str(pth).strip() for pth in self.days_from_config))
        # 动态时刻: 同 days_from_config 的校验
        if self.times_from_config:
            for pth in self.times_from_config:
                if not isinstance(pth, str) or not pth.strip():
                    raise ValueError(
                        f'times_from_config 的项必须是配置路径字符串, '
                        f'实际 {pth!r}')
            object.__setattr__(
                self, 'times_from_config',
                tuple(str(pth).strip() for pth in self.times_from_config))
        # 月内日: 1-31; 空 = 不限
        if self.days_of_month:
            for d in self.days_of_month:
                if not (1 <= int(d) <= 31):
                    raise ValueError(f'非法月内日: {d!r}(应为 1-31)')
            object.__setattr__(
                self, 'days_of_month',
                tuple(sorted({int(d) for d in self.days_of_month})))

    @property
    def restricts_month_day(self) -> bool:
        """是否限制了月内日。"""
        return bool(self.days_of_month) and len(self.days_of_month) < 31

    # ------------------------------------------------------------ 基本属性
    @property
    def crosses_midnight(self) -> bool:
        """是否跨午夜(如 22:00-02:00)。"""
        return _minutes(self.end) <= _minutes(self.start)

    @property
    def duration_minutes(self) -> int:
        """每天开放时长(分钟)。"""
        if not self.enabled:
            return 24 * 60
        span = _minutes(self.end) - _minutes(self.start)
        return span if span > 0 else span + 24 * 60

    @property
    def is_unrestricted(self) -> bool:
        """是否"实质上不限时段"（全周 + 整天 + 不限月内日）。

        ★ 三个维度**都要看** —— 曾经只判 `len(self.days) == 7`, 于是
          `AvailabilityWindow(True, 17:00, 23:00)` 被**误判成"不限"**
          （它明明只开放 6 小时）。这个 bug 由
          `test_is_unrestricted_accounts_for_month` 抓到。
        """
        if not self.enabled:
            return True
        if len(self.days) != 7 or self.restricts_month_day:
            return False
        if self.days_from_config or self.times_from_config:
            # 动态值运行时才知道 -> 保守地**不**当作"不限"
            return False
        # 时刻必须覆盖整天才算不限。
        # `end` 用 23:59 表示"当天结束"（`AvailabilityWindow` 的默认值）,
        # 因此把 `end <= start` 且 start 为 00:00 的情况也算作整天
        # （即 00:00-23:59 或跨午夜的 00:00-00:00）。
        if _minutes(self.start) != 0:
            return False
        return _minutes(self.end) >= 23 * 60 + 59

    # ------------------------------------------------------------ 判定
    def contains(self, at) -> bool:
        """`at` 是否落在本时段内。

        ★ 动态窗口（`days_from_config` / `times_from_config`）**未解析**时:
          本对象**不知道**实际星期/时刻 -> 返回 True（**不误拦**）。
          真正的判定在 `Config.in_window()`（那里能读配置解析动态值）。
          —— 否则 `TaskSpec.in_window()` 会因为 `days=()` 而**永远 False**（踩过）。
        """
        if self.days_from_config or self.times_from_config:
            return True
        if not self.enabled:
            return True
        m = _minutes(at)
        s, e = _minutes(self.start), _minutes(self.end)

        # ★ 月内日门禁（`Period.MONTHLY` 用）。空元组 = 不限。
        if self.days_of_month and at.day not in self.days_of_month:
            return False

        if not self.crosses_midnight:
            if not (s <= m < e):
                return False
            return at.weekday() in self.days

        # 跨午夜: 当日 [s, 24:00) 属今天; [00:00, e) 属昨天
        if m >= s:
            return at.weekday() in self.days
        if m < e:
            prev = (at - timedelta(days=1)).weekday()
            return prev in self.days
        return False

    # ------------------------------------------------------------ 下一次开/关
    def next_opening(self, now: datetime, strict: bool = False) -> datetime:
        """
        下一次开放的时刻。

        * `strict=False`(默认): 若 `now` 已在时段内, 返回 `now` 本身。
          适合"我最早什么时候能跑"的语义。
        * `strict=True`: 返回**严格晚于当前这个窗口**的下一次开放。
          用于枚举"未来的所有开放时刻" —— 若 `now` 已在窗口内,
          非严格模式会反复返回同一个 `now`, 导致枚举退化。
          (踩过: 用它枚举候选点时, 窗口内只得到周期边界候选,
           漏掉次日 17:00, 于是 next_available 跳到 32 天上界。)

        时段未启用时返回 `now`。
        """
        if not self.enabled:
            return now
        if self.contains(now):
            if not strict:
                return now
            # 跳到当前窗口结束之后, 再重新找
            now = self.next_closing(now)
        for delta in range(0, 9):
            day = now + timedelta(days=delta)
            opening = day.replace(hour=self.start.hour, minute=self.start.minute,
                                  second=0, microsecond=0)
            if opening <= now:
                continue
            if day.weekday() in self.days:
                return opening
        # 理论上不可达(days 非空 -> 7 天内必有)
        return now + timedelta(days=7)

    def next_closing(self, now: datetime) -> datetime:
        """
        当前(或下一次)窗口的关闭时刻。

        用于自学习: 记录"这个时段内实际成功过", 以及判断一次成功是否发生在
        窗口边界附近。
        """
        if not self.enabled:
            return now + timedelta(days=365)
        if not self.contains(now):
            now = self.next_opening(now)
        closing = now.replace(hour=self.end.hour, minute=self.end.minute,
                              second=0, microsecond=0)
        if self.crosses_midnight and _minutes(now) >= _minutes(self.start):
            closing += timedelta(days=1)
        elif closing <= now:
            closing += timedelta(days=1)
        return closing

    def today_span(self, now: datetime):
        """
        返回"当前这一天"的开放区间 [(start, end)], 便于界面显示。
        跨午夜时 end 落在次日。
        """
        if not self.enabled:
            return None
        s = now.replace(hour=self.start.hour, minute=self.start.minute,
                        second=0, microsecond=0)
        e = now.replace(hour=self.end.hour, minute=self.end.minute,
                        second=0, microsecond=0)
        if e <= s:
            e += timedelta(days=1)
        return s, e

    # ------------------------------------------------------------ 显示
    def describe(self) -> str:
        """人类可读描述, 供界面与日志使用。"""
        if not self.enabled:
            return '未声明开放时段'
        span = f'{self.start:%H:%M}-{self.end:%H:%M}'
        if self.crosses_midnight:
            span += '(跨夜)'
        # ★ 月内日（`Period.MONTHLY`）
        if self.days_of_month and len(self.days_of_month) == 31:
            return f'每月 {span}'
        if self.days_of_month:
            if set(self.days_of_month) == set(range(1, 16)):
                label = '1-15'
            elif set(self.days_of_month) == set(range(16, 32)):
                label = '16-月末'
            else:
                label = ','.join(str(d) for d in self.days_of_month)
            return f'每月 {label} 日 {span}'
        if len(self.days) == 7 and not self.days_from_config:
            return f'每天 {span}'
        names = ''.join(DAY_NAMES[d] for d in self.days)
        if self.days_from_config:
            # ★ 实际值**运行时**才知道 -> 标出来, 别显示错的星期
            names = f'{names}+配置' if names else '来自配置'
        if self.times_from_config:
            span = '时刻来自配置'
        return f'{names} {span}'


# --------------------------------------------------------------------------- 周期 -> 窗口
def window_for_period(period, start: time = None, end: time = None):
    """由**周期**推导默认开放时段（用户新澄清的设计）。

    ## 用户原话

    > "window 的设计应当再展开说下, 每天的任务其实也有 window,
    >  只不过是每天的 0 点到 24 点。但是选择周期选择每天, 每周则是
    >  每周一 0 点到周日 24 点, 每月以此类推。而逢魔则是每天的 17 点-23 点。
    >  等等。**所有的定时都有着 window 属性**。"

    ## 推导规则

    | `period` | window |
    |---|---|
    | `DAILY` | 每天 **00:00-24:00**（全周）|
    | `WEEKLY` | **周一 00:00 - 周日 24:00**（全周 —— 一周就是一个周期）|
    | `MONTHLY` | 当月 **1 日 00:00 - 月末 24:00**（`days_of_month=1..31`）|
    | `NONE` | 没有周期 -> **没有可推导的窗口**, 返回 `None`（调用方回退）|

    ★ 注意 `WEEKLY` 的窗口**也是全周** —— 因为"一周"这个周期本身就覆盖 7 天。
      它表达的是"这个任务的**节奏**是每周", 而不是"只允许某几天跑"。
      真正限制到具体某几天/某几个小时的, 是**活动窗口**
      （如 `AbyssShadows` 周五六日 19:00-20:00）—— 那由各任务
      `meta.py` **显式声明**, 会覆盖这里的默认值。

    :param period: `module.config.resource.Period`（或同值的 str）
    :param start/end: 可选, 进一步收窄时刻（如逢魔 17:00-23:00）
    """
    val = getattr(period, 'value', period)
    val = str(val).lower() if val is not None else 'none'

    if val == 'daily':
        return AvailabilityWindow(
            enabled=True,
            start=start if start is not None else time(0, 0),
            end=end if end is not None else time(23, 59),
            days=ALL_DAYS)
    if val == 'weekly':
        return AvailabilityWindow(
            enabled=True,
            start=start if start is not None else time(0, 0),
            end=end if end is not None else time(23, 59),
            days=ALL_DAYS)
    if val == 'monthly':
        return AvailabilityWindow(
            enabled=True,
            start=start if start is not None else time(0, 0),
            end=end if end is not None else time(23, 59),
            days=ALL_DAYS,
            days_of_month=tuple(range(1, 32)))
    # NONE: 没有周期可推导
    return None


# --------------------------------------------------------------------------- 自学习
@dataclass
class ObservedWindow:
    """
    从**实际运行记录**反推的开放时段(自学习)。

    为什么需要: 游戏时段可能改版, 或初始配置不准。与其依赖一次填对,
    不如让软件观察"每次成功运行发生在什么时刻", 汇总出真实时段, 再与
    用户配置比对 —— 不一致时提示用户。

    只记录**成功**样本: 失败可能因为体力不足/网络问题等无关原因, 会污染推断。

    字段:
        samples: 成功时刻的"当日分钟数"列表(0-1439)
        days: 观测到成功的星期集合
        count: 样本总数
    """

    samples: list = None
    days: set = None
    count: int = 0

    def __post_init__(self):
        if self.samples is None:
            self.samples = []
        if self.days is None:
            self.days = set()

    def observe(self, at: datetime) -> None:
        """记录一次成功运行的时刻。"""
        self.samples.append(_minutes(at))
        self.days.add(at.weekday())
        self.count += 1
        # 控制内存: 只保留最近 500 个样本
        if len(self.samples) > 500:
            del self.samples[:-500]

    @property
    def has_enough_data(self) -> bool:
        """样本太少时不下结论(避免误报)。"""
        return self.count >= 5

    def infer(self, pad_minutes: int = 5) -> AvailabilityWindow or None:
        """
        推断开放时段。

        取样本的 1%/99% 分位并向外扩 `pad_minutes`, 以抵抗偶发异常值。
        样本不足 5 个时返回 None。
        """
        if not self.has_enough_data:
            return None
        s = sorted(self.samples)
        n = len(s)
        lo = s[max(0, int(n * 0.01) - 1)]
        hi = s[min(n - 1, int(n * 0.99))]
        lo = max(0, lo - pad_minutes)
        hi = min(24 * 60 - 1, hi + pad_minutes)
        return AvailabilityWindow(
            enabled=True,
            start=time(lo // 60, lo % 60),
            end=time(hi // 60, hi % 60),
            days=tuple(sorted(self.days)) or ALL_DAYS,
        )

    def suggest(self, configured: AvailabilityWindow) -> str or None:
        """
        与用户配置比对, 返回改进建议; 一致或数据不足时返回 None。

        这是"自学习"对用户真正有用的产物 —— 不是自动改配置, 而是**提示**。
        """
        inferred = self.infer()
        if inferred is None:
            return None
        if not configured.enabled:
            return (f'实测该任务只在 {inferred.describe()} 运行过'
                    f'(共 {self.count} 次); 可考虑启用时段限制以避免白跑')
        # 推断窗显著超出配置窗 -> 配置可能偏窄
        if (inferred.duration_minutes > configured.duration_minutes + 60
                or set(inferred.days) - set(configured.days)):
            return (f'实测时段 {inferred.describe()} 与配置 '
                    f'{configured.describe()} 不符(共 {self.count} 次样本)')
        return None

    # ------------------------------------------------------------ 持久化
    def to_dict(self) -> dict:
        return {'samples': list(self.samples),
                'days': sorted(self.days),
                'count': self.count}

    @classmethod
    def from_dict(cls, data: dict) -> 'ObservedWindow':
        if not isinstance(data, dict):
            return cls()
        return cls(samples=list(data.get('samples') or []),
                   days=set(data.get('days') or []),
                   count=int(data.get('count') or 0))


# ★ (b) 动态 days: 把"星期"的常见表示映射到 0-6（周一=0）。
#
# 为什么放这里: `GuildBanquet` 用的是 `Weekday` 枚举（值是**中文**"星期三"）,
# 而 `AvailabilityWindow.days` 用 0-6。集中一张表, 免得每处各写一份
# （本项目已因"知识存在两处"栽过多次 —— 台账 §10.8 单一数据源）。
WEEKDAY_ALIASES = {
    # 中文（`tasks/GuildBanquet/config.py` 的 `Weekday`）
    '星期一': 0, '星期二': 1, '星期三': 2, '星期四': 3,
    '星期五': 4, '星期六': 5, '星期日': 6, '星期天': 6,
    # 中文简称
    '周一': 0, '周二': 1, '周三': 2, '周四': 3,
    '周五': 4, '周六': 5, '周日': 6, '周天': 6,
    # 英文（大小写不敏感）
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6,
    # 纯数字字符串
    '0': 0, '1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
}


def parse_weekday(value) -> int:
    """把"星期"的任意常见表示解析成 0-6（周一=0）。

    支持: 中文全称/简称 / 英文名（大小写不敏感）/ 0-6 数字 / `Weekday` 枚举。
    解析不出来抛 `ValueError`（**不猜**）。
    """
    # 枚举 -> 取 .value
    raw = getattr(value, 'value', value)
    if isinstance(raw, bool):
        raise ValueError(f'非法星期: {value!r}')
    if isinstance(raw, int):
        if 0 <= raw <= 6:
            return raw
        raise ValueError(f'非法星期: {value!r}(应为 0-6, 周一=0)')
    key = str(raw).strip()
    if key.lower() in WEEKDAY_ALIASES:
        return WEEKDAY_ALIASES[key.lower()]
    if key in WEEKDAY_ALIASES:
        return WEEKDAY_ALIASES[key]
    raise ValueError(f'无法识别的星期: {value!r}')


def parse_time(value):
    """把一个"时刻"的常见表示解析成 `datetime.time`。

    支持: `datetime.time` / `'19:00'` / `'19:00:00'` / `'19：00'`（全角冒号）。
    解析不出来抛 `ValueError`（**不猜**）。
    """
    if isinstance(value, time_cls):
        return value
    key = str(getattr(value, 'value', value)).strip().replace('：', ':')
    for fmt in ('%H:%M:%S', '%H:%M'):
        try:
            return datetime_cls.strptime(key, fmt).time()
        except ValueError:
            continue
    raise ValueError(f'无法识别的时刻: {value!r}')
