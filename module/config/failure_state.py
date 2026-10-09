# -*- coding: utf-8 -*-
"""**连续失败记录与冷却** —— 落盘，避免"失败 3 次就重启进程"的无限循环。

## 改造前的问题（从真实运行日志里读出来的）

`script.py` 原先的逻辑:

```python
failed = self.failure_record[task] if task in self.failure_record else 0
failed = 0 if success else failed + 1
self.failure_record[task] = failed
if failed >= 3:
    logger.critical("Task `{task}` failed 3 or more times.")
    ...
    exit(1)                      # <- 整个子进程退出
```

`failure_record` 是 **`Script` 实例上的内存字典**。进程一退出，服务器就会
重新拉起一个（见 `module/server/script_process.py`），**新进程的
`failure_record` 是空的** —— 于是:

    失败 3 次 -> exit(1) -> 重启 -> 计数归零 -> 又能失败 3 次 -> 再重启 -> ...

**永远停不下来。** 真实日志里一次 7 小时的运行有 **97 次 `START` 块**
（即 90+ 次进程重启），而 `RyouToppa` 被派发 25 次、一次都没打成。

## 现在的做法

1. **计数落盘** —— 重启后计数不丢，不会"重新获得 3 次机会"
2. **到阈值不退出进程**，而是：
   * 记一条 `CRITICAL` 日志
   * **推送通知**（提醒用户上线）
   * 给该任务加**冷却**（`failure_cooldown`，默认 1 小时）
3. **冷却到期后重新给机会**（计数减半，而不是永远拉黑）——
   这样临时性故障（网络抖动、游戏弹窗）能自愈，
   而持续性故障（配置错、素材不匹配）也不会把调度器拖死
4. **任务成功就清零** —— 完全恢复正常调度

画成状态机:

    success          -> 清零, 恢复正常
    fail 1, 2        -> 计数 +1, 照常按 failure_interval 重试
    fail 3 (阈值)     -> 通知 + 冷却 1 小时 + 计数减半
    冷 却 到 期       -> 允许再试（计数已减半, 再失败 3 次才会再冷却）

★ 为什么"计数减半"而不是"清零": 清零等于给满 3 次机会,
  持续故障会变成"每 1 小时重启 3 次"的慢速循环; 减半则是**逐步升级**,
  同时又不会一次失败就永久放弃。

★ 为什么**不**保留 `exit(1)`: 「进程重启」是**用户可见且昂贵**的动作
  （模拟器要重新连、界面要重开）。对一个**任务级**的失败用进程级手段,
  既不匹配也不安全。用户明确同意改掉这个行为。

## 存储

`log/.failure_state.json`，与 `task_state` / `run_record` 同目录，
写入用**原子替换**（临时文件 + `os.replace`），避免写一半损坏。
"""
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock

from module.logger import logger

#: 文件名（放在 log/ 下，与 `.task_state.json` 同级）
STATE_FILENAME = '.failure_state.json'

#: 连续失败到几次就进入冷却。
FAIL_THRESHOLD = 3

#: 进入冷却后停多久。
#:
#: 1 小时是个折中: 足够让"游戏侧临时问题"过去（比如活动维护、网络抖动），
#: 又不会让一个真能跑的任务等太久。
DEFAULT_COOLDOWN_MINUTES = 60

_LOCK = RLock()


def _state_file() -> Path:
    return Path.cwd() / 'log' / STATE_FILENAME


def _norm(name) -> str:
    return str(name or '').strip().lower()


def _read_all() -> dict:
    """
    读整个状态文件。

    任何异常（不存在 / JSON 坏了）都返回空 —— **失败记录坏了不该让任务跑不起来**,
    最坏情况就是"退化成改造前的行为"（每次重试都是新计数）。
    """
    path = _state_file()
    if not path.exists():
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning(f'失败记录读取失败({type(exc).__name__}: {exc}), 当作空')
        return {}


def _write_all(data: dict) -> None:
    """原子写入（同 `run_record` 的理由: 半截 JSON 会全丢）。"""
    path = _state_file()
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
        logger.warning(f'失败记录写入失败({type(exc).__name__}: {exc}), 忽略')


def _entry(data: dict, config_name: str, task: str) -> dict:
    acc = data.setdefault(_norm(config_name), {})
    return acc.setdefault(_norm(task), {'count': 0})


def _parse(iso) -> datetime or None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso))
    except Exception:
        return None


