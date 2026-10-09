# -*- coding: utf-8 -*-
"""**运行记录与归档** —— 跑了多少次、花了多久，落盘保存。

## 与 `task_state` 的分工

| 模块 | 存什么 | 用途 |
|---|---|---|
| `task_state` | 计数、周期完成记忆、存量/充能 | **调度决策**（决定要不要跑、还能跑几次）|
| `run_record`（本模块） | 每轮的**次数 + 耗时** + 归档 | **统计与展示**（跑了多少、花了多久）|

两者都落盘、都按 `(账号, 任务)` 隔离，但**职责不同** ——
把"统计"塞进 `task_state` 会让那个文件既管决策又管报表。

## 数据模型

    {
      "<账号>": {
        "<task>": {
          "current": {"started_at": ..., "updated_at": ...,
                      "runs": 12, "seconds": 345},
          "archive": [
            {"started_at": ..., "updated_at": ..., "archived_at": ...,
             "runs": 30, "seconds": 900},
            ...
          ]
        }
      }
    }

## ★「重置」= 归档后重开（不是删除）

用户明确要求:

> 点击重置选中后**不是清除记录, 而是归档记录后开始新的记录**。
> 这样后续可以分析运行记录和展示运行结果, 如御魂战斗多少次,
> 消耗多少体力, 花了多少时间等等。

所以 `reset()` 做两件事:

1. 把 `current` 追加到 `archive`（**只增不改**）
2. 把 `current` 清零（重开一轮）

★ 但 `runs == 0` 的当前记录**不归档** —— 否则每次误点重置都会
留下一堆空条目。`archive` 是留给"确实跑过"的记录的。

## 存储格式

JSON，与 `task_state` 同一个 `log/` 目录，文件名 `.run_record.json`。
写入用**原子替换**（临时文件 + `os.replace`），避免写一半断电损坏。
"""
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock

from module.logger import logger

#: 记录文件名（放在 log/ 下，与 `.task_state.json` 同级）
RECORD_FILENAME = '.run_record.json'

#: 归档上限 —— 防止无限增长。超过时**丢弃最旧的**。
#:
#: 500 轮是个宽松值: 按每天重置一次算够记一年多；
#: 即使用户频繁手动重置也不会撑爆。
MAX_ARCHIVE = 500

_LOCK = RLock()


def _record_file() -> Path:
    return Path.cwd() / 'log' / RECORD_FILENAME


def _norm(name) -> str:
    """账号 / 任务名归一化 —— `Orochi` 与 `orochi` 是同一个。"""
    return str(name or '').strip().lower()


def _read_all() -> dict:
    """
    读整个记录文件。

    任何异常（文件不存在 / JSON 坏了）都返回空 dict ——
    **统计功能不该让任务跑不起来**。
    """
    path = _record_file()
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(f'运行记录读取失败({type(exc).__name__}: {exc}), 当作空记录')
        return {}


def _write_all(data: dict) -> None:
    """
    原子写入（临时文件 + `os.replace`）。

    ★ 为什么不用直接写: 写到一半进程被杀会留下**半截 JSON**,
      下次读取就全丢了。`os.replace` 在同一分区上是原子的。
    """
    path = _record_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except Exception:
            # 清理临时文件, 避免留垃圾
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as exc:
        logger.warning(f'运行记录写入失败({type(exc).__name__}: {exc}), 忽略')


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _entry_of(data: dict, config_name: str, task: str) -> dict:
    """取（必要时创建）某个 (账号, 任务) 的记录节点。"""
    acc = data.setdefault(_norm(config_name), {})
    return acc.setdefault(_norm(task), {'current': None, 'archive': []})


def _blank_current() -> dict:
    now = _now_iso()
    return {'started_at': now, 'updated_at': now, 'runs': 0, 'seconds': 0}


# --------------------------------------------------------------------------- 记录
def begin(config_name: str, task: str) -> dict:
    """
    标记"这一轮开始了"。

    幂等: 已经有 `current` 时**不改 `started_at`**（保留本轮真正的起点），
    只更新 `updated_at`。
    """
    with _LOCK:
        data = _read_all()
        node = _entry_of(data, config_name, task)
        if not node.get('current'):
            node['current'] = _blank_current()
        node['current']['updated_at'] = _now_iso()
        _write_all(data)
        return node['current']


def finish(config_name: str, task: str, runs: int = 0,
           seconds: int = 0) -> dict:
    """
    累计一次运行结果（**累加**，不是覆盖）。

    :param runs: 本次跑了几次; 负数会被忽略
    :param seconds: 本次耗时（秒）; 负数会被忽略

    ★ 没有先调 `begin()` 也能用 —— 进程重启后 `begin` 可能已经丢了,
      统计不该因此丢数据。
    """
    with _LOCK:
        data = _read_all()
        node = _entry_of(data, config_name, task)
        if not node.get('current'):
            node['current'] = _blank_current()
        cur = node['current']

        add_runs = max(0, int(runs or 0))
        add_secs = max(0, int(seconds or 0))
        cur['runs'] = int(cur.get('runs', 0)) + add_runs
        cur['seconds'] = int(cur.get('seconds', 0)) + add_secs
        cur['updated_at'] = _now_iso()

        _write_all(data)
        return cur


