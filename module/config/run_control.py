# -*- coding: utf-8 -*-
"""运行控制 —— 暂停 / 继续 / 休息 / 延后。

## 为什么需要

此前**没有暂停机制**。唯一的"停止"是硬杀进程
(`script_process.py`: `terminate()` -> 0.7 秒后 `kill()`), 会卡在半途
(战斗中 / 组队房间中), 不安全。`script.py` 里 `stop_event` 的检查**被注释掉了**,
且该变量从未赋值 —— 原作者想做但没做完。

## 三个控件(用户确认的语义)

| 控件 | 语义 |
|---|---|
| **⏸ 暂停调度** | **跑完当前这场战斗(到安全点)**后不再开新任务 |
| **⏭ 本轮跑完再停** | 本任务本轮跑完(把目标次数打满)再停 |
| **▶ 继续调度** | 恢复 |

**不提供「立即停」** —— 会卡在半途, 不安全。

## 安全点在哪

`run_general_battle()` 返回的那一刻 = 战斗 + 结算 + 领奖全部完成 = **安全点**。
所以只在那一处检查, **所有走 `GeneralBattle` 的任务自动受益**
(与此前 `commit_count()` 用的是同一手法: 放在共享层, 一次改动全体受益)。

## 休息 vs 延后(两个概念, 不是"作用范围"参数)

| 条目 | 语义 | 影响 |
|---|---|---|
| **休息** | 全局暂停 N 分钟 —— 真休息 | 定时任务也停 |
| **延后** | 只推迟**列表**推进 N 分钟 | 定时任务照常 |

★ 设计过程中曾错误地引入"休息作用范围(SELF/WHOLE_LIST)"参数 ——
那是把"条目"和"动作"两个概念混在一起。改为两个条目类型后语义自明。

## 状态存放

复用 `module/config/task_state.py` 的状态文件(同一个文件锁, 避免两套写入竞争),
存放在顶层 `run_control` 键下。
"""
import json
from datetime import datetime, timedelta

from module.logger import logger


CONTROL_KEY = 'run_control'

# 暂停模式
PAUSE_NONE = ''            # 未暂停
PAUSE_BATTLE = 'battle'    # ⏸ 跑完当前这场战斗后停
PAUSE_ROUND = 'round'      # ⏭ 本轮(任务)跑完再停

PAUSE_MODES = (PAUSE_NONE, PAUSE_BATTLE, PAUSE_ROUND)

MODE_LABEL = {
    PAUSE_NONE: '运行中',
    PAUSE_BATTLE: '暂停(跑完本场战斗)',
    PAUSE_ROUND: '暂停(跑完本轮)',
}


# --------------------------------------------------------------------------- 读写原语
def _load() -> dict:
    """读取 run_control 段。出错时返回空 dict(不因状态问题卡住脚本)。"""
    from module.config import task_state
    try:
        with task_state._lock():
            data = task_state._read_all()
            rc = data.get(CONTROL_KEY)
            return dict(rc) if isinstance(rc, dict) else {}
    except Exception as exc:
        logger.warning(f'[RunControl] 读取失败({type(exc).__name__}: {exc}), '
                       f'按"运行中"处理')
        return {}


def _save(rc: dict) -> None:
    from module.config import task_state
    try:
        with task_state._lock():
            data = task_state._read_all()
            if rc:
                data[CONTROL_KEY] = rc
            else:
                data.pop(CONTROL_KEY, None)
            task_state._write_all(data)
    except Exception as exc:
        logger.error(f'[RunControl] 写入失败({type(exc).__name__}: {exc})')


def _parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- 暂停
def request_pause(mode: str = PAUSE_BATTLE, reason: str = '') -> dict:
    """
    请求暂停。**立即生效**(调度器下次判就绪时就会看到), 但脚本会在**安全点**才停。

    :param mode: `PAUSE_BATTLE`(默认, 跑完当前这场战斗) 或 `PAUSE_ROUND`(跑完本轮)
    """
    if mode not in PAUSE_MODES or mode == PAUSE_NONE:
        raise ValueError(f'非法暂停模式: {mode!r}; 应为 {PAUSE_MODES[1:]}')
    rc = _load()
    rc['pause_mode'] = mode
    rc['pause_at'] = datetime.now().replace(microsecond=0).isoformat()
    if reason:
        rc['pause_reason'] = reason
    _save(rc)
    logger.info(f'[RunControl] 收到暂停请求: {MODE_LABEL.get(mode, mode)}')
    return state()


def resume() -> dict:
    """恢复调度(清除暂停标记)。"""
    rc = _load()
    for k in ('pause_mode', 'pause_at', 'pause_reason'):
        rc.pop(k, None)
    _save(rc)
    logger.info('[RunControl] 已恢复调度')
    return state()


