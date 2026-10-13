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


# ---------------------------------------------------------------------------
# ★★★ 2026-10-12 用户裁定「2 废弃」：**任务级计数机制已删** ★★★
#
# > "既然你用 `runs`，那就把他**取代 `current_count`**，这两个不是一个东西吗"
# > "**不能存在两套机制**" -> "**2 废弃**"
#
# ★ 这里原来有 **3 个函数**（已删）：
#   * `get_count(config, task, ...)`     读**任务级**计数
#   * `add_count(config, task, ...)`     写**任务级**计数
#   * `reset_count(config, task)`        清**任务级**计数
#
# ★ 为什么删：★ 它们与【条目级 `runs`】（`get_entry_runs` /
#   `bump_entry_runs` / `reset_entry_runs`）**表达同一件事**
#   （"这条任务打了几场"）⇒ ★ **两套机制**。
#
# ★ 现行唯一一套（**条目级**）：
#   | 用途 | 函数 |
#   |---|---|
#   | 读（判据）| `get_entry_runs(config, entry_id)` |
#   | 写（每场 +1）| `bump_entry_runs(config, entry_id, delta)` |
#   | 清零 | `reset_entry_runs(config, entry_id)` |
#   | 总记录（展示，永不清零）| `record_entry_run` / `get_entry_total_runs` |
#
# ⚠ 保留 `period_key()` / `is_completed_in_period()` —— ★ 它们服务
#   **周期完成记忆**（周期任务），与"战斗计数"**不是一回事**。
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# P-3b: 队列循环的**已跑轮数**
#
# ★★ 用户裁定 ★★
# > "我觉得选中后应该加一个**跑几次**的额外输入框, **0代表一直跑**,
# >   **1、2……代表跑几次**。"
# > "如果要重跑这几次循环要怎么设置呢 …… 是不是得有个**手动重置计数**的按钮"
# > -> 用户选 **乙**: ★ **加一个「重置循环计数」按钮**
#
# ## 两个东西必须分开
#
# | 名字 | 性质 | 存哪 |
# |---|---|---|
# | `script.optimization.loop_times` | ★ **用户设置**（我的意图）| 配置 JSON |
# | `loop_rounds`（本模块）| ★ **运行进度**（已经跑了几轮）| **状态文件**（存盘）|
#
# ★ 分开的好处: "跑 N 轮"是**确定**的（改设置不改变已跑的进度），
#   且**重启后端不丢**（用户选 B: 存盘）。
#
# ⚠ 与 `__heartbeat__` 同一做法: 在**配置名那一桶**里放一个 `__` 前缀的键,
#   不会与任务名冲突（任务键都是小写字母/下划线, 不以 `__` 开头）。
# ---------------------------------------------------------------------------
LOOP_KEY = '__loop__'

# ★★★ 条目级运行计数（片 5 / F2「已运行 N 次」）★★★
#
# ## ★★ 用户裁定（原话）★★
#
# > "由于现在是流转的运行，那么就会出现**运行过，状态标记为已运行X次**"
# > 并选定：**按条目**计（甲）—— 与"条目级次数"（`RunEntry.target`）一致。
#
# ## 为什么**必须按条目**而不是按任务
#
# ★ 队列里**同一任务可以有多条条目**（用户用重复条目表达"重复跑整个任务"）。
#   按任务计会**把两条混在一起** —— 与 `running_entry_id`（P-1）同一理由：
#   "**身份，不是位置**"（`docs/scheduler-architecture.md` §1.5）。
#
# ## 存法（与 `__loop__` 同一套）
#
# ```json
# {
#   "恋鸟树": {
#     "__loop__":  {"rounds": 2},
#     "__entries__": {"<entry_id>": {"runs": 3, "updated": "..."}}
#   }
# }
# ```
ENTRIES_KEY = '__entries__'


def _entries_bucket(data: dict, config_name: str) -> dict:
    """取（必要时建）该配置的 `__entries__` 容器。"""
    bucket = data.setdefault(config_name, {})
    item = bucket.get(ENTRIES_KEY)
    if not isinstance(item, dict):
        item = {}
        bucket[ENTRIES_KEY] = item
    return item


