# -*- coding: utf-8 -*-
"""任务自描述 —— `Rest` (休息).

**这个文件是任务与调度器之间的唯一契约。** 新增一个游戏活动时, 只需:
  1. 建 `tasks/Rest/` 目录, 写本文件 + config.py + script_task.py + assets.py
  2. `python dev_tools/assets_extract.py` 生成素材
  3. `python dev_tools/gen_task_catalog.py --check` 校验漏写

调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务, 无需改动任何中心文件。

规范见 `docs/architecture.md` §7(可演进性)。

## ★★★ 休息是什么（用户裁定, 第三次澄清）★★★

用户原话:
> "**休息就是临时任务**（回庭院待着），只不过**可以选择被定时任务插队**。"

> "休息作为**空置任务**它本身就会带来**阻塞**的效果。"

### ★ 为什么它是一个**真正的任务**（而不是队列里的特殊条目）

用户裁定 (乙-A):
> "有 `period` 和 `window` 属性, 是为了**统一管理**。比如初始值是
>  `period=none`, 这样可以轻易地被分进**临时任务**。事实上并不会去把
>  `period` 改为其他值。"
> "需要**分钟**, 不是次数。"
> "在 `period != none` 的情况下, 如果你写的调度模块没问题, 那么就会按照
>  调度来, 每天什么时候休息 —— 不过这是**使用者关心的事**, 咱们只需要
>  **写好逻辑, 确保逻辑不混乱**就行。"

★ 所以:
  * **`period = NONE`（默认）** -> 自然被分进**临时任务**（`_segment_of` 的判据）
  * **`window`** -> "只在这个时段内才休息"（例如 12:00-14:00 午休）
  * **`target` = 分钟数**（不是次数！）—— ★ 用户明确: "需要分钟, 不是次数"
  * 若用户把 `period` 改成 daily/weekly -> **按正常调度走**（每天什么时候休息）

### ★ 为什么"空置任务"天然带来阻塞

`Config.apply_run_list_blocker()` 在调度主循环里检查 `rest_until`:
跑到休息任务时 -> 写 `rest_until = now + target 分钟` -> **整个队列阻塞**。
这就是"**回庭院待着**"的防封效果（游戏不会因长时间无操作断线）。

★ 它**不影响"哪些任务能跑"** —— `_order_by_queue()` 跳过无 `task` 的条目
  （实测: `for entry in queue: cmd = getattr(entry, 'task', None); if not cmd: continue`）。
  所以休息在队列里的**位置**只决定"什么时候休息", 不决定"谁能跑"。

### 「可选择被定时任务插队」

`rest_interleave`（`Config.can_interleave_timed`）: 若休息期间有
**能在剩余时间内跑完**的到点定时任务, 让那个任务先跑。
★ 这是休息**唯一**的特殊能力，**不是约束**。
"""
from datetime import time

from module.config.availability import AvailabilityWindow
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='Rest',
    name_zh='休息',
    # ★ 用 TIMED（= 非次数类）—— 因为它的"次数"其实是**分钟数**,
    #   不应该走 `countable` 的"打满 N 次"语义。
    #   而 `period=NONE` 会让 `_segment_of()` 把它判为**临时任务**
    #   （判据只看 period, 不看 category —— 见 `Config.task_period`）。
    category=Category.TIMED,
    # ★★★ `auto_queue=False` —— 休息**由用户主动添加**（用户裁定 乙）★★★
    #
    # 用户在我给出"甲/乙"两个选项后选: **乙**。
    #
    # ## 为什么不能 `auto_queue=True`（我第一版写错了）
    #
    # `auto_queue=True` 有两个后果, 都不是用户要的:
    #
    # 1. ★ `build_queue()` 会把它**自动补齐进队列** ->
    #    **休息会永远躺在队列里**（用户没主动加也在）。
    #    而休息是"**跑到这一行才歇**"的东西 ——
    #    常驻队列 = 每次都会歇, 那不是用户的意图。
    #
    # 2. ★ `GET /queue/candidates` 会 `if _auto_queue_of(meta, config): continue`
    #    -> **「添加休息」候选里看不到它**。
    #
    # ## 乙 的行为（与用户既有体验一致）
    #
    # 用户点「添加休息」-> `setEnabled('rest', True)` + 加进 `run_list`
    # -> 与改动前"用户主动加一条休息"**完全一致**。
    auto_queue=False,
    # ★ 全天窗口（与 AreaBoss 同样的声明方式）。
    #   ★ 用户可改成 12:00-14:00 之类 -> "只在这个时段才休息"。
    #   全天与"未声明"行为等价（`contains()` 恒 True）—— 纯声明。
    window=AvailabilityWindow(True, time(0, 0), time(23, 59)),
    # ★ period=NONE（默认）-> 分进**临时任务**（用户要的初始值）
    period=Period.NONE,
)
