# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from datetime import datetime

from tasks.Restart.config_scheduler import Scheduler
from tasks.Restart.login import LoginHandler
from tasks.Restart.assets import RestartAssets
from tasks.base_task import BaseTask, Time
from datetime import datetime, time

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
        # 如果启用了定时领体力（每天 12-14、20-22 时内各有 20 体力）
        if self.config.restart.harvest_config.enable_ap:
            # ★★ ⑥(b): 有窗口就用**窗口**, 否则保留旧行为 ★★
            #
            # `harvest_config.enable_ap` 的语义 = "**每天 12:00 与 20:00 各领一次**"。
            # 用户的三条裁定（台账 §21.1 / §20.2）:
            #   * 窗口只回答"这个时间可不可以跑"
            #   * "跑几次"由次数或重复条目体现
            #   * 排期只用窗口
            #
            # 但"一天领两次"**既不是窗口、也不是次数、也不是重复条目** ——
            # 它是**第 4 种**语义。已为它加了 `window_slots`（每日固定时刻）:
            #
            #     scheduler.window_enable = true
            #     scheduler.window_slots  = '12:00,20:00'
            #
            # 那样窗口就是 12:00-14:00 与 20:00-22:00 两段, "一天两次"由
            # **窗口开放次数**自然表达, 不再需要任务自排期。
            #
            # ★ 用户**没配**窗口时保留旧行为 —— 否则会改变既有用户的调度
            #   （#10.5 不猜语义 / 不做会静默改变行为的改动）。
            sch = self.config.restart.scheduler
            if getattr(sch, 'window_enable', False) and \
                    str(getattr(sch, 'window_slots', '') or '').strip():
                logger.info('Restart: 用 window_slots 排期（不再自排期）')
                # 已经 `set_next_run(success=True)` -> 由窗口对齐到下次开放
            else:
                now = datetime.now()
                # 如果时间在00:00-12:00之间则设定时间为当日 12 时
                if now.time() < time(12, 0):
                    self.custom_next_run(task='Restart', custom_time=Time(12, 0), time_delta=0)
                # 如果时间在12:00-20:00之间则设定时间为当日 20 时
                elif now.time() >= time(12, 0) and now.time() < time(20, 0):
                    self.custom_next_run(task='Restart', custom_time=Time(20, 0), time_delta=0)
                # 如果时间在20:00-23:59之间则设定时间为次日 12 时
                else:
                    self.custom_next_run(task='Restart', custom_time=Time(12, 0), time_delta=1)

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









