# -*- coding: utf-8 -*-
"""调度核心 —— 纯函数, 无副作用, 不依赖设备/文件/时间以外的任何东西。

## 这个模块解决什么

旧调度器把"次数"当作**冷却时间**实现:

    # 旧: task_delay()
    interval = scheduler.success_interval
    next_run = start + interval

于是"打 50 次"要拆成两个字段表达(`success_interval=1d` + `limit_count=50`),
而"增量补充"(金币妖怪 0/12 点各补 1)只能靠另一套 `charge_*` 代码旁路实现。

本模块把这件事归约为**一个纯函数**:

    next_available(resource, state, now) -> datetime

给定"资源规则 + 使用状态 + 当前时间", 返回**下一次可运行的最早时刻**。
无副作用、可单测、可解释 —— 取代旧代码里所有零散的排期逻辑。

## 关键性质: 单调性

`credits(T)` —— "池子在 T 时刻的可用次数" —— 对 T **单调不减**:
  * 补充事件只增加 credits
  * 消耗是离散事件, 已计入 `state.credits`
因此 `next_available()` 可以用**二分查找**求最小可行时刻, 结果唯一、无歧义。

## 与旧机制的对应

    RunState.credits        <- 旧的"还剩几次"(原本散在 task_state 里)
    RunState.refill_anchor  <- 旧的 next_run(但只表示"上次补充结算点")
    next_available()        <- 旧的 next_run 计算(原本散在 task_delay 里)
"""
import bisect
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from module.config.resource import Period, Resource

# 候选时刻的搜索上界。取 32 天: 长于任何已知任务的补充周期(最长 7 天),
# 保证一定能在窗口内找到可行时刻。
_MAX_HORIZON = timedelta(days=32)

# 活动期关闭时的重查间隔。核心不知道活动何时开始(那是探针的事),
# 故返回一个"稍后再问"的时刻, 由调用方在彼时重新判定。
_WINDOW_RECHECK = timedelta(minutes=1)


@dataclass(frozen=True)
class RunState:
    """
    某个任务的运行态。

    只有三个字段 —— 这是刻意收窄的: 旧模型把"资源"与"调度"混在一个
    `next_run` 里, 导致语义失真; 这里把"还剩几次"独立出来。

    credits:       当前可用次数(已扣除历史消耗)
    refill_anchor: 上次补充结算的时刻。对 interval 形态是"上次运行时刻";
                   对 slots 形态是"上次结算时刻"。为 None 表示从未记录。
    retry_after:   失败重试退避截止时刻。与资源无关, 是**独立概念**
                   (旧名 `failure_interval` 会误导, 故改名)。
    """

    credits: int = 0
    refill_anchor: datetime = None
    retry_after: datetime = None

    def with_credits(self, credits: int) -> 'RunState':
        return replace(self, credits=max(0, credits))

    def consumed(self, resource: Resource, *, at: datetime) -> 'RunState':
        """
        消耗一次后得到的新状态(纯函数, 不修改自身)。

        `refill_anchor` 对 interval 形态要更新为本次运行时刻 ——
        因为"距上次运行满 N 时间"是从**上次运行**算起的。
        """
        anchor = at if resource.refill == 'interval' else self.refill_anchor
        return replace(self,
                       credits=max(0, self.credits - resource.consume),
                       refill_anchor=anchor)

    def refilled_to(self, credits: int, *, at: datetime) -> 'RunState':
        """结算补充后得到的新状态。"""
        return replace(self, credits=credits, refill_anchor=at)

    def mark_failure(self, resource: Resource, *, at: datetime,
                     retry: timedelta) -> 'RunState':
        """标记一次失败, 设置重试退避(不影响 credits —— 失败不消耗资源)。"""
        return replace(self, retry_after=at + retry)


# --------------------------------------------------------------------------- 内部: 池子计算
def _anchor(resource: Resource, state: RunState, now: datetime) -> datetime:
    """
    计算"池子开始演变"的锚点。

    若 state 有 refill_anchor 就用它, 否则回退到当前周期的起点
    (意味着"本周期一开始池子是满的")。
    """
    if state.refill_anchor is not None:
        return state.refill_anchor
    if resource.is_periodic:
        return resource.period_start(now)
    return now