def add_duration(config_name: str, task: str, delta: timedelta) -> dict:
    """
    按"跑了多久"累加耗时。

    比让调用方自己算秒更自然（任务里已经有 `timedelta` 的用时）。
    """
    try:
        seconds = int(delta.total_seconds())
    except Exception:
        seconds = 0
    return finish(config_name, task, runs=0, seconds=seconds)


def current(config_name: str, task: str):
    """读当前这一轮的记录; 没有则 `None`。"""
    with _LOCK:
        data = _read_all()
        node = (data.get(_norm(config_name)) or {}).get(_norm(task)) or {}
        cur = node.get('current')
        return dict(cur) if isinstance(cur, dict) else None


def archive(config_name: str, task: str) -> list:
    """读归档列表（**最新在最后**）。"""
    with _LOCK:
        data = _read_all()
        node = (data.get(_norm(config_name)) or {}).get(_norm(task)) or {}
        arch = node.get('archive')
        return [dict(x) for x in arch] if isinstance(arch, list) else []


def total(config_name: str, task: str) -> dict:
    """
    总计 = 当前 + 全部归档。供界面展示"累计跑了多少"。
    """
    cur = current(config_name, task) or {'runs': 0, 'seconds': 0}
    arch = archive(config_name, task)
    return {
        'runs': int(cur.get('runs', 0)) + sum(int(a.get('runs', 0)) for a in arch),
        'seconds': int(cur.get('seconds', 0)) + sum(int(a.get('seconds', 0)) for a in arch),
        'archived_rounds': len(arch),
        'current': cur,
    }


# --------------------------------------------------------------------------- 归档
def reset(config_name: str, task: str) -> bool:
    """
    **归档后重开**（不是删除）。

    :return: True 表示确实归档了一轮; False 表示没有可归档的内容

    ★ `runs == 0` 的当前记录**不归档** —— 否则误点重置会留一堆空条目。
    ★ 从没记录过的任务**什么都不做** —— 不凭空造一条空记录
      （用 `_entry_of` 会创建, 那是 `finish` 才该做的）。
    """
    with _LOCK:
        data = _read_all()
        acc = (data.get(_norm(config_name)) or {})
        node = acc.get(_norm(task))
        if not isinstance(node, dict):
            return False

        cur = node.get('current')
        archived = False
        if isinstance(cur, dict) and int(cur.get('runs', 0)) > 0:
            entry = dict(cur)
            entry['archived_at'] = _now_iso()
            arch = node.setdefault('archive', [])
            arch.append(entry)
            # 防止无限增长: 只保留最近的 MAX_ARCHIVE 条
            if len(arch) > MAX_ARCHIVE:
                node['archive'] = arch[-MAX_ARCHIVE:]
            archived = True

        # 重开一轮
        node['current'] = _blank_current()
        _write_all(data)
        return archived


def reset_many(config_name: str, tasks) -> int:
    """
    批量归档（界面上的「重置选中」）。

    :return: 实际归档的轮数

    ★ 单个任务出错**不中断**其余的 —— 批量操作里一个坏名字不该
      让整批失败。
    """
    n = 0
    for task in (tasks or []):
        try:
            if reset(config_name, task):
                n += 1
        except Exception as exc:
            logger.warning(f'归档 {task} 失败({type(exc).__name__}: {exc}), 跳过')
    return n


def clear(config_name: str = None, task: str = None) -> None:
    """
    **彻底删除**记录（排障用，界面上不该暴露）。

    :param config_name: 留空则清空所有账号
    :param task: 留空则清空该账号下所有任务

    ★ 与 `reset()` 的区别: `reset` 是**归档**（保历史）,
      `clear` 是**删除**（丢历史）。日常操作请用 `reset`。
    """
    with _LOCK:
        if not config_name:
            _write_all({})
            return
        data = _read_all()
        acc = _norm(config_name)
        if not task:
            data.pop(acc, None)
        else:
            (data.get(acc) or {}).pop(_norm(task), None)
        _write_all(data)


# --------------------------------------------------------------------------- 展示
def format_duration(seconds) -> str:
    """
    把秒格式化成中文可读。

        0     -> "0 分钟"
        90    -> "1 分钟"
        3600  -> "1 小时"
        3661  -> "1 小时 1 分钟"

    ★ 分钟以下**不显示秒** —— 这个量级的精度对"跑了多久"没意义。
    """
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        total = 0
    minutes = total // 60
    if minutes < 60:
        return f'{minutes} 分钟'
    hours, mins = divmod(minutes, 60)
    if mins == 0:
        return f'{hours} 小时'
    return f'{hours} 小时 {mins} 分钟'


def summarize(config_name: str) -> dict:
    """
    该账号**所有任务**的运行记录汇总（供总览页展示）。

    :return: `{task: {runs, seconds, archived_rounds, ...}}`
    """
    with _LOCK:
        data = _read_all()
        acc = data.get(_norm(config_name)) or {}
        out = {}
        for task, node in acc.items():
            if not isinstance(node, dict):
                continue
            cur = node.get('current') or {}
            arch = node.get('archive') or []
            out[task] = {
                'runs': int(cur.get('runs', 0) or 0)
                        + sum(int(a.get('runs', 0) or 0) for a in arch),
                'seconds': int(cur.get('seconds', 0) or 0)
                           + sum(int(a.get('seconds', 0) or 0) for a in arch),
                'archived_rounds': len(arch),
                'current_runs': int(cur.get('runs', 0) or 0),
                'current_seconds': int(cur.get('seconds', 0) or 0),
                'started_at': cur.get('started_at') or '',
            }
        return out
