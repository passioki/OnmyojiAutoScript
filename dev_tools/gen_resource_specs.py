# -*- coding: utf-8 -*-
"""生成 `Resource` 定义 —— 每个任务的"资源规则"。

**这是把游戏知识从 54 个配置界面收归一处的那一步。**

旧状态: "多久能跑一次"散在 `success_interval` / `charge_slots` / `charge_max` /
`charge_consume` / `limit_count` 五个字段里, 且每个任务用哪些字段还不一样。
新状态: 每个任务一条 `Resource`, 三种形态覆盖全部。

形态判定依据(实测, 不靠猜):
  slots   有 charge_slots           -> 金币妖怪/经验妖怪/石距
  limited 分类为 limited 且无 slots -> 限时活动(活动期才跑, 无法用时间表达)
  period  其余全部                   -> "每周期补满 N 次"

period 形态的 `capacity` 与 `period` 从何而来:
  capacity  <- 有目标次数的任务取 count_default(如日轮 50);
               没有的取 1(表示"一次运行即打满")
  period    <- 旧 success_interval 的语义: 1天 -> daily, 7天 -> weekly,
               其余(3h/12h/6h 等) -> daily 但带 slots 式补充

输出: dev_tools/data/resource_specs.json (供 TaskSpec 使用, 也是人工核对表)
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(r'D:\OAS-dev\OnmyojiAutoScript')
OUT = REPO / 'dev_tools' / 'data' / 'resource_specs.json'

sys.path.insert(0, str(REPO))
import os
os.chdir(REPO)

from module.config import task_catalog as TC  # noqa: E402
from module.config.task_catalog import Category  # noqa: E402

# 手工核定: 这些任务的"周期"无法从 success_interval 推出, 依据游戏规则。
# 每一条都注明理由, 便于以后核对。
PERIOD_OVERRIDE = {
    # 真蛇: 每周 2 次挑战机会(用户确认)
    'TrueOrochi': dict(period='weekly', capacity=2),
    # 秘闻副本: 每周一次(默认 interval 7 天)
    'Secret': dict(period='weekly', capacity=1),
    # 每周琐事: 每周一次
    'WeeklyTrifles': dict(period='weekly', capacity=1),
    # 伪神(活动期): 按活动周期, 无法用固定 period 表达 -> 见 LIMITED
    # 金币/经验/石距: slots 形态, 见下
}

# 手工核定: slots 形态的补充时刻与容量(来源: 任务 config.py 的 charge_slots 等)
SLOTS_OVERRIDE = {
    'GoldYoukai': dict(slots=((0, 0), (12, 0)), amount=1, capacity=2, consume=1),
    'ExperienceYoukai': dict(slots=((0, 0), (12, 0)), amount=1, capacity=2, consume=1),
    'Tako': dict(slots=((0, 0), (12, 0)), amount=1, capacity=2, consume=1),
}


def parse_interval(s: str):
    """把 '00 03:00:00' 解析成 (days, hours, minutes)。"""
    if not s:
        return None
    m = re.match(r'(\d+)\s+(\d+):(\d+):(\d+)', str(s).strip())
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r'(\d+):(\d+):(\d+)', str(s).strip())
    if m:
        return 0, int(m.group(1)), int(m.group(2))
    return None


def infer_period(interval):
    """从 success_interval 推断 period 形态。"""
    p = parse_interval(interval)
    if p is None:
        return 'daily'
    days, hours, _ = p
    if days >= 7:
        return 'weekly'
    return 'daily'


rows = []
for meta in TC.all_meta():
    task = meta.task
    cat = meta.category

    if cat == Category.LIMITED:
        kind = 'window'
        res = {'kind': 'window'}
    elif task in SLOTS_OVERRIDE:
        kind = 'slots'
        res = {'kind': 'slots', **SLOTS_OVERRIDE[task]}
    else:
        kind = 'period'
        if task in PERIOD_OVERRIDE:
            res = {'kind': 'period', **PERIOD_OVERRIDE[task]}
        else:
            capacity = meta.count_default if meta.countable and meta.count_default else 1
            res = {
                'kind': 'period',
                'period': infer_period(meta.success_interval),
                'capacity': capacity,
            }

    rows.append({
        'task': task,
        'name_zh': meta.name_zh,
        'category': cat.value,
        'resource': res,
        # 溯源: 这几个字段解释了 res 是怎么来的
        '_source': {
            'count_field': meta.count_field,
            'count_default': meta.count_default,
            'success_interval': meta.success_interval,
            'charge_slots': meta.charge_slots,
            'charge_max': meta.charge_max,
            'charge_consume': meta.charge_consume,
        },
    })

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

# ---------------------------------------------------------------- 报告
from collections import Counter
print(f'已写出 {OUT.relative_to(REPO)}  ({len(rows)} 个任务)')
print()
print('形态分布:', dict(Counter(r['resource']['kind'] for r in rows)))
print()

print('=' * 104)
print(f'{"任务":<22}{"中文名":<12}{"类别":<9}{"形态":<9}{"参数"}')
print('=' * 104)
for r in rows:
    res = r['resource']
    if res['kind'] == 'period':
        params = f"period={res['period']} capacity={res['capacity']}"
    elif res['kind'] == 'slots':
        params = f"slots={res['slots']} amount={res['amount']} cap={res['capacity']} consume={res['consume']}"
    else:
        params = '活动期判定由探针提供'
    print(f'{r["task"]:<22}{str(r["name_zh"] or "?"):<12}{r["category"]:<9}{res["kind"]:<9}{params}')

print()
print('=' * 104)
print('需要人工确认的点:')
print('=' * 104)
# period 形态且 interval 既不是 1 天也不是 7 天 -> capacity 推断可能不准
suspect = []
for r in rows:
    res, src = r['resource'], r['_source']
    if res['kind'] != 'period':
        continue
    iv = src['success_interval']
    p = parse_interval(iv)
    if p is None:
        continue
    days, hours, _ = p
    # interval 不是整天/整周, 但被归为 period(意味着"每天补 N 次"语义可疑)
    if hours != 0 and days == 0:
        suspect.append((r['task'], iv, res))
for t, iv, res in suspect:
    print(f'  {t:<22} interval={iv} -> {res}   (小时级间隔离散: 确认是否该用 slots?)')
if not suspect:
    print('  无')

print()
print('weekly 的任务:')
for r in rows:
    if r['resource'].get('period') == 'weekly':
        print(f"  {r['task']:<22} capacity={r['resource']['capacity']}  (interval={r['_source']['success_interval']})")
