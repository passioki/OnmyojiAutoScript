# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

# 必须放在文件最顶部(早于任何其他 import):
# Windows 中文版下标准输出默认按 GBK 编码, 而终端/OASX 按 UTF-8 读取, 会导致日志
# 中文与制表符乱码。下面的 module.logger 会经由其他导入被间接加载并在导入期输出,
# 因此本设置必须早于它们执行。详见 module/base/encoding.py
import os
import sys

from module.base.encoding import setup_utf8_stdio

setup_utf8_stdio()

from functools import wraps
import zerorpc
import zmq
import msgpack
import random
import re
import cv2
import time
import os
import inflection
import asyncio
import json

from datetime import date
import threading
from typing import Callable
from datetime import datetime, timedelta
from pathlib import Path
from cached_property import cached_property
from pydantic import BaseModel, ValidationError
from threading import Thread
from multiprocessing.queues import Queue


from module.config.utils import convert_to_underscore
from module.config.config import Config
from module.config.config_model import ConfigModel
from module.config.instance_guard import InstanceGuard
from module.config.anti_ban import AntiBanGuard
from module.config import run_control
from module.device.device import Device
from module.device.env import IS_WINDOWS
from module.base.utils import load_module
from module.base.decorator import del_cached_property
from module.logger import logger
from module.exception import *
from module.server.i18n import I18n
from module.ocr.rpc import ensure_ocr_server_started



_log_switch_lock = threading.Lock()#线程锁