def get_entry_runs(config_name: str, entry_id: str) -> int:
    """★ 某**条目**已经跑了几次（0 = 没跑过 / 查不到）。

    ★ 这是**运行进度**（`task_state` 落盘），不是用户设置。
      任何异常返回 0（不阻断调度）。
    """
    eid = str(entry_id or '').strip()
    if not eid:
        return 0
    try:
        with _lock():
            data = _read_all()
            item = (data.get(config_name) or {}).get(ENTRIES_KEY)
            if isinstance(item, dict):
                one = item.get(eid)
                if isinstance(one, dict):
                    return int(one.get('runs', 0) or 0)
        return 0
    except Exception as exc:
        logger.warning(f'[TaskState] 读条目运行次数失败'
                       f'({type(exc).__name__}: {exc}), 按 0')
        return 0


def bump_entry_runs(config_name: str, entry_id: str, delta: int = 1) -> int:
    """★ 本条**又打了一场** -> `runs` += delta（**判据用的那份**）。

    ## ★★★ 用户裁定「甲」之后，本函数的语义（2026-10-12）★★★

    > "既然你用 `runs`，那就把他**取代 `current_count`**，
    >  这两个**不是一个东西吗**。" -> "**1 甲**"

    ★ 所以 `runs` = **本条已打几场**（= 原来的 `current_count`），
      由**任务内部**每打一场经 `commit_count()` 调用本函数写入。

    ## 与 `record_entry_run()` 的分工（★ 颗粒度不同，别混）

    | 函数 | 写什么 | 颗粒度 | 谁调 |
    |---|---|---|---|
    | ★ **本函数** | `runs`（判据）| ★ **场**（打一场 +1）| `commit_count()`（任务内）|
    | `record_entry_run()` | `total_runs` / `total_log`（展示/分析）| ★ **次**（跑完一遍 +1）| `script.py` 收尾 |

    ★ 早先两者合在一个函数里 —— ★ 那会导致 `commit_count` 每场调一次时
      把"运行**次数**"也加上去（打 2 场 ⇒ 次数 +2，实际只跑了 1 次）。

    :param entry_id: `RunEntry.entry_id`（空 = 不记，返回 0）
    :return: 累加后的 **`runs`**
    """
    eid = str(entry_id or '').strip()
    if not eid:
        return 0
    try:
        with _lock():
            data = _read_all()
            bucket = _entries_bucket(data, config_name)
            one = bucket.get(eid)
            if not isinstance(one, dict):
                one = {}
                bucket[eid] = one
            n = int(one.get('runs', 0) or 0) + int(delta)
            one['runs'] = n
            one['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _write_all(data)
            return n
    except Exception as exc:
        logger.warning(f'[TaskState] 累加条目运行次数失败'
                       f'({type(exc).__name__}: {exc}), 忽略')
        return 0


def set_entry_runs(config_name: str, entry_id: str, value: int) -> int:
    """★★ **直接设定**本条的 `runs`（★ 不是累加）★★

    ## ★ 为什么需要它（2026-10-12 · D7.6 第二层真因）

    ★ 用户实测：★ 探索内部打了 **32 场**，★ 但收尾只写 `runs += 1`
      ★ 而 `target`（出厂 `count_default`）= **30**
      ⇒ ★ `1 >= 30` 不成立 ⇒ ★ **永远"没做完"** ⇒ ★ **反复跑探索**。

    ★ 修法：★ 把**任务内部真实计数**（`current_count` / `battle_count`）
      ★ **直接写进** `runs` ⇒ ★ 这样 `runs >= target` 能成立。

    ## ⚠ 为什么用 `set` 而不是 `bump`（关键）

    ★ 收尾时拿到的是**本轮的总场次**（32），★ **不是增量**
      ⇒ ★ 用 `bump` 会**重复累加**（★ 每次收尾再加 32）
      ⇒ ★ **必须 set**（★ 幂等：同一轮重复调用结果相同）。

    :param value: 本条**已打几场**（绝对值）
    :return: 写入后的 `runs`
    """
    eid = str(entry_id or '').strip()
    if not eid:
        return 0
    try:
        with _lock():
            data = _read_all()
            bucket = _entries_bucket(data, config_name)
            one = bucket.get(eid)
            if not isinstance(one, dict):
                one = {}
                bucket[eid] = one
            n = max(0, int(value))
            one['runs'] = n
            one['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _write_all(data)
            return n
    except Exception as exc:
        logger.warning(f'[TaskState] 设定条目运行场次失败'
                       f'({type(exc).__name__}: {exc}), 忽略')
        return 0


def get_entry_target(config_name: str, entry_id: str) -> int:
    """★ 取**本条**的目标次数（`target`）。

    ⚠ **不在状态文件里** —— `target` 是**配置**（`RunEntry.target`），
      所以本函数**只做占位**，真正的回落由 `Config.entry_target_reached()`
      负责（★ 那儿有 ① 条目 → ② 任务级 → ③ 出厂默认 三级回落）。

    ★ 为什么放在这里：★ `script.py` 收尾时要"**把 runs 设到 target**"
      （★ 让非战斗任务"跑完一次即达标"），★ 需要一个**统一入口**；
      ★ 有了它，将来若 target 也要落盘，**改这一处**即可。

    :return: `target`（**取不到时返回 0** ⇒ 调用方退化为 `+1`）
    """
    eid = str(entry_id or '').strip()
    if not eid:
        return 0
    try:
        from module.server.main_manager import mm
        cfg = mm.config_cache(config_name)
        # ★ 复用 `Config` 的三级回落（★ 唯一权威）
        for e in (cfg.build_run_list().to_list() or []):
            if str(e.get('entry_id') or '') == eid:
                t = int(e.get('target') or 0)
                if t > 0:
                    return t
                name = str(e.get('task') or '')
                break
        else:
            return 0
        from module.config.config_model import convert_to_underscore
        key = convert_to_underscore(name)
        sch = getattr(getattr(cfg.model, key, None), 'scheduler', None)
        if sch is not None:
            t = int(getattr(sch, 'target', 0) or 0)
            if t > 0:
                return t
        from module.config import task_catalog as _TC
        meta = _TC.get(name)
        return int(getattr(meta, 'count_default', 0) or 0) if meta else 0
    except Exception as exc:
        logger.debug(f'[TaskState] 取条目 target 失败'
                     f'({type(exc).__name__}: {exc})')
        return 0


def record_entry_run(config_name: str, entry_id: str,
                     runs_this_time: int = 1) -> int:
    """★ 某**条目跑完一次** -> 记**总记录**（`total_runs` / `total_log`）。

    ## ★★★ 为什么和 `bump_entry_runs` 分开（用户裁定「甲」之后必须分）★★★

    ★ 统一之后 **`runs` = 本条已打几场**，它由**任务自己**每场经
      `commit_count()` 写（`bump_entry_runs`）。
    ★ 而 **`total_runs` = 本条被【运行】了几次**（"跑了 3 遍"），
      是**每次运行**记一笔 ⇒ ★ 两者**颗粒度不同**：
      * `runs`：**场**（打一场 +1）
      * `total_runs`：**次**（跑完一遍 +1）
    ⇒ ★ 若混在一个函数里：`commit_count` 每场调一次会**把"次数"也加一遍**
      （RealmRaid 打 2 场 ⇒ total_runs +2，实际只跑了 **1 次**）。

    ## 记什么

    * `total_runs` += 1（**每次运行**一次）
    * `total_log` 追加 `{'at': 到秒, 'runs': 本次打了几场}`
      —— ★ 用户要求"**包含时间信息到秒**，供后期统计分析"
    * ★ **永不清零**（`reset_entry_runs` 只清 `runs`）

    :param runs_this_time: 本次运行打了几场（写进 `total_log` 明细，便于统计）
    :return: 累加后的 `total_runs`
    """
    eid = str(entry_id or '').strip()
    if not eid:
        return 0
    try:
        with _lock():
            data = _read_all()
            bucket = _entries_bucket(data, config_name)
            one = bucket.get(eid)
            if not isinstance(one, dict):
                one = {}
                bucket[eid] = one
            total = int(one.get('total_runs', 0) or 0) + 1
            one['total_runs'] = total
            # ★★★ 10-13：时间戳改【毫秒】+ 记 session（规格书 §1.6-L410 / §2.6-LR4）
            #   ★ 原来只到秒（`'%Y-%m-%d %H:%M:%S'`）⇒ 不足以区分同一秒内的两次运行。
            now_ms = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:23]
            one['updated'] = now_ms
            log = one.get('total_log')
            if not isinstance(log, list):
                log = []
            # ★ `session` = 这条记录属于哪一次"后端启动"
            #   ⇒ ★ 供"按时间戳比对"使用（与 `mark_session_start()` 写的值同源）。
            _sess = ''
            try:
                _lp = _loop_item(data, config_name)
                _sv = _lp.get('session_start')
                _sess = str(_sv).strip() if isinstance(_sv, str) else ''
            except Exception:
                _sess = ''
            log.append({'at': now_ms,
                        'runs': int(runs_this_time or 0),
                        'session': _sess})
            if len(log) > 500:
                del log[:len(log) - 500]
            one['total_log'] = log
            _write_all(data)
            return total
    except Exception as exc:
        logger.warning(f'[TaskState] 记条目总记录失败'
                       f'({type(exc).__name__}: {exc}), 忽略')
        return 0


def get_entry_total_runs(config_name: str, entry_id: str) -> int:
    """★ 该条目的**累计**运行次数（跨轮，**不清零**）—— 给**展示**用。

    ★ 与 `get_entry_runs()`（本轮计数，会清零）区分开：
      见 `bump_entry_runs()` 的"两份记录"说明。
    ★ 向后兼容：老数据只有 `runs`、没有 `total_runs` ⇒ 退化为读 `runs`。
    """
    eid = str(entry_id or '').strip()
    if not eid:
        return 0
    try:
        with _lock():
            data = _read_all()
            item = (data.get(config_name) or {}).get(ENTRIES_KEY)
            if isinstance(item, dict):
                one = item.get(eid)
                if isinstance(one, dict):
                    if 'total_runs' in one:
                        return int(one.get('total_runs', 0) or 0)
                    return int(one.get('runs', 0) or 0)   # ★ 老数据兜底
        return 0
    except Exception as exc:
        logger.warning(f'[TaskState] 读条目累计次数失败'
                       f'({type(exc).__name__}: {exc}), 按 0')
        return 0


def reset_entry_runs(config_name: str, entry_id: str = '') -> int:
    """★ **重置**：把本轮的 `runs` **归档**，然后开新一轮（返回处理的条目数）。

    ## ★★★ 用户裁定：**"重置" = 归档 + 开新记录（★ 不是清除）** ★★★

    > **[10-09 12:57:14]** ★★ "以上的记录，**点击重置选中后不是清除记录，
    >  而是【归档记录后开始新的记录】**。这样后续可以**分析运行记录和展示运行
    >  结果**，如御魂战斗多少次，消耗多少体力，花了多少时间等等。"
    >
    > **[10-12 13:29:29]** ★ "**取消临时任务，改为不同任务的【长时记录】**"
    >
    > **[10-12 13:34:45]** ★ "把**每次启动的时间记录下并每次启动做比对**就行"

    ## ★★ 归档到哪里

    | 键 | 含义 | 本函数 |
    |---|---|---|
    | `runs` | 本轮已打几场（**判据**）| ★ **归档后清掉** |
    | `completed` / `completed_*` | 本轮完成标记 | ★ **清掉**（新一轮）|
    | ★ **`runs_history`** | ★ **每轮的归档**：`[{at, runs}]` | ★ **追加一条** |
    | `total_runs` / `total_log` | 累计总记录（展示 / 分析）| ★ **保留**（见 `record_entry_run`）|

    ## ★ 为什么"归档"而不是"清除"（用户的用途）

    ★ 用户明确要**后期统计分析**（"御魂战斗多少次，消耗多少体力，花了多少时间"）
      ⇒ ★ 若直接清掉，★ **过去的每轮成绩就永久丢了**。

    ## ⚠ 我踩过的坑（记下来）

    ★ 本函数原来用 `bucket.pop(entry_id)` / `pop(ENTRIES_KEY)`
      —— ★ **把整条记录删掉** ⇒ `total_runs` **一起没了**
      ⇒ ★ 与"总记录永不清零"**自相矛盾**。
    ★ 之后改成"只删 `runs`/`completed`" —— ★ 但**没有归档**
      ⇒ ★ 与"重置 = 归档 + 开新记录"**仍不符**（★ 本轮补上）。
    """
    try:
        def _archive_and_clear(one: dict) -> bool:
            """归档本轮 `runs` 后清掉"本轮"相关的键；返回是否真有动作。"""
            if not isinstance(one, dict):
                return False
            touched = False
            # ★ ① 先归档（只在真有 runs 时记）
            try:
                cur = int(one.get('runs') or 0)
            except (TypeError, ValueError):
                cur = 0
            if cur > 0:
                hist = one.get('runs_history')
                if not isinstance(hist, list):
                    hist = []
                hist.append({
                    'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'runs': cur,
                })
                if len(hist) > 200:
                    del hist[:len(hist) - 200]
                one['runs_history'] = hist
                touched = True
            # ★ ② 再清本轮
            #   10-13：一并清 `completed_session`（与 `completed` 同生共死）
            for k in ('runs', 'completed', 'completed_at',
                      'completed_reason', 'completed_round',
                      'completed_session'):
                if k in one:
                    one.pop(k, None)
                    touched = True
            return touched

        with _lock():
            data = _read_all()
            bucket = (data.get(config_name) or {}).get(ENTRIES_KEY)
            if not isinstance(bucket, dict):
                return 0
            n = 0
            if not entry_id:
                for one in bucket.values():
                    if _archive_and_clear(one):
                        n += 1
            else:
                if _archive_and_clear(bucket.get(str(entry_id))):
                    n = 1
            if n:
                _write_all(data)
            return n
    except Exception as exc:
        logger.warning(f'[TaskState] 清条目运行次数失败'
                       f'({type(exc).__name__}: {exc}), 忽略')
        return 0


# ---------------------------------------------------------------- 本轮已完成
#
# ★★★ "本轮已完成"（用户裁定 丙）★★★
#
# ## ★★ 用户原话 ★★
#
# > "两套计数不行，需要用让他**严格跑派发次数**，而不是自己用一套计数。"
# > "`target` 是**目标次数**，再来个**真实计数**。"
# > "**丙**"（= 调度层默认"跑满 target 才算完成"；个别任务可提前上报完成）
#
# ## 它解决什么
#
# ★ **临时任务（`period=none`）** 没有"周期完成记忆"（`_skip_by_period` 对
#   `period=none` 永远返回 False）⇒ ★ 它**没有任何东西让它在"本轮做完了"之后退出**
#   ⇒ 会被反复派发（实测 RealmRaid 每 40 秒一轮，永不停）。
# ★ 本标记就是那个"退出条件"：
#   * **跑满 `target`** ⇒ 调度层自动标（`script.py`）
#   * **任务提前做完了**（如 RealmRaid 券打完）⇒ 任务自己调
#     `mark_entry_completed`（★ 只需那一个任务改，其它靠 target）
#
# ## ★ 与"次数(runs)"的关系（两个都必要，别混）
#
# | 字段 | 数什么 | 谁判 |
# |---|---|---|
# | `runs`         | ★ 这一行被**派发**了几次 | `_skip_by_count`：`runs >= target` |
# | `completed`    | ★ **本轮已完成**（含提前完成）| 本模块 + 调度层 |
#
# ★ 新一轮（队列循环到末尾）由 `clear_entry_completed()` 清空 ⇒ 可以再跑。

def get_entry_completed(config_name: str, entry_id: str) -> bool:
    """★ 该条目**本轮是否已完成**（查不到 = False）。

    ## ★★★ 2026-10-12 修：**按轮次号自动过期**（用户报的真 bug）★★★

    > "调度有问题：**循环第二次时结界突破没有触发**。"

    ## ★ 原实现的致命缺陷（实测复现）

    ★ `completed` 只有在 `reset_loop_next_run()` 里才被清，而它
      ★ **只在【队列完全为空】时**才被调用（`script.py:429-447`，还要过节流）。
    ★ 而真实队列里**总有别的条目在跑**（Exploration / Rest 反复）
      ⇒ ★ **队列从不"空"** ⇒ 那个钩子**几乎不触发**
      ⇒ ★ `completed` **永久残留** ⇒ ★ 该条**再也不跑**。
    ★ 数据印证：`20261012T141032-RealmRaid  runs=2 completed=True` 一直挂着。

## ★★★ 10-13 再改：**按【本次启动时间】过期**（用户裁定「丙」）★★★

> ★★ **用户原话**：
> > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
> > "**或者按照时间戳来判断**"
> > "**就按这个来**"

## ★ 为什么"轮次号过期"还不够

★ 轮次号只在 **loop 模式 + 队列有可重排候选** 时才 +1
  （`script.py:557-561` 需 `reset_loop_next_run()` 返回非空）
⇒ ★ 在 `goto_main` / `stay_there` / 乱序等模式下**永不推进**
  ⇒ ★ `completed` **跨轮残留** ⇒ ★ 该条**再也不跑**。

★ **按时间戳**就没有这个依赖：
  ★ 每次后端调度循环启动 ⇒ `session_start` 刷新
  ⇒ ★ 上一次启动标的"已完成"**自动全部失效** ⇒ ★ **一定能跑**。

## ★ 现行判据（三级，宽松优先 —— ★ 宁可多跑，不可不跑）

```
① session_start 存在（有基准）
     且 completed_session == 当前 session_start  ⇒ ★ 算已完成
     否则（不同、或没写 completed_session）        ⇒ ★ 未完成
② session_start 缺失（读不到基准）                  ⇒ ★ **按未完成**
     （★ 关键：★ 不能因为读不到基准就永远不跑）
③ completed_session 与 completed_round 都不存在（极老数据）
     ⇒ ★ 退化为「新一轮开始」 ⇒ 未完成
```
"""
    eid = str(entry_id or '').strip()
    if not eid:
        return False
    try:
        with _lock():
            data = _read_all()
            item = (data.get(config_name) or {}).get(ENTRIES_KEY)
            if not isinstance(item, dict):
                return False
            one = item.get(eid)
            if not isinstance(one, dict):
                return False
            if not one.get('completed', False):
                return False

            # ★★★ 现行判据：按【本次启动时间】比对（★ 取代轮次号）★★★
            # ★ 注意：这里**已在 `_lock()` 内** ⇒ ★ 直接读 `data`，
            #   ★ 不能调 `get_session_start()`（它也会加锁 ⇒ 会**嵌套死锁**）。
            cur_session = ''
            try:
                _lp = _loop_item(data, config_name)
                _v = _lp.get('session_start')
                if isinstance(_v, str):
                    cur_session = _v.strip()
            except Exception:
                cur_session = ''
            marked_session = one.get('completed_session')

            if cur_session:
                # ★ 有基准 ⇒ 只认时间戳
                if marked_session and str(marked_session) == str(cur_session):
                    return True        # ★ 本次启动之后标的 ⇒ 确实本轮已完成
                # ★ 不是本次标的 ⇒ 已过期 ⇒ 就地清掉（别留脏数据）
                one.pop('completed', None)
                one.pop('completed_at', None)
                one.pop('completed_reason', None)
                one.pop('completed_round', None)
                one.pop('completed_session', None)
                try:
                    _write_all(data)
                except Exception:
                    pass
                logger.info(f'条目 {eid} 的"本轮已完成"已过期'
                            f'（标记于 {marked_session or "旧版本（无时间戳）"}，'
                            f'本次启动于 {cur_session}）-> 可再跑')
                return False

            # ★ 读不到基准 ⇒ ★ **按未完成**（宁可多跑一次，也不能永远不跑）
            logger.warning(f'条目 {eid} 的完成判定缺少【本次启动时间】基准'
                           f'（session_start 为空）-> 按**未完成**处理，允许重跑')
            return False
    except Exception as exc:
        logger.warning(f'[TaskState] 读"本轮已完成"失败'
                       f'({type(exc).__name__}: {exc}), 按未完成')
        return False


def mark_entry_completed(config_name: str, entry_id: str,
                         reason: str = '') -> bool:
    """★ 标记某条目**本轮已完成**（写盘）。返回是否成功。

    ## ★★★ 10-13 改：**同时写【本次启动时间】**（用户裁定「丙」）★★★

    > ★★ **用户原话**：
    > > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
    > > "**或者按照时间戳来判断**"

    ## ★ 写什么

    | 字段 | 含义 | 过期依据 |
    |---|---|---|
    | `completed` | 布尔：本轮已完成 | — |
    | `completed_at` | ★ 标记时刻（**毫秒**）| 展示用 |
    | ★ `completed_session` | ★★ **标记时的【本次启动时间】** | ★★ **现行过期依据** |
    | `completed_reason` | 可选说明（如"没券了"）| — |
    | `completed_round` | 轮次号 | ⚠ **保留但不再作判据**（★ 向后兼容）|

    ★ `get_entry_completed()` 只在 `completed_session == 当前 session_start`
      时才算"本轮已完成" ⇒ ★ **下一次启动自动全部失效** ⇒ ★ **一定能跑**。
    ★ 详见 `get_entry_completed()` 的说明。

    :param reason: 可选说明（写日志用，如 `'没券了'`）
    """
    eid = str(entry_id or '').strip()
    if not eid:
        return False
    try:
        with _lock():
            data = _read_all()
            bucket = _entries_bucket(data, config_name)
            one = bucket.get(eid)
            if not isinstance(one, dict):
                one = {}
                bucket[eid] = one
            one['completed'] = True
            one['completed_at'] = datetime.now().strftime(
                '%Y-%m-%d %H:%M:%S.%f')[:23]
            # ★★★ 现行判据：记下"本次启动时间" —— 供 `get_entry_completed()` 判过期
            #   ★ 注意：这里**已在 `_lock()` 内** ⇒ 直接读 `data`，不能调
            #     `get_session_start()`（会重复加锁 ⇒ 嵌套死锁）。
            try:
                _lp = _loop_item(data, config_name)
                _ss = _lp.get('session_start')
                one['completed_session'] = str(_ss).strip() if isinstance(_ss, str) else ''
            except Exception:
                one['completed_session'] = ''
            # ⚠ 轮次号保留（向后兼容 + 排障可读），★ 但不再是判据
            try:
                one['completed_round'] = int(
                    _loop_item(data, config_name).get('rounds', 0) or 0)
            except Exception:
                one['completed_round'] = 0
            if reason:
                one['completed_reason'] = str(reason)[:80]
            _write_all(data)
            _sess = one.get('completed_session') or '（无基准）'
            logger.info(f'[TaskState] 条目 {eid} 标记为【本轮已完成】'
                        f'（本次启动于 {_sess} ⇒ 后端下次启动自动失效）'
                        f'{("；" + str(reason)) if reason else ""}')
            return True
    except Exception as exc:
        logger.warning(f'[TaskState] 标记"本轮已完成"失败'
                       f'({type(exc).__name__}: {exc}), 忽略')
        return False


def clear_entry_completed(config_name: str, entry_id: str = '') -> int:
    """★ 清掉"本轮已完成"标记（`entry_id` 空 = 清**全部**），返回清掉的条目数。

    ★ 用于**新一轮开始**（队列循环到末尾）—— 让所有条目重新可跑。
    ★ 10-13：★ 一并清 `completed_session` / `completed_round`
      （★ 它们与 `completed` **同生共死**；留下会形成
        "`completed=False` + `completed_session=旧值`" 的怪组合，排障时易误读）。
    """
    try:
        with _lock():
            data = _read_all()
            bucket = (data.get(config_name) or {}).get(ENTRIES_KEY)
            if not isinstance(bucket, dict):
                return 0

            def _wipe(one):
                """★ 清一个条目的全部"已完成"字段（返回是否有东西被清）。"""
                had = one.pop('completed', None)
                one.pop('completed_at', None)
                one.pop('completed_reason', None)
                one.pop('completed_session', None)
                one.pop('completed_round', None)
                return bool(had)

            n = 0
            if not entry_id:
                for one in bucket.values():
                    if isinstance(one, dict) and _wipe(one):
                        n += 1
            else:
                one = bucket.get(str(entry_id))
                if isinstance(one, dict) and _wipe(one):
                    n = 1
            if n:
                _write_all(data)
            return n
    except Exception as exc:
        logger.warning(f'[TaskState] 清"本轮已完成"失败'
                       f'({type(exc).__name__}: {exc}), 忽略')
        return 0


def _loop_item(data: dict, config_name: str):
    """取（必要时建）该配置的 `__loop__` 项。"""
    bucket = data.setdefault(config_name, {})
    item = bucket.get(LOOP_KEY)
    if not isinstance(item, dict):
        item = {}
        bucket[LOOP_KEY] = item
    return item


def mark_session_start(config_name: str, when: str = '') -> str:
    """★★★ 10-13 新增：记下【本次启动时间】—— "按时间戳比对"的基准量 ★★★

    ## ★★ 用户裁定（[10-13]）

    > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
    > "**或者按照时间戳来判断**"
    > "**就按这个来**"（指 §1.6 现行口径：用【本次启动时间】与【记录里的时间】比对）

    ## ★ 为什么需要它

    ★ 改造前全仓**没有任何"本次启动时间"**：
      * `__loop__.reset_at`（本文件 L931）★ **只写不读**，是死数据
      * `script.py` 的 `_loop_reset_at` 只是**一次函数调用内的局部变量**，不落盘
      * `base_task.py` 的 `start_time` 是**任务实例内存**，随任务对象生灭
    ⇒ ★ 于是"这条本次跑没跑过"只能靠**计数器**（`runs >= target`）判
      ⇒ ★ 计数残留 ⇒ **跑不起来**（用户痛点）。
    ★ 本函数提供那个缺失的基准量：`__loop__.session_start`（**毫秒**精度）。

    ## ★ 调用时机（★ 决定语义）

    ★ `script.py` 的 `loop()` **开头**调一次
      ⇒ ★ 语义 = ★ **"本次后端调度循环启动的时刻"**。
    ★ ⇒ ★ **每次重启后端** ⇒ 基准刷新 ⇒ 所有条目都算"本次没跑过"
      ⇒ ★ **一定能跑**（★ 正是用户要的效果；★ 用户已接受"重启后本轮从 0 重打"）。

    ## ★ 精度

    ★ **毫秒**（`%Y-%m-%d %H:%M:%S.%f` 截到 3 位）
      —— ★ 规格书 §1.6-L410/§2.6-LR4 明确要求"到毫秒"；
      ★ 秒级不足以区分同一秒内的两次运行。

    :param when: 指定时间串（测试用）；空 = 取当前时间
    :return: 写入的 ISO 毫秒时间串
    """
    now_ms = when or datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:23]
    try:
        with _lock():
            data = _read_all()
            item = _loop_item(data, config_name)
            item['session_start'] = now_ms
            item['session_updated'] = datetime.now().strftime(
                '%Y-%m-%d %H:%M:%S.%f')[:23]
            _write_all(data)
        logger.info(f'[TaskState] 本次启动时间已记录: {now_ms}'
                    f'（此后"本条本次跑没跑过"一律与它比对）')
        return now_ms
    except Exception as exc:
        logger.warning(f'[TaskState] 记本次启动时间失败'
                       f'({type(exc).__name__}: {exc}), 忽略')
        return ''


