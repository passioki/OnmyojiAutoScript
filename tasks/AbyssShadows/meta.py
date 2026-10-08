# -*- coding: utf-8 -*-
"""任务自描述 —— `AbyssShadows` (狭间暗域).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/AbyssShadows/` 目录, 写本文件 + config.py + script_task.py + assets.py
  2. `python dev_tools/assets_extract.py` 生成素材
  3. `python dev_tools/gen_task_catalog.py --check` 校验漏写

调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务, 无需改动任何中心文件。

规范见 `docs/architecture.md` §7(可演进性)。

类别依据: 定时任务: 按周期调度
"""
from module.config.resource import Period, Recharge, Resource  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='AbyssShadows',
    name_zh='狭间暗域',
    category=Category.TIMED,
    list_pos=16,
    resource=Resource(capacity=1, recharge=Recharge(kind='none', period=Period.DAILY)),
)
