# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

from datetime import datetime, timedelta

from module.exception import TaskEnd
from module.logger import logger

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_team, page_shikigami_records
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralInvite.config_invite import TeamUserStatus
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul
from tasks.GoldYoukai.assets import GoldYoukaiAssets
from tasks.GoldYoukai.config import GoldYoukaiConfig


class ScriptTask(GameUi, GeneralBattle, GeneralRoom, GeneralInvite, SwitchSoul, GoldYoukaiAssets):

    def run(self):
        # 切换御魂
        if self.config.gold_youkai.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(self.config.gold_youkai.switch_soul.switch_group_team)

        if self.config.gold_youkai.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(self.config.gold_youkai.switch_soul.group_name,
                                         self.config.gold_youkai.switch_soul.team_name)

        # 组队身份: alone(等路人, 同改造前) / leader(邀请好友) / member(等邀请)
        # 注意取自 gold_youkai 分组内部(顶层标量会让 GUI 渲染失败)
        conf_team = self.config.gold_youkai.gold_youkai.user_status

        # 开启加成
        con = self.config.gold_youkai.gold_youkai
        if con.buff_gold_50_click or con.buff_gold_100_click:
            self.goto_page(page_main)
            self.open_buff()
            if con.buff_gold_50_click:
                self.gold_50()
            if con.buff_gold_100_click:
                self.gold_100()
            self.close_buff()
        # 挑战次数: 金币妖怪的次数在每天的固定时刻刷新(charge_slots, 游戏内为 0 点与 12 点),
        # 与改造前去别: 原来是"一次运行连打 2 场"(while count < 2), 现在改为
        # 最多存 charge_max 次。每次运行只做 charge_consume 次, 并把下次排到刷新时再做,
        # 这样"存量 2 次"会分摊到一天里, 而不是背靠背连打(组队场景尤其重要)。
        from module.config import task_state
        TASK_NAME = 'GoldYoukai'
        cfg_name = self.config.config_name

        count = 0
        if con.charge_enable:
            available = task_state.get_charges(cfg_name, TASK_NAME,
                                               max_charges=con.charge_max,
                                               slots=con.charge_slots)
            if available <= 0:
                logger.info(f'金币妖怪次数已用尽(0/{con.charge_max}), '
                            f'排到下次刷新后再做')
                self.set_next_run(task=TASK_NAME, finish=True, success=False,
                                  server=False,
                                  target=task_state.next_charge_time(
                                      cfg_name, TASK_NAME,
                                      max_charges=con.charge_max,
                                      slots=con.charge_slots))
                self.gold_exit(con)
            count_max = min(con.charge_consume, available)
            logger.info(f'金币妖怪可用次数 {available}/{con.charge_max}, '
                        f'本次挑战 {count_max} 场')
        else:
            # 关闭充能控制 -> 保持改造前行为(连打 2 场)
            count_max = 2

        while count < count_max:
            # 队员身份: 不需要开房, 直接等待队长邀请并应战(内含战斗流程)
            if conf_team == TeamUserStatus.MEMBER:
                logger.info('Member mode: wait for the leader invitation')
                self.run_battle_by_accept()
                count += 1
                continue

            self.goto_page(page_team)
            self.check_zones('金币妖怪')
            # 权威确认: "便捷组队"页在**次数用尽时**才显示该玩法的刷新倒计时。
            # 读到了就说明游戏侧确实没次数了, 直接排到倒计时结束, 不进组队流程。
            # (充能记账可能因外部消耗/换号而有偏差, 界面显示才是真相)
            cd = self.read_zone_countdown(con.zone_name)
            if cd and cd > 0:
                logger.info(f'界面显示 {con.zone_name} 还需 {cd}s 刷新次数, 本次跳过')
                self.set_next_run(task=TASK_NAME, finish=True, success=False,
                                  server=False,
                                  target=datetime.now() + timedelta(seconds=cd + 5))
                self.gold_exit(con)
            # 开始: 开公开房(与改造前一致)。队长额外做定向邀请, 空位仍可被路人填充
            if not self.create_room():
                self.gold_exit(con)
            self.ensure_public()
            self.create_ensure()
            # 进房并按身份等待队友, 然后点挑战
            if conf_team == TeamUserStatus.LEADER:
                if not self.enter_room_and_fire(
                        conf_team,
                        invite_config=self.config.gold_youkai.invite_config):
                    logger.warning('Invite team member failed, exit this round')
                    break
            else:
                # ALONE: 保持原有行为——等路人 50s 后即使没人也开战
                self.enter_room_and_fire(conf_team, random_wait=50)
            count += 1
            self.run_general_battle()

        # 消耗次数并安排下次运行
        if con.charge_enable and count > 0:
            for _ in range(count):
                task_state.consume_charge(cfg_name, TASK_NAME,
                                          max_charges=con.charge_max,
                                          slots=con.charge_slots)
            remain = task_state.get_charges(cfg_name, TASK_NAME,
                                            max_charges=con.charge_max,
                                            slots=con.charge_slots)
            if remain <= 0:
                logger.info('金币妖怪次数已用完, 排到下次刷新后再做')
                self.set_next_run(task=TASK_NAME, finish=True, success=True,
                                  server=False,
                                  target=task_state.next_charge_time(
                                      cfg_name, TASK_NAME,
                                      max_charges=con.charge_max,
                                      slots=con.charge_slots))
                self.gold_exit(con)
        # 退出 (要么是在组队界面要么是在庭院)
        self.gold_exit(con)


    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        # 重写
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        # 战斗过程 随机点击和滑动 防封
        logger.info("Start battle process")
        while 1:
            self.screenshot()
            if self.appear_then_click(self.I_PREPARE_HIGHLIGHT, interval=1):
                logger.info('click prepare')
            if self.appear(self.I_DE_WIN):
                logger.info('Win battle')
                self.ui_click_until_disappear(self.I_DE_WIN)
                return True
            if self.appear(self.I_GOLD_WIN):
                logger.info('Win battle')
                self.ui_click_until_disappear(self.I_GOLD_WIN)
                return True

            if self.appear(self.I_FALSE):
                logger.warning('False battle')
                self.ui_click_until_disappear(self.I_FALSE)
                return False

    def gold_exit(self, con):
        self.goto_page(page_main)
        if con.buff_gold_50_click or con.buff_gold_100_click:
            self.open_buff()
            if con.buff_gold_50_click:
                self.gold_50(False)
            if con.buff_gold_100_click:
                self.gold_100(False)
            self.close_buff()

        self.set_next_run(task='GoldYoukai', success=True, finish=False)
        raise TaskEnd('GoldYoukai')


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()
