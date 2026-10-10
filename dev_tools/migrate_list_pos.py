# -*- coding: utf-8 -*-
"""把 `ConfigManual.SCHEDULER_PRIORITY` 的顺序迁到各 `meta.py` 的 `list_pos`。

## 为什么

原先任务调度顺序**硬编码**在 `module/config/config_manual.py` 的
`SCHEDULER_PRIORITY` 常量里(形如 `Restart > SoulsTidy > KekkaiUtilize > ...`)。

用户**改不了**这个顺序。设计上任务列表应由用户编排(见 docs/architecture.md §5)。

迁移做法: 把这个默认顺序转成每个任务 `meta.py` 里的 `list_pos` ——
于是"默认顺序"落在**任务自己**的声明里(与其他元数据一致),
而用户在界面上拖拽后写入 `Script.optimization.task_order` 覆盖它。

## 安全

* 幂等: 已有 `list_pos` 的 meta.py 跳过(或 `--force` 覆盖)
* `--dry-run` 预览
* 不在默认清单里的任务 -> `list_pos` 留空(None), 排最后
"""
import os
import re
import sys
from pathlib import Path

from paths import oas_root  # noqa: E402  ★ 消除硬编码（见 paths.py）
REPO = oas_root()
os.chdir(REPO)
sys.path.insert(0, str(REPO))
import logging
logging.disable(logging.CRITICAL)

from module.config.config_manual import ConfigManual   # noqa: E402
from module.config import task_catalog as TC           # noqa: E402


def parse_priority(text: str) -> list:
    """把 'A > B > C' 解析成 ['A', 'B', 'C'](忽略换行与缩进)。"""
    out = []
    for part in re.split(r'[>\n]', text):
        part = part.strip()
        if part:
            out.append(part)
    return out


def main() -> int:
    dry = '--dry-run' in sys.argv
    force = '--force' in sys.argv

    order = parse_priority(ConfigManual.SCHEDULER_PRIORITY)
    known = set(TC.all_tasks())

    print('=' * 92)
    print(f'迁移 SCHEDULER_PRIORITY -> meta.py 的 list_pos'
          f'{"  (--dry-run)" if dry else ""}')
    print('=' * 92)
    print(f'  内置清单 {len(order)} 项; task_catalog {len(known)} 个任务')

    missing = [t for t in order if t not in known]
    not_listed = sorted(t for t in known if t not in order)
    if missing:
        print(f'  ⚠ 清单里有但 catalog 没有(可能已删/改名): {missing}')
    if not_listed:
        print(f'  ⚠ catalog 有但清单没有(将留空, 排最后): {not_listed}')
    print()

    pos = {name: i for i, name in enumerate(order)}
    changed, skipped = [], []

    for meta in TC.all_meta():
        task = meta.task
        f = REPO / 'tasks' / task / 'meta.py'
        if not f.exists():
            skipped.append(f'{task}(无 meta.py)')
            continue
        text = f.read_text(encoding='utf-8')
        if 'list_pos=' in text and not force:
            skipped.append(f'{task}(已有)')
            continue

        want = pos.get(task)
        if want is None:
            skipped.append(f'{task}(不在清单)')
            continue

        # 去掉已有的 list_pos 行
        text = re.sub(r'\n\s*list_pos=\d+,', '', text)
        # 插到 category= 之后(保持字段顺序可读)
        m = re.search(r'(\n(\s*)category=Category\.\w+,)', text)
        if not m:
            skipped.append(f'{task}(找不到插入点)')
            continue
        indent = m.group(2)
        text = (text[:m.end()]
                + f'\n{indent}list_pos={want},'
                + text[m.end():])

        if not dry:
            f.write_text(text, encoding='utf-8')
        changed.append((task, want))

    for task, want in changed:
        print(f'  + {task:<24} list_pos={want}')
    if skipped:
        print()
        print(f'  跳过 {len(skipped)} 个: {skipped[:8]}'
              + (' ...' if len(skipped) > 8 else ''))
    print()
    print(f'  合计: 写入 {len(changed)}, 跳过 {len(skipped)}')
    if dry:
        print('  (预览模式, 未写入)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
