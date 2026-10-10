# -*- coding: utf-8 -*-
"""任务自描述 —— `RealmRaid` (个人突破).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/RealmRaid/` 目录, 写本文件 + config.py + script_task.py + assets.py
  2. `python dev_tools/assets_extract.py` 生成素材
  3. `python dev_tools/gen_task_catalog.py --check` 校验漏写

调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务, 无需改动任何中心文件。

规范见 `docs/architecture.md` §7(可演进性)。

类别依据: 结界突破: 定点开放 + 次数上限
"""
from datetime import time
from module.config.availability import AvailabilityWindow
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='RealmRaid',
    name_zh='个人突破',
    category=Category.TOPPA,
    # 定时类自动进队列 / 次数类需【添加任务】（见 architecture.md §3.5）
    auto_queue=False,
    # ★ F2c: 显式声明开放时段（用户: "所有的定时都有着 window 属性"）。
    #
    # 目前是**整天** —— 与"未声明"在行为上**完全等价**（`contains()` 都恒 True）,
    # 所以这是**纯声明**, 不改变任何既有行为。
    #
    # ⚠ 但**不是**"没有时段": 它让"这个任务有 window"这件事**可见**
    #   （`dev_tools/check_windows.py` 会核对）。
    #   若该玩法有**真实游戏时段**, 应把它收窄成实际的起止时刻 ——
    #   那属于**行为变更**, 需要按机制核实后再改。
    window=AvailabilityWindow(True, time(0, 0), time(23, 59)),
    list_pos=11,
    period=Period.NONE,
)