# --------------------------------------------------------------------------- 读
def failure_count(config_name: str, task: str) -> int:
    """连续失败次数（0 = 正常）。"""
    with _LOCK:
        node = (_read_all().get(_norm(config_name)) or {}).get(_norm(task))
        if not isinstance(node, dict):
            return 0
        try:
            return max(0, int(node.get('count', 0) or 0))
        except (TypeError, ValueError):
            return 0


def cooldown_until(config_name: str, task: str, now=None):
    """
    该任务的冷却到期时间；不在冷却则 `None`（过期的也算"不在冷却"）。

    :param now: 可注入的"现在"（方便测试）
    """
    now = now or datetime.now()
    with _LOCK:
        node = (_read_all().get(_norm(config_name)) or {}).get(_norm(task))
        if not isinstance(node, dict):
            return None
    until = _parse(node.get('cooldown_until'))
    if until is None:
        return None
    return until if until > now else None


def in_cooldown(config_name: str, task: str, now=None) -> bool:
    """该任务现在是否处于冷却中。"""
    return cooldown_until(config_name, task, now) is not None


def cooldown_remaining_minutes(config_name: str, task: str, now=None) -> int:
    """冷却还剩几分钟（不在冷却则 0）。"""
    now = now or datetime.now()
    until = cooldown_until(config_name, task, now)
    if until is None:
        return 0
    return max(0, int((until - now).total_seconds() // 60))


def summarize(config_name: str) -> dict:
    """该账号所有任务的失败状态（供界面展示"哪些任务在冷却"）。"""
    with _LOCK:
        acc = _read_all().get(_norm(config_name)) or {}
    now = datetime.now()
    out = {}
    for task, node in acc.items():
        if not isinstance(node, dict):
            continue
        try:
            count = int(node.get('count', 0) or 0)
        except (TypeError, ValueError):
            count = 0
        until = _parse(node.get('cooldown_until'))
        if count <= 0 and (until is None or until <= now):
            continue
        out[task] = {
            'count': count,
            'cooldown_until': until.replace(microsecond=0).isoformat()
                              if (until and until > now) else None,
            'cooldown_minutes': max(0, int((until - now).total_seconds() // 60))
                                if (until and until > now) else 0,
        }
    return out


# --------------------------------------------------------------------------- 写
def record_success(config_name: str, task: str) -> None:
    """
    任务成功 -> **清零**（含冷却）。

    ★ 这是"自愈"的关键: 临时性故障过去之后, 任务立刻回到完全正常的调度,
      不会因为"历史上失败过"而被区别对待。
    """
    with _LOCK:
        data = _read_all()
        acc = data.get(_norm(config_name))
        if not isinstance(acc, dict):
            return
        if _norm(task) not in acc:
            return
        acc.pop(_norm(task), None)
        if not acc:
            data.pop(_norm(config_name), None)
        _write_all(data)


def record_failure(config_name: str, task: str,
                   threshold: int = FAIL_THRESHOLD,
                   cooldown_minutes: int = DEFAULT_COOLDOWN_MINUTES,
                   now=None) -> dict:
    """
    记一次失败，并按需进入冷却。

    :return: `{'count', 'cooldown_until', 'just_cooled', 'should_notify'}`

    `just_cooled=True` 表示**这一次**刚好达到阈值并进入冷却 ——
    调用方据此决定要不要发通知（避免每次都发）。
    """
    now = now or datetime.now()
    with _LOCK:
        data = _read_all()
        node = _entry(data, config_name, task)

        try:
            count = max(0, int(node.get('count', 0) or 0))
        except (TypeError, ValueError):
            count = 0
        count += 1

        just_cooled = False
        until = None
        if count >= max(1, int(threshold)):
            # 到阈值 -> 冷却 + **计数减半**（不是清零, 见模块文档）
            until = now + timedelta(minutes=max(0, int(cooldown_minutes)))
            node['cooldown_until'] = until.replace(microsecond=0).isoformat()
            node['count'] = count // 2
            just_cooled = True
        else:
            node['count'] = count
            node.pop('cooldown_until', None)

        node['updated_at'] = now.replace(microsecond=0).isoformat()
        _write_all(data)

        return {
            'count': count,
            'cooldown_until': until,
            'just_cooled': just_cooled,
            'should_notify': just_cooled,
        }


def clear(config_name: str = None, task: str = None) -> None:
    """
    清除失败状态（供界面"我修好了, 让我立刻重试"用）。

    * 都留空 -> 清空全部
    * 只给 `config_name` -> 清空该账号
    * 都给 -> 清空该任务（**同时解除冷却**）
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