def pause_mode() -> str:
    rc = _load()
    m = rc.get('pause_mode') or PAUSE_NONE
    return m if m in PAUSE_MODES else PAUSE_NONE


def is_paused() -> bool:
    """调度器是否应停止派发新任务。"""
    return pause_mode() != PAUSE_NONE


# --------------------------------------------------------------------------- 休息
def rest(minutes: int = 0, until: datetime = None) -> dict:
    """
    **休息**: 全局暂停到指定时刻(定时任务也不跑)。`minutes=0` 表示取消。
    """
    rc = _load()
    if minutes and minutes > 0:
        t = (datetime.now() + timedelta(minutes=int(minutes))).replace(microsecond=0)
        rc['rest_until'] = t.isoformat()
        logger.info(f'[RunControl] 休息至 {t:%Y-%m-%d %H:%M}')
    elif until is not None:
        rc['rest_until'] = until.replace(microsecond=0).isoformat()
        logger.info(f'[RunControl] 休息至 {until:%Y-%m-%d %H:%M}')
    else:
        rc.pop('rest_until', None)
        logger.info('[RunControl] 已取消休息')
    _save(rc)
    return state()


def rest_until() -> datetime or None:
    """休息结束时刻; 已过期或未休息返回 None。"""
    t = _parse_dt(_load().get('rest_until'))
    if t is None:
        return None
    return t if t > datetime.now() else None


def in_rest() -> bool:
    return rest_until() is not None


# --------------------------------------------------------------------------- 延后
def delay(minutes: int = 0, until: datetime = None) -> dict:
    """
    **延后**: 只推迟**列表**推进(定时任务照常)。`minutes=0` 表示取消。
    """
    rc = _load()
    if minutes and minutes > 0:
        t = (datetime.now() + timedelta(minutes=int(minutes))).replace(microsecond=0)
        rc['list_resume_at'] = t.isoformat()
        logger.info(f'[RunControl] 列表延后至 {t:%Y-%m-%d %H:%M}')
    elif until is not None:
        rc['list_resume_at'] = until.replace(microsecond=0).isoformat()
        logger.info(f'[RunControl] 列表延后至 {until:%Y-%m-%d %H:%M}')
    else:
        rc.pop('list_resume_at', None)
        logger.info('[RunControl] 已取消延后')
    _save(rc)
    return state()


def list_resume_at() -> datetime or None:
    """列表恢复推进的时刻; 无延后返回 None。"""
    t = _parse_dt(_load().get('list_resume_at'))
    if t is None:
        return None
    return t if t > datetime.now() else None


def list_delayed() -> bool:
    return list_resume_at() is not None


# --------------------------------------------------------------------------- 汇总
def state() -> dict:
    """
    当前运行控制状态(供界面显示)。

    返回:
        {paused, pause_mode, pause_mode_label, pause_at, pause_reason,
         rest_until, rest_remaining, delayed, list_resume_at, list_remaining,
         can_run}
    """
    rc = _load()
    now = datetime.now()
    m = rc.get('pause_mode') or PAUSE_NONE
    if m not in PAUSE_MODES:
        m = PAUSE_NONE

    ru = _parse_dt(rc.get('rest_until'))
    ru = ru if (ru and ru > now) else None
    lu = _parse_dt(rc.get('list_resume_at'))
    lu = lu if (lu and lu > now) else None

    def _remain(t):
        if t is None:
            return 0
        return max(0, int((t - now).total_seconds()))

    return {
        'paused': m != PAUSE_NONE,
        'pause_mode': m,
        'pause_mode_label': MODE_LABEL.get(m, m),
        'pause_at': rc.get('pause_at'),
        'pause_reason': rc.get('pause_reason') or '',
        'rest_until': ru.strftime('%Y-%m-%d %H:%M:%S') if ru else None,
        'rest_remaining': _remain(ru),
        'delayed': lu is not None,
        'list_resume_at': lu.strftime('%Y-%m-%d %H:%M:%S') if lu else None,
        'list_remaining': _remain(lu),
        # 现在能不能派发新任务(暂停或休息都不行)
        'can_run': (m == PAUSE_NONE) and (ru is None),
    }


def wait_seconds() -> int:
    """
    调度器该等多久再检查一次(秒)。

    暂停时给一个较短的轮询间隔 —— 用户可能随时点"继续",
    不该等到下一个任务周期才响应。
    """
    if is_paused():
        return 15
    if in_rest():
        ru = rest_until()
        return max(5, min(300, int((ru - datetime.now()).total_seconds())))
    return 0


def clear_all(config_name: str = None) -> None:
    """清除所有运行控制状态(测试与重置用)。"""
    _save({})
