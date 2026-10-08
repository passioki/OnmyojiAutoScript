# -*- coding: utf-8 -*-
"""为 54 个任务生成 `Resource` 定义（"能跑几次 / 什么时候允许跑"的规则）。

## 这个脚本的定位

**分类逻辑只存在一处** —— 全部委托给 `Resource.from_legacy()`，本脚本只负责：
  1. 从 `task_catalog` 取各任务的原始字段
  2. 套用**无法从代码推导**的游戏知识（`PERIOD_OVERRIDE`）
  3. 输出 JSON 供人工核对

★ 为什么强调"只存在一处"：早期版本本脚本自己写了一套分类判定，与
`Resource.from_legacy` 不一致，导致 **6 个任务的"小时级间隔"被错归为 `period`**，
丢掉了"每 3 小时/6 小时"的信息。这是"知识存在两处"的典型代价。

## 关于开放时段（window）

**本脚本不填任何开放时段。** 理由见 `docs/architecture.md` §3.0 与 §8：

* 开放时段是**游戏机制**，而代码里没有这份数据（`success_interval` 是用户
  为了绕过"不确定何时开放"而设的轮询节奏，**不能当游戏机制读**）
* 用户明确要求：**不写死时间段**、**全部开放出来由用户配置**
* 因此时段由用户在配置界面填写，默认"不限时段"
* 软件通过 `ObservedWindow` **自学习**实际时段并给出提示

输出: `dev_tools/data/resource_specs.json`
"""
import dataclasses
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / 'dev_tools' / 'data' / 'resource_specs.json'

sys.path.insert(0, str(REPO))
os.chdir(REPO)

from module.config import task_catalog as TC                        # noqa: E402
from module.config.resource import Period, Recharge, Resource       # noqa: E402


# --------------------------------------------------------------------------- 手工核定
# 只放**无法从现有代码字段推导**的游戏知识。每条注明依据。
# 能推导的一律交给 from_legacy —— 避免两处逻辑不一致。
#
# `Resource` 的 `recharge` 是嵌套 dataclass, 故 override 要整块替换 Recharge。
PERIOD_OVERRIDE = {
    # 真八岐大蛇: 每周 2 次挑战机会(用户确认)。
    # 现有配置只有 success_interval=3天, 推导不出"每周2次", 故手工核定。
    'TrueOrochi': {
        'capacity': 2,
        'recharge': Recharge(period=Period.WEEKLY, amount=2),
    },
}


def _dump(res: Resource) -> dict:
    """把 Resource 序列化成可读 JSON(供人工核对与前端展示)。"""
    out = {
        'capacity': res.capacity,
        'consume': res.consume,
        'refill': res.refill,
        'period': res.period.value,
        'amount': res.amount,
    }
    if res.refill == 'interval':
        d, h, mi = res.interval
        out['interval'] = {'days': d, 'hours': h, 'minutes': mi}
        out['interval_text'] = (f'{d}天' if d else '') + \
                               (f'{h}小时' if h else '') + \
                               (f'{mi}分' if mi else '')
    if res.refill == 'slots':
        out['slots'] = [f'{h:02d}:{m:02d}' for h, m in res.slots]
    if res.has_window:
        out['window'] = {
            'start': f'{res.window.start:%H:%M}',
            'end': f'{res.window.end:%H:%M}',
            'days': list(res.window.days),
        }
    return out


def _describe_override(override: dict) -> dict:
    """把手工核定转成可 JSON 序列化的描述(Recharge 不是 JSON 友好的)。"""
    out = {}
    for k, v in override.items():
        if isinstance(v, Recharge):
            out[k] = {'kind': v.kind, 'period': v.period.value,
                      'amount': v.amount}
        elif isinstance(v, Period):
            out[k] = v.value
        else:
            out[k] = v
    return out


