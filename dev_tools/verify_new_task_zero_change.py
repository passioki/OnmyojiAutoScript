# -*- coding: utf-8 -*-
"""验证「新增一个活动 = 只写 tasks/<New>/，零改动其它文件」是否真的成立。

方法: 临时造一个**假的新活动任务**(只写 meta.py)，看系统能否自动发现它 ——
不改 task_catalog_data.json、不改 config_model.py、不改 i18n。

验证点:
  1. 被 task_catalog 发现(出现在 all_tasks / all_meta)
  2. 拿到正确的中文名与类别
  3. 拿到资源规则
  4. 删除后不影响其它任务
"""
import os
import shutil
import sys
from pathlib import Path

from paths import oas_root  # noqa: E402  ★ 消除硬编码（见 paths.py）
REPO = oas_root()
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import logging                        # noqa: E402
logging.disable(logging.CRITICAL)

from module.config import task_catalog as TC   # noqa: E402
from module.config.task_catalog import Category  # noqa: E402

FAKE = 'ZZZDemoActivity'
DIR = REPO / 'tasks' / FAKE

META = '''# -*- coding: utf-8 -*-
"""演示: 新增一个游戏活动只需写这个文件。"""
from module.config.resource import Period
from module.config.task_catalog import Category, TaskSpec

SPEC = TaskSpec(
    task='ZZZDemoActivity',
    name_zh='演示新活动',
    category=Category.LIMITED,
    resource=Resource(capacity=1),
)
'''

fails = []


def chk(desc, ok, extra=''):
    print(f'  {"OK " if ok else "BAD"} {desc:<46} {extra}')
    if not ok:
        fails.append(desc)


before = set(TC.all_tasks())

try:
    print('=' * 92)
    print('步骤 1: 只创建一个 tasks/<New>/meta.py (不动任何中心文件)')
    print('=' * 92)
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / 'meta.py').write_text(META, encoding='utf-8')
    print(f'  已写入 {DIR.relative_to(REPO)}\\meta.py')
    print()

    TC.reload()
    TC.reload_specs()

    print('=' * 92)
    print('步骤 2: 系统是否自动发现它')
    print('=' * 92)
    after = set(TC.all_tasks())
    chk('出现在 all_tasks()', FAKE in after)
    chk('任务总数 +1', len(after) == len(before) + 1,
        f'{len(before)} -> {len(after)}')

    spec = TC.get_spec(FAKE)
    chk('get_spec 拿到 SPEC', spec is not None)
    if spec:
        chk('中文名正确', spec.name_zh == '演示新活动', spec.name_zh)
        chk('类别正确', spec.category == Category.LIMITED, spec.category.value)
        chk('资源规则正确',
            spec.resource is not None and spec.resource.refill == 'window')

    meta = TC.get(FAKE)
    chk('get() 拿到 TaskMeta', meta is not None)
    if meta:
        chk('TaskMeta 中文名来自 SPEC', meta.name_zh == '演示新活动', meta.name_zh)
        chk('TaskMeta 类别来自 SPEC', meta.category == Category.LIMITED,
            meta.category.value)

    chk('by_category(LIMITED) 包含它',
        FAKE in {m.task for m in TC.by_category(Category.LIMITED)})

finally:
    print()
    print('=' * 92)
    print('步骤 3: 清理并确认无残留')
    print('=' * 92)
    if DIR.exists():
        shutil.rmtree(DIR)
        print(f'  已删除 {DIR.relative_to(REPO)}')
    # 清掉可能生成的 __pycache__
    pc = DIR / '__pycache__'
    if pc.exists():
        shutil.rmtree(pc, ignore_errors=True)

    TC.reload()
    TC.reload_specs()
    restored = set(TC.all_tasks())
    chk('任务列表已还原', restored == before,
        f'{len(restored)} 个')
    chk('假任务已消失', FAKE not in restored)

print()
print('=' * 92)
if fails:
    print(f'*** {len(fails)} 项失败 ***')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('*** 全部通过 —— "新增活动零改动"成立 ***')
print('=' * 92)
print()
print('新增一个游戏活动的完整步骤:')
print('  1. 建 tasks/<New>/ 目录, 写 meta.py + config.py + script_task.py + assets.py')
print('  2. python dev_tools/assets_extract.py          # 生成素材')
print('  3. python dev_tools/gen_task_catalog.py --check  # 校验漏写')
print()
print('调度器 / 配置模型 / 前端 schema / i18n 会自动获得该任务。')
