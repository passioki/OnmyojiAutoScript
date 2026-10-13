# This Python file uses the following encoding: utf-8
# @author runhey
# 脚本进程
# github https://github.com/runhey
import sys, os
import signal
import multiprocessing
from asyncio import QueueEmpty, CancelledError, sleep
from enum import Enum

from module.logger import logger
from module.server.config_manager import ConfigManager
from module.server.script_websocket import ScriptWSManager


class ScriptState(int, Enum):
    INACTIVE = 0
    RUNNING = 1
    WARNING = 2
    UPDATING = 3


class ScriptProcess(ScriptWSManager):

    def __init__(self, config_name: str) -> None:
        super().__init__()
        if config_name not in ConfigManager.all_script_files():
            raise FileNotFoundError(f'{config_name}.json not found')
        self.config_name = config_name  # config_name
        self.log_pipe_out, self.log_pipe_in = multiprocessing.Pipe(False)
        self.state_queue = multiprocessing.Queue()
        self.state: ScriptState = ScriptState.INACTIVE
        self._process = None

    async def start(self):
        if self._process:
            logger.warning(f'Script {self.config_name} is initialized')
        if self._process and self._process.is_alive():
            logger.warning(f'Script {self.config_name} is already running and first stop it')
            # 必须 await: 漏掉会让旧子进程存活, 随后 self._process 被覆盖成新对象,
            # 旧进程将成为无人管理、仍在操作模拟器的孤儿进程。
            #
            # ★ 必须在**设置 RUNNING 之前** stop —— `stop()` 自己会把
            #   `self.state` 设为 INACTIVE 并广播。原先 `start()` 是
            #   "先 state=RUNNING 再 stop()", 于是 stop() 把状态覆盖回
            #   INACTIVE, 而**日志协程正是靠 `state != INACTIVE` 才去读管道**
            #   -> 重启后日志永远推不出来(实测: 第 2 次 start 起 0 条)。
            await self.stop()
        # ★ **每次启动都要重建日志管道**。
        #
        #   踩过的坑: 管道只在 `__init__` 里建一次, 而旧子进程退出时会
        #   `log_pipe_in.close()` -> **写端从此关闭**。于是"停止后再启动"时,
        #   新子进程往一个已关闭的写端写日志(或静默丢弃),
        #   读端 `poll()` 永远 False -> 此后再也不推任何日志。
        #
        #   读端是**同一个属性对象**, 所以已经跑着的协程会自动用上新管道。
        self._renew_log_pipe()
        # ★★★ 片 11: **启动脚本【不碰】调度状态**（用户裁定 —— 纠正我的设计）★★★
        #
        # ## ★★ 用户原话 ★★
        #
        # > "我改变主意了，这个**暂停调度/恢复调度**不是集成到**任务运行行里的
        # >  按钮**上了吗，**这应该是 bug，不应该给别的按钮添加该功能造成混淆**。"
        # > "**不要加手动重置**，这个重置功能**本来就应该在已有的按钮中**啊"
        #
        # ## 我原来错在哪
        #
        # ★ 我在 `start()` 里加了 `run_control.clear_all()`（清掉暂停/休息/延后）
        #   ⇒ ★ 让**「启动脚本」按钮**也承担了"恢复调度"的职责
        #   ⇒ 与"暂停/恢复只能由**队列行那个按钮**干"**冲突**，造成混淆。
        #
        # ## 现在（正确职责划分）
        #
        # | 按钮 | 唯一职责 | **不碰** |
        # |---|---|---|
        # | ★ `[▶]/[⏸]`（**队列行**）| 暂停 / 恢复调度 + 播放头 | — |
        # | `[▶ 启动脚本]`（顶部）| ★ **只启停脚本进程** | ✗ 暂停状态 |
        # | 添加 / 清空 / 播放模式 | 只改队列 / 模式 | ✗ 暂停状态 |
        #
        # ⇒ ★ **暂停标记是落盘的、跨进程存活的** —— 这**是正确行为**：
        #   用户点「启动脚本」后仍是暂停态，要靠**队列行那个 `[▶]`** 恢复。
        # ★★★ 子进程**不弹黑色命令行窗口**（用户报的 bug）★★★
        #
        # ## ★★ 用户原话 ★★
        #
        # > "另外启动脚本后，出现了**一个黑色的命令行窗口**，检查一下，
        # >  把他**隐藏掉**。"
        #
        # ## 为什么会弹
        #
        # ★ Windows 上 `multiprocessing` 用 `spawn` 启动子进程时，
        #   会**新建一个控制台窗口**（除非父进程已经是"无控制台"的
        #   GUI 程序 —— 而本服务常常是从控制台 / IDE 启动的）。
        # ★ 子进程本身**不需要**控制台（日志走 `log_pipe`，
        #   状态走 `state_queue`）⇒ 直接给它 `CREATE_NO_WINDOW`。
        #
        # ## 实现
        #
        # ★ `subprocess.CREATE_NO_WINDOW` 在 Windows 上会被
        #   `multiprocessing` 透传给 `CreateProcess`。
        # ★ 非 Windows 平台**没有**这个常量 ⇒ 用 `getattr` 兜底，
        #   保证跨平台不报错（本项目主要跑 Windows，但别写死）。
        _flags = 0
        try:
            import subprocess as _sp
            _flags = getattr(_sp, 'CREATE_NO_WINDOW', 0)
        except Exception:
            _flags = 0

        self._process = multiprocessing.Process(
            target=func,
            args=(self.config_name, self.state_queue, self.log_pipe_in,),
            name=self.config_name,
            daemon=True)
        # ⚠ `creationflags` 只能在**启动前**设（它是进程属性，不是 start() 参数）
        if _flags:
            self._process.creationflags = _flags
        self._process.start()
        # 子进程起来之后再置 RUNNING, 并广播
        self.state = ScriptState.RUNNING
        await self.broadcast_state({"state": self.state})

    def _renew_log_pipe(self) -> None:
        """重建日志管道(旧写端可能已被退出的子进程关闭)。"""
        try:
            if not self.log_pipe_out.closed:
                self.log_pipe_out.close()
        except Exception:
            pass
        self.log_pipe_out, self.log_pipe_in = multiprocessing.Pipe(False)

    async def stop(self):
        self.state = ScriptState.INACTIVE
        await self.broadcast_state({"state": self.state})
        if self._process is None:
            logger.warning(f'Script {self.config_name} process is removed')
            return
        if not self._process.is_alive():
            logger.warning(f'Script {self.config_name} is not running')
            return
        self._process.terminate()
        self._process.join(timeout=0.7)
        if self._process.is_alive():
            logger.error(f'Script {self.config_name} subprocess terminate failed')
            self._process.kill()
        self._process = None

    async def coroutine_broadcast_state(self):
        """
        把子进程的状态转成 WebSocket 推送。

        ★ 同 `coroutine_broadcast_log`: **只 `continue`, 不要 `return`**。
          `main_manager.push_data_handle()` 按 name 记录任务存在与否,
          协程一旦结束就**不会重建** —— 再也不会推状态。
        """
        from asyncio import sleep
        while 1:
            if self.state == ScriptState.INACTIVE:
                await sleep(1)
                continue
            if self._process is None or not self._process.is_alive():
                await sleep(1)
                continue
            await sleep(0.1)
            try:
                if self.state_queue.empty():
                    await sleep(1)
                    continue
                data = self.state_queue.get_nowait()
                if not data:
                    await sleep(0.5)
                    continue
                if 'state' in data and data['state'] == ScriptState.WARNING:
                    self.state = ScriptState.WARNING
                await self.broadcast_state(data)
            except QueueEmpty as e:
                logger.warning(f'QueueEmpty: {e}')
                await sleep(0.5)
                continue
            except CancelledError:
                logger.warning(f'{self.config_name} state coroutine is cancelled')
                return
            except Exception as e:
                logger.error(f'State Error: {e}')
                await sleep(0.5)
                continue

    async def coroutine_broadcast_log(self):
        """
        把子进程的日志转成 WebSocket 推送。

        ## ★ 这里踩过一个坑: 早期 `return` 会**永久**杀死日志

        之前写的是"进程已退出就 `return`" —— 但 `return` 会让**协程整个结束**,
        而 `main_manager.push_data_handle()` 是按 `name` 记录任务是否存在的
        (`if coroutine_log_name not in tasks`), **不会重建**已结束的协程。

        于是: 脚本跑完一轮 -> 协程 `return` 结束 -> 任务字典里还有它 ->
        **此后再也不会推任何日志**, 直到重启 server。
        表现就是"某个账号的日志突然就不显示了"(用户实测反馈)。

        ## 正确做法

        用 `continue` 只**跳过本轮**, 让协程活着 —— 下次 `start()` 后就又能推了。
        """
        from asyncio import sleep
        while 1:
            # ★ 日志协程**不看 `state`** —— 只看"子进程还在不在"。
            #
            #   踩过的坑: 原先要求 `state != INACTIVE` 才读管道, 而
            #   `start()` 里"先设 RUNNING 再 stop()"会把状态覆盖回 INACTIVE
            #   -> 日志协程一直跳过 -> 重启后日志永远推不出来。
            #
            #   日志是"子进程活着就该转发"的东西, 与调度状态无关;
            #   绑在一起只会让两个问题互相牵连。
            if self._process is None or not self._process.is_alive():
                # 进程没了 -> 等下一轮(可能重新 start)
                await sleep(1)
                continue
            await sleep(0.05)
            # ★ 每轮**动态取**读端 —— 不能写成循环外的局部变量。
            #
            #   踩过的坑: `self._renew_log_pipe()` 会替换 `self.log_pipe_out`,
            #   但循环外取一次的局部引用仍指向**旧管道**, 于是重启后
            #   依然读不到任何日志(实测: 第 2 次 start 起日志就是 0 条)。
            pipe = self.log_pipe_out
            try:
                if pipe.closed:
                    await sleep(0.5)
                    continue
                if not pipe.poll():
                    await sleep(0.3)
                    continue
                log = pipe.recv()
                if not log:
                    await sleep(0.5)
                    continue
                await self.broadcast_log(log)
            except (EOFError, OSError) as e:
                # 管道关闭/坏掉: 不能 return, 等下一轮再看
                await sleep(0.5)
                logger.warning(f'{self.config_name} log pipe: {e}')
                continue
            except CancelledError:
                logger.warning(f'{self.config_name} log coroutine is cancelled')
                return
            except Exception as e:
                logger.error(f'Log Error: {e}')
                await sleep(0.5)
                continue


