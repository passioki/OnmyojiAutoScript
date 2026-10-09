# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
# ★ 4-F: 删掉 `time`（原来给 `custom_next_run` 的 `time(6,0)` / `time(17,0)` 用）
from datetime import timedelta, datetime
from cached_property import cached_property

from module.exception import TaskEnd
from module.logger import logger
from module.base.timer import Timer

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_hunt, page_hunt_kirin, page_shikigami_records
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.Hunt.assets import HuntAssets


class ScriptTask(GameUi, GeneralBattle, GeneralInvite, SwitchSoul, HuntAssets):
    kirin_day = True  # 不是麒麟就是阴界之门

    def run(self):
        # ★ 4-F: 不再需要 `self.con_time`（原来给 `custom_next_run` 用的
        #   `kirin_time` / `netherworld_time`）。排期由调度器 + 窗口负责。
        self.check_datetime()
        con = self.config.hunt.hunt_config
        if con.kirin_group_team != '-1,-1' or con.netherworld_group_team != '-1,-1':
            self.goto_page(page_shikigami_records)

            if self.kirin_day:
                if con.kirin_group_team != '-1,-1':
                    self.run_switch_soul(con.kirin_group_team)
            else:
                if con.netherworld_group_team != '-1,-1':
                    self.run_switch_soul(con.netherworld_group_team)
        if self.kirin_day:
            self.goto_page(page_hunt_kirin)
            self.kirin()
        else:
            self.goto_page(page_hunt)
            self.netherworld()
        sleep(1)

        # ★ 4-F: 原来这里 `plan_tomorrow_hunt()`（手工排明天的 19:00）。
        #   现在由 `set_next_run` 自行落盘 —— 走到这里说明任务已正常结束,
        #   基类会把 `next_run` 推后并按窗口对齐。
        raise TaskEnd('Hunt')

    def check_datetime(self) -> bool:
        """
        判断今天是**麒麟**还是**阴界之门**, 并据此选路。

        ## ★ 4-F: 这里只剩"选哪种模式", 不再管排期

        原来这个方法还兼了两件事:

        * **太早**（麒麟日 <06:00 / 阴界日 <17:00）-> `custom_next_run(今天该时刻)` + 退出
        * **太晚**（>23:00）-> `plan_tomorrow_hunt()` + 退出

        两者都**已删除**, 因为"什么时候允许跑"已由
        `tasks/Hunt/meta.py` 的**两段窗口**表达:

            周一~周四 06:00-23:00（麒麟）
            周五~周日 17:00-23:00（阴界）

        由 `Config._align_to_window()` 统一裁决:

        * **不会太早**: 不在窗口内时调度器根本不会把任务排进 pending;
          且 `next_run` 会被对齐到窗口开放时刻（实测: 周一 22:30 跑完
          -> 推到**周二 06:00**, 而不是 01:30）
        * **不会太晚**: 窗口 23:00 结束, 23:00 之后不会被派发 ——
          所以原来那个 `>23:00` 分支**永远走不到**（死代码）

        :return: 始终 True（选路信息由 `self.kirin_day` 带出）
        """
        day_of_week = datetime.now().weekday()
        # 周一~周四 = 麒麟日; 周五~周日 = 阴界之门日
        self.kirin_day = 0 <= day_of_week <= 3
        if self.kirin_day:
            logger.info('Today is the Kirin day')
        else:
            logger.info('Today is the Netherworld day')
        return True

    def kirin(self):
        logger.hr('kirin', 2)
        while 1:
            self.screenshot()
            if self.appear(self.I_PREPARE_HIGHLIGHT):
                break
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.9)\
                    or self.appear_then_click(self.I_UI_CONFIRM_SAMLL, interval=0.9):
                continue
            if self.appear_then_click(self.I_KIRIN_CHALLAGE, interval=1.5):
                continue
            if self.appear_then_click(self.I_KIRIN_START_CHALLAGE, interval=2.5):
                continue
            if self.appear(self.I_KIRIN_END):
                # 今日已挑战
                logger.warning('Today have already challenged the Kirin')
                self.ui_click_until_disappear(self.I_UI_BACK_YELLOW)
                return
        logger.info('Start battle')
        self.run_general_battle(self.config.hunt.kirin_battle_config)

    def netherworld(self):
        logger.hr('netherworld', 2)
        while 1:
            self.screenshot()
            if self.is_in_room(False):
                self.screenshot()
                if not self.appear(self.I_FIRE):
                    continue
                self.click_fire()
                break

            if self.appear_then_click(self.I_NW, interval=0.9):
                continue
            if self.appear_then_click(self.I_UI_CONFIRM, interval=0.9):
                continue
            if self.appear_then_click(self.I_NW_CHALLAGE, interval=1.5):
                continue
            if self.appear(self.I_NW_DONE):
                # 今日已挑战
                logger.warning('Today have already challenged the Netherworld')
                self.ui_click_until_disappear(self.I_UI_BACK_RED)
                return
        logger.info('Start battle')
        self.run_general_battle(self.config.hunt.netherworld_battle_config)

    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        """
        重写，
        阴界之门： 胜利后回到狩猎战的主界面
        麒麟： 胜利后回到麒麟的主界面
        :param random_click_swipt_enable:
        :return:
        """
        # if self.kirin_day:
        #     return super().battle_wait(random_click_swipt_enable)

        # 阴界之门
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        # 战斗过程 随机点击和滑动 防封
        logger.info("Start battle process")
        stuck_timer = Timer(180)
        stuck_timer.start()
        while 1:
            self.screenshot()
            if self.appear(self.I_WIN):
                logger.info('Battle win')
                self.ui_click_until_disappear(self.I_WIN)
                return True
            # 如果出现失败 就点击，返回False
            if self.appear(self.I_FALSE, threshold=0.8):
                logger.info("Battle result is false")
                self.ui_click_until_disappear(self.I_FALSE)
                return False
            if self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1.5):
                logger.info('Netherworld click prepare after maybe failed')
                self.device.stuck_record_add('BATTLE_STATUS_S')
                continue
            # 如果三分钟还没打完，再延长五分钟
            if stuck_timer and stuck_timer.reached():
                stuck_timer = None
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()

