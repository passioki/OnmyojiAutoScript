# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import datetime

from tasks.Restart.config_scheduler import Scheduler
from tasks.Restart.login import LoginHandler
from tasks.Restart.assets import RestartAssets
from tasks.base_task import BaseTask

from module.logger import logger
from module.exception import TaskEnd, RequestHumanTakeover


class ScriptTask(LoginHandler):

    def run(self) -> None:
        """
        主要就是登录的模块
        :return:
        """
        if not self.delay_pending_tasks():
            self.app_restart()
        raise TaskEnd('ScriptTask end')

    def app_stop(self):
        logger.hr('App stop')
        self.device.app_stop()

    def app_start(self):
        logger.hr('App start')
        self.device.app_start()
        self.app_handle_login()
        # self.ensure_no_unfinished_campaign()

    def app_restart(self):
        logger.hr('App restart')
        self.device.app_stop()
        self.device.app_start()
        self.app_handle_login()

        # self.config.task_delay(server_update=True)
        self.set_next_run(task='Restart', success=True, finish=True, server=True)
        # ★★ 用户最终裁定（2026-10-10）: **删掉任务内自排期** ★★
        #
        # 用户原话:
        #   "删 custom_next_run, **用户没配窗口, 代表着这个只能按照排序依次执行**,
        #    而不是通过 custom_next_run 来调度。"
        #   "能重构就重构, **不要做冗余代码适配**, 这会让后期维护变得困难。"
        #
        # 所以这里**不再**按 `enable_ap` 手工排 12:00 / 20:00 —— 那是任务内自排期,
        # 与"窗口是唯一排期依据 + 队列顺序"是两套机制。
        #
        # 领体力的"一天两次"现在由**窗口**表达:
        #
        #     scheduler.window_enable = true
        #     scheduler.window_slots  = '12:00,20:00'    -> 12:00-14:00 与 20:00-22:00
        #
        # **没配窗口** -> 就按队列顺序依次执行（不再自排期）。
        if self.config.restart.harvest_config.enable_ap:
            logger.info('Restart: 领体力时段由**窗口**决定'
                        '（如需每天 12/20 点各一次, 请设 window_slots）')

    def delay_pending_tasks(self) -> bool:
        """
        周三更新游戏的时候延迟
        @return:
        """
        datetime_now = datetime.now()
        if not (datetime_now.weekday() == 2 and 6 <= datetime_now.hour <= 8):
            return False
        logger.info("The game server is updating, delay the pending tasks to 9:00")
        logger.warning('Delay pending tasks')
        # running 中的必然是 Restart
        for task in self.config.pending_task:
            print(task.command)
            self.set_next_run(task=task.command, target=datetime_now.replace(hour=9, minute=0, second=0, microsecond=0))
        self.set_next_run(task='Restart', success=True, finish=True, server=True)
        return True


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    config = Config('oas1')
    device = Device(config)
    task = ScriptTask(config, device)
    for i in range(3):
        task.app_restart()
    # task.config.update_scheduler()
    # task.delay_pending_tasks()









