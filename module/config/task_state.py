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


def peer_charges(config_name: str, task: str,
                 max_charges: int = 2, slots=None,
                 now: datetime = None) -> int:
    """
    读取**对方**在某个次数型任务上的剩余次数。

    slots 为 None 时会从状态文件里该任务已记录的 slots 推断(首次没有则用 0,12)。
    异常时返回 max_charges(视为对方次数充足, 避免因为读不到而总是推迟)。
    """
    now = now or datetime.now()
    try:
        with _lock():
            data = _read_all()
    except Exception:
        return max_charges

    rec = _charges_of(data, config_name, task)
    if not slots:
        slots = (rec or {}).get('slots') or '0,12'
    slot_hours = parse_slots(slots)

    count, last, cur = _decode_charges_v2(rec, slot_hours, max_charges, now)
    count, _ = _normalize(count, last, cur, max_charges)
    return max(0, min(max_charges, count))


def summarize(config_name: str, now: datetime = None) -> dict:
    """
    汇总某账号的完成记忆与次数状态, 供界面总览使用。

    返回: {
        "config": 账号名,
        "global":  {任务名: {"period","period_key","last_success"}},
        "charges": {任务名: {"count","slots","last_consume"}},
    }

    只读一次状态文件后展开, 避免逐任务加锁(该文件的 FileLock 粒度是整文件)。
    """
    now = now or datetime.now()
    try:
        with _lock():
            data = _read_all()
    except Exception as exc:
        logger.warning(f'[TaskState] 汇总状态失败({type(exc).__name__}: {exc})')
        return {'config': config_name, 'global': {}, 'charges': {}}

    bucket = data.get(config_name) or {}
    glob = {}
    charges = {}
    for key, item in bucket.items():
        if not isinstance(item, dict):
            continue
        if 'period' in item or 'last_success' in item:
            glob[key] = {
                'period': item.get('period'),
                'period_key': item.get('period_key'),
                'last_success': item.get('last_success'),
            }
        rec = item.get('charges')
        if isinstance(rec, dict):
            slots = parse_slots(rec.get('slots') or '0,12')
            cap = 2
            try:
                cap = max(1, int(rec.get('max', 2) or 2))
            except (TypeError, ValueError):
                cap = 2
            count, last, cur = _decode_charges_v2(rec, slots, cap, now)
            count, _ = _normalize(count, last, cur, cap)
            charges[key] = {
                'count': max(0, count),
                'max': cap,
                'slots': ','.join(str(h) for h in slots),
                'last_consume': rec.get('last_consume'),
            }
    return {'config': config_name, 'global': glob, 'charges': charges}


def peers_status(my_config: str, task: str = None,
                 max_charges: int = 2, slots=None,
                 now: datetime = None) -> list:
    """
    其他账号的在线与次数概况, 供界面显示"对方在不在、还剩几次"。

    :return: [{"config","online","charges"(指定 task 时)}]
    """
    now = now or datetime.now()
    out = []
    for name in discover_configs():
        if name == my_config:
            continue
        rec = {'config': name, 'online': is_online(name, now=now)}
        if task:
            rec['charges'] = peer_charges(name, task, max_charges=max_charges,
                                          slots=slots, now=now)
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# 按固定时刻刷新的挑战次数(经验妖怪 / 金币妖怪 / 石距 这类)
#
# 游戏事实: 次数在**每天的固定时刻**刷新(默认 0 点与 12 点), 最多储存 2 次。
# 注意这不是"间隔 12 小时": 若在 01:00 用掉一次, 下一次是当天 12:00 刷新,
# 而不是 13:00。用固定时刻建模既更准确, 也更利于多账号在同一个刷新点对齐组队。
# ---------------------------------------------------------------------------
def parse_slots(spec) -> tuple:
    """
    解析刷新时刻配置。接受 '0,12' / '0,12,18' / '12' 这类字符串,
    也接受列表或已经是 int 的可迭代对象。

    :return: 排序去重后的整点小时元组, 例如 (0, 12); 非法则返回 (0, 12)
    """
    default = (0, 12)
    if spec is None:
        return default
    if isinstance(spec, str):
        parts = [p.strip() for p in spec.replace('，', ',').split(',') if p.strip()]
    elif isinstance(spec, (list, tuple, set)):
        parts = list(spec)
    else:
        parts = [spec]
    hours = []
    for p in parts:
        try:
            h = int(float(p))
        except (TypeError, ValueError):
            continue
        if 0 <= h <= 23:
            hours.append(h)
    if not hours:
        return default
    return tuple(sorted(set(hours)))


