# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
"""
任务完成记忆。

解决的问题
----------
原先调度器只有 next_run + success_interval 两个概念, 它回答的是"下次什么时候跑",
却不记录"本周期到底做成没有"。于是用户想表达"每天只做一次"时, 只能靠手工设
success_interval = 1 天 来近似; 一旦任务中途失败或提前结束, 语义就失真了
(例如"刷满 100 次"只刷了 10 次, 照样把下次运行推到明天)。

本模块记录每个任务在其周期内是否已成功完成, 使调度器可以直接回答:
    "本(游戏)日/周已经做过了吗?"
周期边界按**游戏重置时间**计算(阴阳师为每日 00:00, 见 Scheduler.reset_at),
而不是机械地取自然日 —— 该时刻可通过 reset_at 调整, 以适配不同区服。

设计取舍
--------
- 状态存文件而不是内存: 需要跨进程(每个配置一个子进程)与跨重启存活。
  仓库已有同类做法: module/config/instance_guard.py 用 log/.queue_state.json。
- 路径可配: 若日后把多个实例拆成不同 OAS 目录, 让它们指向同一目录即可共享;
  未配置时各自独立, 行为退化为"不做周期判断", 不会出错。
- 任何异常都只告警并退化为"不判断周期", 绝不因为记忆功能让原本能跑的任务跑不了。
"""
import json
import os
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path

from filelock import FileLock

from module.logger import logger

# 状态文件路径(可用环境变量覆盖, 便于多实例共享)
_STATE_FILE_ENV = 'OAS_TASK_STATE_FILE'
_DEFAULT_STATE_FILE = Path.cwd() / 'log' / '.task_state.json'

# 默认周期边界: 与 tasks/Component/config_scheduler.py 的 Scheduler.reset_at 一致,
# 阴阳师以每日凌晨 0 点为界。
DEFAULT_RESET_AT = dt_time(hour=0, minute=0, second=0)

# 兼容旧的直接调用方式
STATE_FILE = Path(os.environ.get(_STATE_FILE_ENV) or _DEFAULT_STATE_FILE)


def _state_file() -> Path:
    """每次读取时重新解析, 便于测试与运行时改环境变量。"""
    return Path(os.environ.get(_STATE_FILE_ENV) or _DEFAULT_STATE_FILE)


def _lock() -> FileLock:
    return FileLock(str(_state_file()) + '.lock', timeout=10)


def _coerce_reset_at(reset_at) -> dt_time:
    """把 reset_at 规整为 datetime.time; 非法值退回默认(0 点)。"""
    if isinstance(reset_at, dt_time):
        return reset_at
    if isinstance(reset_at, str):
        try:
            return dt_time.fromisoformat(reset_at)
        except ValueError:
            return DEFAULT_RESET_AT
    return DEFAULT_RESET_AT


# ---------------------------------------------------------------------------
# 周期计算
# ---------------------------------------------------------------------------
def period_key(period: str, reset_at: dt_time = DEFAULT_RESET_AT,
               now: datetime = None) -> str:
    """
    计算当前所处的周期标识。周期边界按 reset_at 偏移, 而不是机械地取自然日。

    例(默认 reset_at=00:00, 即阴阳师的每日重置点):
        10-07 23:00 -> '2026-10-07'
        10-08 00:30 -> '2026-10-08'

    若某区服把重置点设在别处(例如 05:00), 则:
        10-07 23:00 -> '2026-10-07'
        10-08 03:00 -> '2026-10-07'   (未过 5 点, 仍属前一游戏日)
        10-08 05:01 -> '2026-10-08'

    :param period: 'daily' / 'weekly'(其他值返回空串, 表示不做周期判断)
    :param reset_at: 游戏重置时间
    :param now: 便于测试注入
    :return: 周期标识字符串; 空串表示该 period 不参与周期控制
    """
    if not period or str(period).lower() in ('none', ''):
        return ''
    period = str(period).lower()
    now = now or datetime.now()
    reset_at = _coerce_reset_at(reset_at)

    # 减去 reset_at 的偏移量, 使"游戏日"与自然日对齐
    shifted = now - timedelta(hours=reset_at.hour,
                              minutes=reset_at.minute,
                              seconds=reset_at.second)
    if period == 'daily':
        return shifted.date().isoformat()
    if period == 'weekly':
        # 周一为一周之始
        monday = shifted.date() - timedelta(days=shifted.weekday())
        return f'W{monday.isoformat()}'
    return ''


