# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from datetime import time, datetime, timedelta

from module.logger import logger
from module.exception import TaskEnd
from module.config import task_state
from module.config import team_coordinator

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main, page_team, page_shikigami_records
from tasks.Component.GeneralBattle.general_battle import GeneralBattle
from tasks.Component.GeneralRoom.general_room import GeneralRoom
from tasks.Component.GeneralInvite.general_invite import GeneralInvite
from tasks.Component.GeneralInvite.config_invite import TeamUserStatus
from tasks.Component.SwitchSoul.switch_soul import SwitchSoul


class ScriptTask(GameUi, GeneralBattle, GeneralRoom, GeneralInvite, SwitchSoul):

    def run(self):
        conf = self.config.tako
        if conf.switch_soul.enable:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul(conf.switch_soul.switch_group_team)

        if conf.switch_soul.enable_switch_by_name:
            self.goto_page(page_shikigami_records)
            self.run_switch_soul_by_name(conf.switch_soul.group_name,
                                         conf.switch_soul.team_name)
        # 加成
        conf_buff = conf.tako_config
        if conf_buff.enable:
            self.goto_page(page_main)
            self.open_buff()
            if conf_buff.buff_gold_50_click:
                self.gold_50()
            if conf_buff.buff_gold_100_click:
                self.gold_100()
            if conf_buff.buff_exp_50_click:
                self.exp_50()
            if conf_buff.buff_exp_100_click:
                self.exp_100()
            self.close_buff()

        # 组队身份: alone(等路人, 同改造前) / leader(邀请好友) / member(等邀请)
        # 注意取自 tako_config 分组内部(顶层标量会让 GUI 渲染失败)
        conf_team = conf.tako_config.user_status
        # 挑战次数配置(与金币妖怪一致)
        conf_charge = conf.tako_config
        TASK_NAME = 'Tako'
        cfg_name = self.config.config_name

        # 让另一个账号知道我在线(跨账号协同需要判断"对方在不在")
        task_state.write_heartbeat(cfg_name)

        # 队员身份: 不需要选副本/开房, 直接等队长邀请并应战(内含战斗流程)
        if conf_team == TeamUserStatus.MEMBER:
            logger.info('Member mode: wait for the leader invitation')
            self.run_battle_by_accept()
            self.exit_task()

        # 记账检查: 次数为 0 时直接排到下次刷新, 不去开房
        if conf_charge.charge_enable:
            available = task_state.get_charges(
                cfg_name, TASK_NAME,
                max_charges=conf_charge.charge_max,
                slots=conf_charge.charge_slots)
            if available <= 0:
                logger.info(f'石距次数已用尽(0/{conf_charge.charge_max}), '
                            f'排到下次刷新后再做')
                self.set_next_run(task=TASK_NAME, finish=True, success=False,
                                  server=False,
                                  target=task_state.next_charge_time(
                                      cfg_name, TASK_NAME,
                                      max_charges=conf_charge.charge_max,
                                      slots=conf_charge.charge_slots))
                self.exit_task()
            logger.info(f'石距可用次数 {available}/{conf_charge.charge_max}')

            # 跨账号协同: 组队任务需要两边都有次数才有意义。
            # 若对方还没恢复, 就等一个刷新点再一起做(等太久会自动放弃, 见防死锁)。
            if conf_team != TeamUserStatus.MEMBER:
                decision = team_coordinator.decide(
                    TASK_NAME, cfg_name,
                    max_charges=conf_charge.charge_max,
                    slots=conf_charge.charge_slots)
                logger.info(f'[TeamCoord] 石距协同决策: {decision}')
                if not decision.should_start:
                    self.set_next_run(task=TASK_NAME, finish=True, success=False,
                                      server=False,
                                      target=datetime.now()
                                      + timedelta(seconds=decision.wait_seconds + 5))
                    self.exit_task()

        # 进入
        self.goto_page(page_team)
        if 5 <= self.start_time.weekday() <= 6:
            # 周末
            zone_name = '喷怒的石距'
            self.check_zones(zone_name)
        else:
            zone_name = '石距'
            self.check_zones(zone_name)
        # 权威确认: "便捷组队"页在**次数用尽时**才显示该玩法的刷新倒计时。
        # 读到了就说明游戏侧确实没次数了, 直接排到倒计时结束, 不进组队流程。
        cd = self.read_zone_countdown(zone_name)
        if cd and cd > 0:
            logger.info(f'界面显示 {zone_name} 还需 {cd}s 刷新次数, 本次跳过')
            self.set_next_run(task=TASK_NAME, finish=True, success=False,
                              server=False,
                              target=datetime.now() + timedelta(seconds=cd + 5))
            self.exit_task()
        if not self.create_room():
            self.exit_task()
        self.ensure_public()
        self.create_ensure()
        # 进入到了房间里面: 按身份等待队友并点击挑战
        if conf_team == TeamUserStatus.LEADER:
            if not self.enter_room_and_fire(conf_team, invite_config=conf.invite_config):
                logger.warning('Invite team member failed')
                self.exit_task()
        else:
            # ALONE: 保持原有行为——等路人 60s 后没等到就退出
            self.enter_room_and_fire(conf_team, random_wait=60)
        self.run_general_battle()
        # 打完一场 -> 消耗一次次数
        if conf_charge.charge_enable:
            task_state.consume_charge(cfg_name, TASK_NAME,
                                      max_charges=conf_charge.charge_max,
                                      slots=conf_charge.charge_slots)
        self.exit_task()

    def exit_task(self):
        """
        退出任务
        :return:
        """
        conf_buff = self.config.tako.tako_config
        self.goto_page(page_main)
        if conf_buff.enable:
            self.goto_page(page_main)
            self.open_buff()
            if conf_buff.buff_gold_50_click:
                self.gold_50(False)
            if conf_buff.buff_gold_100_click:
                self.gold_100(False)
            if conf_buff.buff_exp_50_click:
                self.exp_50(False)
            if conf_buff.buff_exp_100_click:
                self.exp_100(False)
            self.close_buff()

        self.set_next_run(task='Tako', success=True, finish=False)
        raise TaskEnd('Tako')

    def battle_wait(self, random_click_swipt_enable: bool) -> bool:
        # 重写
        self.device.stuck_record_add('BATTLE_STATUS_S')
        self.device.click_record_clear()
        # 战斗过程 随机点击和滑动 防封
        logger.info("Start battle process")
        while 1:
            self.screenshot()
            if self.appear(self.I_WIN) or self.appear(self.I_REWARD):
                logger.info('Win battle')
                self.ui_click_until_disappear(self.I_WIN)
                while 1:
                    self.screenshot()
                    if self.appear(self.I_CHECK_MAIN) or self.appear(self.I_CHECK_TEAM):
                        break
                    if self.click(self.C_REWARD_2, interval=2):
                        continue
                return True

            if self.appear(self.I_FALSE):
                logger.warning('False battle')
                self.ui_click_until_disappear(self.I_FALSE)
                return False

if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)
    t.screenshot()

    t.run()



