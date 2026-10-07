# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
"""
跨账号组队协同（Availability Oracle 的最小可用实现）。

解决的问题
----------
组队任务（经验妖怪 / 金币妖怪 / 石距 这类需要两个账号一起打的玩法）如果两个
账号各自为政，很容易出现"一个账号有次数去开房、另一个已经没次数"的情况：
开房的一方白白等一轮邀请，两边都浪费一次刷新点。

思路
----
各账号的"剩余次数"本来就按配置名分桶存在同一个状态文件里
（见 module/config/task_state.py 的 _charges_of），因此协同**不需要另建一套
状态文件**，只要再加一个心跳就能回答两个问题：

    1. 对方在不在线？（心跳是否超时）
    2. 对方这个任务还剩几次？（读对方分桶里的次数）

组队任务开始前的判断：

    对方离线              -> START（没人可等，按自己能力做）
    对方还有次数          -> START（双方都能打，此刻一起做最合适）
    对方次数为 0          -> DEFER（等对方先恢复，否则我做完就变成"我有他没有"）
    读不到/异常           -> START（宁可按原行为运行，也不要卡住任务）

这条规则刻意保持简单：两个账号都按同一个固定刷新点（如 0 点/12 点）恢复次数，
因此"双方都有次数才一起做"足以让它们自然收敛，而不需要复杂的协商协议。

设计原则（沿用 period/次数 的约定）
------------------------------------
任何异常都必须退化为"START"，即照常运行原任务。宁可不同步，也不能因为
协同逻辑把原本能跑的任务搞挂。
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from module.logger import logger
from module.config import task_state

# 决策结果
START = 'START'
DEFER = 'DEFER'


@dataclass
class TeamDecision:
    """协同决策结果。"""
    action: str = START                  # START / DEFER
    reason: str = ''                     # 人类可读的原因(用于日志)
    peer: str = ''                       # 参与协同的对方账号名
    wait_seconds: int = 0                # 建议等待秒数(action=DEFER 时有意义)
    details: dict = field(default_factory=dict)

    @property
    def should_start(self) -> bool:
        return self.action == START

    def __str__(self) -> str:
        return (f'{self.action}(peer={self.peer or "-"}, wait={self.wait_seconds}s, '
                f'{self.reason})')


def _candidate_peers(my_config: str, peer: str = None) -> list:
    """确定要与谁协同。显式指定 peer 时只用它, 否则取"除我之外的所有配置"。"""
    if peer:
        return [peer] if peer != my_config else []
    return [c for c in task_state.discover_configs() if c != my_config]


def _mark_wait_start(my_config: str, task: str, now: datetime) -> None:
    """记录"我开始等待这个任务了"; 若已在等待则不覆盖(用于测量累计等待时长)。"""
    try:
        from module.config import task_state as ts
        rec = ts.read_heartbeat(my_config) or {}
        waiting = dict(rec.get('waiting') or {})
        key = str(task).lower()
        if key not in waiting:
            waiting[key] = now.replace(microsecond=0).isoformat()
            ts.write_heartbeat(my_config, {'waiting': waiting})
    except Exception as exc:
        logger.warning(f'[TeamCoord] 记录等待起点失败: {exc}')


def _clear_wait(my_config: str, task: str) -> None:
    """清除"等待中"标记(开始执行或成功执行后调用)。"""
    try:
        from module.config import task_state as ts
        rec = ts.read_heartbeat(my_config)
        if not rec or not rec.get('waiting'):
            return
        waiting = dict(rec.get('waiting') or {})
        if waiting.pop(str(task).lower(), None) is not None:
            ts.write_heartbeat(my_config, {'waiting': waiting})
    except Exception as exc:
        logger.warning(f'[TeamCoord] 清除等待标记失败: {exc}')


def _waited_seconds(my_config: str, task: str, now: datetime) -> int:
    """已经为了这个任务等待了多少秒(没有记录则 0)。"""
    try:
        from module.config import task_state as ts
        rec = ts.read_heartbeat(my_config) or {}
        since = (rec.get('waiting') or {}).get(str(task).lower())
        if not since:
            return 0
        return max(0, int((now - datetime.fromisoformat(since)).total_seconds()))
    except Exception:
        return 0


# 等待超过"一个刷新周期"仍未等到 -> 不再等, 直接做。
# 这是防死锁的关键: 双方若互相认为对方没次数, 最多互相等一个周期就会各自开始。
MAX_WAIT_PERIODS = 1.0


def decide(task: str,
           my_config: str,
           peer: str = None,
           max_charges: int = 2,
           slots=None,
           now: datetime = None) -> TeamDecision:
    """
    组队任务开始前的协同决策。

    :param task: 任务名(下划线或大驼峰均可)
    :param my_config: 本账号的配置名
    :param peer: 指定对方账号名; 留空则自动取"除我之外的所有配置"
    :param max_charges: 次数的储存上限
    :param slots: 刷新时刻; 留空则由状态记录推断
    :param now: 便于测试注入
    :return: TeamDecision
    """
    now = now or datetime.now()
    peers = _candidate_peers(my_config, peer)

    if not peers:
        return TeamDecision(START, '没有其他账号可协同(单账号运行)', peer='')

    t = str(task).lower()
    for p in peers:
        if not task_state.is_online(p, now=now):
            # 对方不在线: 不能等, 按自己能力做
            _clear_wait(my_config, t)
            return TeamDecision(START, f'对方 {p} 不在线(心跳超时)', peer=p)

    # 对方都在线: 谁的次数为 0 就等谁
    deferred_peer = None
    for p in peers:
        try:
            left = task_state.peer_charges(p, t, max_charges=max_charges,
                                           slots=slots, now=now)
        except Exception as exc:
            logger.warning(f'[TeamCoord] 读取 {p} 的次数失败'
                           f'({type(exc).__name__}: {exc}), 按可协同处理')
            continue
        if left <= 0:
            deferred_peer = p
            break
        logger.info(f'[TeamCoord] 对方 {p} 的 {task} 还剩 {left} 次, 可以一起做')

    if deferred_peer is None:
        _clear_wait(my_config, t)
        return TeamDecision(START, '双方都有次数, 可以一起组队', peer=peers[0])

    # 需要等待: 先看是否已经等得太久(防死锁)
    waited = _waited_seconds(my_config, t, now)
    period = _period_seconds(slots)
    if waited >= period * MAX_WAIT_PERIODS:
        _clear_wait(my_config, t)
        return TeamDecision(
            START,
            f'已等待 {waited}s(超过一个刷新周期 {int(period)}s), 不再等对方, 直接执行',
            peer=deferred_peer, details={'waited': waited})

    _mark_wait_start(my_config, t, now)
    wait = _time_to_next_slot(slots, now)
    return TeamDecision(
        DEFER,
        f'对方 {deferred_peer} 的 {task} 次数为 0, 等它恢复后再一起做',
        peer=deferred_peer, wait_seconds=wait,
        details={'waited': waited})


def _period_seconds(slots) -> float:
    """一个刷新周期是多少秒(每天 2 个刷新点 -> 12 小时)。"""
    try:
        n = len(task_state.parse_slots(slots) if slots else (0, 12))
        return 24 * 3600.0 / max(1, n)
    except Exception:
        return 12 * 3600.0


def _time_to_next_slot(slots, now: datetime) -> int:
    """
    距离下一个刷新点还有多少秒(用于把任务排到刷新之后)。

    这里直接用 task_state 的槽位解析, 避免各处重复实现时间计算。
    """
    try:
        from datetime import time as _time
        slot_list = task_state.parse_slots(slots) if slots else (0, 12)
        for day_offset in (0, 1, 2):
            base = (now + timedelta(days=day_offset)).date()
            for h in slot_list:
                t = datetime.combine(base, _time(hour=h))
                if t > now:
                    return int((t - now).total_seconds())
    except Exception as exc:
        logger.warning(f'[TeamCoord] 计算下次刷新时间失败: {exc}')
    return 12 * 3600
