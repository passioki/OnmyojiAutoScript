# This Python file uses the following encoding: utf-8
"""`FlowDemo`（流程示例）的任务实现。★ 由「新建任务」生成（SPEC §1.16 NT3）。

## ★★ 这是**安全空壳**（★ 四条保证）

* ★ **没有任何"乱点屏幕"的动作** —— 免得素材没配好就误操作账号
* ★ `enable=False`（`config.py`）⇒ ★ 开关没打开时它不做事
* ★ `period=none` + `auto_queue=False`（`meta.py`）⇒ ★ **不会自动进队列**
* ★ 结尾**一定** `set_next_run` + `TaskEnd` ⇒ ★ 不会把调度器挂住

## ★ 示例识别在哪里

★ 下面 `self.appear(self.I_UI_BACK_RED, ...)` 就是**示例识别** ——
  ★ 用的是**全局素材**（`tasks/GlobalGame/assets.py` 的 `I_UI_BACK_RED`，一定存在）
  ⇒ ★ **开箱即可跑**，不需要你先标素材。
★ 你自己的素材标好之后，把那一行换成 `self.I_YOUR_ASSET` 即可。
"""
from module.exception import TaskEnd
from module.logger import logger

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main


class ScriptTask(GameUi):
    """★ 类名**必须**叫 `ScriptTask`、**必须**实现 `run()`（`script.py:848-852` 写死）。"""

    def run(self) -> None:
        logger.hr('FlowDemo', 1)

        # ── ① 准备（SPEC §1.19-C2）：回到庭院 —— 以已知界面为起点
        self.goto_page(page_main)

        # ── ② 示例识别（★ 用户要求"骨架要带示例识别"）
        if self.appear(self.I_UI_BACK_RED, threshold=0.8, interval=1):
            logger.info('★ 示例识别命中：`I_UI_BACK_RED` 可见 —— '
                        '★ 这里就是写"识别到之后做什么"的地方')
        else:
            logger.info('★ 示例识别未命中（★ 也正常：骨架不做任何点击）')

        # ── ③ 收尾（SPEC §1.19-C7）：★ 上报本轮成功 + 交回调度器
        #   ★ `finish=True` ⇒ 以**收尾时刻**为基准排下一次（`base_task.py:1570-1571`）
        self.set_next_run(task='FlowDemo', success=True, finish=True)
        raise TaskEnd('FlowDemo')