def get_session_start(config_name: str) -> str:
    """★ 读【本次启动时间】（毫秒串）；没有则返回 `''`。

    ★ 与 `mark_session_start()` 成对：
      * `''` ⇒ ★ **没有基准** ⇒ 调用方应视为"**无法判定**"
        （★ `get_entry_completed()` 对这种情况**按未完成**处理，
          ★ 宁可多跑一次，也不能因为读不到基准就永远不跑 —— ★ 这是用户痛点）。
    """
    try:
        with _lock():
            data = _read_all()
            item = (data.get(config_name) or {}).get(LOOP_KEY)
            if isinstance(item, dict):
                v = item.get('session_start')
                if isinstance(v, str):
                    return v.strip()
        return ''
    except Exception as exc:
        logger.warning(f'[TaskState] 读本次启动时间失败'
                       f'({type(exc).__name__}: {exc}), 按空')
        return ''


def get_loop_rounds(config_name: str) -> int:
    """★ 队列循环**已经跑了几轮**（0 = 还没跑过）。

    ★ 这是**运行进度**，不是用户设置（用户设置是
      `script.optimization.loop_times`）。任何异常返回 0（不阻断调度）。
    """
    try:
        with _lock():
            data = _read_all()
            item = (data.get(config_name) or {}).get(LOOP_KEY)
            if isinstance(item, dict):
                return int(item.get('rounds', 0) or 0)
        return 0
    except Exception as exc:
        logger.warning(f'[TaskState] 读循环轮数失败({type(exc).__name__}: {exc}), 按 0')
        return 0


