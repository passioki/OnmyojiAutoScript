# -*- coding: utf-8 -*-
"""任务自描述 —— `WantedQuests` (悬赏封印).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/WantedQuests/` 目录, 写本文件 + config.py + script_task.py + assets.py
  2. `python dev_tools/assets_extract.py` 生成素材
  3. `python dev_tools/gen_task_catalog.py --check` 校验漏写

调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务, 无需改动任何中心文件。

规范见 `docs/architecture.md` §7(可演进性)。

类别依据: 固定任务: 有"打满 N 次"的语义
"""
from datetime import time
from module.config.availability import AvailabilityWindow
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='WantedQuests',
    name_zh='悬赏封印',
    category=Category.FIXED,
    # ★★★ 废弃（片 4 / W-a，用户裁定）★★★
    #
    # 悬赏封印的 `before_end` 无法用 window start 表达：
    #   `script_task.py:101-112` 用它算「**活动结束前 N 分钟**」的下次运行时刻 ——
    #   它是**相对偏移量**，塞进 window start 会**语义反转**。
    #   ★ 用户裁定: 标为废弃不可启用，留待删除或适配。
    deprecated=("WantedQuests 因字段语义冲突被标记为废弃，留待删除或适配。详见本文件上方的说明与 DEV-SCHEDULER-UNIFY-PLAN.md 的 W-a 审计。"),
    # 定时类自动进队列 / 次数类需【添加任务】（见 architecture.md §3.5）
    auto_queue=True,
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
    list_pos=31,
    period=Period.NONE,
)
