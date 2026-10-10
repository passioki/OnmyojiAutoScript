# -*- coding: utf-8 -*-
"""任务自描述 —— `FindJade` (寻找协作任务).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/FindJade/` 目录, 写本文件 + config.py + script_task.py + assets.py
  2. `python dev_tools/assets_extract.py` 生成素材
  3. `python dev_tools/gen_task_catalog.py --check` 校验漏写

调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务, 无需改动任何中心文件。

规范见 `docs/architecture.md` §7(可演进性)。

类别依据: 定时任务: 按周期调度
"""
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='FindJade',
    name_zh='寻找协作任务',
    category=Category.TIMED,
    # 定时类自动进队列 / 次数类需【添加任务】（见 architecture.md §3.5）
    auto_queue=True,
    period=Period.DAILY,
)
