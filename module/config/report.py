# -*- coding: utf-8 -*-
"""**任务完成汇报**（用户 2026-10-10 新需求）。

## 用户原话

> "这顺便发现了一个可以添加的显式汇报屏幕功能 —— 添加一个**任务完成汇报 tab**,
>  现在的日志属于原始日志, 应该**转移到单独界面**, 用来 debug,
>  当前日志位置替换为**任务完成汇报**的 tab, 只会报完成了哪些、
>  **出错任务标注**等等其它可以作为简报的内容"

## 设计

**不新增状态存储** —— 现有三份状态文件已经足够:

| 来源 | 回答什么 |
|---|---|
| `run_record`（`log/.run_record.json`）| 跑了**几次**、花了**多久** |
| `task_state`（`log/.task_state.json`）| **本周期完成**了哪些、充能还剩几次 |
| `failure_state`（`log/.failure_state.json`）| **失败**计数 + 冷却到什么时候 |

本模块把它们**合成一份简报**: 每个任务一行, 含
* 中文名
* 本轮**跑了几次 / 共多少秒**
* **是否已在本周期完成**
* **失败次数**（>0 要**标注**）
* **冷却中**（还要等几分钟）
* 充能任务的**剩余次数**

★ 为什么单独一个模块而不是塞进 `schema_router`: 它是**纯数据聚合**（无 FastAPI 依赖）,
  可以单独单测, 也方便以后被别处复用（如导出报告）。
"""
from datetime import datetime

from module.logger import logger

# 一次运行少于这么多秒, 视为"进去看了一眼就退"（可能没做成事）
_SHORT_RUN_SECONDS = 20


def build_report(config_name: str, now: datetime = None) -> dict:
    """生成任务完成汇报。

    :param config_name: 账号名（如 `恋鸟树`）
    :param now: 便于测试注入
    :return: 见下面的结构说明
    """
    now = now or datetime.now()
    out = {
        'config': config_name,
        'at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'summary': {
            'total': 0,          # 有记录的任务数
            'completed': 0,      # 本周期已完成
            'failed': 0,         # 有失败记录
            'in_cooldown': 0,    # 冷却中
            'total_runs': 0,     # 累计运行次数
            'total_minutes': 0,  # 累计耗时（分钟）
        },
        'tasks': [],
        'errors': [],            # 需要用户注意的（失败 / 冷却 / 短运行）
    }

    # ---------------- 三个数据源（任一坏掉都不该让整页挂）----------------
    runs = _safe(lambda: _runs(config_name), {})
    completed = _safe(lambda: _completed(config_name, now), set())
    fails = _safe(lambda: _fails(config_name, now), {})
    charges = _safe(lambda: _charges(config_name), {})

    names = sorted(set(runs) | set(completed) | set(fails) | set(charges))

    for key in names:
        r = runs.get(key) or {}
        f = fails.get(key) or {}
        row = {
            'key': key,
            'name': _zh(key),
            'runs': int(r.get('runs') or 0),
            'seconds': int(r.get('seconds') or 0),
            'updated_at': r.get('updated_at'),
            'completed_in_period': key in completed,
            'fail_count': int(f.get('count') or 0),
            'in_cooldown': bool(f.get('cooldown_until')),
            'cooldown_until': f.get('cooldown_until'),
            'cooldown_minutes': int(f.get('cooldown_minutes') or 0),
        }
        if key in charges:
            c = charges[key]
            row['charges'] = {'count': c.get('count'), 'max': c.get('max')}

        # ---- 标注（用户要求"出错任务标注"）----
        marks = []
        if row['in_cooldown']:
            marks.append('cooldown')
        if row['fail_count'] > 0:
            marks.append('failed')
        if row['completed_in_period']:
            marks.append('completed')
        if row['runs'] > 0 and 0 < row['seconds'] < _SHORT_RUN_SECONDS:
            marks.append('short')
        row['marks'] = marks
        out['tasks'].append(row)

        # ---- 汇总 ----
        out['summary']['total'] += 1
        out['summary']['total_runs'] += row['runs']
        if row['completed_in_period']:
            out['summary']['completed'] += 1
        if row['fail_count'] > 0:
            out['summary']['failed'] += 1
        if row['in_cooldown']:
            out['summary']['in_cooldown'] += 1

    out['summary']['total_minutes'] = round(
        sum(t['seconds'] for t in out['tasks']) / 60.0, 1)

    # ---- 错误清单（按严重度排：冷却 > 失败 > 短运行）----
    for t in out['tasks']:
        if t['in_cooldown']:
            out['errors'].append({
                'key': t['key'], 'name': t['name'], 'level': 'cooldown',
                'text': (f"{t['name']}：失败 {t['fail_count']} 次，"
                         f"冷却中（还有约 {t['cooldown_minutes']} 分钟）"),
            })
        elif t['fail_count'] > 0:
            out['errors'].append({
                'key': t['key'], 'name': t['name'], 'level': 'failed',
                'text': f"{t['name']}：失败 {t['fail_count']} 次",
            })
        elif 'short' in t['marks']:
            out['errors'].append({
                'key': t['key'], 'name': t['name'], 'level': 'short',
                'text': (f"{t['name']}：运行 {t['seconds']} 秒就结束，"
                         f"可能没做成事"),
            })

    logger.info(f'汇报 {config_name}: {out["summary"]}')
    return out


