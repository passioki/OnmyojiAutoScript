# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from time import sleep
from typing import Union

from module.atom.click import RuleClick
from module.atom.long_click import RuleLongClick
from module.atom.ocr import RuleOcr
from module.base.timer import Timer
from module.logger import logger

from tasks.base_task import BaseTask
from tasks.GameUi.assets import GameUiAssets
from tasks.Component.GeneralInvite.assets import GeneralInviteAssets
from tasks.Component.GeneralInvite.config_invite import InviteConfig, InviteNumber, FindMode
from tasks.Component.SwitchSoul.assets import SwitchSoulAssets


# switch_soul_by_name 里"按名字找目标阵容"的最大尝试次数。
# 为什么需要: 这两处原本是 `while 1` 无界循环, 目标阵容名不在列表里时
# (OCR 失配 / 配置写错 / 该阵容其实在别的分组)会一直滑动或点击, 直到 device 的
# 卡死看门狗抛 GameStuckError 并把**整局任务**判死重启游戏。
# 线上实测 2026-10-08 11:55(日轮之陨): 阵容列表为 ['安魂冢','真蛇'], 目标 '日轮'
# 不在其中, 循环持续约 60s 后被看门狗判死并重启游戏。
# 切换御魂本身是可选项 —— 找不到就跳过, 让任务继续跑, 远好于重启游戏。
# 取 30 次: 每次含一次截图+OCR(约 0.4~1.1s), 相当于 20~30 秒的搜索预算。
SS_TEAM_FIND_MAX_ATTEMPTS = 30

# "切换御魂"阶段的兜底时限(秒)。正常流程是点 4 次, 约 6 秒完成;
# 若 I_SOU_SWITCH_SURE 与目标阵容都识别不到, 原来的 `while 1` 会一直转。
SS_SOUL_SWITCH_TIMEOUT = 30

# 双向扫描里"朝一个方向最多滑几次"。
# 一屏约显示 3 项预设, 常见分组也就几项; 12 次足够覆盖到列表尽头。
# 两个方向各 12 次 → 最多 24 次滑动(每次含截图+OCR 约 1.5~2.5s)。
SS_SCAN_MAX_SWIPES = 12



def switch_parser(switch_str: str) -> tuple:
    switch_list = switch_str.split(',')
    if len(switch_list) != 2:
        raise ValueError('Switch_str must be 2 length')
    return int(switch_list[0]), int(switch_list[1])


