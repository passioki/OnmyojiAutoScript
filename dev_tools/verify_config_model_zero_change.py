# -*- coding: utf-8 -*-
"""端到端验证: 新增一个任务**无需改动 `config_model.py`**。

## 验证什么

之前新增一个游戏活动, 必须在 `config_model.py` 里加两处:
    from tasks.<New>.config import <New>          # 1 行 import
    new_task: <New> = Field(default_factory=<New>) # 1 行字段

漏掉任何一处的后果是**静默的**: 任务不报错, 只是配置里读不到它。

现在改为自动发现。本脚本临时造一个完整的新任务(meta.py + config.py),
验证它能否自动进入 `ConfigModel` —— **且全程不改 config_model.py**。

## 与 verify_new_task_zero_change.py 的区别

那个验证的是 `task_catalog`(元数据层)的自动发现; 本脚本验证的是
`ConfigModel`(配置模型层)的自动发现。两层都自动, "零改动"才真正成立。
"""
import importlib
import json
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

FAKE = 'ZZZDemoNewTask'
DIR = REPO / 'tasks' / FAKE
# 注意: `convert_to_underscore('ZZZDemoNewTask')` = 'zzz_demo_new_task'
# (连续大写被视为一个词, 不会拆成 z_z_z_)。这里直接调用它, 避免手写猜错。
from module.config.utils import convert_to_underscore  # noqa: E402
KEY = convert_to_underscore(FAKE)

fails = []


def chk(desc, ok, extra=''):
    print(f'  {"OK " if ok else "BAD"} {desc:<48} {extra}')
    if not ok:
        fails.append(desc)


CONFIG_PY = '''# -*- coding: utf-8 -*-
"""演示: 新增任务的配置模型。"""
from pydantic import Field

from tasks.Component.config_base import ConfigBase, TimeDelta
from tasks.Component.config_scheduler import Scheduler


class ZZZDemoNewTask(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    limit_count: int = Field(default=7, description='limit_count_help')
'''

META_PY = '''# -*- coding: utf-8 -*-
"""演示: 新增任务的自描述。"""
from module.config.resource import Period
from module.config.task_catalog import Category, TaskSpec

SPEC = TaskSpec(
    task='ZZZDemoNewTask',
    name_zh='演示新任务',
    category=Category.FIXED,
    resource=Resource(capacity=7),
)
'''

# 记录改动前的 config_model.py 内容, 用于证明"没动它"
CM = REPO / 'module' / 'config' / 'config_model.py'
cm_before = CM.read_bytes()

try:
    print('=' * 92)
    print('步骤 1: 只创建 tasks/<New>/{meta,config}.py (不动 config_model.py)')
    print('=' * 92)
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / 'config.py').write_text(CONFIG_PY, encoding='utf-8')
    (DIR / 'meta.py').write_text(META_PY, encoding='utf-8')
    print(f'  已写入 {DIR.relative_to(REPO)}/config.py')
    print(f'  已写入 {DIR.relative_to(REPO)}/meta.py')
    print()

    print('=' * 92)
    print('步骤 2: config_model.py 是否真的没动')
    print('=' * 92)
    chk('config_model.py 字节未变', CM.read_bytes() == cm_before)
    print()

    print('=' * 92)
    print('步骤 3: 重新导入 ConfigModel, 看是否自动包含新任务')
    print('=' * 92)
    # 清掉已导入的模块缓存, 让发现逻辑重新跑
    for name in list(sys.modules):
        if (name.startswith('module.config.config_model')
                or name.startswith(f'tasks.{FAKE}')):
            del sys.modules[name]

    from module.config.config_model import ConfigModel
    keys = set(ConfigModel.__annotations__)
    chk('新任务字段自动出现', KEY in keys,
        f'字段总数 {len(keys)}')
    if KEY in keys:
        cls = ConfigModel.__annotations__[KEY]
        chk('字段类型正确',
            str(cls).split('.')[-1].rstrip("']>") == FAKE,
            str(cls))
        inst = ConfigModel()
        obj = getattr(inst, KEY, None)
        chk('实例可访问', obj is not None, type(obj).__name__)
        if obj is not None:
            chk('默认值生效', obj.limit_count == 7, str(obj.limit_count))
            chk('scheduler 子模型存在', obj.scheduler is not None)
        chk('type() 可解析',
            ConfigModel.type(KEY) == FAKE, ConfigModel.type(KEY))

    print()
    print('=' * 92)
    print('步骤 4: 元数据层也自动发现(task_catalog)')
    print('=' * 92)
    from module.config import task_catalog as TC
    TC.reload()
    TC.reload_specs()
    chk('出现在 all_tasks()', FAKE in TC.all_tasks())
    spec = TC.get_spec(FAKE)
    chk('get_spec 拿到 SPEC', spec is not None)
    if spec:
        chk('中文名正确', spec.name_zh == '演示新任务', spec.name_zh)

finally:
    print()
    print('=' * 92)
    print('步骤 5: 清理并确认还原')
    print('=' * 92)
    if DIR.exists():
        shutil.rmtree(DIR)
        print(f'  已删除 {DIR.relative_to(REPO)}')
    for name in list(sys.modules):
        if name.startswith(f'tasks.{FAKE}'):
            del sys.modules[name]

    CM.write_bytes(cm_before)   # 保险: 内容本就未变
    chk('config_model.py 仍与初始一致', CM.read_bytes() == cm_before)

    for name in list(sys.modules):
        if name.startswith('module.config.config_model'):
            del sys.modules[name]

print()
print('=' * 92)
if fails:
    print(f'*** {len(fails)} 项失败 ***')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('*** 全部通过 —— 新增任务无需改动 config_model.py ***')
print('=' * 92)
print()
print('两层自动发现:')
print('  * task_catalog   扫描 tasks/*/meta.py   -> 名称/类别/资源规则')
print('  * ConfigModel    扫描 tasks/*/config.py -> 配置字段')
print()
print('因此"新增活动 = 只写 tasks/<New>/"在配置层与元数据层都成立。')