# ---------------------------------------------------------------- 内部
def _safe(fn, default):
    """任一个数据源坏了都只记日志, 不让整页挂。"""
    try:
        return fn()
    except Exception as exc:
        logger.warning(f'汇报数据源失败({type(exc).__name__}: {exc}), 用空值')
        return default


def _zh(key: str) -> str:
    """任务键 -> 中文名（拿不到就回退原键, **不静默变空**）。"""
    try:
        from module.config import task_catalog as TC
        meta = TC.get(key)
        if meta is not None and getattr(meta, 'name_zh', None):
            return meta.name_zh
    except Exception:
        pass
    return key


def _runs(config_name: str) -> dict:
    """每任务的 `{runs, seconds, updated_at}`。"""
    from module.config import run_record
    data = run_record.summarize(config_name)
    out = {}
    # `summarize` 的返回结构在不同版本可能是 dict-of-dict 或 list
    if isinstance(data, dict):
        src = data.get('tasks') if 'tasks' in data else data
        if isinstance(src, dict):
            for k, v in src.items():
                if isinstance(v, dict):
                    out[str(k).lower()] = v
        elif isinstance(src, list):
            for v in src:
                if isinstance(v, dict) and v.get('task'):
                    out[str(v['task']).lower()] = v
    return out


def _completed(config_name: str, now: datetime) -> set:
    """本周期**已完成**的任务键集合。"""
    from module.config import task_state
    data = task_state.summarize(config_name, now)
    got = set()
    for k, v in (data or {}).items():
        if k in ('config', 'global'):
            continue
        if isinstance(v, dict) and v.get('completed_in_period'):
            got.add(str(k).lower())
    return got


def _fails(config_name: str, now: datetime) -> dict:
    """每任务的失败信息 `{count, cooldown_until, cooldown_minutes}`。"""
    from module.config import failure_state
    data = failure_state.summarize(config_name) or {}
    out = {}
    for k, v in data.items():
        if not isinstance(v, dict):
            continue
        cd = v.get('cooldown_until')
        out[str(k).lower()] = {
            'count': v.get('count', 0),
            'cooldown_until': cd,
            # `summarize` 直接给了分钟数就用它; 否则自己算
            'cooldown_minutes': v.get(
                'cooldown_minutes',
                _minutes_left(cd, now)),
        }
    return out


def _minutes_left(cooldown_until, now: datetime) -> int:
    if not cooldown_until:
        return 0
    try:
        if isinstance(cooldown_until, str):
            cooldown_until = datetime.fromisoformat(cooldown_until)
        return max(0, int((cooldown_until - now).total_seconds() // 60))
    except Exception:
        return 0


def _charges(config_name: str) -> dict:
    """充能任务的剩余次数。"""
    from module.config import task_state
    data = task_state.summarize(config_name) or {}
    got = data.get('charges') or {}
    return {str(k).lower(): v for k, v in got.items() if isinstance(v, dict)}
