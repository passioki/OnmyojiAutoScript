# -*- coding: utf-8 -*-
"""新旧调度逻辑对照 —— 用**真实配置**验证新模型。

## 为什么要先做对照, 而不是直接切换

新调度核心(`scheduler_core`)目前**未接线**, `get_next()` 仍在跑旧逻辑。
切换是首次改变实际行为的一步, 风险最高。因此在切换前, 先做一次**只读对照**:

  对每个已启用的任务, 用新模型算 `next_available()`, 与配置里现有的
  `next_run` 比对, 看是否一致、不一致的原因是什么。

这样能把"新模型理解错了游戏规则"这类问题在切换前暴露出来。

## 对照的局限(必须说明)

旧逻辑的 `next_run` 是**历史运行时状态**: 它由历次运行后的 `task_delay()` 累积而成,
反映的是"上次跑完之后排的时间", 而不是"按规则重算的时间"。
因此两者**本来就不该完全相等** —— 有差异是预期的。

真正有意义的观察是:
  1. 新模型能否解释每个任务的"能跑/不能跑"状态
  2. `cannot_run_reason()` 给出的理由是否符合直觉
  3. 是否存在"新模型认为永远跑不了"的任务(那是 bug)
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(r'D:\OAS-dev\OnmyojiAutoScript')
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import logging
logging.disable(logging.CRITICAL)

from module.config import task_catalog as TC             # noqa: E402
from module.config.resource import Resource              # noqa: E402
from module.config.scheduler_core import (               # noqa: E402
    RunState, cannot_run_reason, credits_at, next_available)


def load_config(name: str) -> dict:
    f = REPO / 'config' / f'{name}.json'
    return json.loads(f.read_text(encoding='utf-8'))


def build_resource(meta) -> Resource:
    """从任务元数据构造 Resource(含用户配置的开放时段)。"""
    return Resource.from_legacy(
        success_interval=meta.success_interval,
        charge_slots=meta.charge_slots,
        charge_max=meta.charge_max,
        charge_consume=meta.charge_consume,
        count_default=meta.count_default,
        category=meta.category.value,
    )


def snake(n: str) -> str:
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', n).lower()


def main() -> int:
    now = datetime.now().replace(microsecond=0)
    cfg_name = '恋鸟树'
    cfg = load_config(cfg_name)

    print('=' * 104)
    print(f'新旧调度对照  ·  配置={cfg_name}  ·  现在={now:%Y-%m-%d %H:%M:%S}')
    print('=' * 104)
    print()
    print('说明: 旧 next_run 是**历史运行态**累积的结果, 与新模型重算值本不应完全相等。')
    print('      这里关注的是"新模型能否合理解释状态", 而非数值对齐。')
    print()

    never_runnable = []
    rows = []

    for meta in TC.all_meta():
        key = snake(meta.task)
        node = cfg.get(key)
        if not isinstance(node, dict):
            continue
        sch = node.get('scheduler') or {}
        if not sch.get('enable'):
            continue

        res = build_resource(meta)
        old_next = sch.get('next_run')

        # 新模型状态: 从配置的 next_run 反推"已用掉多少"是不可靠的,
        # 因此这里取**最保守**的假设: credits = capacity(池子满),
        # 即"如果资源充足, 最早什么时候能跑"。这检验的是**时段与资源规则**本身。
        st_full = RunState(credits=res.capacity, refill_anchor=None)
        nxt = next_available(res, st_full, now)
        reason = cannot_run_reason(res, st_full, now)

        # 再取"池子空"的情形, 看多久能补回来
        st_empty = RunState(credits=0, refill_anchor=now)
        nxt_empty = next_available(res, st_empty, now)
        gap = nxt_empty - now

        rows.append({
            'task': meta.task,
            'name_zh': meta.name_zh,
            'category': meta.category.value,
            'refill': res.refill,
            'period': res.period.value,
            'capacity': res.capacity,
            'old_next': old_next,
            'new_next_full': nxt,
            'new_next_empty': nxt_empty,
            'gap_min': int(gap.total_seconds() // 60),
            'reason': reason,
        })

        # 健全性检查: 池子满 + 无时段限制时, 应该"现在就能跑"
        if res.capacity >= res.consume and not res.has_window and nxt != now:
            never_runnable.append((meta.task, nxt, reason))

    print('=' * 104)
    print(f'{"任务":<22}{"中文名":<12}{"类别":<9}{"补充":<9}{"周期":<7}'
          f'{"容量":<5}{"旧 next_run":<20}{"新:池满最早":<20}{"空池等待"}')
    print('=' * 104)
    for r in rows:
        old = str(r['old_next'])[:19] if r['old_next'] else '-'
        newf = f"{r['new_next_full']:%m-%d %H:%M}" if r['new_next_full'] else '-'
        gap = f"{r['gap_min']}分" if r['gap_min'] < 1440 else f"{r['gap_min']//1440}天"
        print(f'{r["task"]:<22}{str(r["name_zh"] or "?"):<12}{r["category"]:<9}'
              f'{r["refill"]:<9}{r["period"]:<7}{r["capacity"]:<5}'
              f'{old:<20}{newf:<20}{gap}')

    print()
    print('=' * 104)
    print('健全性检查:')
    print('=' * 104)
    if never_runnable:
        print('  !! 以下任务在"池子满且无时段限制"时仍未判定为现在可跑(可能是 bug):')
        for t, n, reason in never_runnable:
            print(f'     {t:<22} next={n}  reason={reason}')
    else:
        print('  ✓ 所有任务在"池子满 + 无时段限制"时均判定为现在可跑')

    # 有开放时段的任务
    win = [r for r in rows if r['reason'] and '开放时段' in str(r['reason'])]
    print()
    if win:
        print('  因"不在开放时段"而暂缓的任务:')
        for r in win:
            print(f'     {r["task"]:<22} {r["reason"]}')
    else:
        print('  (无任务配置了开放时段 —— 符合预期, 新字段默认关闭)')

    print()
    print(f'  统计: 已启用任务 {len(rows)} 个')
    from collections import Counter
    print(f'        补充方式 {dict(Counter(r["refill"] for r in rows))}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