def _slot_times(slots: tuple, now: datetime, count: int) -> list:
    """
    返回 `now` 之前(含当前所处周期)最近的 count 个刷新时刻, 由新到旧。

    例: slots=(0,12), now=14:00 -> [今天12:00, 今天00:00]
        slots=(0,12), now=01:00 -> [今天00:00, 昨天12:00]
    """
    if not slots or count <= 0:
        return []
    per_day = len(slots)
    out = []
    day_offset = 0
    # 每天 per_day 个点, 取够 count 个最多需要 count/per_day + 1 天
    max_days = (count // per_day) + 2
    while day_offset <= max_days and len(out) < count:
        base = (now + timedelta(days=-day_offset)).date()
        for h in reversed(slots):          # 同一天内由晚到早
            t = datetime.combine(base, dt_time(hour=h))
            if t <= now:
                out.append(t)
                if len(out) >= count:
                    break
        day_offset += 1
    return out


def _slot_key(t: datetime) -> str:
    return t.strftime('%Y-%m-%dT%H:%M')


def _charges_of(data: dict, config_name: str, task: str) -> dict:
    """取出某任务的 charges 记录(不存在则返回空 dict)。"""
    return ((data.get(config_name) or {}).get(str(task).lower()) or {}).get('charges') or {}




def _charge_window_slots(slots: tuple, max_charges: int) -> int:
    """
    "初始可用次数"的推算窗口 = 覆盖 max_charges 个刷新点所需的槽位数。

    例: slots=(0,12), max_charges=2 -> 窗口 2 个槽位(即回溯 24 小时),
    因此 12:05 首次算作 2 次(窗口含 00:00 与 12:00), 而 01:00 首次算作 1 次。
    """
    return max(1, int(max_charges))


def _slot_id_of(slots: tuple, now: datetime) -> int:
    """
    把当前时刻换算成**绝对槽位号** = 所在天的序号 * 每天槽位数 + 该天已过的槽位下标。

    用整数比较代替日期时间比较, 避免边界(跨天/跨月/跨年)与"含不含端点"的歧义。
    """
    n = len(slots)
    day_no = now.toordinal()
    idx = -1
    for i, h in enumerate(slots):
        if now.hour >= h:
            idx = i
        else:
            break
    if idx < 0:
        # 还没到今天第一个刷新点 -> 归入前一天最后一个槽位
        return (day_no - 1) * n + (n - 1)
    return day_no * n + idx


def _slot_id_before(slots: tuple, now: datetime) -> int:
    """严格早于 now 的最近槽位号(用于消耗后把 last_slot 前移)。"""
    cur = _slot_id_of(slots, now)
    n = len(slots)
    day_no = now.toordinal()
    idx = -1
    for i, h in enumerate(slots):
        if now.hour >= h:
            idx = i
        else:
            break
    if idx < 0:
        return cur          # 已在"前一天最后槽位", 无可前移
    if idx == 0 and n == 1:
        return cur - 1      # 只有 0 点时, 前一个槽位就是昨天那一个
    return cur


def _slots_before_or_at(slots: tuple, ref: datetime, now: datetime) -> int:
    """
    统计 (ref, now] 内的刷新点个数。保留该函数是为了兼容旧调用与测试。
    """
    if not slots:
        return 0
    ref_id = _slot_id_of(slots, ref)
    now_id = _slot_id_of(slots, now)
    return max(0, now_id - ref_id)


def _slot_at_or_before(slots: tuple, now: datetime) -> datetime:
    """now 之前(含当前所处周期)最近的刷新点。"""
    t = _slot_times(slots, now, 1)
    return t[0] if t else now


def _decode_charges_v2(rec: dict, slots: tuple, max_charges: int,
                       now: datetime):
    """
    读取并规范化 (count, last_slot):
      * 无记录 -> count 由"窗口回溯"推算(normalize 期间会补足), last_slot=cur-窗口
      * 有记录 -> 沿用; 但把 last_slot 夹到不超过 cur, 以免影响本次 normalize 的补足
    返回 (count, last_slot, cur_slot)
    """
    cur = _slot_id_of(slots, now)
    period_slots = _charge_window_slots(slots, max_charges)
    raw = (rec or {}).get('last_slot')
    try:
        last = int(raw) if raw is not None else cur - period_slots
    except (TypeError, ValueError):
        last = cur - period_slots
    try:
        count = int((rec or {}).get('count', 0) or 0)
    except (TypeError, ValueError):
        count = 0
    count = max(0, min(max_charges, count))
    if last > cur:
        last = cur
        count = max(0, min(max_charges, count))
    return count, last, cur


def _normalize(count: int, last: int, cur: int,
               max_charges: int) -> tuple:
    """
    把 count 补到 cur 槽位, 返回 (count, last)。

    **每个经过的槽位只补 1 次**(受上限约束), 而不是补"经过的槽位数" ——
    因为游戏是"每 12 小时恢复 1 次", 不是"每个槽位恢复槽位数量次"。
    例: count=0, 从 10/7 00:00 槽位跨到 10/8 12:00 槽位(经过 3 个), 只补 1 次
    (期间未上线, 未消耗, 因此存量最多也就 1 次, 受上限 2 约束亦为 1)。
    但若中间**确实经过了多个槽位且期间没有消耗**, 每个槽位都该补 1，
    所以这里按经过的槽位数逐个 +1 并封顶。
    """
    if cur > last:
        count = min(max_charges, count + (cur - last))
        last = cur
    return count, last


def get_charges(config_name: str, task: str,
                max_charges: int = 2, slots='0,12',
                now: datetime = None) -> int:
    """
    当前可用次数(剩余存量)。

    模型(整数槽位, 无日期边界歧义):
        cur        = 当前槽位号(每天 len(slots) 个槽位, 如 0 点/12 点)
        count      = 剩余次数(上限 max_charges)
        last_slot  = 上次把刷新计入 count 的槽位号
        查询时: count += (cur - last_slot), 封顶 max_charges; last_slot = cur

    首次(无记录)时 last_slot 取 cur - max_charges, 等价于"回溯 max_charges 个槽位":
        slots=(0,12), 上限 2 -> 12:05 首次为 2 次; 01:00 首次为 1 次

    逐步验算(slots=(0,12), 上限 2):
        10/7 12:05 初始 -> 2
        消耗 1 次        -> 1        消耗 2 次 -> 0
        10/7 23:59      -> 0        (未跨槽位)
        10/8 00:05      -> 1        (跨 1 个槽位)
        10/8 12:05      -> 2        (再跨 1 个)
        10/20 任意      -> 2        (封顶)

    异常时返回 max_charges(即"照常运行", 不因状态问题卡住任务)。
    """
    now = now or datetime.now()
    slot_hours = parse_slots(slots)
    try:
        with _lock():
            data = _read_all()
            rec = _charges_of(data, config_name, task)
    except Exception as exc:
        logger.warning(f'[TaskState] 查询次数失败({type(exc).__name__}: {exc}), '
                       f'按满次数处理')
        return max_charges

    count, last, cur = _decode_charges_v2(rec, slot_hours, max_charges, now)
    count, _ = _normalize(count, last, cur, max_charges)
    return max(0, min(max_charges, count))


def next_charge_time(config_name: str, task: str,
                     max_charges: int = 2, slots='0,12',
                     now: datetime = None) -> datetime:
    """
    下一次次数刷新的时刻(固定时刻), 用于把任务排到刷新后再做。

    - 只要还有可用次数 -> 返回 now(立刻可做);
    - 次数用尽 -> 返回下一个刷新点(今天还没到的第一个; 今天已过完则取明天第一个)。
    """
    now = now or datetime.now()
    slot_hours = parse_slots(slots)
    if get_charges(config_name, task, max_charges, slots, now) > 0:
        return now

    for day_offset in (0, 1, 2):
        base = (now + timedelta(days=day_offset)).date()
        for h in slot_hours:
            t = datetime.combine(base, dt_time(hour=h))
            if t > now:
                return t
    return now + timedelta(hours=12)


def consume_charge(config_name: str, task: str,
                   max_charges: int = 2, slots='0,12',
                   now: datetime = None) -> int:
    """
    消耗 1 次次数, 返回消耗后剩余次数。无可用次数时不做改动并返回 0。

    实现: 先 normalize 到当前槽位, 再把 count 减 1; 同时把 last_slot 前移一格,
    以便**同一槽位内继续消耗**时不会立刻被 normalize 补回来。
    """
    now = now or datetime.now()
    slot_hours = parse_slots(slots)
    key = str(task).lower()
    try:
        with _lock():
            data = _read_all()
            bucket = data.setdefault(config_name, {})
            item = bucket.setdefault(key, {})
            rec = item.get('charges') or {}

            count, last, cur = _decode_charges_v2(rec, slot_hours,
                                                  max_charges, now)
            count, last = _normalize(count, last, cur, max_charges)
            if count <= 0:
                return 0

            count -= 1
            # last_slot 保持在**当前槽位**: 本槽位还剩几次由 count 表达,
            # _normalize 只会在槽位真正推进时才补足, 因此不会把刚消耗的补回来。
            item['charges'] = {
                'count': count,
                'last_slot': cur,
                'slots': ','.join(str(h) for h in slot_hours),
                'last_consume': now.replace(microsecond=0).isoformat(),
            }
            _write_all(data)

        logger.info(f'[TaskState] 消耗一次次数: {config_name}.{task}, '
                    f'剩余 {count}/{max_charges}')
        return count
    except Exception as exc:
        logger.warning(f'[TaskState] 消耗次数失败({type(exc).__name__}: {exc}), '
                       f'按成功处理')
        return max(0, max_charges - 1)