# -*- coding: utf-8 -*-
"""任务自描述 —— `FlowDemo`（流程示例）。★ 由「新建任务」生成（SPEC §1.16 NT1~NT4）。

★ **这个文件是任务与调度器之间的唯一契约**（权威说明见 `tasks/Rest/meta.py:4-9`）。

## 新增/维护一个任务要做的事

1. ★ 建 `tasks/FlowDemo/`（本工厂已建好）并写 4 个文件：
   `meta.py` + `config.py` + `script_task.py` + `assets.py`
2. ★ 标素材：`/tool/annotator` 里标好并保存 ⇒ 保存时**自动重生成** `assets.py`
   （★ 命令行等价物：`python dev_tools/assets_extract.py`）
3. ★ 自查：`python dev_tools/gen_task_catalog.py`（★ 更新 `task_catalog_data.json`）

★ 调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务，无需改任何中心文件。
★ 规范见 `docs/architecture.md` §7（可演进性）。
"""
from datetime import time

from module.config.availability import AvailabilityWindow  # noqa: F401
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='FlowDemo',
    name_zh='流程示例',
    # ★ 类别：FIXED 固定 / TOPPA 突破 / LIMITED 限时 / TIMED 定时
    category=Category.TIMED,
    # ★★ `auto_queue`：★ 本项目的不变量是 **`auto_queue == NOT countable`**
    #   （"**次数任务不自动进队列，定时任务自动进**" —— 见
    #    `tests/module/config/test_execution_queue.py:test_auto_queue_matches_countable`）
    #   ⇒ ★ 新任务（TIMED、非次数类）**必须** `auto_queue=True`，★ 否则那条守卫变红。
    #   ⚠ **[10-14] 实测订正**：本模板原来写 `auto_queue=False`（想表达"新建后不自动跑"），
    #     但那**违反项目不变量**。★ **安全性不靠它**：★ 真正拦住"新建即乱跑"的是
    #     `scheduler.enable=False`（任务开关）+ 下面 `config.py` 分组里的 `enable=False`。
    auto_queue=True,
    # ★★ `list_pos` 必须**全局唯一**（★ 守卫 `test_list_pos_metadata.py` 强制）
    #   ⇒ ★ 工厂已自动取"当前最大值 + 1"（★ 别手改成 0，那会让守卫变红）
    list_pos=54,
    # ★ 周期：Period.NONE 临时 / DAILY 每天 / WEEKLY 每周 / MONTHLY 每月
    period=Period.NONE,
    # ★★ **开放时段必须显式给**（★ 守卫 `test_every_task_has_window.py` 强制：
    #   "所有的定时都有着 window 属性"）—— ★ `Period.NONE` **推导不出**窗口
    #   ⇒ ★ 新任务默认给**全天**；★ 按玩法改成你要的，例
    #   `AvailabilityWindow(True, time(17, 0), time(23, 0))`
    window=AvailabilityWindow(True, time(0, 0), time(23, 59)),
)