def _interval_parts(s):
    """'01 00:00:00' -> (days, hours, minutes)；解析失败返回 None。"""
    if not s:
        return None
    m = re.match(r'(\d+)\s+(\d+):(\d+):(\d+)', str(s).strip())
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r'(\d+):(\d+):(\d+)', str(s).strip())
    if m:
        return 0, int(m.group(1)), int(m.group(2))
    return None


def main() -> int:
    rows = []
    for meta in TC.all_meta():
        # 统一走 from_legacy —— 分类逻辑只存在一处
        res = Resource.from_legacy(
            success_interval=meta.success_interval,
            charge_slots=meta.charge_slots,
            charge_max=meta.charge_max,
            charge_consume=meta.charge_consume,
            count_default=meta.count_default,
            category=meta.category.value,
        )
        override = PERIOD_OVERRIDE.get(meta.task, {})
        if override:
            res = dataclasses.replace(res, **override)

        rows.append({
            'task': meta.task,
            'name_zh': meta.name_zh,
            'category': meta.category.value,
            'resource': _dump(res),
            # 溯源: 解释这个 resource 是怎么推导出来的, 便于人工核对
            '_source': {
                'count_field': meta.count_field,
                'count_default': meta.count_default,
                'success_interval': meta.success_interval,
                'charge_slots': meta.charge_slots,
                'charge_max': meta.charge_max,
                'manual_override': (_describe_override(override)
                                    if override else None),
            },
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')

    # ------------------------------------------------------------------ 报告
    from collections import Counter
    print(f'已写出 {OUT.relative_to(REPO)}  ({len(rows)} 个任务)')
    print()
    print('补充方式分布:', dict(Counter(r['resource']['refill'] for r in rows)))
    print()

    print('=' * 110)
    print(f'{"任务":<22}{"中文名":<12}{"类别":<9}{"补充方式":<10}{"周期":<8}'
          f'{"容量":<5}{"参数"}')
    print('=' * 110)
    for r in rows:
        res = r['resource']
        if res.get('interval_text'):
            params = res['interval_text']
        elif res.get('slots'):
            params = '时刻 ' + ', '.join(res['slots'])
        else:
            params = ''
        print(f'{r["task"]:<22}{str(r["name_zh"] or "?"):<12}{r["category"]:<9}'
              f'{res["refill"]:<10}{res.get("period", ""):<8}'
              f'{res["capacity"]:<5}{params}')

    # ------------------------------------------------------------------ 核对提示
    print()
    print('=' * 110)
    print('需人工核对的点:')
    print('=' * 110)

    # 1) 被归为"周期"但原始 interval 是小时级 -> 可能丢信息(这是曾经的 bug)
    suspect = []
    for r in rows:
        res, src = r['resource'], r['_source']
        if res['refill'] != 'none':
            continue
        parts = _interval_parts(src['success_interval'])
        if not parts:
            continue
        days, hours, _ = parts
        if hours != 0 and days == 0:
            suspect.append((r['task'], src['success_interval'], res['period']))
    if suspect:
        for t, iv, per in suspect:
            print(f'  ⚠ {t:<22} interval={iv} 被归为 period={per} —— 可能丢信息')
    else:
        print('  ✓ 无"小时级间隔被误归为周期"的情况')

    # 2) 手工核定的任务 -> 这些是人工判断, 需复核
    print()
    manual = [(r['task'], r['_source']['manual_override']) for r in rows
              if r['_source'].get('manual_override')]
    if manual:
        print('  手工核定的任务(依据不可从代码推导, 请复核):')
        for t, ov in manual:
            print(f'    {t:<22} {ov}')
    else:
        print('  无手工核定')

    # 3) 开放时段: 本脚本一个都不填
    print()
    print(f'  开放时段: 本脚本**不填任何时段**(共 {len(rows)} 个任务均未设置)')
    print('    理由: 时段是游戏机制, 代码里没有这份数据;')
    print('          且用户要求"不写死时间段、全部开放出来由用户配置"。')
    print('    由用户在配置界面填写, 默认"不限时段";')
    print('    软件通过 ObservedWindow 自学习实际时段并提示。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