def period_start(period: str, reset_at: dt_time = DEFAULT_RESET_AT,
                 now: datetime = None) -> datetime:
    """
    返回当前周期的起始时刻, 以及下个周期起点(实现为返回**下个**周期起点)。

    用于把"已完成"任务的 next_run 推到下个周期, 避免每轮重复判断。

    以 reset_at=00:00 为例: 若现在 10-08 03:00, 当前周期起点是 10-08 00:00,
    下一个周期起点则是 10-09 00:00。
    """
    if not period or str(period).lower() in ('none', ''):
        return now or datetime.now()
    period = str(period).lower()
    now = now or datetime.now()
    reset_at = _coerce_reset_at(reset_at)

    shifted = now - timedelta(hours=reset_at.hour,
                              minutes=reset_at.minute,
                              seconds=reset_at.second)
    if period == 'daily':
        anchor = shifted.date()
        step = timedelta(days=1)
    elif period == 'weekly':
        anchor = shifted.date() - timedelta(days=shifted.weekday())
        step = timedelta(days=7)
    else:
        return now
    cur_start = datetime.combine(anchor, reset_at)
    return cur_start + step


# ---------------------------------------------------------------------------
# 状态读写
# ---------------------------------------------------------------------------
def _read_all() -> dict:
    path = _state_file()
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        logger.warning('[TaskState] 状态文件损坏, 已重置')
        return {}


def _write_all(data: dict) -> None:
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _state_key(task: str, entry_id: str = None) -> str:
    """完成记忆的**存储键**。

    ## 为什么从 `task` 改成 `entry_id`（用户选项 2 · 显式）

    队列里同一任务可以出现**多次**（用户用重复条目表达"重复跑整个任务"）:

        a 50次, a 50次

    原来按 `task` 记 -> 第一条跑完就把 `a` 标成"本周期已完成"
    -> **第二条也被跳过** -> 只跑了 1 次（用户要 2 次）。

    按 `entry_id` 记就分得开了。

    ## 兜底（向后兼容）

    `entry_id` 为空（旧数据 / 没走进队列的任务）-> 退回 `task`。
    这样**旧状态文件仍能读到**, 不会因为改造让所有任务"重新跑一遍"。
    """
    eid = (entry_id or '').strip()
    return str(eid if eid else task).lower()


def record_success(config_name: str, task: str,
                   period: str = 'none',
                   reset_at: dt_time = DEFAULT_RESET_AT,
                   entry_id: str = None) -> None:
    """
    记录某任务在"当前周期"已成功完成。

    :param config_name: 配置名(如 '伴生树'), 多账号互不干扰
    :param task: 任务名(下划线形式或大驼峰都可, 内部统一小写)
    :param period: 周期类型; 为 none 时仅记录时间戳, 不参与周期判断
    :param reset_at: 游戏重置时间
    """
    key = _state_key(task, entry_id)
    pkey = period_key(period, reset_at)
    try:
        with _lock():
            data = _read_all()
            bucket = data.setdefault(config_name, {})
            item = bucket.setdefault(key, {})
            item['last_success'] = datetime.now().replace(microsecond=0).isoformat()
            item['period'] = str(period).lower() if period else 'none'
            if pkey:
                item['period_key'] = pkey
            _write_all(data)
        logger.info(f'[TaskState] 记录完成: {config_name}.{task} '
                    f'(period={period}, key={pkey or "-"})')
    except Exception as exc:  # 记忆功能失败不应影响任务本身
        logger.warning(f'[TaskState] 记录完成失败({type(exc).__name__}: {exc}), 忽略')


def is_completed_in_period(config_name: str, task: str,
                           period: str,
                           reset_at: dt_time = DEFAULT_RESET_AT,
                           entry_id: str = None) -> bool:
    """
    判断某任务在当前周期内是否已成功完成过。

    任何异常(文件损坏/权限等)都返回 False —— 即"当作没完成", 保证任务照常运行。
    """
    if not period or str(period).lower() in ('none', ''):
        return False
    pkey = period_key(period, reset_at)
    if not pkey:
        return False
    try:
        with _lock():
            data = _read_all()
    except Exception as exc:
        logger.warning(f'[TaskState] 读取状态失败({type(exc).__name__}: {exc}), 视为未完成')
        return False
    item = (data.get(config_name) or {}).get(_state_key(task, entry_id)) or {}
    return item.get('period_key') == pkey


def clear(config_name: str = None, task: str = None) -> None:
    """清除记忆(便于排障与测试)。不传参数则清空全部。"""
    try:
        with _lock():
            if config_name is None:
                _write_all({})
                return
            data = _read_all()
            if task is None:
                data.pop(config_name, None)
            else:
                (data.get(config_name) or {}).pop(str(task).lower(), None)
            _write_all(data)
    except Exception as exc:
        logger.warning(f'[TaskState] 清除失败({type(exc).__name__}: {exc}), 忽略')