class Script:
    def __init__(self, config_name: str ='oas') -> None:
        logger.hr('Start', level=0)
        self.server = None
        self.state_queue: Queue = None
        self._emulator_down = False
        self.gui_update_task: Callable = None  # 回调函数, gui进程注册当每次config更新任务的时候更新gui的信息
        self.config_name = config_name
        # Skip first restart
        self.is_first_task = True
        # Failure count of tasks
        # Key: str, task name, value: int, failure count
        self.failure_record = {}
        # 本次 run() 是否算作任务失败, 供 loop() 累计 failure_record。
        # 由 run() 的各 except 分支设置: 能在"任务级"处理的异常置 True 并让实例继续运行,
        # 而不是直接 exit(1) 终止整个实例(那样会连带停掉其它所有任务)。
        self._task_failed = False
        # 运行loop的线程
        self.loop_thread: Thread = None
        # 跨进程排队管理器（仅在 queue_mode=True 时初始化）
        self.instance_guard: InstanceGuard = None
        self.anti_ban_guard: AntiBanGuard = AntiBanGuard()

    @cached_property
    def config(self) -> "Config":
        try:
            from module.config.config import Config
            config = Config(config_name=self.config_name)
            return config
        except RequestHumanTakeover:
            logger.critical('Request human takeover')
            exit(1)
        except Exception as e:
            logger.exception(e)
            exit(1)

    @cached_property
    def device(self) -> "Device":
        try:
            from module.device.device import Device
            device = Device(config=self.config)
            return device
        except RequestHumanTakeover:
            logger.critical('Request human takeover')
            exit(1)
        except Exception as e:
            logger.exception(e)
            exit(1)

    def save_error_log(self):
        """
        Save last 60 screenshots in ./log/error/<timestamp>
        Save logs to ./log/error/<timestamp>/log.txt
        """
        from module.base.utils import save_image
        from module.handler.sensitive_info import (handle_sensitive_image,
                                                   handle_sensitive_logs)
        if self.config.script.error.save_error:
            if not os.path.exists('./log/error'):
                os.mkdir('./log/error')
            folder_name = str(int(time.time() * 1000))
            folder = f'./log/error/{folder_name}'
            logger.warning(f'Saving error: {folder}')
            logger.info('保存详细错误的日志和截图到路径:')
            logger.info(f'{str( Path.cwd() / "log" / "error" / folder_name)}')
            os.mkdir(folder)
            for data in self.device.screenshot_deque:
                image_time = datetime.strftime(data['time'], '%Y-%m-%d_%H-%M-%S-%f')
                image = handle_sensitive_image(data['image'])
                save_image(image, f'{folder}/{image_time}.png')
            with open(logger.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                start = 0
                for index, line in enumerate(lines):
                    line = line.strip(' \r\t\n')
                    if re.match('^═{15,}$', line):
                        start = index
                lines = lines[start - 2:]
                lines = handle_sensitive_logs(lines)
            with open(f'{folder}/log.txt', 'w', encoding='utf-8') as f:
                f.writelines(lines)

    def init_server(self, port: int) -> int:
        """
        初始化zerorpc服务，返回端口号
        :return:
        """
        self.server = zerorpc.Server(self)
        try:
            self.server.bind(f'tcp://127.0.0.1:{port}')
            return port
        except zmq.error.ZMQError:
            logger.error(f"Ocr server cannot bind on port {port}")
            return None

    def run_server(self) -> None:
        """
        启动zerorpc服务
        :return:
        """
        self.server.run()

    def gui_args(self, task: str) -> str:
        """
        获取给gui显示的参数
        :return:
        """
        return self.config.gui_args(task=task)

    def gui_menu(self) -> str:
        """
        获取给gui显示的菜单
        :return:
        """
        return self.config.gui_menu

    def gui_task(self, task: str) -> str:
        """
        获取给gui显示的任务 的参数的具体值
        :return:
        """
        return self.config.model.gui_task(task=task)

    def gui_set_task(self, task: str, group: str, argument: str, value) -> bool:
        """
        设置给gui显示的任务 的参数的具体值
        :return:
        """
        # 验证参数
        task = convert_to_underscore(task)
        group = convert_to_underscore(group)
        argument = convert_to_underscore(argument)
        # pandtic验证
        if isinstance(value, str):
            if len(value) == 8:
                try:
                    value = datetime.strptime(value, '%H:%M:%S').time()
                except ValueError:
                    pass


        path = f'{task}.{group}.{argument}'
        task_object = getattr(self.config.model, task, None)
        group_object = getattr(task_object, group, None)
        argument_object = getattr(group_object, argument, None)

        if argument_object is None:
            logger.error(f'Set arg {task}.{group}.{argument}.{value} failed')
            return False

        try:
            setattr(group_object, argument, value)
            argument_object = getattr(group_object, argument, None)
            logger.info(f'Set arg {task}.{group}.{argument}.{argument_object}')
            self.config.save()  # 我是没有想到什么方法可以使得属性改变自动保存的
            return True
        except ValidationError as e:
            logger.error(e)
            return False

    @zerorpc.stream
    def gui_mirror_image(self):
        """
        获取给gui显示的镜像
        :return: cv2的对象将 numpy 数组转换为字节串。接下来MsgPack 进行序列化发送方将图像数据转换为字节串
        """
        # return msgpack.packb(cv2.imencode('.jpg', self.device.screenshot())[1].tobytes())
        img = cv2.cvtColor(self.device.screenshot(), cv2.COLOR_RGB2BGR)
        self.device.stuck_record_clear()
        ret, buffer = cv2.imencode('.jpg', img)
        yield buffer.tobytes()

    def _gui_update_tasks(self) -> None:
        """
        获取更新任务后 pending waiting 的任务 和 当前的任务的数据。打包给gui显示
        :return:
        """
        data = {}
        pending = []
        waiting = []
        task = {}
        if self.config.task is not None and self.config.task.next_run < datetime.now():
            task["name"] = self.config.task.command
            task["next_run"] = str(self.config.task.next_run)
        data["task"] = task

        for p in self.config.pending_task[1:]:
            item = {"name": p.command, "next_run": str(p.next_run)}
            pending.append(item)

        for w in self.config.waiting_task:
            item = {"name": w.command, "next_run": str(w.next_run)}
            waiting.append(item)


        data["pending"] = pending
        data["waiting"] = waiting

        if self.gui_update_task is not None:
            self.gui_update_task(data)

    def _gui_set_status(self, status: str) -> None:
        """
        设置给gui显示的状态
        :param status: 可以在gui中显示的状态 有 "Init", "Empty"(不显示), "Run"(运行中), "Error", "Free"(空闲)
        :return:
        """
        data = {"status": status}
        if self.gui_update_task is not None:
            self.gui_update_task(data)

    def gui_task_list(self) -> str:
        """
        获取给gui显示的任务列表
        :return:
        """
        result = {}
        for key, value in self.config.model.dict().items():
            if isinstance(value, str):
                continue
            if key == "restart":
                continue
            if "scheduler" not in value:
                continue

            scheduler = value["scheduler"]
            item = {"enable": scheduler["enable"],
                    "next_run": str(scheduler["next_run"])}
            key = self.config.model.type(key)
            result[key] = item
        return json.dumps(result)

    def _release_token_before_wait(func):
        @wraps(func)
        def wrapper(self, future):
            if self.instance_guard and self.instance_guard.should_release(
                pending_task=self.config.pending_task,
                waiting_task=self.config.waiting_task,
                idle_threshold_minutes=self.config.script.optimization.queue_idle_threshold
            ):
                self.instance_guard.release()
            return func(self, future)
        return wrapper

    @_release_token_before_wait
    def wait_until(self, future):
        """
        Wait until a specific time.

        Args:
            future (datetime):

        Returns:
            bool: True if wait finished, False if config changed.
        """
        future = future + timedelta(seconds=1)
        self.config.start_watching()
        while 1:
            if datetime.now() > future:
                return True

            time.sleep(5)

            if self.config.should_reload():
                return False

    def get_next_task(self) -> str:
        """
        获取下一个任务的名字, 大驼峰。
        :return:
        """
        # ★★ P-3: 队列循环的**节流时间戳**（见下面 `when_task_queue_empty == 'loop'`）★★
        #
        # ⚠ 为什么需要它: 循环把 `next_run` 拉回现在 -> 立刻又有任务可跑 ->
        #   若某个任务**瞬间完成**（如"检查签到"几秒），会变成**热循环**。
        # ★ 用户裁定**不加最小间隔**（"用户自己可以选择添加休息时间来避免狂刷"），
        #   ★ 但**防热循环**是两回事 —— 那是**实现缺陷**，不是用户策略。
        #   所以这里给一个**很轻**的节流（默认 5 秒），只保证"不把 CPU 打满"。
        _loop_throttle_s = 5
        _loop_reset_at = None

        while True:
            # ---- 运行列表的「休息」条目 ----
            #
            # 休息条目**阻塞列表推进**（不像 task 那样只影响排序）——
            # 这就是它存在的意义: "执行到这一行时去庭院待着 N 分钟"。
            #
            # ★ `apply_run_list_blocker()` 内部会考虑「休息时可穿插定时任务」:
            #   若存在**能在休息剩余时间内跑完**的到点定时任务, 它会返回 False
            #   让那个任务先跑（判据见 `config.can_interleave_timed`）。
            try:
                if self.config.apply_run_list_blocker():
                    time.sleep(run_control.wait_seconds() or 15)
                    del_cached_property(self, "config")
                    continue
            except Exception as exc:
                logger.warning(f'运行列表阻塞检查失败({type(exc).__name__}: {exc}), '
                               f'按不阻塞处理')

            task = self.config.get_next()
            self.config.task = task
            if self.state_queue:
                self.state_queue.put({"schedule": self.config.get_schedule_data()})
            now = datetime.now()
            antiban_wake = self.anti_ban_guard.wake_time(now, self.config.script.anti_ban)
            if antiban_wake is not None:
                task.next_run = max(task.next_run, antiban_wake)
            if not self._try_acquire_queue_token():
                del_cached_property(self, "config")
                continue
            # 任务时间到了返回任务名称
            if task.next_run <= now:
                return task.command
            # 根据策略执行等待逻辑
            #
            # ★★★ P-3: **队列循环**（用户裁定）★★★
            #
            # > "循环任务是指**队列整体循环：跑完最后一条后从头再来**
            # >  （而不是停下 / 回庭院）"
            #
            # ★ 为什么在这里拦: 走到这一步 = "队首任务还没到点" =
            #   **没有可立即派发的任务**（= 用户说的"跑空"）。
            #   此时若策略是 `loop`，就把"该再来一轮"的任务 `next_run`
            #   拉回现在，然后 `continue` 让循环重新取任务。
            #
            # ⚠ 节流: `_loop_throttle_s` 秒内**只重置一次** ——
            #   防"瞬间完成的任务"造成热循环（那是**实现缺陷**, 不是用户策略）。
            #
            # ★★★ P-3b: **跑几轮**（用户裁定）★★★
            #
            # > "我觉得选中后应该加一个**跑几次**的额外输入框, **0代表一直跑**,
            # >   **1、2……代表跑几次**。"
            # > "如果要重跑这几次循环要怎么设置呢 …… 是不是得有个**手动重置
            # >  计数**的按钮" -> ★ 用户选 **乙**: 加「重置循环计数」按钮
            #
            # | 值 | 行为 |
            # |---|---|
            # | `loop_times = 0` | ★ **一直跑** |
            # | `loop_times = N` | ★ 跑 **N 轮**后**不再主动重排** -> 退化成
            #   `goto_main` 的行为（★ **到点的周期任务照常跑** —— 用户裁定"照常跑"）|
            #
            # ★ "已经跑了几轮" **存盘**（`task_state`）—— 重启后端不丢（用户选 B）。
            # ★ 只有用户点「重置循环计数」才清 0（用户选 乙）。
            try:
                if (str(self.config.script.optimization.when_task_queue_empty)
                        == 'loop'):
                    _now_loop = datetime.now()
                    if (_loop_reset_at is None
                            or (_now_loop - _loop_reset_at).total_seconds()
                            >= _loop_throttle_s):
                        from module.config import task_state as _ts
                        _times = int(getattr(self.config.script.optimization,
                                             'loop_times', 0) or 0)
                        _done = _ts.get_loop_rounds(self.config_name)
                        # ★ 0 = 一直跑；否则到轮数就**不再重排**（退化成回庭院待命）
                        if _times > 0 and _done >= _times:
                            _loop_reset_at = _now_loop
                            logger.info(
                                f'队列循环: 已跑满 {_done}/{_times} 轮 -> '
                                f'**停止循环**（回庭院待命; 到点的周期任务照常跑）。'
                                f'★ 想再跑 {_times} 轮请点「重置循环计数」')
                        else:
                            reset = self.config.reset_loop_next_run(_now_loop)
                            _loop_reset_at = _now_loop
                            if reset:
                                # ★ 一轮 = "把所有该跑的都跑了一遍" -> 记一轮
                                _n = _ts.bump_loop_rounds(self.config_name)
                                logger.info(
                                    f'队列循环: 第 {_n} 轮开始'
                                    + (f'（目标 {_times} 轮）' if _times > 0
                                       else '（不限轮数）'))
                                del_cached_property(self, "config")
                                continue
            except Exception as exc:
                logger.warning(f'队列循环重排失败({type(exc).__name__}: {exc}), '
                               f'按原策略等待')
            if not self._handle_wait_during_idle(task.next_run):
                # 若等待被打断, 则刷新配置
                del_cached_property(self, "config")

    def _try_acquire_queue_token(self) -> bool:
        """
        尝试获取排队执行权。
        如果排队模式未启用，返回 True。
        如果排队模式启用但未能获取到执行权，进入等待循环直到获取成功或配置变更。

        Returns:
            True: 获取得执行权，可以执行任务
            False: 等待被配置变更打断，调用方应重新加载配置后重试
        """
        # 是否开启排队模式
        if not self.config.script.optimization.queue_mode:
            if self.instance_guard:
                self.instance_guard.remove_from_queue()
                self.instance_guard = None
            return True

        # 懒加载instance_guard
        if self.instance_guard is None:
            try:
                self.instance_guard = InstanceGuard(self.config_name)
                logger.info(f"[Queue] Queue mode enabled for '{self.config_name}'")
            except Exception:
                self.instance_guard = None
                return True

        # 尝试获取执行权
        if self.instance_guard.try_acquire():
            return True

        # 执行权获取失败，关闭模拟器并进入等待循环
        logger.info(f"[Queue] '{self.config_name}' waiting for execution token...")
        if (self.config.script.optimization.when_task_queue_empty == 'close_game'
                and not self._emulator_down
                and 'device' in self.__dict__):
            try:
                self.device.emulator_stop()
                self._emulator_down = True
                logger.info(f"[Queue] Emulator closed during queue wait")
            except Exception:
                pass
        self.config.start_watching()
        while True:
            time.sleep(30)

            if self.config.should_reload():
                logger.info(f"[Queue] Config changed, re-evaluating")
                return False

            if self.instance_guard.try_acquire():
                return True

    def _handle_wait_during_idle(self, next_run: datetime) -> bool:
        """
        处理任务空闲期间的行为策略
        :param next_run: 下一个任务的时间
        :return: True 表示等待成功完成, False 表示等待被中断
        """
        method = self.config.script.optimization.when_task_queue_empty
        strategy_map = {
            "close_game": self._wait_close_game,
            "goto_main": self._wait_goto_main,
        }
        func = strategy_map.get(method)
        if func is None:
            logger.warning(f"Invalid Optimization_WhenTaskQueueEmpty: {method}, fallback to stay_there")
            func = self._wait_stay_there
        return func(next_run)

    @staticmethod
    def _time_to_timedelta(value) -> timedelta:
        if value is None:
            return timedelta(0)
        return timedelta(hours=value.hour, minutes=value.minute, seconds=value.second)

    def _wait_until_with_emulator_preheat(self, next_run: datetime) -> bool:
        """Wait until next_run; if emulator is down, preheat startup before next task."""
        if not self._emulator_down:
            return self.wait_until(next_run)

        startup_lead = self._time_to_timedelta(self.config.script.optimization.emulator_startup_lead_time)
        now = datetime.now()
        wake_time = next_run - startup_lead if startup_lead > timedelta(0) else next_run
        if wake_time < now:
            wake_time = now

        now = datetime.now()
        if wake_time > now:
            logger.info(f"Wait before wake emulator: {wake_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if not self.wait_until(wake_time):
                return False

        if self._emulator_down:
            logger.info("Wake emulator before next task")
            if not self._try_acquire_queue_token():
                return False
            self.device = Device(self.config)
            self._emulator_down = False

        if wake_time < next_run:
            return self.wait_until(next_run)
        return True

    def _wait_close_game(self, next_run: datetime) -> bool:
        if self._emulator_down:
            logger.info("Emulator is down, skip close_game/goto_main action and wait with preheat")
            return self._wait_until_with_emulator_preheat(next_run)

        close_game_wait_duration = self.config.script.optimization.close_game_wait_duration
        close_game_wait = self._time_to_timedelta(close_game_wait_duration)
        close_emulator_wait_duration = self.config.script.optimization.close_emulator_wait_duration
        close_emulator_wait = self._time_to_timedelta(close_emulator_wait_duration)

        if close_emulator_wait > timedelta(0) and next_run > datetime.now() + close_emulator_wait:
            logger.info("Close emulator during wait")
            self.device.emulator_stop()
            self._emulator_down = True

            if not self._wait_until_with_emulator_preheat(next_run):
                return False

            self.run("Restart")
            return True

        if close_game_wait <= timedelta(0):
            logger.info("Close game during wait")
            self.device.app_stop()
            self.device.release_during_wait()
            if not self.wait_until(next_run):
                return False
            self.run("Restart")
            return True

        if next_run > datetime.now() + close_game_wait:
            logger.info("Close game during wait")
            self.device.app_stop()
            self.device.release_during_wait()
            if not self.wait_until(next_run):
                return False
            self.run("Restart")
            return True

        logger.info("Wait without closing game (close_game wait duration not reached)")
        self.device.release_during_wait()
        if not self.wait_until(next_run):
            return False
        return True

    def _wait_goto_main(self, next_run: datetime) -> bool:
        if self._emulator_down:
            logger.info("Emulator is down, skip goto_main and wait with preheat")
            return self._wait_until_with_emulator_preheat(next_run)

        close_emulator_wait_duration = self.config.script.optimization.close_emulator_wait_duration
        close_emulator_wait = self._time_to_timedelta(close_emulator_wait_duration)
        if close_emulator_wait > timedelta(0) and next_run > datetime.now() + close_emulator_wait:
            logger.info("Close emulator during wait")
            self.device.emulator_stop()
            self._emulator_down = True

            if not self._wait_until_with_emulator_preheat(next_run):
                return False

            self.run("Restart")
            return True

        logger.info("Goto main page during wait")
        self.run("GotoMain")
        self.device.release_during_wait()
        return self.wait_until(next_run)

    def _wait_stay_there(self, next_run: datetime) -> bool:
        if self._emulator_down:
            logger.info("Stay_there during wait (emulator is down, with preheat)")
            return self._wait_until_with_emulator_preheat(next_run)

        logger.info("Stay_there (no action) during wait")
        self.device.release_during_wait()
        return self.wait_until(next_run)

    def exception_handler(self, e: Exception, command: str) -> None:
        # 处理御魂溢出
        from tasks.Utils.post_diagnotor import PostDiagnotor, AnalyzeType
        image = getattr(self.device, 'image', None)
        # image为None则不做处理
        if image is None:
            return
        analyse_type = PostDiagnotor().handle(e=e, command=command, image=image)
        if analyse_type == AnalyzeType.SoulOverflow:
            self.config.task_call('SoulsTidy')
            time.sleep(1)

    def run(self, command: str) -> bool:
        """
        :param command:  大写驼峰命名的任务名字
        :return:
        """
        if command == 'start' or command == 'goto_main':
            logger.error(f'Invalid command `{command}`')

        if not self._try_acquire_queue_token():
            return False

        # ★ 「运行一次」: 任务**真正要跑了**才把它从队列里取走。
        #
        #   为什么不放在 `Config._order_by_manual_run()`（排序那一步）:
        #   `get_next()` 每轮会被调多次（等待/重试/暂停恢复都会重算），
        #   在排序时消耗队列会导致"点了 3 个只跑 1 个"。
        #
        #   放在这里（派发点）语义最清楚: **跑一次就出队一次**。
        self._consume_manual_run(command)

        if self.instance_guard and self.instance_guard.token_lost:
            logger.warning(f'Token lost, stopping emulator and rejoining queue')
            try:
                self.device.emulator_stop()
            except Exception:
                pass
            self._emulator_down = True
            self.instance_guard.release()
            return False

        try:
            self.device.screenshot()
            module_name = 'script_task'
            module_path = str(Path.cwd() / 'tasks' / command / (module_name+'.py'))
            logger.info(f'module_path: {module_path}, module_name: {module_name}')
            task_module = load_module(module_name, module_path)
            task_obj = task_module.ScriptTask(config=self.config, device=self.device)
            # ★ 运行记录: 在**框架层**记一次"这个任务跑了多久、打了几次"。
            #
            #   为什么放在这里而不是各任务里: 54 个任务逐个改既容易漏、
            #   又会让"统计"这件事散落各处。在这里包一层, 所有任务自动获得。
            #
            #   记录落在 `module/config/run_record.py`（与 task_state 同级、
            #   同样落盘），供界面展示与"重置=归档后重开"。
            runs_before = self._task_runs_snapshot(task_obj)
            started = datetime.now()
            try:
                task_obj.run()
            finally:
                self._record_task_run(task_obj, command, started, runs_before)
        except TaskPaused:
            # ★★★ 收到「暂停调度」—— 在安全点中断, **不跳过收尾** ★★★
            #
            # ## 为什么在这里接（而不是让任务自己处理）
            #
            # `TaskPaused` 是从**任意安全点**抛上来的（战斗循环里 /
            # `run_general_battle()` 里）。★ 走到这里时:
            #   * 任务自己的**收尾逻辑已经跑完了**
            #     （战斗已结束 + 结算 + 领奖 —— 安全点的定义）
            #   * 上面那个 `finally` 也已记录运行时长/次数
            #   ★ 所以**不会卡在半途**（见 docs/architecture.md §6.1）
            #
            # ## 为什么不直接退出进程
            #
            # ★ 暂停是**可恢复**的: 返回 `True` -> 回到 `loop()` ->
            #   `_handle_run_control()` 发现 `run_control.is_paused()` 为真,
            #   就**阻塞等待**用户点「继续」, 恢复后照常调度。
            #   ⚠ 若在这里 `exit()`, 用户点「继续」就**没有进程可恢复**了。
            logger.info('调度已暂停: 当前任务在安全点中断, 等待「继续」')
            return True
        except TaskEnd:
            return True
        except GameNotRunningError as e:
            logger.warning(e)
            self.exception_handler(e=e, command=command)
            self.config.task_call('Restart')
            return True
        except (GameStuckError, GameTooManyClickError) as e:
            logger.error(e)
            self.save_error_log()
            self.exception_handler(e=e, command=command)
            logger.warning(f'Game stuck, {self.device.package} will be restarted in 10 seconds')
            logger.warning('If you are playing by hand, please stop Alas')
            self.config.notifier.push(title=f'{I18n.trans_zh_cn(command)}{command}', content=f"<{self.config_name}> GameStuckError or GameTooManyClickError")
            self.config.task_call('Restart')
            self.device.sleep(10)
            return False
        except GameBugError as e:
            logger.warning(e)
            self.save_error_log()
            self.exception_handler(e=e, command=command)
            logger.warning('An error has occurred in Azur Lane game client, Alas is unable to handle')
            logger.warning(f'Restarting {self.device.package} to fix it')
            self.config.task_call('Restart')
            self.device.sleep(10)
            return False
        except GamePageUnknownError as e:
            logger.info('Game server may be under maintenance or network may be broken, check server status now')
            # 这个还不重要 留着坑填
            logger.critical('Game page unknown')
            self.save_error_log()
            self.exception_handler(e=e, command=command)
            self.config.notifier.push(title=f'{I18n.trans_zh_cn(command)}{command}', content=f"<{self.config_name}> GamePageUnknownError")
            self.config.task_call('Restart')
            self.device.sleep(10)
            return False
        except ScriptError as e:
            # 开发者级错误(或偶发问题)。原实现直接 exit(1), 会连带停掉同一实例下所有其它
            # 任务, 而这属于"任务级"失败: 交给 loop() 累计 failure_record, 连续 3 次后
            # 仍会按既有策略请求人工介入。
            logger.critical(e)
            self.exception_handler(e=e, command=command)
            logger.critical('This is likely to be a mistake of developers, but sometimes just random issues')
            self.config.notifier.push(title=f'{I18n.trans_zh_cn(command)}{command}', content=f"<{self.config_name}> ScriptError")
            self._task_failed = True
            return False
        except RequestHumanTakeover as e:
            # 硬停止: 按设计这里必须停下来等人处理, 因此保留终止整个实例的行为。
            logger.critical(e)
            self.exception_handler(e=e, command=command)
            logger.critical('Request human takeover')
            self.config.notifier.push(title=f'{I18n.trans_zh_cn(command)}{command}', content=f"<{self.config_name}> RequestHumanTakeover")
            exit(1)
        except Exception as e:
            # 未分类异常。原实现 exit(1)。改为任务级失败: 单个界面异常(例如某条识别规则的
            # 模板文件缺失触发 FileNotFoundError)不应终止整个实例, 否则用户其它任务全部停摆。
            logger.exception(e)
            self.exception_handler(e=e, command=command)
            self.save_error_log()
            self.config.notifier.push(title=f'{I18n.trans_zh_cn(command)}{command}', content=f"<{self.config_name}> Exception occured")
            self._task_failed = True
            return False

    def _consume_manual_run(self, command: str) -> None:
        """
        「运行一次」出队。

        ★ 队列是 **FIFO 且只跑一次**，但**不必**严格等于队首:
          若队首那个任务还没到点（`get_next()` 选了别人), 就先让它等下 ——
          用户的点击顺序是"优先级提示", 不是"必须插在调度约束之前"。

        ★ 失败只记 warning —— 插队是锦上添花, 不该影响跑任务。
        """
        try:
            from module.config import manual_run

            if not manual_run.is_pending(self.config_name, command):
                return
            manual_run.cancel(self.config_name, command)
            left = manual_run.pending(self.config_name)
            logger.info(f'运行一次: {command} 已出队（剩余 {len(left)} 个）')
        except Exception as exc:
            logger.warning(f'运行一次出队失败({type(exc).__name__}: {exc}), 忽略')

    # ---------------------------------------------------------------- 运行记录
    def _task_runs_snapshot(self, task_obj) -> int:
        """
        取任务**当前**已打次数（用于算增量）。

        优先用任务对象内存里的 `current_count`（那是权威值, 由
        `bind_counter` 从磁盘恢复、由战斗代码递增）；
        取不到就退回 `task_state` 的持久化值。
        """
        try:
            v = getattr(task_obj, 'current_count', None)
            if v is not None:
                return int(v)
        except Exception:
            pass
        try:
            from module.config import task_state
            return int(task_state.get_count(
                self.config_name, task_obj.get_task_name()))
        except Exception:
            return 0

    def _record_task_run(self, task_obj, command: str,
                         started: datetime, runs_before: int) -> None:
        """
        把这次运行记进 `run_record`（次数 + 耗时）。

        ★ 统计失败**绝不能影响任务** —— 全部异常吞掉并记 warning。
          记录只是"报表"，跑任务才是正事。
        """
        try:
            from module.config import run_record

            runs_after = self._task_runs_snapshot(task_obj)
            delta = max(0, runs_after - runs_before)
            elapsed = max(0, int((datetime.now() - started).total_seconds()))

            run_record.finish(self.config_name, command,
                              runs=delta, seconds=elapsed)
            logger.info(f'运行记录: {command} 本次 {delta} 次, '
                        f'{run_record.format_duration(elapsed)}')
        except Exception as exc:
            logger.warning(f'运行记录写入失败({type(exc).__name__}: {exc}), 忽略')

    def loop(self):
        """
        Main loop of scheduler.
        :return:
        """
        with _log_switch_lock:
            logger.set_file_logger(self.config_name, do_cleanup=True)
        start_day = date.today()
        logger.info(f'Start scheduler loop: {self.config_name}')
        self.config.model.running_task = ''
        self.anti_ban_guard.reset()

        # Update GUI 防呆, 读取设置并立刻显示后台模拟器到前台
        if not self.config.script.device.run_background_only and IS_WINDOWS:
            from module.device.platform2.platform_windows import minimize_by_name, show_window_by_name
            target_window_name = self.config.script.device.handle  # 在这里输入你的具体窗口名称
            if self.config.script.device.emulator_window_minimize:
                minimize_by_name(target_window_name)
                logger.info(f'重新显示: {target_window_name}')
            else:
                show_window_by_name(target_window_name)
                
        while 1:
            if date.today() > start_day:
                with _log_switch_lock:
                    logger.set_file_logger(self.config_name, do_cleanup=True)
                start_day = date.today()

            # Get task
            task = self.get_next_task()
            # Skip first restart
            if self.is_first_task and task == 'Restart':
                logger.info('Skip task `Restart` at scheduler start')
                self.config.task_delay(task='Restart', success=True, server=True)
                del_cached_property(self, 'config')
                continue

            if self._emulator_down:
                self.device = Device(self.config)
                self._emulator_down = False
            else:
                _ = self.device

            # Run
            logger.info(f'Scheduler: Start task `{task}`')
            self.device.stuck_record_clear()
            self.device.click_record_clear()
            logger.hr(task, level=0)
            self.config.model.running_task = task
            _task_start = datetime.now()
            self._task_failed = False
            success = self.run(inflection.camelize(task))
            # run() 在任务级异常分支里会置 _task_failed, 此时即使返回值是 True 也算失败。
            # (TaskEnd / GameNotRunningError 等"已转交后续处理"的分支不置该标志, 仍算成功)
            if self._task_failed:
                success = False
            self.config.model.running_task = ''
            logger.info(f'Scheduler: End task `{task}`')
            self.is_first_task = False
            self.anti_ban_guard.record_active((datetime.now() - _task_start).total_seconds())

            # ---- 失败记录：落盘 + 冷却（**不再 exit(1)**）----
            #
            # ★★ 改造前的行为是错的 ★★
            #
            # 原实现:
            #     self.failure_record[task] = failed      # 内存字典
            #     if failed >= 3:
            #         ...
            #         exit(1)                            # 整个子进程退出
            #
            # `failure_record` 是 `Script` 实例上的内存字段。进程一退出,
            # 服务器就重新拉起一个（`module/server/script_process.py`）,
            # **新进程的计数是空的** —— 于是:
            #
            #   失败 3 次 -> exit -> 重启 -> 计数归零 -> 又能失败 3 次 -> 再重启 ...
            #
            # **永远停不下来。** 真实日志里 7 小时有 97 次 `START` 块
            # （90+ 次进程重启）, `RyouToppa` 被派发 25 次一次都没打成。
            #
            # 现在: 计数**落盘**、到阈值**不退出进程**而是给该任务加冷却。
            # 详见 `module/config/failure_state.py`。
            try:
                from module.config import failure_state

                if success:
                    failure_state.record_success(self.config_name, task)
                    # 成功后**同时**清掉内存里的旧计数（保持两者一致）
                    self.failure_record.pop(task, None)
                else:
                    res = failure_state.record_failure(self.config_name, task)
                    self.failure_record[task] = res['count']
                    if res['should_notify']:
                        minutes = failure_state.cooldown_remaining_minutes(
                            self.config_name, task)
                        logger.critical(
                            f'任务 `{task}` 连续失败 {res["count"]} 次, '
                            f'进入冷却 {minutes} 分钟（不再重启进程）。'
                            f'可能原因: 配置不对 / 素材与游戏界面不匹配 / '
                            f'任务本身有 bug。')
                        self.config.notifier.push(
                            title=f'{I18n.trans_zh_cn(task)}{task}',
                            content=f'<{self.config_name}> 任务连续失败, '
                                    f'已冷却 {minutes} 分钟；修正后可点'
                                    f'「清除失败」立刻重试'
                        )
                        # 把这个任务推到冷却结束之后, 免得调度器反复选中它
                        try:
                            self.config.task_delay(
                                task,
                                success=False,
                                server=True,
                                target=res['cooldown_until'])
                        except Exception as exc:
                            logger.warning(
                                f'设置 {task} 冷却失败({type(exc).__name__}: '
                                f'{exc}), 靠 update_scheduler 的冷却检查兜底')
            except Exception as exc:
                # ★ 失败记录本身出问题**绝不能**影响任务调度
                logger.warning(f'失败记录处理失败({type(exc).__name__}: {exc}), 忽略')

            # ---- 运行控制: 暂停 / 休息 ----
            #
            # 放在这里而不是循环开头: 上面的成功分支用 `continue` 直接跳回开头,
            # 会**跳过**循环开头的检查。放在 `continue` 之前才可靠。
            #
            # 注意: 走到这里时任务已经完整结束(战斗 + 结算 + 领奖 + 收尾),
            # 因此这是**安全点** —— 不会卡在半途(见 docs/architecture.md §6.1)。
            if self._handle_run_control():
                del_cached_property(self, 'config')
                continue

            if success:
                del_cached_property(self, 'config')
                continue
            elif self.config.script.error.handle_error:
                del_cached_property(self, 'config')
                continue
            else:
                break

    def _handle_run_control(self) -> bool:
        """
        处理暂停 / 休息。返回 True 表示"已等待, 应重新调度"。

        * **暂停**(⏸ / ⏭): 不派发新任务, 循环等待用户点"继续"
        * **休息**: 全局暂停到指定时刻(定时任务也不跑)

        两者都在**安全点**被检查(任务已完整结束)。等待期间给较短的轮询间隔
        (15 秒), 因为用户可能随时点"继续", 不该等到下个任务周期才响应。
        """
        try:
            from module.config import run_control
        except Exception as exc:
            logger.warning(f'运行控制不可用({type(exc).__name__}: {exc}), 继续调度')
            return False

        try:
            if run_control.is_paused():
                st = run_control.state()
                logger.info(f'调度已暂停({st["pause_mode_label"]}), 等待"继续"…')
                while run_control.is_paused():
                    time.sleep(run_control.wait_seconds() or 15)
                logger.info('暂停已解除, 恢复调度')
                return True

            if run_control.in_rest():
                ru = run_control.rest_until()
                logger.info(f'休息中, 至 {ru:%Y-%m-%d %H:%M}, 暂停派发任务')
                while run_control.in_rest():
                    time.sleep(run_control.wait_seconds() or 15)
                logger.info('休息结束, 恢复调度')
                return True
        except Exception as exc:
            logger.warning(f'运行控制处理异常({type(exc).__name__}: {exc}), 继续调度')
        return False

    def start_loop(self) -> None:
        """
        创建一个线程，运行loop
        :return:
        """
        if self.loop_thread is None:
            self.loop_thread = Thread(target=self.loop, name='Script_loop')
            self.loop_thread.start()


if __name__ == "__main__":
    ensure_ocr_server_started()
    script = Script("oas1")
    script.loop()
