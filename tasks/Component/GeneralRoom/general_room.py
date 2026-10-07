# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import time
import random
import re
import cv2
import numpy as np

from random import randint

from tasks.Component.GeneralRoom.assets import GeneralRoomAssets
from module.atom.ocr import RuleOcr
from module.atom.image import RuleImage
from tasks.base_task import BaseTask
from module.logger import logger
from module.base.timer import Timer


class GeneralRoom(BaseTask, GeneralRoomAssets):

    def create_room(self) -> bool:
        """
        创建队伍  一般是下方的黄色按钮
        :return:
        """
        logger.info('Create room')
        if not self.appear(self.I_CREATE_ROOM):
            logger.warning('No create room button')
            return False
        click_number = 0
        while 1:
            self.screenshot()
            if click_number > 3:
                logger.warning('Create room button do not take effect')
                logger.warning('The most possible reason is that there are not challenge tickets')
                return False
            if self.appear_then_click(self.I_CREATE_ROOM, interval=2):
                click_number += 1
                continue
            if self.appear(self.I_CREATE_ENSURE):
                return True
            if self.appear(self.I_CREATE_ENSURE_2):
                return True

    def ensure_private(self) -> bool:
        """
        确认私人房间, 不公开仅邀请
        :return:
        """
        logger.info('Ensure private')
        while 1:
            self.screenshot()
            if self.appear(self.I_ENSURE_PRIVATE):
                return True
            if self.appear(self.I_ENSURE_PRIVATE_2):
                return True
            if self.appear_then_click(self.I_ENSURE_PRIVATE_FALSE, interval=1):
                continue
            if self.appear_then_click(self.I_ENSURE_PRIVATE_FALSE_2, interval=1):
                continue

    def ensure_public(self) -> bool:
        """
        确认公开房间， 允许任何人加入
        :return:
        """
        logger.info('Ensure public')
        while 1:
            self.screenshot()
            if self.appear(self.I_ENSURE_PUBLIC):
                return True
            if self.appear(self.I_ENSURE_PUBLIC_2):
                return True
            if self.appear_then_click(self.I_ENSURE_PUBLIC_FALSE, interval=1):
                continue
            if self.appear_then_click(self.I_ENSURE_PUBLIC_FALSE_2, interval=1):
                continue

    def create_ensure(self) -> bool:
        """
        创建确认
        :return:
        """
        logger.info('Create ensure')
        appear1 = self.I_CREATE_ENSURE.match(self.device.image)
        appear2 = self.I_CREATE_ENSURE_2.match(self.device.image)
        target = None
        if appear1:
            target = self.I_CREATE_ENSURE
        elif appear2:
            target = self.I_CREATE_ENSURE_2
        if not target:
            logger.warning('No create ensure button')
            return False

        while 1:
            self.screenshot()
            if self.appear_then_click(target, interval=1.5):
                continue
            if not self.appear(target):
                return True

    def exit_team(self) -> bool:
        """
        在组队界面 退出组队的界面， 返回到庭院或者是你一开始进入的入口
        :return:
        """
        if self.appear(self.I_CHECK_TEAM):
            logger.info('Exit team ui')
            while 1:
                self.screenshot()
                if not self.appear(self.I_CHECK_TEAM):
                    return True
                if self.appear_then_click(self.I_GR_BACK_YELLOW, interval=0.5):
                    continue

    @staticmethod
    def parse_countdown_text(text: str):
        """
        把"便捷组队"页上的倒计时文本解析成秒数。

        该页倒计时为中文格式, 例如 '2分9秒' / '0分5秒' / '35秒' / '1时2分3秒',
        而 module/ocr/sub_ocr.py 的 Duration.parse_time 只认 'HH:MM:SS',
        因此这里单独解析。

        :param text: OCR 出的文本, 例如 '0分21秒'
        :return: 秒数(int); 无法解析时返回 None
        """
        if not text:
            return None
        t = str(text).strip()
        # 归一化易混字符
        t = t.replace('O', '0').replace('o', '0').replace('I', '1').replace('l', '1')
        total = 0
        matched = False
        for num, unit in re.findall(r'(\d+)\s*([时分秒])', t):
            matched = True
            n = int(num)
            if unit == '时':
                total += n * 3600
            elif unit == '分':
                total += n * 60
            else:
                total += n
        if not matched:
            return None
        return total

    def read_zone_countdown(self, zone_name: str):
        """
        在"便捷组队"页读取指定玩法的"次数刷新倒计时"。

        实测(游戏 1280x720, 便捷组队/同心队 页): 左侧玩法列表的条目名下方会显示该
        玩法的刷新倒计时, 且**仅在次数已用尽时出现**; 仍有次数时不显示。
        实测(条目名 y -> 倒计时文本 y, x≈145~230):
            彼世逢魔 y≈174 -> 301   妖气封印 y≈248 -> (无)
            经验妖怪 y≈321 -> 301   金币妖怪 y≈394 -> 376
            年兽 y≈464 -> (无)      石距 y≈541 -> (无)
        注意: 倒计时出现在条目名**上方**约 20px, 因此按实测取固定的 x 区间,
        并以条目名 y 为基准向上、向下各留一些余量做 OCR。

        :param zone_name: 玩法名, 如 '经验妖怪' / '金币妖怪' / '石距'
        :return: 倒计时秒数(int); 未显示倒计时(即仍有次数)时返回 0;
                 无法定位条目时返回 None
        """
        try:
            self.screenshot()
            image = self.device.image
            if image is None:
                return None

            # 1) 找到该玩法条目名在左栏的位置(L_TEAM_LIST 是既有资产)
            pos = self.list_find(self.L_TEAM_LIST, zone_name)
            if not pos:
                logger.warning(f'read_zone_countdown: 左栏未找到 {zone_name}')
                return None
            _, zone_y = pos

            # 2) 倒计时位于条目名**上方**约 20px(实测: '5分36秒' y=303-326 在
            #    '经验妖怪' y=322-357 之上), 故取条目名上方一条来做 OCR。
            x0, x1 = 130, 250
            y0 = max(0, int(zone_y) - 48)
            y1 = max(y0 + 1, int(zone_y) - 2)

            # 3) 借用一个 RuleOcr 做检测+识别(它的 roi 会被 crop 使用, 与模式无关)
            probe = RuleOcr(roi=(x0, y0, x1 - x0, y1 - y0), area=(x0, y0, x1 - x0, y1 - y0),
                            mode='Full', method='Default', keyword='', name='zone_countdown')
            results = probe.detect_and_ocr(image)
            for r in results:
                sec = self.parse_countdown_text(getattr(r, 'ocr_text', ''))
                if sec is not None:
                    logger.info(f'{zone_name} 次数刷新倒计时: {r.ocr_text!r} ({sec}s)')
                    return sec
            # 没读到倒计时 -> 视为仍有次数
            return 0
        except Exception as exc:
            logger.warning(f'read_zone_countdown({zone_name}) 异常: '
                           f'{type(exc).__name__}: {exc}')
            return None

    def check_zones(self, name: str) -> bool:
        """
        确认副本的名称，并选中
        :param name:
        :return:
        """
        pos = self.list_find(self.L_TEAM_LIST, name)
        if not pos:
            return False
        if name == '愤怒的石距' or name == '喷怒的石距':
            name = '价悠的石距'
        self.O_GR_ZONES_NAME.keyword = name
        click_timer = Timer(1.1)
        click_timer.start()
        while 1:
            self.screenshot()

            if self.ocr_appear(self.O_GR_ZONES_NAME):
                break
            # https://github.com/runhey/OnmyojiAutoScript/issues/488
            # 只能说朴实无华
            text_ocr = self.O_GR_ZONES_NAME.ocr(self.device.image)
            if name == '石距' and name in text_ocr:
                break
            if name == '金币妖怪' and "金币" in text_ocr:
                break
            if name == '经验妖怪' and '经验' in text_ocr:
                break
            if click_timer.reached():
                click_timer.reset()
                self.device.click(x=pos[0] + randint(-5, 5), y=pos[1] + randint(-5, 5))

        return True