def _credits_at(resource: Resource, state: RunState, at: datetime) -> int:
    """
    池子在 `at` 时刻的可用次数。

    统一处理两件事(**按时间顺序**):
      1. **周期边界** -> 池子回满 `capacity`
         (限额型资源如限时活动就靠这个: 每日回满 1 次额度)
      2. **补充事件** -> 池子 +capacity(封顶)
         * `interval`: 距锚点每满一个间隔补一次(相对时间)
         * `slots`   : 在每个固定时刻补一次(绝对时间)

    `at` 必须 >= 锚点。当 `at` 早于 `state.refill_anchor` 时由调用方处理。
    """
    cursor = _anchor(resource, state, at)
    credits = state.credits

    # ---- 1. 先追赶周期边界 ----
    if resource.is_periodic:
        while resource.next_period_start(cursor) <= at:
            cursor = resource.next_period_start(cursor)
            credits = resource.capacity

    # ---- 2. 再追赶补充事件 ----
    #
    # 注意锚点的语义: `refill_anchor` 是一个**已结算点** —— 该时刻的补充
    # 已经计入 `state.credits`。因此只统计**严格晚于**锚点的补充事件。
    # (踩过: slots_between 用 [start, end) 会把锚点那个 slot 重复计算,
    #  导致 credits 多加一格。)
    if resource.refill == 'interval':
        step = resource.interval_timedelta
        if step.total_seconds() > 0:
            elapsed = (at - cursor).total_seconds()
            if elapsed > 0:
                n = int(elapsed // step.total_seconds())
                if n > 0:
                    credits = min(resource.capacity,
                                  credits + n * resource.capacity)
    elif resource.refill == 'slots':
        # include_end=True: 若 `at` 恰好落在某个 slot 上, 那次补充**已发生**,
        # 必须计入 —— 否则额度要等到 slot 之后才生效, next_available 会跳到下一个
        # slot(踩过: 12:00 整不可行, 12:00:01 才行, 结果 next_available 返回次日)。
        n = resource.slots_between(cursor, at, include_end=True)
        if n > 0:
            credits = min(resource.capacity, credits + n * resource.capacity)

    return min(credits, resource.capacity)


def credits_at(resource: Resource, state: RunState, now: datetime) -> int:
    """
    公开接口: 当前可用次数。

    若 `now` 早于 `state.refill_anchor`(时钟回拨等异常), 直接返回 state.credits,
    避免出现负数或倒退。
    """
    anchor = _anchor(resource, state, now)
    if now < anchor:
        return state.credits
    return _credits_at(resource, state, now)


# --------------------------------------------------------------------------- 核心: next_available
def _is_feasible(resource: Resource, state: RunState, at: datetime,
                 window_open: bool) -> bool:
    """
    在 `at` 时刻是否可运行。

    三道闸门, 全部通过才可行:
      1. **开放时段**(`resource.window`)—— 游戏机制决定的硬约束。
         不在时段内一律不跑(这正是旧代码缺失、只能靠频繁轮询绕过的那个概念)。
      2. **活动期**(`window_open` 参数)—— 限时活动是否开放, 由外部探针判定。
      3. **资源额度** + 失败退避。
    """
    if resource.has_window and not resource.window.contains(at):
        return False
    if resource.is_activity_gated and not window_open:
        return False
    if state.retry_after is not None and at < state.retry_after:
        return False
    return credits_at(resource, state, at) >= resource.consume


def _candidate_times(resource: Resource, state: RunState, now: datetime) -> list:
    """
    列出 `now` 之后所有"可能变得可行"的时刻。

    资源只在这些时刻发生变化, 因此**只需检查这些候选点**, 不必逐秒搜索。

    候选来源:
      * 周期边界(池子回满)
      * slots 固定时刻
      * interval 的整数倍刻度
      * 失败重试退避结束时刻
      * 兜底上界

    这比"二分查找时间轴"精确 —— 二分受秒级精度限制, 会在事件边界上差 1 秒
    (踩过: 12:00:00 判定不可行, 12:00:00.000001 可行, 结果返回 12:00:01)。
    """
    cands = [now]
    if state.retry_after is not None and state.retry_after > now:
        cands.append(state.retry_after)

    # 开放时段: 枚举未来的开放时刻。
    #
    # 必须用 `strict=True` —— 否则 `now` 已在窗口内时, next_opening 会反复
    # 返回同一个 now, 枚举退化成"只找到周期边界", 漏掉次日的开放点。
    # 踩过: 窗口内额度用完时, next_available 跳到 32 天上界。
    if resource.has_window:
        cur = now
        for _ in range(10):
            nxt = resource.window.next_opening(cur, strict=True)
            if nxt > now + _MAX_HORIZON:
                break
            cands.append(nxt)
            cur = nxt
        # 周期边界若恰好落在窗口外, 单独补上"边界之后的下一次开放"
        if resource.is_periodic:
            boundary = resource.next_period_start(now)
            while boundary <= now + _MAX_HORIZON:
                cands.append(boundary)
                cands.append(resource.window.next_opening(boundary, strict=True))
                boundary = boundary + timedelta(
                    days=7 if resource.period == Period.WEEKLY else 1)

    # interval: 从锚点起算的整数倍
    if resource.refill == 'interval':
        step = resource.interval_timedelta
        if step.total_seconds() > 0:
            cur = _anchor(resource, state, now)
            while cur <= now:
                cur += step
            while cur <= now + _MAX_HORIZON:
                cands.append(cur)
                cur += step
            if cur <= now + _MAX_HORIZON:
                cands.append(cur)

    # slots: 未来的每个固定时刻
    if resource.refill == 'slots':
        # 池子已被消耗时, 下一个 slot 就是最早的补充点;
        # 但额度可能不足 consume, 故多取几个
        cur = resource.next_slot(now - timedelta(microseconds=1))
        for _ in range(len(resource.slots) * 8):
            if cur > now + _MAX_HORIZON:
                break
            if cur > now:
                cands.append(cur)
            cur = resource.next_slot(cur)

    # 周期边界
    if resource.is_periodic:
        cur = resource.next_period_start(now)
        while cur <= now + _MAX_HORIZON:
            cands.append(cur)
            cur = cur + timedelta(days=7 if resource.period == Period.WEEKLY else 1)

    # 兜底
    cands.append(now + _MAX_HORIZON)

    return sorted({c for c in cands if c >= now})


def next_available(resource: Resource, state: RunState, now: datetime,
                   window_open: bool = True) -> datetime:
    """
    **下一次可运行的最早时刻**。

    这是整个调度器的核心纯函数: 给定资源规则 + 使用状态 + 当前时间,
    返回最早可行的时刻。若此刻就可运行, 返回 `now`。

    :param window_open: 活动期是否开放。仅对 `refill='window'` 有意义。
                        判定交给外部探针(见 `StateProvider`), 核心不关心怎么判的。
    """
    if _is_feasible(resource, state, now, window_open):
        return now

    # 开放时段未开: 核心**知道**下一次开放时刻(时段是显式建模的),
    # 因此可以直接给出答案, 而不是"稍后再问"。
    if resource.has_window and not resource.window.contains(now):
        opening = resource.window.next_opening(now)
        if _is_feasible(resource, state, opening, window_open):
            return opening

    # 活动期关闭: 核心不知道活动何时开始(那是探针的事, 属于外部信息),
    # 只能返回"稍后再问"的时刻。
    if resource.is_activity_gated and not window_open:
        return now + _WINDOW_RECHECK

    for cand in _candidate_times(resource, state, now):
        if _is_feasible(resource, state, cand, window_open):
            return cand

    # 理论上不可达(周期边界一定能让池子回满); 兜底返回上界
    return now + _MAX_HORIZON


# --------------------------------------------------------------------------- 便捷判定
def remaining(resource: Resource, state: RunState, now: datetime) -> int:
    """当前可用次数(界面显示 x/y 用)。"""
    return credits_at(resource, state, now)


def cannot_run_reason(resource: Resource, state: RunState, now: datetime,
                      window_open: bool = True) -> str or None:
    """
    为什么现在不能跑 —— 用于界面显示与排障。

    返回人类可读的短语; 可运行则返回 None。
    """
    if resource.has_window and not resource.window.contains(now):
        opening = resource.window.next_opening(now)
        return (f'不在开放时段（{resource.window.describe()}，'
                f'{opening:%m-%d %H:%M} 开放）')
    if resource.is_activity_gated and not window_open:
        return '不在活动期'
    if state.retry_after is not None and now < state.retry_after:
        return f'失败重试退避至 {state.retry_after:%H:%M}'
    if credits_at(resource, state, now) < resource.consume:
        nxt = next_available(resource, state, now, window_open)
        if resource.refill == 'slots':
            return f'等待补充（{nxt:%H:%M} 补充）'
        if resource.refill == 'interval':
            return f'等待冷却（{nxt:%H:%M} 后可做）'
        return f'本周期已用完（{nxt:%m-%d %H:%M} 重置）'
    return None
