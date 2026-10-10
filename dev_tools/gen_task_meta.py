# -*- coding: utf-8 -*-
"""为 54 个任务批量生成 `tasks/<Name>/meta.py` —— 任务自描述。

## 为什么要生成而不是手写

任务自描述的目标是"**新增活动只写 `tasks/<New>/`，零改动其它文件**"。
但现有 54 个任务都没有 `meta.py`，手写 54 个文件既慢又容易抄错。
因此用本脚本从**已实测的权威数据**批量生成一次，之后由维护者按需手改。

数据来源(与 `task_catalog` 一致, 不另造一套):
  * 中文名 / 类别 -> `module/config/task_catalog.py`(源自 OASX i18n + 本轮实测)
  * 资源规则     -> `dev_tools/data/resource_specs.json`(由 gen_resource_specs 生成)

## 生成的 meta.py 长什么样

    from module.config.resource import Period
    from module.config.task_catalog import Category, TaskSpec

    SPEC = TaskSpec(
        task='FallenSun',
        name_zh='日轮之陨',
        category=Category.FIXED,
    )

## 幂等与安全

* **默认不覆盖已存在的 meta.py**(可能有手工修改) —— 需要覆盖时加 `--force`
* `--dry-run` 只列出将要写入的文件

用法:
    python dev_tools/gen_task_meta.py --dry-run
    python dev_tools/gen_task_meta.py
    python dev_tools/gen_task_meta.py --force     # 覆盖已有
"""
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / 'tasks'
SPECS_FILE = REPO / 'dev_tools' / 'data' / 'resource_specs.json'

sys.path.insert(0, str(REPO))
os.chdir(REPO)

import logging                        # noqa: E402
logging.disable(logging.CRITICAL)

from module.config import task_catalog as TC   # noqa: E402
from module.config.task_catalog import Category  # noqa: E402

# 类别 -> 判定依据说明(写进生成文件的注释, 便于维护者理解为什么是这个类别)
CATEGORY_NOTE = {
    Category.FIXED: '固定任务: 有"打满 N 次"的语义',
    Category.TOPPA: '结界突破: 定点开放 + 次数上限',
    Category.LIMITED: '限时活动: 隔一段时间才推出, 非常驻',
    Category.TIMED: '定时任务: 按周期调度',
}

HEADER = '''# -*- coding: utf-8 -*-
"""任务自描述 —— `{task}` ({name_zh}).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/{task}/` 目录, 写本文件 + config.py + script_task.py + assets.py
  2. `python dev_tools/assets_extract.py` 生成素材
  3. `python dev_tools/gen_task_catalog.py --check` 校验漏写

调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务, 无需改动任何中心文件。

规范见 `docs/architecture.md` §7(可演进性)。

类别依据: {category_note}
"""
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task={task!r},
    name_zh={name_zh!r},
    category=Category.{category_upper},
{list_pos_block}{requires_block}{note_block}    period={resource_expr},
)
'''


def resource_expr(res: dict) -> str:
    """把 `resource_specs.json` 里的一条转成 **`period=`** 表达式。

    ## ★★ S5: `Resource(...)` 已删除 ★★

    用户裁定: "去掉组队协同，去掉存量次数" + "连 `charge_*` 字段和存量逻辑一起删"。

    原来这里生成 `resource=Resource(capacity=..., recharge=Recharge(...))`
    —— `Resource` / `Recharge` 已删, 所以改成只生成**唯一还有意义的**
    `period=Period.XXX`（`TaskSpec.period` 在用）。

    ★ 容量 / 补充时刻 / 每次消耗这些**存量概念**已在窗口机制里消失,
      所以这些参数**直接丢弃**（不再有对应的字段）。
    """
    period = res.get('period', 'none')
    if period == 'none':
        return ''
    return f'Period.{period.upper()}'


def main() -> int:
    dry = '--dry-run' in sys.argv
    force = '--force' in sys.argv

    if not SPECS_FILE.exists():
        print(f'缺少 {SPECS_FILE.relative_to(REPO)}')
        print('请先运行: python dev_tools/gen_resource_specs.py')
        return 1

    specs = {r['task']: r for r in json.loads(
        SPECS_FILE.read_text(encoding='utf-8'))}

    written, skipped, missing = [], [], []
    for meta in TC.all_meta():
        task = meta.task
        d = OUT_DIR / task
        if not d.is_dir():
            missing.append(task)
            continue
        target = d / 'meta.py'
        if target.exists() and not force:
            skipped.append(task)
            continue

        spec = specs.get(task)
        if not spec:
            missing.append(task)
            continue

        # 保留 meta.py 里已有的 list_pos(用户可编排的默认顺序)
        list_pos = None
        if target.exists():
            m = re.search(r'^\s*list_pos=(\d+),', target.read_text(encoding='utf-8'),
                          re.M)
            if m:
                list_pos = int(m.group(1))
        if list_pos is None:
            existing = TC.get_spec(task)
            list_pos = getattr(existing, 'list_pos', None) if existing else None

        content = HEADER.format(
            task=task,
            name_zh=meta.name_zh or task,
            category_note=CATEGORY_NOTE.get(meta.category, ''),
            category_upper=meta.category.name,
            resource_expr=resource_expr(spec['resource']),
            # 保留已有的 list_pos —— 它是**用户可编排的默认顺序**,
            # 重新生成时不能丢(否则用户拖拽过的列表会被重置)。
            list_pos_block=(f'    list_pos={list_pos},\n'
                            if list_pos is not None else ''),
            requires_block='',
            note_block='',
        )
        if dry:
            written.append(f'{target.relative_to(REPO)}  ({len(content)} 字节)')
            continue
        target.write_text(content, encoding='utf-8')
        written.append(f'{target.relative_to(REPO)}')

    print('=' * 92)
    print(f'生成 tasks/<Name>/meta.py {"(--dry-run)" if dry else ""}'
          f'{"  --force 覆盖已有" if force else ""}')
    print('=' * 92)
    for line in written:
        print(f'  + {line}')
    if skipped:
        print()
        print(f'  跳过(已存在, 未加 --force): {len(skipped)} 个')
        for t in skipped[:8]:
            print(f'      {t}')
        if len(skipped) > 8:
            print(f'      ... 共 {len(skipped)} 个')
    if missing:
        print()
        print(f'  !! 缺数据或目录不存在: {missing}')

    print()
    print(f'  合计: 写入 {len(written)}, 跳过 {len(skipped)}, 异常 {len(missing)}')
    if dry:
        print('  (预览模式, 未实际写入)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
