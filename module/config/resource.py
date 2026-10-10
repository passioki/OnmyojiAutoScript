# -*- coding: utf-8 -*-
"""任务的"资源规则"(Resource) —— 把游戏知识从 54 个配置界面收归一处。

## 为什么需要它

旧状态: "多久能跑一次"散落在**五个字段**里, 且每个任务用哪些字段还不一样:

    success_interval / charge_slots / charge_max / charge_consume / limit_count

于是"想知道某任务现在能不能跑"要读好几处, 且充能类只能靠另一套代码旁路实现。

新状态: 每个任务一条 `Resource`。**一个概念一个词**(设计原则 1),
**游戏知识只存在一处**(原则 2)。

## 三种补充方式, 覆盖全部 54 个任务

| 补充方式 | 语义 | 例 |
|---|---|---|
| `interval` | 距上次运行满 N 时间后, 补满容量 | 逢魔之时: 每 1 小时可做 1 次 |
| `slots` | 在**固定时刻**补满容量 | 金币妖怪: 0 点 +1、12 点 +1, 上限 2 |
| `window` | 只在**活动期**内可做 | 超鬼王: 活动开了才能打 |

三者本质相同 —— 都是"什么时候有资源" —— 所以是**同一个 `Resource` 的三种形态**,
而不是三套并列机制。

## 与旧字段的对应

    Resource(interval=(0,1,0), capacity=1)    <-  success_interval=1h
    Resource(slots=((0,0),(12,0)), capacity=2) <- charge_slots='0,12' + charge_max=2
    Resource(capacity=50)                     <- limit_count=50  (周期=每日, 由 period 给)

注意最后一行: 旧代码用 **两个** 字段(`success_interval=1d` + `limit_count=50`)
表达"每天打 50 次"; 新模型一个 `Resource` 就够。
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Literal

from module.config.availability import AvailabilityWindow


class Period(str, Enum):
    """容量重置周期。仅在 refill 为 `none` 时有意义。"""

    NONE = 'none'          # 不重置(只靠 interval/slots 补充)
    DAILY = 'daily'        # 每天 0 点(或 reset_at)重置
    WEEKLY = 'weekly'      # 每周一 0 点重置
    # ★ 用户明确要求: "选择周期选择每天, 每周则是每周一0点到周日24点,
    #   每月以此类推" —— 所以需要 MONTHLY。
    #   窗口 = 当月 1 日 00:00 到 月末 24:00
    #   （见 `availability.window_for_period()`）。
    MONTHLY = 'monthly'    # 每月 1 日 0 点重置

# ★★ S5: `Recharge` / `Resource` **已删除** —— 用户裁定 ★★
#   "去掉组队协同，去掉存量次数"
#   "连 `charge_*` 字段和存量逻辑一起删"
#
# 它们就是"**存量/充能**"机制: 池子容量 + 按间隔/时刻补充 + 每次消耗。
# 用户裁定: "**靠 window 的多次设置完全可以做到正常运行**" ——
# "一天在几个时段各跑一次"用**多个窗口**表达, "跑几轮"用**重复条目**。
#
# 设计依据: `docs/scheduler-architecture.md` §0。
def _parse_interval(s):
    """'01 00:00:00' / '00:03:00' -> (days, hours, minutes)。"""
    if not s:
        return None
    import re
    s = str(s).strip()
    m = re.match(r'(\d+)\s+(\d+):(\d+):(\d+)', s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r'(\d+):(\d+):(\d+)', s)
    if m:
        return 0, int(m.group(1)), int(m.group(2))
    return None