def bump_loop_rounds(config_name: str, delta: int = 1) -> int:
    """★ 队列循环**跑完一轮** -> 轮数 +1，返回新值（**写盘**）。"""
    try:
        with _lock():
            data = _read_all()
            item = _loop_item(data, config_name)
            n = int(item.get('rounds', 0) or 0) + int(delta)
            item['rounds'] = n
            item['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _write_all(data)
            return n
    except Exception as exc:
        logger.warning(f'[TaskState] 累加循环轮数失败({type(exc).__name__}: {exc}), 忽略')
        return 0


def reset_loop_rounds(config_name: str) -> int:
    """★★ 用户点「重置循环计数」-> 把已跑轮数清 0（**写盘**）★★

    ★ 用户选 **乙**（手动按钮）的理由:
    > "如果要重跑这几次循环要怎么设置呢，我没想好，
    >  是不是得有个手动重置计数到设定值的按钮"

    ★ 为什么"清 0"而不是"设成 `loop_times`":
      语义是"**已经跑了几轮**" —— 清 0 = "一轮都还没跑" = 可以再跑 N 轮。
      （"设成 N" 会让计数**超过** target，`已跑 >= 目标` 仍然成立 ->
        还是不会跑，是**反的**。）

    :return: 重置后的值（恒 0）
    """
    try:
        with _lock():
            data = _read_all()
            item = _loop_item(data, config_name)
            item['rounds'] = 0
            item['reset_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _write_all(data)
        logger.info(f'[TaskState] 循环轮数已重置（{config_name}）—— 可以重新跑 N 轮')
    except Exception as exc:
        logger.warning(f'[TaskState] 重置循环轮数失败({type(exc).__name__}: {exc}), 忽略')
    return 0


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
