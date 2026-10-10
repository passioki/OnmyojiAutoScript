# -*- coding: utf-8 -*-
"""任务自描述 —— `DemonEncounter` (逢魔之时).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/DemonEncounter/` 目录, 写本文件 + config.py + script_task.py + assets.py
  2. `python dev_tools/assets_extract.py` 生成素材
  3. `python dev_tools/gen_task_catalog.py --check` 校验漏写

调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务, 无需改动任何中心文件。

规范见 `docs/architecture.md` §7(可演进性)。

类别依据: 定时任务: 按周期调度
"""
from datetime import time
from module.config.availability import AvailabilityWindow
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='DemonEncounter',
    name_zh='逢魔之时',
    category=Category.TIMED,
    # 定时类自动进队列 / 次数类需【添加任务】（见 architecture.md §3.5）
    auto_queue=True,
    # ★ 逢魔之时的**开放时段**（台账 9.6 一直记录着, 现在终于落进 meta.py）。
    #
    # 依据是**任务代码本身**（`script_task.py` 的 `check_time()`）:
    #
    #     if now.hour < 17:   -> set_next_run(target=当天 17:30)   太早
    #     elif now.hour >= 23: -> set_next_run(target=次日 17:30)  太晚
    #     else: return True                                        可以跑
    #
    # 即 **每天 17:00–23:00**。
    #
    # ⚠ `check_time()` 的 docstring 写的是"17:00到22:00" —— 那是**过时注释**,
    #   代码实际用的是 23。**以代码为准**（已核对 L647 / L653）。
    #
    # ★ 这里**不删** `check_time()`: 它用 `set_next_run(target=...)`（**新机制**,
    #   不是 `custom_next_run`）, 且语义是"太早/太晚时把本次运行推后",
    #   与窗口是**互补**的（窗口管"允不允许", 它管"这次具体什么时候")。
    #   加上窗口后 `_align_to_window()` 会把 `next_run` 收进 17:00–23:00,
    #   与 `check_time()` 的 17:30 目标一致, **不冲突**。
    window=AvailabilityWindow(True, time(17, 0), time(23, 0)),
    list_pos=4,
    period=Period.NONE,
)
