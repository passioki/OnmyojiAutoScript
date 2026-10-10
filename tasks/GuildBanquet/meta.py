# -*- coding: utf-8 -*-
"""任务自描述 —— `GuildBanquet` (寮宴会).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/GuildBanquet/` 目录, 写本文件 + config.py + script_task.py + assets.py
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
    task='GuildBanquet',
    name_zh='寮宴会',
    category=Category.TIMED,
    # 定时类自动进队列 / 次数类需【添加任务】（见 architecture.md §3.5）
    auto_queue=True,
    # ★★ (b) 动态窗口: 宴会日与时刻都**引用用户配置** ★★
    #
    # 用户裁定:
    #   "AvailabilityWindow 支持动态 days（运行时从配置读）, 让窗口能引用配置字段"
    #   "窗口是唯一排期依据, 这个 B 并不冲突"
    #
    # `GuildBanquetTime` 有**两场**宴会, 各自带"星期 + 时刻":
    #     day_1 = 星期三, run_time_1 = 19:00
    #     day_2 = 星期六, run_time_2 = 19:00
    #
    # ★ 路径是**相对任务**的（`GuildBanquet/meta.py` 只拿到任务级数据）
    # 所以给**两段**窗口, 每段引用对应字段 —— 用户在任务配置里改宴会日/时刻,
    # 窗口运行时跟着变; 而不是把"周三/周六 19:00"硬编码进代码。
    window=(
        # `days=()` = **没有静态约束** —— 星期完全由配置决定
        AvailabilityWindow(True, time(18, 0), time(22, 0), days=(),
                           days_from_config=(
                               'guild_banquet_time.day_1',),
                           times_from_config=(
                               'guild_banquet_time.run_time_1',)),
        AvailabilityWindow(True, time(18, 0), time(22, 0), days=(),
                           days_from_config=(
                               'guild_banquet_time.day_2',),
                           times_from_config=(
                               'guild_banquet_time.run_time_2',)),
    ),
    list_pos=18,
    period=Period.DAILY,
    resource=Resource(capacity=1, recharge=Recharge(kind='none', period=Period.DAILY)),
)
