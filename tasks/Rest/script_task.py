# This Python file uses the following encoding: utf-8
"""`Rest` (休息) 的任务实现 —— **回庭院待着 N 分钟**.

## ★★★ 休息就是临时任务（用户裁定）★★★

> "**休息就是临时任务**（回庭院待着），只不过**可以选择被定时任务插队**。"

> "休息作为**空置任务**它本身就会带来**阻塞**的效果。"

## 它做什么

1. 回到**庭院**（`page_main`）——
   ★ 这一步是**关键**，不是"什么都不做"：
   > 游戏不会因为长时间无操作而**断线**，组队任务回来时人也"在"。
2. 然后**待着** `scheduler.target` 分钟。

## ★ 分钟数 = `scheduler.target`

用户裁定 (乙-A):
> "需要**分钟**, 不是次数。"

★ 所以这里读 `scheduler.target`（那个"目标次数"框），
  对休息任务它的语义就是**分钟**。

## ⚠ 与"阻塞队列"的关系

★ 真正的阻塞**不在这里** —— 而在 `Config.apply_run_list_blocker()`：
休息期间 `rest_until` 被写入，调度主循环看到它就**不派发任何任务**
（除"可穿插的定时任务"）。

★ 所以本任务**不需要**自己"停住整个队列" —— 它只要**待在庭院**，
  让 `rest_until` 生效即可。这也是为什么"空置任务本身就会带来阻塞效果"
  （用户原话）。
"""
from module.exception import TaskEnd
from module.logger import logger
from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main


class ScriptTask(GameUi):

    def run(self) -> None:
        # ① 回庭院 —— 让游戏保持"有人在"的状态（防断线）
        self.goto_page(page_main)

        # ② 休息多少分钟 = 通用的 `scheduler.target`
        #
        # ★ 用户裁定: "需要**分钟**, 不是次数。"
        minutes = 0
        try:
            minutes = int(getattr(self.config.rest.scheduler, 'target', 0) or 0)
        except Exception as exc:
            logger.warning(f'读取休息分钟数失败({type(exc).__name__}: {exc}), '
                           f'按 0 处理')

        if minutes <= 0:
            # ★ `target = 0` = 用默认值。休息的"默认"取 30 分钟
            #   （与队列里「休息」条目的历史默认一致）。
            #
            # ⚠ 为什么不是"不休息": `target=0` 在别的任务是"用任务配置里的
            #   次数上限"，但休息**没有**那种上限 —— 所以给它一个可见的默认。
            minutes = 30
            logger.info('休息未设置分钟数（target=0）-> 用默认 30 分钟')

        logger.info(f'休息 {minutes} 分钟（回庭院待着）')

        # ③ 待在庭院等 —— 走 `self.device.sleep` 以便**响应停止/暂停**
        #
        # ★ 为什么用 `device.sleep` 而不是 `time.sleep`:
        #   前者会检查停止信号，用户点「暂停调度」/「停止」能**及时**退出；
        #   `time.sleep(N*60)` 会让用户等满 N 分钟。
        #
        # ⚠ 分片睡: 一次睡满会让"停止"最多延迟 `minutes` 分钟。
        #   切成 30 秒一片，兼顾"及时响应"与"不空转"。
        slice_s = 30
        total_s = minutes * 60
        slept = 0
        while slept < total_s:
            step = min(slice_s, total_s - slept)
            self.device.sleep(step)
            slept += step

        raise TaskEnd('Rest end')
