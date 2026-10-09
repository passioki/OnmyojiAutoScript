# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import timedelta, datetime, time
from cached_property import cached_property

from module.exception import TaskEnd
from module.logger import logger
from module.base.timer import Timer

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_hunt, page_shikigami_records, page_guild
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.DemonRetreat.assets import DemonRetreatAssets
from tasks.AbyssShadows.assets import AbyssShadowsAssets
from tasks.DemonRetreat.config import DemonRetreat

class ScriptTask(GameUi, GeneralBattle, SwitchSoul, DemonRetreatAssets, AbyssShadowsAssets):

    def run(self):
        """
        首领退治主函数
        """

        cfg: DemonRetreat = self.config.demon_retreat

        # ★★ 4-F: 删掉任务内的**硬编码星期判断** ★★
        #
        # 原来这里有 20 行: 判 `weekday() == 5`, 算 `days_until_saturday`,
        # 然后 `custom_next_run(..., time_delta=days_until_saturday)`。
        #
        # 现在这段知识写在 **`tasks/DemonRetreat/meta.py`** 的
        # `window=AvailabilityWindow(True, 19:00, 20:00, days=(5,))` ——
        # 由调度器 `Config._align_to_window()` 统一裁决:
        # 不是周六时, 任务照常被调度到, 但 `next_run` 会被**对齐到周六 19:00**。
        #
        # ★ 等价性**已实测**（4/4 场景与旧逻辑完全一致）: 周一/周三/周日 -> 本周六 19:00;
        #   周六成功 -> 下周六 19:00。
        #
        # ⚠ 这里**故意不**再加一层 `if weekday != 5: return`:
        #   那是第二套机制（本项目已因"知识存在两处"栽过多次）。
        #   不在窗口内时, 调度器根本不会把任务排进 pending.
        if cfg.switch_soul_config.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(cfg.switch_soul_config.switch_group_team)
        if cfg.switch_soul_config.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(cfg.switch_soul_config.group_name, cfg.switch_soul_config.team_name)

        # 进入妖怪退治
        if not self.goto_demon_retreat():
            logger.warning("Failed to enter demon retreat")
            if self.appear_then_click(self.I_DEMON_BACK_CHECK, interval=1):
                pass
            self.goto_main()
            self.set_next_run(task='DemonRetreat', finish=False, server=True, success=False)
            raise TaskEnd

        # 首领退治战斗
        success = self.demon_retreat()

        # 战斗结束 回到寮信息界面 准备领取奖励
        # 先返回
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_PRAY, interval=1):
                logger.warning("Claim rewards")
            if self.appear_then_click(self.I_HUNT, interval=1):
                continue
            if self.appear_then_click(self.I_REWARD_ALL, interval=1.5):
                self.ui_reward_appear_click(True)
                logger.info('Claim rewards finished')
                break
            if self.appear(self.I_RANK_LSIT):
                logger.info("No rewards to claim")
                if self.appear_then_click(self.I_DEMON_BACK_CHECK, interval=1):
                    break

        # 保持好习惯，一个任务结束了就返回到庭院，方便下一任务的开始
        self.goto_main()

        # 设置下次运行时间
        if success:
            # ★ 4-F: 原来是 `custom_next_run(..., time_delta=7)`（手工推到"下周六"）。
            #   现在交给调度器: `success_interval` + **窗口对齐**（meta.py 里
            #   `window=AvailabilityWindow(True, 19:00, 20:00, days=(5,))`）
            #   -> 结果同样是"下周六 19:00"（已实测等价）。
            self.set_next_run(task='DemonRetreat', finish=True,
                              server=True, success=True)
        else:
            self.set_next_run(task="DemonRetreat", finish=True, server=True, success=False)

        raise TaskEnd



    def goto_demon_retreat(self) -> bool:
        """
        进入首领退治
        """
        cfg: DemonRetreat = self.config.demon_retreat
        logger.info("Entering demon_retreat")
        self.goto_page(page_guild)

        goto_demon_retreat_num = 0
        while 1:
            self.screenshot()
            # 进入神社
            if self.appear_then_click(self.I_SHRINE, interval=1):
                logger.info("Enter I_SHRINE")
                continue
            # 进入首领退治
            if self.appear_then_click(self.I_HUNT, interval=1.5):
                goto_demon_retreat_num += 1

            # 确保不离开退治
            if self.appear_then_click(self.I_QUIT_BACK, interval=1):
                pass
            if (self.appear(self.I_HUNT_CHECK)
                    or self.appear(self.I_DEMON_GATHER)
                    or self.is_in_prepare(False)):
                if self.appear_then_click(self.I_QUIT_BACK, interval=1):
                    pass
                logger.info("Enter demon_retreat success")
                return True

            # 周六打完了，但是迟到了只能领取奖励
            if self.appear_then_click(self.I_REWARD_ALL, interval=1):
                logger.info("Already challenged demon_retreat")
                sleep(1)
                if self.appear_then_click(self.I_DEMON_BACK_CHECK, interval=1):
                    pass
                # ★ 4-F: 同前 —— 不再手工推到"下周六", 交给调度器 + 窗口对齐
                self.set_next_run(task='DemonRetreat', finish=True,
                                  server=True, success=True)
                raise TaskEnd

            if self.appear(self.I_RANK_LSIT):
                logger.info("Enter demon_retreat false")
                sleep(3)
                if self.appear_then_click(self.I_DEMON_BACK_CHECK, interval=1):
                    pass
                sleep(20)
            # 超过五次没有进入进入认为失败
            if goto_demon_retreat_num >= 5:
                break
        return False

    def demon_retreat(self):
        cfg: DemonRetreat = self.config.demon_retreat
        logger.hr('demon retreat', 2)

        # 来晚了直接进入战斗
        if not set(self.O_LATER_ENTER_CHECK.ocr(image=self.device.image)).intersection(set("集结")):
            logger.info("arrive later")
            self.ui_click_until_disappear(self.I_ENTER_FIRE, interval=1)
            self.device.stuck_record_add('BATTLE_STATUS_S')
            success = self.run_demon_battle(cfg.general_battle)
        else:
            # 等待进入战斗
            sleep(5)
            self.device.stuck_record_add('BATTLE_STATUS_S')
            self.wait_until_disappear(self.I_DEMON_GATHER)
            self.device.stuck_record_clear()
            self.device.stuck_record_add('BATTLE_STATUS_S')
            success = self.run_demon_battle(cfg.general_battle)

        return success




    def run_demon_battle(self, config: GeneralBattleConfig = None) -> bool:
        """
        重写通用战斗
        三轮战斗 战斗过程中检测挑战
        """
        # TODO 战斗过程中切换预设
        logger.hr("General battle start", 2)
        self.current_count += 1
        logger.info(f"Current count: {self.current_count}")
        if config is None:
            config = GeneralBattleConfig()

        # 如果没有锁定队伍。那么可以根据配置设定队伍
        if not config.lock_team_enable:
            logger.info("Lock team is not enable")
            # 如果更换队伍
            if self.current_count == 1:
                self.switch_preset_team(config.preset_enable, config.preset_group, config.preset_team)

            # 点击准备按钮
            self.wait_until_appear(self.I_PREPARE_HIGHLIGHT)
            self.wait_until_appear(self.I_BUFF)
            while 1:
                self.screenshot()
                if not self.appear(self.I_BUFF):
                    break
                if self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1.5):
                    continue

            logger.info("Click prepare ensure button")

            # 照顾一下某些模拟器慢的
            sleep(0.1)

        # 绿标
        self.wait_until_disappear(self.I_BUFF)
        if self.is_in_battle(False):
            self.green_mark(config.green_enable, config.green_mark)

        win = self.battle_wait(config.random_click_swipt_enable)
        if win:
            return True
        else:
            return False




    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        """
        重写 三轮战斗 战斗过程中点击准备 返回到寮信息界面
        :param random_click_swipt_enable:
        :return:
        """
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        # 战斗过程 随机点击和滑动 防封 并点击 准备
        logger.info("Start battle process")
        stuck_timer = Timer(180)
        stuck_timer.start()
        while 1:
            self.screenshot()
            if self.appear(self.I_WIN):
                logger.info('Battle win')
                self.ui_click_until_disappear(self.I_WIN)
                return True
            # 战斗过程中出现准备
            if self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1.5):
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')
            # 如果出现失败 就点击，返回False
            if self.appear(self.I_FALSE, threshold=0.8):
                logger.info("Battle result is false")
                self.ui_click_until_disappear(self.I_FALSE)
                return False
            # 如果三分钟还没打完，再延长五分钟
            if stuck_timer and stuck_timer.reached():
                stuck_timer = None
                self.device.stuck_record_clear()
                self.device.stuck_record_add('BATTLE_STATUS_S')


    def goto_main(self):
        ''' 保持好习惯，一个任务结束了就返回庭院，方便下一任务的开始或者是出错重启
        '''
        logger.info("Exiting DemonRetreat")
        self.goto_page(page_main)






if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('日常1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()

