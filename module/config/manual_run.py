# -*- coding: utf-8 -*-
"""「运行一次」—— 手动请求"立刻跑一次"，按**点击顺序**插队。

## 用户确认的语义

> 点击后按照点击先后顺序，直接排在最高优先级
> （就是跑完当前任务/战斗后插队运行）

要点：

1. **所有任务**都能点（固定任务与定时任务都可以）
2. **按点击先后**排队
3. **跑完当前任务/战斗后**才插队 —— 不是立即打断
4. 只跑**一次** —— 跑完就从队列消失

## 为什么用"时间戳队列"而不是布尔标记

用户要"按点击顺序"。若只记一个 `set`，多个任务同时被点就**丢了顺序**。
用 `[(ts, task)]` 列表，天然有序。

## 为什么不做"立即打断"

打断会卡在半途（战斗中 / 组队房间里）—— 与「暂停调度」同样的理由。
所以插队点是**任务边界**：当前任务跑完，队列里的下一个就是它。

## 与「重置选中」的关系

两者在界面上是邻居（都在"停用选中"旁），但语义完全不同：

| 按钮 | 做什么 | 影响 |
|---|---|---|
| **运行一次** | 排队立刻跑一次 | 不改历史记录 |
| **重置选中** | 归档 + 重开 | 清空当前计数（历史进归档）|

## 存储

`log/.manual_run.json`，与 `task_state` / `run_record` 同目录。
写入同样用**原子替换**，避免写一半损坏。
"""
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import RLock

from module.logger import logger

#: 队列文件名（放在 log/ 下）
QUEUE_FILENAME = '.manual_run.json'

#: 队列长度上限 —— 防止误点几百次把文件撑爆。
MAX_QUEUE = 100

_LOCK = RLock()


def _queue_file() -> Path:
    return Path.cwd() / 'log' / QUEUE_FILENAME


def _norm(name) -> str:
    """账号 / 任务名归一化 —— `Orochi` 与 `orochi` 是同一个。"""
    return str(name or '').strip().lower()


def _nice(name) -> str:
    """归一化但**保留原样大小写**用于存储（任务名是驼峰, 便于人读）。"""
    return str(name or '').strip()


def _read_all() -> dict:
    """读队列文件；任何异常都返回空（插队功能坏了不该让任务跑不起来）。"""
    path = _queue_file()
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(f'运行一次队列读取失败({type(exc).__name__}: {exc}), 当作空')
        return {}


def _write_all(data: dict) -> None:
    """原子写入（临时文件 + `os.replace`）—— 同 `run_record` 的理由。"""
    path = _queue_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise
    except Exception as exc:
        logger.warning(f'运行一次队列写入失败({type(exc).__name__}: {exc}), 忽略')


def _norm_list(raw) -> list:
    """把存储的 `[{ts, task}]` 规范化成 `[(ts, task)]`（坏条目跳过）。"""
    out = []
    for item in (raw or []):
        try:
            if isinstance(item, dict):
                out.append((float(item.get('ts', 0)), _nice(item.get('task'))))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append((float(item[0]), _nice(item[1])))
        except Exception:
            continue
    return [x for x in out if x[1]]


# --------------------------------------------------------------------------- 写
def request(config_name: str, task: str) -> list:
    """
    请求"立刻跑一次"。

    :return: 更新后的队列（任务名列表, 按点击顺序）

    ★ 同一个任务重复点**不会重复排队** —— 否则会连跑两次。
      但如果它已经被取走（正在跑/跑完了）, 再点就会**排到队尾**
      （那次点击是新的顺序）。
    """
    name = _nice(task)
    if not name:
        return pending(config_name)

    with _LOCK:
        data = _read_all()
        acc = _norm(config_name)
        queue = _norm_list(data.get(acc))

        if name.lower() in [t.lower() for _, t in queue]:
            # 已在队列里 -> 不重复加
            return [t for _, t in queue]

        queue.append((datetime.now().timestamp(), name))
        if len(queue) > MAX_QUEUE:
            queue = queue[-MAX_QUEUE:]
        data[acc] = [{'ts': ts, 'task': t} for ts, t in queue]
        _write_all(data)
        return [t for _, t in queue]


def request_many(config_name: str, tasks) -> list:
    """
    批量请求（界面上可能对"选中的多个任务"一起点）。

    ★ 按**给定顺序**排队；空/坏名字跳过。
    """
    for task in (tasks or []):
        request(config_name, task)
    return pending(config_name)


def take(config_name: str):
    """
    取出队首任务（**并移除** —— 只跑一次）。

    :return: 任务名; 队列为空则 `None`
    """
    with _LOCK:
        data = _read_all()
        acc = _norm(config_name)
        queue = _norm_list(data.get(acc))
        if not queue:
            return None
        _, task = queue.pop(0)
        data[acc] = [{'ts': ts, 'task': t} for ts, t in queue]
        _write_all(data)
        return task


def cancel(config_name: str, task: str) -> bool:
    """取消某个排队中的请求。:return: 是否真的取消了。"""
    with _LOCK:
        data = _read_all()
        acc = _norm(config_name)
        queue = _norm_list(data.get(acc))
        kept = [(ts, t) for ts, t in queue if t.lower() != _norm(task)]
        if len(kept) == len(queue):
            return False
        data[acc] = [{'ts': ts, 'task': t} for ts, t in kept]
        _write_all(data)
        return True


def clear(config_name: str) -> None:
    """清空该账号的队列。"""
    with _LOCK:
        data = _read_all()
        data.pop(_norm(config_name), None)
        _write_all(data)


# --------------------------------------------------------------------------- 读
def pending(config_name: str) -> list:
    """当前排队的任务名（**按点击顺序**）。"""
    with _LOCK:
        data = _read_all()
        return [t for _, t in _norm_list(data.get(_norm(config_name)))]


def peek(config_name: str):
    """看队首但不取走。"""
    q = pending(config_name)
    return q[0] if q else None


def is_pending(config_name: str, task: str) -> bool:
    return _norm(task) in [_norm(t) for t in pending(config_name)]


def summarize(config_name: str) -> dict:
    """给界面用的一份摘要。"""
    q = pending(config_name)
    return {'tasks': q, 'count': len(q), 'head': q[0] if q else ''}


# --------------------------------------------------------------------------- 排序
def order_first(pending_tasks, queue):
    """
    把**手动请求的任务**提到最前（按点击顺序），其余保持原序。

    :param pending_tasks: 已到点的任务列表（`Function` 对象）
    :param queue: `pending()` 返回的任务名列表（点击顺序）
    :return: 重排后的列表（**原地不改原列表**）

    ★ 这是"插队"的**排序侧**实现。真正的切换发生在**任务边界**
      （当前任务跑完）, 因为立即打断会卡在半途。

    ★ 请求了但**不在 `pending_tasks` 里**的任务（还没到点 / 被禁用）
      被忽略 —— 不能因为用户点了就跳过调度约束。
    """
    items = list(pending_tasks or [])
    if not items or not queue:
        return items

    by_name = {}
    for it in items:
        by_name.setdefault(_norm(getattr(it, 'command', '')), it)

    first, used = [], set()
    for name in queue:
        key = _norm(name)
        it = by_name.get(key)
        if it is not None and key not in used:
            first.append(it)
            used.add(key)
    rest = [it for it in items
            if _norm(getattr(it, 'command', '')) not in used]
    return first + rest