class SwitchSoul(BaseTask, SwitchSoulAssets):

    def goto_shikigami_records(self, button):
        """
        进入式神录
        """
        while 1:
            self.screenshot()
            if self.appear(GameUiAssets.I_CHECK_RECORDS):
                break
            if self.appear_then_click(button, interval=1.5):
                continue
        logger.info('Entry shikigami records')

    def exit_shikigami_records(self) -> None:
        """
        退出式神录的界面
        :return:
        """
        while 1:
            self.screenshot()
            if not self.appear(self.I_SOU_CHECK_IN):
                break
            if self.appear_then_click(self.I_RECORD_SOUL_BACK, interval=3.5):
                continue
        logger.info('Exit shikigami records')


    def run_switch_soul(self, target: tuple | list[tuple] | str):
        """
        保证在式神录的界面
        :return:
        """
        if isinstance(target, str):
            try:
                target = switch_parser(target)
            except ValueError:
                logger.error('Switch soul config error')
                return
        self.click_preset()
        self.switch_souls(target)

    def click_preset(self) -> None:
        """
        点击预设
        :return:
        """
        while 1:
            self.screenshot()
            if self.appear(self.I_SOU_SWITCH_1):
                break
            if self.appear(self.I_SOU_SWITCH_2):
                break
            if self.appear(self.I_SOU_SWITCH_3):
                break
            if self.appear(self.I_SOU_SWITCH_4):
                break
            if self.appear(self.I_SOU_TEAM_PRESENT):
                break
            if self.appear(self.I_SOUL_PRESET):
                self.click(self.I_SOUL_PRESET, interval=3)
                continue
        logger.info('Click preset in switch soul')

    def switch_soul_one(self, group: int, team: int) -> None:
        """
        设置一个队伍的预设御魂
        :param group: 只能是[1-7]
        :param team: 只能是[1-4]
        :return:
        """

        def get_group_assets(group: int) -> tuple:
            match = {
                1: tuple([self.C_SOU_GROUP_1, self.I_SOU_CHECK_GROUP_1]),
                2: tuple([self.C_SOU_GROUP_2, self.I_SOU_CHECK_GROUP_2]),
                3: tuple([self.C_SOU_GROUP_3, self.I_SOU_CHECK_GROUP_3]),
                4: tuple([self.C_SOU_GROUP_4, self.I_SOU_CHECK_GROUP_4]),
                5: tuple([self.C_SOU_GROUP_5, self.I_SOU_CHECK_GROUP_5]),
                6: tuple([self.C_SOU_GROUP_6, self.I_SOU_CHECK_GROUP_6]),
                7: tuple([self.C_SOU_GROUP_7, self.I_SOU_CHECK_GROUP_7]),
            }
            return match[group]

        def get_team_asset(team: int):
            match = {
                1: self.I_SOU_SWITCH_1,
                2: self.I_SOU_SWITCH_2,
                3: self.I_SOU_SWITCH_3,
                4: self.I_SOU_SWITCH_4,
            }
            return match[team]

        # 滑动至分组最上层(分組過多, 导致第一个分组显示不全)
        cur_text = ""
        while 1:
            self.screenshot()
            compare1 = self.O_SS_GROUP_NAME.detect_and_ocr(self.device.image)
            ocr_text = str([result.ocr_text for result in compare1])
            # 相等时 滑动到最上层
            if cur_text == ocr_text:
                break
            cur_text = ocr_text
            # 向上滑动
            self.swipe(self.S_SS_GROUP_SWIPE_UP, 1.5)
            # 等待滑动动画
            sleep(0.5)

        if group < 1 or group > 7:
            raise ValueError('Switch soul_one group must be in [1-7]')
        if team < 1 or team > 4:
            raise ValueError('Switch soul_one team must be in [1-4]')
        # 这一步是选择组
        target_click, target_check = get_group_assets(group)
        # while 1:
        #     self.screenshot()
        #     if self.click(target_click, interval=1):
        #         continue
        #     if self.appear(target_check):
        #         break
        # 2023.8.5 修改为无反馈的点击切换
        for i in range(2):
            self.click(target_click)
            sleep(0.5)
        # 点击队伍
        target_team = get_team_asset(team)
        for i in range(3):
            sleep(0.8)
            self.screenshot()
            if self.appear(self.I_SOU_SWITCH_SURE):
                while 1:
                    self.click(self.I_SOU_SWITCH_SURE, 3)
                    self.screenshot()
                    if self.appear_then_click(self.I_CHECK_BLOCK, 3):
                        continue
                    if not self.appear(self.I_SOU_SWITCH_SURE):
                        break
                continue
            if not self.appear_then_click(target_team, interval=3):
                logger.warning(f'Click team {team} failed in group {group}')
        # 兜底若还出现确认按钮则点击
        self.ui_click_until_disappear(self.I_SOU_SWITCH_SURE)
        logger.info(f'Switch soul_one group {group} team {team}')

    def switch_souls(self, target: tuple or list[tuple]) -> None:
        """
        切换御魂
        :param target: [(1, 1), (2, 2), (3, 3), (4, 4)]  或者是单独的一个元组(4, 4) 第一个是组, 第二个是队伍
        :return:
        """
        if isinstance(target, tuple):
            target = [target]
        for group, team in target:
            group = int(group)
            team = int(team)
            self.switch_soul_one(group, team)

    def run_switch_soul_by_name(self, groupName, teamName):
        """
        保证在式神录的界面
        :return:
        """
        if isinstance(groupName, str) and isinstance(teamName, str):
            self.click_preset()
            self.switch_soul_by_name(groupName, teamName)

    def _scan_for_name(self, rule, target_name: str,
                       swipe_forward, swipe_backward,
                       swipe_sleep: float = 1.5) -> bool:
        """
        在可滑动列表里找 `target_name`, **先看当前屏, 再双向扫描**。

        为什么不沿用原来的单向 `while 1`: 原实现是"先滑再看", 于是
        1) 目标本来就在当前屏时, 第一下就把它滑走了;
        2) 而且只朝一个方向翻 —— 一旦划过头(目标被推到可视区之外)就再也回不来;
        3) 列表一屏只显示约 3 项, 滑过一次就会永久错过。

        线上实测 2026-10-08 11:55(日轮之陨): 阵容列表一屏只显示 3 个预设,
        目标 '日轮' 本来在最上面, 被 `S_SS_TEAM_SWIPE_UP`(朝"更靠前"方向翻)
        推到了可视区上方, 之后一直 OCR 不到, 循环空转 60s 被看门狗判死重启游戏。

        现在的做法: 当前屏 → 朝 swipe_forward 扫到尽头 → 换 swipe_backward 回扫。
        因此无论目标在列表的哪一端、当前停在何处, 都不会被跳过。
        仍未找到则返回 False(调用方跳过切换, 不要让整局任务卡死)。

        :param rule: 带 keyword 的 RuleOcr 实例(调用方负责设置 keyword)
        :param swipe_forward: 朝"更靠后"方向翻的滑动(会浮现列表下方的项)
        :param swipe_backward: 朝"更靠前"方向翻的滑动(会浮现列表上方的项)
        :return: 最终是否能在屏幕上看到目标
        """
        def seen() -> bool:
            self.screenshot()
            texts = [r.ocr_text for r in rule.detect_and_ocr(self.device.image)]
            return bool(set(texts).intersection({target_name}))

        # 1) 先看当前屏 —— 目标可能已经可见, 不要先滑
        if seen():
            return True
        # 2) 朝一个方向扫到尽头
        for _ in range(SS_SCAN_MAX_SWIPES):
            self.swipe(swipe_forward)
            sleep(swipe_sleep)
            if seen():
                return True
        # 3) 换方向回扫, 覆盖"目标在另一端 / 之前划过头"的情况
        for _ in range(SS_SCAN_MAX_SWIPES):
            self.swipe(swipe_backward)
            sleep(swipe_sleep)
            if seen():
                return True
        return seen()

    def switch_soul_by_name(self, groupName, teamName):
        """
        保证在式神录的界面
        :return:
        """
        logger.hr('Switch soul by name')
        # 滑动至分组最上层
        last_group_text = ''
        while 1:
            self.screenshot()
            compare1 = self.O_SS_GROUP_NAME.detect_and_ocr(self.device.image)
            now_group_text = str([result.ocr_text for result in compare1])
            if now_group_text == last_group_text:
                break
            self.swipe(self.S_SS_GROUP_SWIPE_UP, 2)
            sleep(2.5)
            last_group_text = now_group_text
        logger.info('Swipe to top of group')

        # 判断有无目标分组
        # 先看当前屏再双向扫描, 避免"先滑再看"把已在屏上的目标滑走, 也避免划过头后回不来。
        # 分组列表方向: SWIPE_UP 的内容移动方向与阵容列表一致。
        self.O_SS_GROUP_NAME.keyword = groupName
        if not self._scan_for_name(self.O_SS_GROUP_NAME, groupName,
                                   self.S_SS_GROUP_SWIPE_UP,
                                   self.S_SS_GROUP_SWIPE_DOWN,
                                   swipe_sleep=1.5):
            logger.warning(
                f'切换御魂: 双向扫描后仍未找到目标分组 {groupName!r}, 跳过本次切换'
            )
            return
        logger.info('Found target group')

        # 选中分组
        selected_group = False
        for _ in range(SS_TEAM_FIND_MAX_ATTEMPTS):
            self.screenshot()
            self.O_SS_GROUP_NAME.keyword = groupName
            if self.ocr_appear_click(self.O_SS_GROUP_NAME):
                selected_group = True
                break
        if not selected_group:
            logger.warning(f'切换御魂: 未能点中目标分组 {groupName!r}, 跳过本次切换')
            return
        logger.info(f'Select group {groupName}')

        # 滑动至阵容最上层
        last_team_text = ''
        while 1:
            self.screenshot()
            compare1 = self.O_SS_TEAM_NAME.detect_and_ocr(self.device.image)
            now_team_text = str([result.ocr_text for result in compare1])
            # 向上滑动
            if now_team_text == last_team_text:
                break
            self.swipe(self.S_SS_TEAM_SWIPE_DOWN, 1.5)
            sleep(2)
            last_team_text = now_team_text
        logger.info('Swipe to top of team')

        # 判断当前分组有无目标阵容
        # 先看当前屏再双向扫描。原实现是"先滑再看"且只朝一个方向:
        # 一屏只显示约 3 个预设, 目标本来在最上面时会被 SWIPE_UP(朝"更靠前"方向翻)
        # 推到可视区上方, 之后永远 OCR 不到 —— 实测 2026-10-08 11:55 就是这样空转
        # 60s 被看门狗判死重启游戏(目标 '日轮' 本来在列表里, 用户确认是划过头了)。
        self.O_SS_TEAM_NAME.keyword = teamName
        if not self._scan_for_name(self.O_SS_TEAM_NAME, teamName,
                                   self.S_SS_TEAM_SWIPE_UP,
                                   self.S_SS_TEAM_SWIPE_DOWN,
                                   swipe_sleep=1.5):
            logger.warning(
                f'切换御魂: 双向扫描后仍未找到目标阵容 {teamName!r}, 跳过本次切换'
            )
            return
        logger.info('Found target team')

        # 选中分组
        # 同样必须限次: 找不到目标时这里会一直点击, 直到看门狗重启游戏。
        selected = False
        for _ in range(SS_TEAM_FIND_MAX_ATTEMPTS):
            self.screenshot()
            self.O_SS_TEAM_NAME.keyword = teamName
            if self.ocr_appear_click(self.O_SS_TEAM_NAME):
                selected = True
                break
        if not selected:
            logger.warning(
                f'切换御魂: 未能点中目标阵容 {teamName!r}, 跳过本次切换'
            )
            return
        logger.info(f'Select team {teamName}')
        # 切换御魂
        # 这两个退出条件都依赖识别成功: cnt_click 只在 OCR 命中目标阵容时递增;
        # I_SOU_SWITCH_SURE 也要识别到才会点击。若两者都识别不到, 循环会一直转,
        # 直到看门狗判死重启游戏。加一个时间上限兜底(正常流程 4 次点击约 6s)。
        cnt_click: int = 0
        self.O_SS_TEAM_NAME.keyword = teamName
        switch_timer = Timer(SS_SOUL_SWITCH_TIMEOUT).start()
        while 1:
            self.screenshot()
            if cnt_click >= 4:
                break
            if switch_timer.reached():
                logger.warning(
                    f'切换御魂: {SS_SOUL_SWITCH_TIMEOUT}s 内未能完成切换'
                    f'(已点击 {cnt_click} 次), 放弃本次切换'
                )
                break
            if self.appear_then_click(self.I_SOU_SWITCH_SURE, interval=0.8):
                continue
            if self.ocr_appear_click_by_rule(self.O_SS_TEAM_NAME, self.I_SOU_CLICK_PRESENT, interval=1.5):
                cnt_click += 1
                continue
        logger.info(f'Switch soul_one group {groupName} team {teamName}')

    def ocr_appear_click_by_rule(self,
                                 target: RuleOcr,
                                 action: Union[RuleClick, RuleLongClick] = None,
                                 interval: float = None,
                                 duration: float = None) -> bool:
        """
        ocr识别目标，如果目标存在，则触发动作
        :param target:
        :param action:
        :param interval:
        :param duration:
        :return:
        """
        appear = self.ocr_appear(target, interval)

        if not appear:
            return False

        x1, y1, w1, h1 = target.area
        x, y = action.coord()

        self.device.click(x=x, y=y1, control_name=target.name)
        return True


if __name__ == '__main__':
    from module.config.config import Config
    from module.device.device import Device

    c = Config('oas1')
    d = Device(c)
    s = SwitchSoul(c, d)

    s.click_preset()
    # s.switch_soul_one(4, 1)
    # s.switch_soul_by_name('契灵', '茨球')
    s.switch_soul_by_name('默认分组', '队伍5')
