# -*- coding: utf-8 -*-
"""任务自描述 —— `FrogBoss` (对弈竞猜).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/FrogBoss/` 目录, 写本文件 + config.py + script_task.py + assets.py
  2. `python dev_tools/assets_extract.py` 生成素材
  3. `python dev_tools/gen_task_catalog.py --check` 校验漏写

调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务, 无需改动任何中心文件。

规范见 `docs/architecture.md` §7(可演进性)。

类别依据: 限时活动: 隔一段时间才推出, 非常驻
"""
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='FrogBoss',
    name_zh='对弈竞猜',
    category=Category.LIMITED,
    # ★★★ 废弃（片 4 / W-a，用户裁定）★★★
    #
    # 对弈竞猜的 `before_end_frog` 无法用 window start 表达：
    #   `script_task.py:156-166` 用它算「活动结束前的相对时刻」——
    #   同样是**相对偏移量**，不是偏好时刻。
    #   ★ 用户裁定: 标为废弃不可启用，留待删除或适配。
    deprecated=("FrogBoss 因字段语义冲突被标记为废弃，留待删除或适配。详见本文件上方的说明与 DEV-SCHEDULER-UNIFY-PLAN.md 的 W-a 审计。"),
    # 定时类自动进队列 / 次数类需【添加任务】（见 architecture.md §3.5）
    auto_queue=True,
    list_pos=48,
    period=Period.DAILY,
)