# ---------------------------------------------------------------------------
# 战斗计数的持久化
#
# 问题: `BaseTask.current_count` 只存在内存里(每个任务还在 run() 开头重置为 0),
# 进程一旦重启(手动重启、崩溃后 restart、任务被中断)计数就归零, 于是
# "我今天要打 N 次"这类固定任务会从头再打一遍, 永远打不满 N。
# 这里把它落到与"完成记忆/次数"同一个状态文件里, 按周期自动重置。
# ---------------------------------------------------------------------------
def _coerce_period(period) -> str:
    """把周期参数规范化成字符串; 接受 TaskPeriod 枚举或普通字符串。"""
    if period is None:
        return 'none'
    return str(getattr(period, 'value', period)).lower()


def get_count(config_name: str, task: str, period='none',
              reset_at: dt_time = DEFAULT_RESET_AT,
              now: datetime = None) -> int:
    """
    读取某任务在当前周期内已累计的战斗次数。

    周期变了(或从未记录过)则返回 0。任何异常也返回 0 —— 计数失败不应影响任务。
    """
    now = now or datetime.now()
    pkey = period_key(_coerce_period(period), reset_at, now)
    try:
        with _lock():
            data = _read_all()
    except Exception:
        return 0
    item = (data.get(config_name) or {}).get(str(task).lower()) or {}
    if pkey and item.get('count_key') != pkey:
        return 0            # 换了周期, 旧计数作废
    try:
        return max(0, int(item.get('count', 0) or 0))
    except (TypeError, ValueError):
        return 0


def add_count(config_name: str, task: str, delta: int = 1, period='none',
              reset_at: dt_time = DEFAULT_RESET_AT,
              now: datetime = None) -> int:
    """
    累加战斗次数并写盘, 返回累加后的值。

    跨周期时先归零再加。写盘失败只记 warning —— 计数不应成为任务失败的原因。
    """
    now = now or datetime.now()
    pkey = period_key(_coerce_period(period), reset_at, now)
    key = str(task).lower()
    try:
        with _lock():
            data = _read_all()
            item = data.setdefault(config_name, {}).setdefault(key, {})
            if pkey and item.get('count_key') != pkey:
                item['count'] = 0
                item['count_key'] = pkey
            try:
                cur = max(0, int(item.get('count', 0) or 0))
            except (TypeError, ValueError):
                cur = 0
            # 夹到 >= 0: 负数会让状态文件里留下脏值(虽然读取时会再夹一次),
            # 也会让"已打次数"看起来倒退。
            cur = max(0, cur + int(delta))
            item['count'] = cur
            item['count_updated'] = now.replace(microsecond=0).isoformat()
            _write_all(data)
        return cur
    except Exception as exc:
        logger.warning(f'[TaskState] 记录战斗次数失败({type(exc).__name__}: {exc}), 忽略')
        return get_count(config_name, task, period, reset_at, now)


def reset_count(config_name: str, task: str) -> None:
    """清零某任务的累计次数(例: 用户手动要求重新计数)。"""
    key = str(task).lower()
    try:
        with _lock():
            data = _read_all()
            item = (data.get(config_name) or {}).get(key)
            if isinstance(item, dict):
                item.pop('count', None)
                item.pop('count_key', None)
                item.pop('count_updated', None)
                _write_all(data)
    except Exception as exc:
        logger.warning(f'[TaskState] 重置战斗次数失败({type(exc).__name__}: {exc}), 忽略')


# ---------------------------------------------------------------------------
# 跨账号协同支撑: 心跳 / 可用配置发现 / 读取对方次数
#
# 说明: 各账号的"剩余次数"本来就按配置名分桶存在同一个状态文件里
# (见 _charges_of), 因此协同不需要另建一套状态文件 —— 只要再加一个心跳,
# 就能回答"对方在不在线"以及"对方这个任务还剩几次"。
# ---------------------------------------------------------------------------
HEARTBEAT_KEY = '__heartbeat__'
DEFAULT_HEARTBEAT_TIMEOUT = 180      # 秒; 超过视为离线


def write_heartbeat(config_name: str, extra: dict = None) -> None:
    """刷新本账号的心跳时间戳(用于让其他账号判断"我在线")。"""
    if not config_name:
        return
    try:
        with _lock():
            data = _read_all()
            hb = data.setdefault(HEARTBEAT_KEY, {})
            rec = {'at': datetime.now().replace(microsecond=0).isoformat()}
            if extra and isinstance(extra, dict):
                rec.update(extra)
            hb[config_name] = rec
            _write_all(data)
    except Exception as exc:
        logger.warning(f'[TaskState] 写心跳失败({type(exc).__name__}: {exc}), 忽略')


