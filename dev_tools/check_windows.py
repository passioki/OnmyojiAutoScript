# -*- coding: utf-8 -*-
"""F2c: 校验 54 个任务的窗口是否齐备 —— **让缺失可见**。

## 为什么需要这个脚本

用户明确要求:

> "所有的定时都有着 window 属性"
> "我顺便发现了很多定时任务没有开放 window 和周期的设置"

如果"没写 window"只是静默地退化成"不限时段", 就**永远看不出有没有漏** ——
这正是本项目反复出现的"静默降级"缺陷模式。

所以: 每个任务都应有**可推导或显式声明**的窗口; 没有的**列出来并报错**。

## 用法

    python dev_tools/check_windows.py          # 列出缺失, 有缺失则 exit 1
    python dev_tools/check_windows.py --quiet   # 只输出结论
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from module.config import task_catalog as TC  # noqa: E402


def audit() -> dict:
    """返回 {'total', 'declared', 'derived', 'missing': [(task, period, category)]}。"""
    specs = TC._load_specs()
    declared, derived, missing = [], [], []
    for task, spec in sorted(specs.items()):
        if spec.declared_window is not None:
            declared.append(task)
            continue
        real = [w for w in spec.windows_effective if w.enabled]
        if real:
            derived.append(task)
        else:
            missing.append((task, spec.period_effective, str(spec.category)))
    return {
        'total': len(specs),
        'declared': declared,
        'derived': derived,
        'missing': missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='校验任务窗口齐备性')
    ap.add_argument('--quiet', action='store_true', help='只输出结论')
    args = ap.parse_args()

    r = audit()
    if not args.quiet:
        print(f'任务总数: {r["total"]}')
        print(f'  显式声明 window : {len(r["declared"])}')
        print(f'  由周期推导      : {len(r["derived"])}')
        print(f'  **缺失**        : {len(r["missing"])}')
        if r['missing']:
            print()
            print('以下任务**没有**开放时段（既没显式声明, 也无法由周期推导）:')
            print(f'  {"任务":<24}{"period":<12}category')
            for task, period, cat in r['missing']:
                p = getattr(period, 'value', period)
                print(f'  {task:<24}{str(p):<12}{cat}')
            print()
            print('修法（二选一）:')
            print('  a) 在 tasks/<Name>/meta.py 里显式写 '
                  'window=AvailabilityWindow(...)')
            print('  b) 给它的 Resource.recharge 设 period=Period.DAILY/WEEKLY/MONTHLY')
            print('     （用户: "所有的定时都有着 window 属性"）')

    if r['missing']:
        print(f'\nFAIL: {len(r["missing"])} 个任务缺 window')
        return 1
    print(f'\nOK: 全部 {r["total"]} 个任务都有窗口')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
