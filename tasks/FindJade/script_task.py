import importlib
from datetime import datetime, timedelta

from module.exception import TaskEnd, RequestHumanTakeover
from module.logger import logger
from tasks.Component.SwitchAccount.switch_account import SwitchAccount
from tasks.FindJade import WantedQuestsEx
from tasks.FindJade.assets import FindJadeAssets
from tasks.FindJade.config import AccountInfo, FindJade
from tasks.GameUi.game_ui import GameUi


class ScriptTask(GameUi, FindJadeAssets):
    fade_conf: FindJade= None

    def run(self):
        self.fade_conf = self.config.find_jade

        for accountInfo in self.fade_conf.sup_account_list:
            # ★★★ 任务级暂停安全点（A 方案的排除名单任务）★★★
            #
            # 用户确认: 第一件按 **A**（框架级兜底）做。
            # ⚠ 但 `FindJade` 在**排除名单**里（它会给真人发邀请 ——
            #   中途停下会让队友干等, 不可回滚）, 所以框架级 `screenshot()`
            #   检查**不覆盖**它。
            #
            # ★ 所以这里手放一个**任务级**安全点: 位置在**账号切换的间隙**
            #   —— 当前账号已完整跑完（登录 / 找勾协 / 保存历史都做完）,
            #   下一个账号还没登录。中断在这里**不会留下半个账号的状态**。
            from tasks.base_task import BaseTask  # noqa: F401  (类型提示用)
            self.raise_if_paused()
            logger.info("start %s-%s ", accountInfo.character, accountInfo.svr)
            if not self.is_need_login(accountInfo):
                logger.warning("%s Skipped last Login Time:%s", accountInfo.character, accountInfo.last_complete_time)
                continue
            suc = SwitchAccount(self.config, self.device, accountInfo).switchAccount()
            if not suc:
                logger.warning("switch to %s-%s Failed", accountInfo.character, accountInfo.svr)
                continue
            #
            wq = self.CreatObjectFromModule("WantedQuests", config=self.config, device=self.device)
            wq.fade_conf = self.fade_conf

            try:
                wq.run()
            except TaskEnd as e:
                logger.warning("%s-%s TaskEnd", accountInfo.character, accountInfo.svr)
                # 更新配置文件中的时间
                self.fade_conf.update_account_login_history(accountInfo)
                self.save_config()
                continue
            except RequestHumanTakeover as e:
                raise
            except Exception as e:
                logger.error(e)
                self.next_run("FindJade", success=False)
        self.next_run("FindJade", success=True)
        raise TaskEnd("FindJade")
        pass


    def is_need_login(self, item: AccountInfo):
        """
            根据上次登陆时间 判断是否需要登录查找
        @param item:
        @type item:
        """
        lastTime = item.last_complete_time
        now = datetime.now()
        if now - lastTime > timedelta(hours=13):
            return True
        if (lastTime.hour >= 18 or lastTime.hour < 5) and (18 > now.hour >= 5):
            return True
        if (5 <= lastTime.hour < 18) and now.hour >= 18:
            return True
        return False

    def CreatObjectFromModule(self, task_name: str, **kwargs):
        module_name = 'script_task'
        from pathlib import Path
        module_path = str(Path.cwd() / 'tasks' / task_name / (module_name + '.py'))

        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        WQEX = type("WQEX", (module.ScriptTask,), {
            "need_invite_vip": WantedQuestsEx.need_invite_vip,
            "get_invite_vip_name": WantedQuestsEx.get_invite_vip_name,
            "next_run": WantedQuestsEx.next_run,
            "invite_success_callback": WantedQuestsEx.invite_success_callback,
            "get_config": WantedQuestsEx.get_config
        })
        wq = WQEX(**kwargs)
        return wq

    def save_config(self):
        self.config.save()

    def next_run(self, task: str, finish: bool = False,
                 success: bool = None, server: bool = True, target: datetime = None) -> None:
        now = datetime.now()
        if success:
            if 5 <= now.hour < 18:
                self.set_next_run(task, target=now.replace(hour=18, minute=5))
            elif now.hour < 5:
                self.set_next_run(task, target=now.replace(hour=5, minute=5))
            else:
                self.set_next_run(task, target=now.replace(hour=18, minute=5) + timedelta(days=1))
        else:
            self.set_next_run(task, target=now + timedelta(minutes=10))


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device
    # from mypatch import SimplePatch

    # SimplePatch.patch()

    c = Config('oas1')
    d = Device(c)
    t = ScriptTask(c, d)

    t.run()