def read_heartbeat(config_name: str):
    """读取某账号的心跳信息(dict); 无记录返回 None。"""
    try:
        with _lock():
            data = _read_all()
    except Exception:
        return None
    hb = (data.get(HEARTBEAT_KEY) or {}).get(config_name)
    return hb if isinstance(hb, dict) else None


def is_online(config_name: str, timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
              now: datetime = None) -> bool:
    """对方是否在线(心跳未超时)。异常时返回 False(视为离线, 不做协同)。"""
    rec = read_heartbeat(config_name)
    if not rec or not rec.get('at'):
        return False
    try:
        at = datetime.fromisoformat(rec['at'])
    except (ValueError, TypeError):
        return False
    now = now or datetime.now()
    return (now - at).total_seconds() <= float(timeout)


def discover_configs(config_dir: str = None) -> list:
    """
    发现所有可用的配置名(账号), 用于确定"对方是谁"。

    来源: config/*.json 的文件名(排除 template), 再并入状态文件里已有分桶的名字。
    这样即使两台机器共享状态目录、各自只有自己的 config, 也能互相发现。
    """
    names = set()
    try:
        root = Path(config_dir) if config_dir else (Path.cwd() / 'config')
        for p in root.glob('*.json'):
            if p.stem and p.stem.lower() not in ('template',):
                names.add(p.stem)
    except Exception:
        pass
    try:
        with _lock():
            data = _read_all()
        for k in data.keys():
            if k != HEARTBEAT_KEY:
                names.add(k)
        for k in (data.get(HEARTBEAT_KEY) or {}).keys():
            names.add(k)
    except Exception:
        pass
    return sorted(names)


def summarize(config_name: str, now: datetime = None) -> dict:
    """
    汇总某账号的**完成记忆**, 供界面总览使用。

    返回: {
        "config": 账号名,
        "global":  {任务名: {"period","period_key","last_success"}},
    }

    ★ S5: 原本还返回 `"charges"`（存量）—— 用户裁定删除存量机制, 已去掉。

    只读一次状态文件后展开, 避免逐任务加锁(该文件的 FileLock 粒度是整文件)。
    """
    now = now or datetime.now()
    try:
        with _lock():
            data = _read_all()
    except Exception as exc:
        logger.warning(f'读取任务状态失败({type(exc).__name__}: {exc})')
        return {'config': config_name, 'global': {}}

    bucket = data.get(config_name) or {}
    glob = {}
    for key, item in bucket.items():
        if not isinstance(item, dict):
            continue
        if 'period' in item or 'last_success' in item:
            glob[key] = {
                'period': item.get('period'),
                'period_key': item.get('period_key'),
                'last_success': item.get('last_success'),
            }
        # ★ S5: 原来这里还读 `item['charges']` 算存量 —— **已删除**
        #   （`parse_slots` / `_decode_charges_v2` / `_normalize` 也随之删除）。
    return {'config': config_name, 'global': glob}


def peers_status(my_config: str, task: str = None,
                 now: datetime = None) -> list:
    """其他账号的**在线**概况（供界面显示"对方在不在"）。

    ## ★ S5: **只剩在线状态, 去掉"还剩几次"**

    用户裁定: "去掉组队协同，去掉存量次数。"

    原来还有 `task` / `max_charges` / `slots` 三个参数, 用来算"对方还剩几次"
    （靠 `peer_charges`, 已删除）。现在**只剩 `online`**。

    ★ `task` 参数**保留在签名里**（向后兼容调用方）—— 但**不再产生 `charges`**。

    :return: [{"config", "online"}]
    """
    now = now or datetime.now()
    out = []
    for name in discover_configs():
        if name == my_config:
            continue
        out.append({'config': name, 'online': is_online(name, now=now)})
    return out


# ★★ S5: **存量（充能）与组队协同的存储已删除** —— 用户裁定 ★★
#
#   "去掉组队协同，去掉存量次数。组队协同应该是**单独模块**啊，"
#   "不应该放在金币妖怪里。"
#
# 原来这里有一整套"存量记账"（`get_charges` / `consume_charge` /
# `next_charge_time` / `parse_slots` / `_slot_*` / `_decode_charges_v2`）
# 与"跨账号心跳/协同"（`write_heartbeat` / `read_heartbeat` / `is_online` /
# `discover_configs` / `peer_charges` / `peers_status`）—— 全部删除。
#
# **为什么删**: 用户裁定"**靠 window 的多次设置完全可以做到正常运行**" ——
# "一天在几个时段各跑一次"用**多个窗口**表达; "跑几轮"用**重复条目**表达。
#
# 设计依据: `docs/scheduler-architecture.md` §0（三句话命题）。
