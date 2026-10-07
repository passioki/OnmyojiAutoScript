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


def record_success(config_name: str, task: str,
                   period: str = 'none',
                   reset_at: dt_time = DEFAULT_RESET_AT) -> None:
    """
    记录某任务在"当前周期"已成功完成。

    :param config_name: 配置名(如 '伴生树'), 多账号互不干扰
    :param task: 任务名(下划线形式或大驼峰都可, 内部统一小写)
    :param period: 周期类型; 为 none 时仅记录时间戳, 不参与周期判断
    :param reset_at: 游戏重置时间
    """
    key = str(task).lower()
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
                           reset_at: dt_time = DEFAULT_RESET_AT) -> bool:
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
    item = (data.get(config_name) or {}).get(str(task).lower()) or {}
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
# 充能式挑战次数(经验妖怪 / 金币妖怪 这类"每 N 小时恢复一次、最多存 M 次")
# ---------------------------------------------------------------------------
def _charges_of(data: dict, config_name: str, task: str) -> dict:
    return ((data.get(config_name) or {}).get(str(task).lower()) or {}).get('charges') or {}


def _compute_charges(rec: dict, max_charges: int, recover_hours: float,
                     now: datetime) -> tuple:
    """
    根据记录推算当前可用次数。

    模型: 每 recover_hours 恢复 1 次, 最多累积 max_charges 次。
    rec 里存 used(已消耗次数) 与 since(计时起点)。
    返回 (available, base)：base 是用于回写规整的 (used, since)。
    """
    if max_charges <= 0 or recover_hours <= 0:
        return max_charges, (0, now)
    used = int(rec.get('used', 0) or 0)
    since_raw = rec.get('since')
    try:
        since = datetime.fromisoformat(since_raw) if since_raw else now
    except (ValueError, TypeError):
        since = now

    # 距离计时起点已经恢复了多少次
    elapsed_hours = (now - since).total_seconds() / 3600.0
    recovered = int(elapsed_hours // recover_hours) if elapsed_hours > 0 else 0
    if recovered > 0:
        used = max(0, used - recovered)
        # 计时起点前移整周期, 保留余数以免丢失进度
        since = since + timedelta(hours=recovered * recover_hours)

    # 累积上限: until = used + available <= max_charges
    available = max(0, max_charges - used)
    return available, (used, since)


def get_charges(config_name: str, task: str,
                max_charges: int = 2, recover_hours: float = 12,
                now: datetime = None) -> int:
    """
    查询当前可用次数。异常时返回 max_charges(即"照常运行", 不因状态问题卡住任务)。
    """
    now = now or datetime.now()
    try:
        with _lock():
            data = _read_all()
            rec = _charges_of(data, config_name, task)
            available, base = _compute_charges(rec, max_charges, recover_hours, now)
            return available
    except Exception as exc:
        logger.warning(f'[TaskState] 查询次数失败({type(exc).__name__}: {exc}), '
                       f'按满次数处理')
        return max_charges


def consume_charge(config_name: str, task: str,
                   max_charges: int = 2, recover_hours: float = 12,
                   now: datetime = None) -> int:
    """
    消耗 1 次次数, 返回消耗后剩余可用次数。

    若当前没有可用次数则不做任何消耗并返回 0(调用方应据此跳过本次挑战)。
    """
    now = now or datetime.now()
    key = str(task).lower()
    try:
        with _lock():
            data = _read_all()
            bucket = data.setdefault(config_name, {})
            item = bucket.setdefault(key, {})
            rec = item.get('charges') or {}
            available, (used, since) = _compute_charges(rec, max_charges,
                                                        recover_hours, now)
            if available <= 0:
                return 0
            item['charges'] = {'used': used + 1,
                               'since': since.replace(microsecond=0).isoformat()}
            _write_all(data)
            logger.info(f'[TaskState] 消耗一次次数: {config_name}.{task}, '
                        f'剩余 {available - 1}/{max_charges}')
            return available - 1
    except Exception as exc:
        logger.warning(f'[TaskState] 消耗次数失败({type(exc).__name__}: {exc}), '
                       f'按成功处理')
        return max(0, max_charges - 1)


def next_charge_time(config_name: str, task: str,
                     max_charges: int = 2, recover_hours: float = 12,
                     now: datetime = None) -> datetime:
    """
    下一次次数恢复的时刻, 用于把任务排到"充能好了再做"。

    - 当前仍有可用次数(含存量) -> 返回 now, 表示立刻可做;
    - 已用尽 -> 返回**下一格**充能完成的时刻(不是整整 recover_hours 之后,
      而是按 elapsed 的余数计算), 这样恢复后会及时再跑一次。
    """
    now = now or datetime.now()
    try:
        with _lock():
            data = _read_all()
            rec = _charges_of(data, config_name, task)
    except Exception:
        return now

    available, (used, since) = _compute_charges(rec, max_charges, recover_hours, now)
    if available > 0:
        return now
    if recover_hours <= 0:
        return now

    elapsed_hours = max(0.0, (now - since).total_seconds() / 3600.0)
    # _compute_charges 已把 since 前移过已恢复的整周期, 故 elapsed < recover_hours
    remaining = recover_hours - elapsed_hours
    if remaining <= 0:
        remaining = recover_hours
    return now + timedelta(hours=remaining)