def func(config: str, state_queue: multiprocessing.Queue, log_pipe_in) -> None:
    def signal_handler(signum, frame):
        logger.info(f'Script {config} received signal {signum}, exiting gracefully')
        log_pipe_in.close()
        state_queue.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    def start_log() -> None:
        try:
            from module.logger import set_file_logger, set_func_logger
            set_file_logger(name=config)
            set_func_logger(log_pipe_in.send)
        except Exception as e:
            logger.exception(f'Start log error')
            logger.error(f'Error: {e}')
            raise
    start_log()
    import time
    try:
        # while 1:
        #     time.sleep(1)
        #     logger.info(f'Script {config} is running')
        #     state_queue.put({"state": ScriptState.RUNNING})
        from script import Script
        script = Script(config_name=config)
        script.state_queue = state_queue
        script.loop()
    except SystemExit as e:
        logger.info(f'Script {config} process exit')
        logger.error(f'Error: {e}')
        state_queue.put({"state": ScriptState.WARNING})
        time.sleep(0.1)
        exit(-1)
    except Exception as e:
        logger.exception(f'Run script {config} error')
        logger.error(f'Error: {e}')
        raise


if __name__ == '__main__':
    p = ScriptProcess('oas1')
    p.start()
    from time import sleep
    sleep(10)
    logger.info(p._process.exitcode)


