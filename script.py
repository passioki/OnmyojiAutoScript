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
        # ★★★ 2026-10-13（用户裁定「丙」）：★ 上一个被执行的**任务实例** ★★★
        #
        # ★ 用户原话："**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
        #   / "**或者按照时间戳来判断**"。
        #
        # ★ 为什么需要它：★ `loop()` 收尾时要**如实**把"本次几场"写进长时记录
        #   （`task_state.record_entry_run(runs_this_time=...)`），
        #   ★ 而 `self.config.task` 是 **`Function`**（调度元数据）——
        #   ★ **没有** `current_count`（见 `run()` 里的赋值处与 `tasks/base_task.py:116`）。
        # ★ "本轮进度"按规格书 §1.6-L500/L504 **只活在内存**
        #   （★ 不落盘、★ 重启后从 0 开始）⇒ ★ 只能经由**任务实例**取。
        # ★ 默认 `None`：★ 还没跑过任何任务就走到收尾 ⇒ 记为 **0 场（如实）**,
        #   ★ **绝不"补记 1 场"**（★ §2.2-REC5「不能未完成却标记完成」）。
        self._last_task_obj = None
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
        # ★★★ 2026-10-12 用户裁定「S3」：**临时任务不看 `next_run` 显示** ★★★
        #
        # ## ★ 原来错在哪
        #
        # ★ 原来用 `next_run < now` 决定"要不要把当前任务报给界面"。
        # ★ 但临时任务的 `next_run` **没有排期语义**（§1.2）——
        #   ★ 它可能是"未来"或"很久以前" ⇒ ★ **界面显示为空/错乱**。
        #
        # ## ★ 修法
        #
        # ★ 临时任务：★ **只要有当前任务就报**，★ 且**不报 `next_run`**
        #   （★ 改为 `'按顺序'` —— ★ 它的顺序由队列决定）。
        # ★ 周期任务：★ 照旧（`next_run < now` + 报 `next_run`）。
        _cur = self.config.task
        if _cur is not None:
            _cur_temp = False
            try:
                _tp = self.config.task_period(_cur.command)
                _cur_temp = (not _tp) or str(_tp).lower() == 'none'
            except Exception:
                _cur_temp = False
            if _cur_temp:
                task["name"] = _cur.command
                task["next_run"] = '按顺序'
            elif _cur.next_run < datetime.now():
                task["name"] = _cur.command
                task["next_run"] = str(_cur.next_run)
        data["task"] = task

        # ★ 小工具：临时任务显示"按顺序"，周期任务显示真实时间
        def _nr(f):
            try:
                _p = self.config.task_period(f.command)
                if (not _p) or str(_p).lower() == 'none':
                    return '按顺序'
            except Exception:
                pass
            return str(f.next_run)

        for p in self.config.pending_task[1:]:
            item = {"name": p.command, "next_run": _nr(p)}
            pending.append(item)

        for w in self.config.waiting_task:
            item = {"name": w.command, "next_run": _nr(w)}
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
            # ★★★ 2026-10-12 用户裁定「S2」：**防封不为临时任务改 `next_run`** ★★★
            #
            # ## ★ 为什么
            #
            # ★ `antiban_wake` 是"**防封让任务再等一会儿**"的机制 ——
            #   ★ 它把 `next_run` **推到未来**。
            # ★ 但临时任务**没有排期语义**（§1.2 分型规则）：
            #   ★ 它由 **次数 / 门票 / 队列顺序** 决定何时跑。
            # ★ 若这里把它的 `next_run` 推远 ⇒
            #   ★ 虽然 S1 已让派发判定跳过 `next_run`，
            #   ★ 但**界面/日志/其它读它的代码**仍会看到一个"未来的时间"
            #     ⇒ ★★ **误导**（用户就是因此以为"还在用 next_run 排期"）。
            #
            # ## ★ 修法
            #
            # ★ 先算出这个任务是不是临时任务；
            # ★ **是临时任务** ⇒ ★ **不改 `next_run`**（跳过这一句）。
            # ⚠ 周期任务**照旧**（防封对它们仍是必要的）。
            _is_temp_task = False
            try:
                _tp = self.config.task_period(task.command)
                _is_temp_task = (not _tp) or str(_tp).lower() == 'none'
            except Exception:
                _is_temp_task = False
            antiban_wake = self.anti_ban_guard.wake_time(now, self.config.script.anti_ban)
            if antiban_wake is not None and not _is_temp_task:
                task.next_run = max(task.next_run, antiban_wake)
            if not self._try_acquire_queue_token():
                del_cached_property(self, "config")
                continue
            # 任务时间到了返回任务名称
            #
            # ★★★ 2026-10-12 用户裁定「S1」：**临时任务【跳过】时点判定** ★★★
            #
            # ## ★★ 用户报的问题（原话）
            #
            # > "**怎么还有 next_run？没有按照新的调度吗？**"
            # > "**是只是日志语义没适配，还是内层代码逻辑还是 `next_run`？**"
            #
            # ## ★★ 我先前只改了【门④】，★ 没改【这里】—— 这就是"说了四五遍
            #    还没完成"的真正原因
            #
            # ★ 我改的门④（`config.py:1907`）只管"**谁进 `pending_task`**"。
            # ★ 但"**要不要现在派发**"是【本行】决定的：
            #   ★ 队首任务 `next_run` 在未来 ⇒ **不 return** ⇒ 落到下面的
            #     "等待逻辑"（`_handle_wait_during_idle`）
            #   ⇒ ★★ **临时任务照样被 `next_run` 拦在门外**。
            #
            # ## ★ 设计依据（§1.2 分型规则）
            #
            # | 维度 | 临时任务（`period = none`）|
            # |---|---|
            # | `next_run` | ★★ **不参与派发判断** |
            # | 谁决定"能不能跑" | ★ **次数（`runs`/`target`）+ 门票** |
            # | 谁决定"下一条是谁" | ★ **队列顺序**（§1.1-R3）|
            #
            # ⇒ ★ 临时任务在**所有时点判定**里都应被跳过
            #   ★ （★ 这是设计的**核心**："不允许被执行顺序以外的机制调动"）。
            #
            # ⚠ 周期任务**完全不动**（时间排期是它们的正确语义）。
            #
            # ★ 注：`_is_temp_task` 已在上面（防封那一段）算好，★ 这里直接复用。
            if _is_temp_task or task.next_run <= now:
                logger.info(f'★[派发诊断] 派发 {task.command}'
                            f'（entry={getattr(task, "entry_id", "")}）'
                            f' 临时={_is_temp_task}'
                            f' next_run={task.next_run}')
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
            # ★★★ 片 5 (P1-P3): **乱序**（`SHUFFLE`）★★★
            #
            # > 用户裁定: "**P2 乱序就是随机挑一个可跑的**。"
            #
            # ★ 与 `loop`（循环）**共用候选判据**（`Config._loop_candidates`）——
            #   区别只在"全都要" vs "**随机挑一个**"。
            # ★ 放在 `loop` 之前: 三种模式互斥（同一个配置字段），
            #   所以先匹配哪个都一样; 这里只是让"乱序"更早短路。
            try:
                # ★★★ 2026-10-12 修：**枚举比较 bug**（与 D12 同一类）★★★
                #
                # ## ★★ 症状
                # > "**循环计数有问题，一直显示 1，导致无法停止**"
                #
                # ## ★ 根因
                # ★ `when_task_queue_empty` 是**枚举** `WhenTaskQueueEmpty.LOOP`
                #   `str(枚举)` = `'WhenTaskQueueEmpty.LOOP'`
                #   ⇒ ★★ **永远不等于 `'shuffle'` / `'loop'`**
                #   ⇒ ★ **整段循环逻辑从不执行**
                #   ⇒ ★ `bump_loop_rounds()` 从不被调
                #   ⇒ ★ 计数**停在旧值**（用户看到"一直是 1"）
                #   ⇒ ★ 停止判据 `_done >= _times` **永不成立**
                #   ⇒ ★★ **无法停止**（用户报的症状完全吻合）
                #
                # ★ 修法：★ 取 `.value`（★ 与项目其它地方同一手法）。
                _wte_raw = self.config.script.optimization.when_task_queue_empty
                _wte = str(getattr(_wte_raw, 'value', _wte_raw) or '').lower()
                if _wte == 'shuffle':
                    _now_sh = datetime.now()
                    if (_loop_reset_at is None
                            or (_now_sh - _loop_reset_at).total_seconds()
                            >= _loop_throttle_s):
                        _picked = self.config.shuffle_next_run(_now_sh)
                        if _picked:
                            _loop_reset_at = _now_sh
                            del_cached_property(self, "config")
                            continue
                        _loop_reset_at = _now_sh
                        logger.info('队列乱序: 当前没有可跑的任务 -> 按原策略等待')
            except Exception as exc:
                logger.warning(f'队列乱序重排失败({type(exc).__name__}: {exc}), '
                               f'按原策略等待')
            try:
                # ★ 复用上面算好的 `_wte`（★ 同一枚举 bug，见上）
                if _wte == 'loop':
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
        # ★★★ 2026-10-12 修：`loop` / `shuffle` **不是非法值** ★★★
        #
        # ## ★★ 用户报的 bug + 日志证据
        #
        # ```
        # WARNING | Invalid Optimization_WhenTaskQueueEmpty: loop,
        #           fallback to stay_there
        # ... 条目 RealmRaid【本轮已完成】-> 跳过
        # ... 条目 Exploration【本轮已完成】-> 跳过
        # ... Pending tasks: ['Exploration', 'RealmRaid']
        # ... [Task] Exploration (Enable, 5, 2026-10-12 20:18:45)
        #     ↑ ★ next_run 在过去却【不跑】
        # ```
        #
        # ## ★ 根因
        #
        # ★ `WhenTaskQueueEmpty` 的**合法值**有 4 个：
        #   `goto_main` / `close_game` / ★ **`loop`** / ★ **`shuffle`**
        #   （见 `tasks/Script/config_optimization.py`）
        # ★ 但这里的 `strategy_map` **只有前两个**
        #   ⇒ ★ `loop` / `shuffle` 落到 `func is None`
        #   ⇒ ★★ **误报 "Invalid"** + 退化成 `stay_there`（**什么都不做**）
        #
        # ## ★ 为什么 `loop`/`shuffle` 不该走这个函数
        #
        # ★ 它们由**上层**处理：`script.py` 主循环里的
        #   `reset_loop_next_run()` / `shuffle_next_run()`
        #   （★ 见本文件 L411~L460）
        # ⇒ ★ 走到这里只可能是"**上层没找到可重排的任务**"
        #   ⇒ ★ 此时 **`stay_there` 是正确行为**（等待下一个到点任务）
        #   ★ 但**不该报 "Invalid"** —— ★ 那不是配置错误。
        strategy_map = {
            "close_game": self._wait_close_game,
            "goto_main": self._wait_goto_main,
            # ★ 合法值：交给 `stay_there`（★ 上层已尝试过重排）
            "loop": self._wait_stay_there,
            "shuffle": self._wait_stay_there,
        }
        func = strategy_map.get(method)
        if func is None:
            logger.warning(f"Invalid Optimization_WhenTaskQueueEmpty: {method}, "
                           f"fallback to stay_there")
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
            # ★★★ 2026-10-13（用户裁定「丙」）：★ 存下**任务实例**，供收尾读"本次几场" ★★★
            #
            # ## ★★ 用户原话
            # > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
            # > "**或者按照时间戳来判断**"
            #
            # ## ★ 为什么收尾（`loop()`）**读不到**这个数
            #
            # ★ `_task_obj` 是**本函数的局部变量** ⇒ ★ `loop()` 里根本看不见它。
            # ★ 而 `loop()` 里能拿到的 `self.config.task` 是 **`Function`**
            #   （调度元数据：`command` / `next_run` / `entry_id` / `target`）
            #   ⇒ ★ **没有** `current_count`、**没有** `_counter_task`
            #   ⇒ ★ 这就是缺陷 A 的根因。
            # ★ `current_count` 只在**任务实例**上（`tasks/base_task.py:116` 初始化、
            #   `bind_counter()` L374 **置 0**）—— ★ 它才是**本轮进度**，
            #   ★ 而本轮进度**只在内存**（规格书 §1.6-L500/L504）。
            #
            # ## ★ 与规格书对齐
            #
            # ★ §1.6-L502-L504：「磁盘**只保留长时记录**；"这一轮打了多少场"
            #   ⇒ ★ **只活在内存**」⇒ ★ 所以只能**从内存里的任务实例**取。
            #
            # ## ⚠ 赋值时机（`task_obj` 已构造好）
            #
            # ★ 本句在下面 `try:` **之前**执行，★ 而 `loop()` 的收尾在
            #   `run()` **返回之后** ⇒ ★ 引用一定已就绪（★ 不会读到上一轮的陈旧值）。
            self._last_task_obj = task_obj
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
        取任务**本次运行**已打次数（用于算增量 `runs_after - runs_before`）。

        ## ★★★ 2026-10-13 用户裁定「丙」：★ **只读内存，★ 绝不读盘** ★★★

        ## ★★ 用户原话
        > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
        > "**或者按照时间戳来判断**"

        ## ★ 这个方法现在**应该**返回什么

        ★ 它要的是"**本次运行期间，这个任务实例打了几场**"
          ⇒ ★ 答案**只可能在内存**（`task_obj.current_count`）
          ⇒ ★ **取不到就返回 0**（★ 0 就是 0，★ 如实，★ 不猜、不补）。

        ## ⚠ 为什么**必须删掉**"退回 `task_state.get_entry_runs(...)`（读盘）"

        ★ `runs` **不再由本轮写盘** —— `bind_counter()` 从 0 开始（不读盘）、
          `commit_count()` 空操作（不写盘），`script.py` 收尾也不再
          `set_entry_runs` / `bump_entry_runs`
          （见 `tasks/base_task.py` 的 `bind_counter` / `commit_count`）。
        ★ 于是读盘读到的**只会是上一轮的残留/假数据**
          ⇒ ★ 报表失真（★ 实测日志 `本次 88 次, 0 分钟` 就是这类错位）。
        ★ 而且"**这条本次跑没跑过**"的判定**已经**换成
          ★ `completed_session` ↔ `__loop__.session_start` 的**时间戳比对**
          （`task_state.get_entry_completed()`，§1.6-L496-L498）
          ⇒ ★ 磁盘里的 `runs` **不再参与任何调度判定**
          ⇒ ★ 读它**没有任何正当理由**，★ 只会把上一轮的数字带回来。

        ## ★ 与规格书对齐（`docs\\DESIGN-SPEC.md` §1.6）

        ★ §1.6-L500「**不再把"本轮进度计数"落盘**」
        ★ §1.6-L502-L504「磁盘**只保留长时记录**（`total_runs` / `total_log`，
          纯统计、**不参与调度判定**）；"这一轮打了多少场"
          ⇒ ★ **只活在内存**（★ 重启后从 0 开始）」。

        ## ★ 调用点不受影响（见 `run()` 的 `runs_before` 与 `_record_task_run()`）

        ★ `runs_before` 在 `task_obj` **刚构造完、`run()` 之前**取 ——
          `BaseTask.__init__`（`tasks/base_task.py:116`）已把 `current_count`
          置 0，★ 所以它**本来就是 0**（★ 与本次改动无关）。
        ★ `runs_after` 在 `run()` 之后取，而 `bind_counter()` 本轮**从 0 开始**
          ⇒ ★ `delta = runs_after - 0` = ★ **本次这个实例打的场数**（语义干净）。
        """
        try:
            v = getattr(task_obj, 'current_count', None)
            if v is not None:
                return int(v)
        except Exception:
            pass
        # ★ 取不到就**如实返回 0** —— ★ **绝不**退回 `task_state.get_entry_runs()`
        #   （★ 那是读盘 `runs`；★ 本轮不再写盘 ⇒ ★ 只会读到上一轮的残留/假数据，
        #     ★ 正是用户报的"读取了上一轮跑的计数"）。
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

        # ★★★ 10-13 新增：记下【本次启动时间】（用户裁定「丙」）★★★
        #
        # ## ★★ 用户原话
        # > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
        # > "**或者按照时间戳来判断**"
        # > "**就按这个来**"
        #
        # ## ★ 这是规格书 §1.6-L453 / §2.6-LR5 缺的那个量
        # ★ 规格书要求："这条【本次】跑没跑过" = 用【本次启动时间】与【记录里的时间】比对。
        # ★ 但全仓**没有任何"本次启动时间"**：
        #   * `__loop__.reset_at` 只写不读（死数据）
        #   * `_loop_reset_at`（本文件后面）只是**一次函数调用内的局部变量**，不落盘
        #   * `base_task.start_time` 是**任务实例内存**，随任务对象生灭
        # ⇒ ★ 于是"跑没跑过"只能靠**计数器**（`runs >= target`）判
        #   ⇒ ★ 计数残留 ⇒ **跑不起来**（用户痛点）。
        #
        # ## ★ 语义与效果
        # ★ 每次**后端调度循环启动**刷新一次 ⇒ ★ `get_entry_completed()` 的过期基准
        #   ★ 从"轮次号"改成"本时间戳" ⇒ ★ **每次重启后端，所有条目都算"本次没跑过"**
        #   ⇒ ★★ **一定能跑**（★ 用户已接受"重启后本轮从 0 重打"）。
        # ★ 彻底摆脱"轮次号只在 loop 模式才推进"的依赖
        #   （`goto_main` / `stay_there` / 乱序下轮次号永不推进 ⇒ 旧实现会永久残留）。
        try:
            from module.config import task_state as _task_state
            _task_state.mark_session_start(self.config_name)
        except Exception as exc:
            # ★ 绝不因为记时间失败而挡住调度 —— 宁可没基准（判定会放宽为"可跑"）
            logger.warning(f'记录【本次启动时间】失败'
                           f'({type(exc).__name__}: {exc}), 忽略'
                           f'（完成判定会放宽为"可跑"）')

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
            # ★★★ P-1: 同时记下**正在跑那一条的 `entry_id`**（用户裁定）★★★
            #
            # > "点击暂停调度, 正在运行的任务**自动回退到队列首位, 视作等待执行**"
            #
            # ★ `running_task` 只有任务名 —— 队列里同一任务可以有**多条条目**
            #   （用户用重复条目表达"重复跑整个任务"）。
            #   ⇒ 只按任务名找会**退错那一条**。
            #
            # ⚠ 为什么必须**落盘**: 脚本跑在独立进程, HTTP 端（`put_pause`）
            #   拿不到内存里的 `self.config.task`。
            # ⚠ 为什么记 `entry_id` 而不是下标: 下标会随用户拖动而变
            #   （"**身份，不是位置**" —— `docs/scheduler-architecture.md` §1.5）。
            try:
                self.config.model.running_entry_id = str(
                    getattr(self.config.task, 'entry_id', '') or '')
            except Exception as exc:
                logger.debug(f'记 running_entry_id 失败({type(exc).__name__}: {exc})')
                self.config.model.running_entry_id = ''
            _task_start = datetime.now()
            self._task_failed = False
            success = self.run(inflection.camelize(task))
            # run() 在任务级异常分支里会置 _task_failed, 此时即使返回值是 True 也算失败。
            # (TaskEnd / GameNotRunningError 等"已转交后续处理"的分支不置该标志, 仍算成功)
            if self._task_failed:
                success = False
            self.config.model.running_task = ''
            # ★★★ 片 5 (F2): 条目跑完 -> **条目级计数 +1**（界面上显示"已运行 N 次"）★★★
            #
            # ## ★★ 用户裁定 ★★
            #
            # > "由于现在是**流转的运行**，那么就会出现**运行过，状态标记为已运行X次**"
            # > 并选定：**按条目**计（甲）—— 与"条目级次数"（`RunEntry.target`）一致。
            #
            # ★ 为什么按条目: 队列里**同一任务可以有多条条目** ——
            #   按任务计会把两条混在一起（与 `running_entry_id` 同一理由:
            #   "**身份，不是位置**"）。
            # ★ **必须在这里记** —— 再下一行就把 `running_entry_id` 清掉了。
            #
            # ═══════════════════════════════════════════════════════════════════
            # ★★★ 2026-10-13 重写（用户裁定「丙」）：这里**只**记长时记录 ★★★
            # ═══════════════════════════════════════════════════════════════════
            #
            # ## ★★ 用户原话
            #
            # > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
            # > "**或者按照时间戳来判断**"
            #
            # ## ★ 本次删掉了哪两条路（都是"计数当判据"的遗物）
            #
            # ★ ① **`set_entry_runs(eid, target)`**（把 `runs` **直接覆写成 target**，原 L1233）
            #   * ★ 它与「**本轮进度只在内存**」**直接冲突**：`runs` 一旦被写成
            #     `target` ⇒ ★ 就"跨轮存活且虚高" ⇒ ★ **下次真的跑不起来**
            #     （★ 用户痛点本体）。
            #   * ★ 它还**污染长时统计**：`runs` 变成"被赋过的值"，不再是"打了几场"。
            # ★ ② **"0 场也补记 1 场"** 的两处补记（`_bound` 分支 + `else` 分支）
            #   * ★ 对 `target=1` 的条目 ⇒ ★ `runs` 至少为 1 ⇒
            #     ★ **一场没打也被判"本轮完成"** ⇒ ★ 撞规格书 §2.2-REC5
            #     「**不能未完成却标记完成**」（★ 用户亲令"最重要的一点"）。
            #   * ★ "没打就是没打"：★ **不能补**；★ `total_log` 的 `runs`
            #     必须**如实**记本次打了 0 场。
            #
            # ## ★★ 缺陷 A：`_bound` 恒为 `False` ⇒ 那里是**死代码**
            #
            # ★ 原判据: `_bound = bool(getattr(self.config.task, '_counter_task', None))`
            # ★ 为什么**永远**是 `False`（两条证据）：
            #   * ★ `self.config.task` 是 **`Function`**（见 `run()` 上方
            #     `self.config.task = task`，`task` 来自 `self.config.get_next()`；
            #     再往上是 `Config.get_next()` 里的 `self.task = _f`，
            #     `_f` 取自 `self.pending_task` ⇒ ★ 都是 `Function`）
            #   * ★ 而 `_counter_task` 全仓**只**在 `tasks/base_task.py` 里被赋值
            #     （`__init__` 置 `None`、`bind_counter()` 置 `name.lower()`）
            #     ⇒ ★ 它**只存在于【任务实例】**上
            #     （`ScriptTask(config=..., device=...)`，见 `run()` 里 `task_obj`）
            # ★ 两者**不是同一个对象** ⇒ `getattr(Function, '_counter_task', None)`
            #   ★ 恒为 `None`（`Function` 是**普通类**、只设 `self.model` 那些字段，
            #   没有 `__getattr__` 兜底 ⇒ ★ 拿不到、也不会抛）
            #   ⇒ ★ `_bound` 恒 `False` ⇒ ★ `if not _bound:` **恒真**
            #   ⇒ ★ `else:` 那一整段**不可达**（死分支）★ 已删。
            #
            # ## ★★ 缺陷 B 的后果（★ 这才是"任务跑不起来"的最后一环）
            #
            # ★ `if not _bound:` 恒真 ⇒ ★ **所有** `target > 0` 的条目收尾都走
            #   `set_entry_runs(eid, target)` ⇒ ★ **runs 被直接覆写成 target**。
            # ★ 对**战斗任务**也照做（★ 它本该只由 `commit_count()` 按场计数）
            #   ⇒ ★ 打了几场根本不看 ⇒ ★ 计数**凭空达标**。
            #
            # ## ★★ 现行做法（★ 实际统一走哪条路）
            #
            # ★ 现在**没有分支**了：★ **战斗任务 / 非战斗任务走同一条路** ——
            #   * ★ **只调** `task_state.record_entry_run(runs_this_time=本次几场)`
            #     ⇒ ★ 写 `total_runs`（"本条被运行了几次"）+ `total_log`
            #       （★ 时间戳到**毫秒** + 本次几场）
            #   * ★ **删掉** `set_entry_runs` / `bump_entry_runs`
            #     ⇒ ★ **不再写盘 `runs`** ⇒ ★ 与「本轮进度只在内存」一致
            #   * ★ "**本次跑没跑过**"由 ★ `mark_entry_completed()`（下方）
            #     写的 `completed_session` ↔ `session_start` 的**时间戳比对**判定
            #     （§1.6-L496-L498）—— ★ **不再用"计数 >= target"**
            #
            # ## ★ 为什么**不再需要**"既然没统计到就补记 1"来避免"反复派发"
            #
            # ★ `Config.entry_target_reached()` 已按「丙」改成
            #   "★ **临时任务成功跑完一次即 `True`**；周期任务返回 `False`"
            #   ⇒ ★ "跑完 ⇒ 标 completed" 这条腿**不再依赖 `runs`**
            #   ⇒ ★ 之前靠"补记 1 场把 runs 顶到 target"的**动机已消失**。
            #
            # ⚠ 将来若要改这段，★ 请**先**确认 `entry_target_reached()` 的语义 ——
            #   它已**不代表**"计数达标"（名字是历史遗留）。
            try:
                _eid = str(getattr(self.config.model, 'running_entry_id', '') or '')
                if _eid and success:
                    from module.config import task_state as _ts2
                    # ★★ 如实取"本次打了几场"（★ 0 就是 0，★ 不补记）★★
                    #
                    # ★ 取值来源 = **任务实例的内存计数** `current_count`
                    #   （★ 由 `bind_counter()` L374 **从 0 开始**、
                    #    战斗代码场内自增；见 `tasks/base_task.py:116/374`）。
                    #
                    # ⚠ 为什么**不能**读 `self.config.task`：
                    #   ★ 它是 `Function`（调度元数据）⇒ ★ **没有** `current_count`
                    #   ⇒ ★ 读出来恒是"取不到" ⇒ ★ 就会误记成 0
                    #   ⇒ ★ 这也是缺陷 A 的同一个根因。
                    # ⚠ 为什么**不能**再 `get_entry_runs(...)`（读盘 `runs`）：
                    #   ★ `runs` 现在**不再由本轮写盘**（`commit_count` 空操作、
                    #     本处也不再 `set/bump`）⇒ ★ 读到的只会是**旧值/残留**
                    #   ⇒ ★ 记进 `total_log` 就是**假数据**。
                    #
                    # ★ 与规格书对齐：§1.6-L500「**不再把"本轮进度计数"落盘**」、
                    #   §1.6-L502-L504「磁盘**只保留长时记录**；"这一轮打了多少场"
                    #   ⇒ ★ **只活在内存**（★ 重启后从 0 开始）」。
                    _n = 0
                    try:
                        _n = int(getattr(self._last_task_obj,
                                        'current_count', 0) or 0)
                    except Exception as _exc_n:
                        _n = 0
                        logger.debug(f'读本次场次失败'
                                     f'({type(_exc_n).__name__}: {_exc_n})，按 0')
                    # ★★ 记"总记录"（**每次运行**一笔，颗粒度 = 次）★★
                    #    ★ 它**只**写 `total_runs` / `total_log` / `updated`，
                    #      ★ **不碰** `runs` 字段 ⇒ ★ 与"本轮进度不落盘"不冲突
                    #    ★ 与 `runs`（场次）分开 —— 见 `record_entry_run` 的说明
                    _tot = _ts2.record_entry_run(
                        self.config_name, _eid, runs_this_time=_n)
                    logger.info(f'条目运行计数: {_eid} -> 本次 {_n} 场（如实）, '
                                f'累计运行 {_tot} 次')
                    # ★★★ 片 12（用户裁定 丙）: **本次跑完 -> 本轮完成** ★★★
                    #
                    # ## ★★ 这修的是"券用完了还一直重复个人突破" ★★
                    #
                    # ★ 临时任务（`period=none`）**没有**周期完成记忆
                    #   ⇒ ★ 跑完之后**没有任何东西让它退出** ⇒ 被反复派发
                    #   （实测 RealmRaid 每 40 秒一轮，永不停）。
                    # ★ 丙 的两条腿：
                    #   * ★ **调度层**：本次跑完 ⇒ 自动标 completed（这里）
                    #   * ★ **任务自己**：提前做完（如 RealmRaid 券打完）
                    #     ⇒ 调 `mark_entry_completed()` 上报
                    #
                    # ⚠ 判据**已不是**"跑满 target" ——
                    #   ★ 见 `Config.entry_target_reached()`（临时任务成功跑完即 True；
                    #     周期任务 False）；★ 方法名是**历史遗留**，别被名字误导。
                    # ⚠ 只对 `period='none'` 生效（周期任务走周期记忆，不变）。
                    #
                    # ★★ 这一句**必须保留**（不是"计数落盘"）★★
                    #   ★ `mark_entry_completed()` 写的是 `completed_session`
                    #   （= **本次启动时间**），★ 而 `get_entry_completed()`
                    #   **按它与 `session_start` 比对判过期**
                    #   ⇒ ★ **下一次启动自动全部失效 ⇒ 一定能跑** ★ = §1.6 核心机制。
                    #   ★ 删掉它 ⇒ ★ 临时任务无完成标记 ⇒ ★ 反复派发。
                    try:
                        if self.config.entry_is_temporary(_eid) \
                                and self.config.entry_target_reached(_eid):
                            _ts2.mark_entry_completed(
                                self.config_name, _eid,
                                reason=f'本次跑完（已打 {_n} 场）')
                    except Exception as _exc2:
                        logger.debug(f'标记本轮完成失败'
                                     f'({type(_exc2).__name__}: {_exc2})')
            except Exception as exc:
                logger.debug(f'读条目运行计数失败({type(exc).__name__}: {exc})')
            # ★ P-1: 身份一起清掉（不留"上一次跑的是哪条"的错觉）
            self.config.model.running_entry_id = ''
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
