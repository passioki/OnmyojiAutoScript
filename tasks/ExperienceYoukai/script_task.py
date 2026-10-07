# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

from module.exception import TaskEnd
from module.logger import logger

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_team, page_shikigami_records
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralInvite.config_invite import TeamUserStatus
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.ExperienceYoukai.assets import ExperienceYoukaiAssets
from tasks.ExperienceYoukai.config import ExperienceYoukaiConfig


class ScriptTask(GameUi, GeneralBattle, GeneralRoom, GeneralInvite, SwitchSoul, ExperienceYoukaiAssets):

    def run(self):
        # 切换御魂
        if self.config.experience_youkai.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(self.config.experience_youkai.switch_soul.switch_group_team)

        if self.config.experience_youkai.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(self.config.experience_youkai.switch_soul.group_name,
                                         self.config.experience_youkai.switch_soul.team_name)

        # 组队身份: alone(等路人, 同改造前) / leader(邀请好友) / member(等邀请)
        conf_team = self.config.experience_youkai.user_status

        # 开启加成
        con = self.config.experience_youkai.experience_youkai
        if con.buff_exp_50_click or con.buff_exp_100_click:
            self.goto_page(page_main)
            self.open_buff()
            if con.buff_exp_50_click:
                self.exp_50()
            if con.buff_exp_100_click:
                self.exp_100()
            self.close_buff()
        count = 0
        while count < 2:
            # 队员身份: 不需要开房, 直接等待队长邀请并应战(内含战斗流程)
            if conf_team == TeamUserStatus.MEMBER:
                logger.info('Member mode: wait for the leader invitation')
                self.run_battle_by_accept()
                count += 1
                continue

            self.goto_page(page_team)
            self.check_zones('经验妖怪')
            # 开始: 开公开房(与改造前一致)。队长额外做定向邀请, 空位仍可被路人填充
            if not self.create_room():
                self.experience_exit(con)
            self.ensure_public()
            self.create_ensure()
            # 进房并按身份等待队友, 然后点挑战
            if conf_team == TeamUserStatus.LEADER:
                if not self.enter_room_and_fire(
                        conf_team,
                        invite_config=self.config.experience_youkai.invite_config):
                    logger.warning('Invite team member failed, exit this round')
                    break
            else:
                # ALONE: 保持原有行为——等路人 50s 后即使没人也开战
                self.enter_room_and_fire(conf_team, random_wait=50)
            count += 1
            self.run_general_battle()
        # 退出 (要么是在组队界面要么是在庭院)
        self.experience_exit(con)

    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        # 重写
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        # 战斗过程 随机点击和滑动 防封
        logger.info("Start battle process")
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_PREPARE_HIGHLIGHT,interval=1):
                logger.info('click prepare')
            if self.appear(self.I_DE_WIN):
                logger.info('Win battle')
                self.ui_click_until_disappear(self.I_DE_WIN)
                return True
            if self.appear(self.I_EXP_WIN):
                logger.info('Win battle')
                self.ui_click_until_disappear(self.I_EXP_WIN)
                return True

            if self.appear(self.I_FALSE):
                logger.warning('False battle')
                self.ui_click_until_disappear(self.I_FALSE)
                return False

    def experience_exit(self, con):
        self.goto_page(page_main)
        if con.buff_exp_50_click or con.buff_exp_100_click:
            self.open_buff()
            if con.buff_exp_50_click:
                self.exp_50(False)
            if con.buff_exp_100_click:
                self.exp_100(False)
            self.close_buff()

        self.set_next_run(task='ExperienceYoukai', success=True, finish=False)
        raise TaskEnd('ExperienceYoukai')

if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
