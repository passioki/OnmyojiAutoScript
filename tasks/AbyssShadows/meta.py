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
from datetime import time
from module.config.availability import AvailabilityWindow
from module.config.resource import Period, Recharge, Resource  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='AbyssShadows',
    name_zh='狭间暗域',
    category=Category.TIMED,
    # 定时类自动进队列 / 次数类需【添加任务】（见 architecture.md §3.5）
    auto_queue=True,
    # ★ 游戏实际开放 周五六日 **19:00-19:15**。
    #
    #   这里给到 **20:00** 是**刻意留余量** —— 用户可配的
    #   `custom_run_time_friday/saturday/sunday`（默认 19:30）必须落在窗口内,
    #   否则 `Config._align_to_window()` 会把**本来合法**的时刻推走
    #   （踩过: 窗口写成 19:00-19:15 时, 19:05 这个合法时刻被推到下一段）。
    #
    #   余量只是"别把合法时刻推走", **不会**让任务在 19:15 之后真的能跑 ——
    #   游戏那边关了就进不去, 任务会自己失败返回。
    window=AvailabilityWindow(True, time(19, 0), time(20, 0), days=(4, 5, 6)),
    list_pos=16,
    period=Period.DAILY,
    resource=Resource(capacity=1, recharge=Recharge(kind='none', period=Period.DAILY)),
)
