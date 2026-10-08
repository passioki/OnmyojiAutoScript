# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import copy
import datetime
import operator
import threading
import random

from datetime import datetime, timedelta
from cached_property import cached_property
from threading import Lock

from module.base.filter import Filter
from module.config.config_manual import ConfigManual
from module.config.config_watcher import ConfigWatcher
from module.config.config_menu import ConfigMenu
from module.config.config_model import ConfigModel
from module.config.config_state import ConfigState
from module.config.scheduler import TaskScheduler
from module.config.utils import *
from module.notify.notify import Notifier

from module.exception import RequestHumanTakeover, ScriptError
from module.logger import logger


class Function:
    def __init__(self, key: str, data: dict):
        """
        输入的是每一个ConfigModel的一个字段对象
        :param data:
        """
        if isinstance(data, dict) is False:
            self.enable = False
            self.command = "Unknown"
            self.next_run = DEFAULT_TIME
            self.window = None
            return
        if data.get("scheduler") is None:
            self.enable = False
            self.command = "Unknown"
            self.next_run = DEFAULT_TIME
            self.window = None
            return

        self.enable: bool = data['scheduler']['enable']
        self.command: str = ConfigModel.type(key)
        next_run = data['scheduler']['next_run']
        if isinstance(next_run, str):
            next_run = datetime.strptime(next_run, "%Y-%m-%d %H:%M:%S")
        self.next_run: datetime = next_run
        priority = data['scheduler']['priority']
        if isinstance(priority, str):
            priority = int(priority)
        self.priority: int = priority
        if not isinstance(self.priority, int):
            logger.error(f"Invalid priority: {self.priority}")

        # 开放时段(游戏机制, 硬约束)。**默认关闭** -> 不限时段, 行为与改造前一致。
        #
        # 阴阳师很多玩法有固定开放时段(如逢魔之时 17:00-23:00)。此前 OAS 没有这个
        # 概念, 用户只能把 success_interval 设短让任务频繁醒来碰运气 —— 于是
        # "用户轮询节奏"混进了本该表达游戏机制的字段。这里把它显式建模。
        #
        # 解析失败时退化为"不限时段", 不让配置错误把任务卡死。
        self.window = self._build_window(data.get('scheduler') or {})

        # self.enable = deep_get(data, keys="Scheduler.Enable", default=False)
        # self.command = deep_get(data, keys="Scheduler.Command", default="Unknown")
        # self.next_run = deep_get(data, keys="Scheduler.NextRun", default=DEFAULT_TIME)

    def _build_window(self, sch: dict):
        """
        从 `scheduler` 节点构造开放时段。

        **与 `Scheduler.build_window()` 共用 `AvailabilityWindow`, 且解析规则一致** ——
        避免同一份配置在两处被解释成不同结果(本项目已因"知识存在两处"
        栽过一次: 生成器与 from_legacy 的分类判定不一致, 丢了 6 个任务的间隔信息)。
        """
        from module.config.availability import ALL_DAYS, AvailabilityWindow
        if not sch.get('window_enable'):
            return AvailabilityWindow()

        days, bad = [], []
        for part in str(sch.get('window_days') or '').split(','):
            part = part.strip()
            if part == '':
                continue
            if part.lstrip('-').isdigit() and 0 <= int(part) <= 6:
                days.append(int(part))
            else:
                bad.append(part)
        if bad:
            # 逐项跳过而不是整体丢弃: '4,abc,6' 里 4/6 仍是有效的用户意图
            logger.warning(f'{self.command}: window_days 无效项已忽略 {bad}'
                           f'（应为 0-6, 周一=0）')

        try:
            return AvailabilityWindow(
                enabled=True,
                start=sch['window_start'],
                end=sch['window_end'],
                days=tuple(sorted(set(days))) or ALL_DAYS,
            )
        except Exception as exc:
            logger.warning(f'{self.command}: 开放时段配置非法'
                           f'({type(exc).__name__}: {exc}), 按不限时段处理')
            return AvailabilityWindow()

    def in_window(self, now: datetime = None) -> bool:
        """当前是否落在开放时段内。未配置时段时恒为 True。"""
        if self.window is None or not self.window.enabled:
            return True
        return self.window.contains(now or datetime.now())

    @property
    def window_reason(self) -> str or None:
        """若因开放时段不可跑, 返回可读原因; 否则 None。"""
        if self.window is None or not self.window.enabled:
            return None
        now = datetime.now()
        if self.window.contains(now):
            return None
        opening = self.window.next_opening(now)
        return (f'不在开放时段（{self.window.describe()}，'
                f'{opening:%m-%d %H:%M} 开放）')

    def __str__(self):
        enable = "Enable" if self.enable else "Disable"
        return f"{self.command} ({enable}, {self.priority}, {str(self.next_run)})"

    __repr__ = __str__

    def __eq__(self, other):
        if not isinstance(other, Function):
            return False

        if self.command == other.command and self.next_run == other.next_run:
            return True
        else:
            return False


def name_to_function(name):
    """
    Args:
        name (str):

    Returns:
        Function:
    """
    function = Function({})
    function.command = name
    function.enable = True
    return function


class Config(ConfigState, ConfigManual, ConfigWatcher, ConfigMenu):

    def __init__(self, config_name: str, task=None) -> None:
        """

        :param config_name:
        :param task:
        """
        super().__init__(config_name)  # 调用 ConfigState 的初始化方法
        super(ConfigManual, self).__init__()
        super(ConfigWatcher, self).__init__()
        super(ConfigMenu, self).__init__()
        self.model = ConfigModel(config_name=config_name)
        self.scheduler_update_dt = None  # 调度器更新时间

    def __getattr__(self, name):
        """
        一开始是打算直接继承ConfigModel的，但是pydantic会接管所有的变量
        故而选择持有ConfigModel
        :param name:
        :return:
        """
        try:
            return getattr(self.model, name)
        except AttributeError:
            # 这个导致 大量的无用log
            # logger.error(f'can not ask this variable {name}')
            return None  # 或者抛出异常，或者返回其他默认值

    @cached_property
    def lock_config(self) -> Lock:
        return Lock()

    @cached_property
    def notifier(self):
        notifier = Notifier(self.model.script.error.notify_config, enable=self.model.script.error.notify_enable)
        notifier.config_name = self.config_name.upper()
        logger.info(f'Notifier: {notifier.config_name}')
        return notifier

    def gui_args(self, task: str) -> str:
        """
        获取给gui显示的参数
        :return:
        """
        return self.model.gui_args(task=task)

    def get_arg(self, task: str, group: str, argument: str):
        """

        :param task:
        :param group:
        :param argument:
        :return: str/int/float
        """
        try:
            return self.data[task][group][argument]
        except:
            logger.exception(f'have no arg {task}.{group}.{argument}')

    def set_arg(self, task: str, group: str, argument: str, value) -> None:
        """

        :param task:
        :param group:
        :param argument:
        :param value:
        :return:
        """
        try:
            self.data[task][group][argument] = value
        except:
            logger.exception(f'have no arg {task}.{group}.{argument}')

    def reload(self):
        self.model = ConfigModel(config_name=self.config_name)

    def save(self) -> None:
        """
        保存配置文件
        :return:
        """
        self.model.write_json(self.config_name, self.model.dict())

    def update_scheduler(self) -> None:
        """
        更新调度器， 设置pending_task and waiting_task
        :return:
        """
        pending_task = []
        waiting_task = []
        error = []
        self.scheduler_update_dt = datetime.now()
        for key, value in self.model.dict().items():
            func = Function(key, value)
            if not func.enable:
                continue
            if not isinstance(func.next_run, datetime):
                error.append(func)
            elif func.next_run < self.scheduler_update_dt:
                # 完成记忆: 本周期已成功完成过的任务不再入队, 并把 next_run 推到下个周期
                if self._skip_by_period(key, value):
                    waiting_task.append(func)
                    continue
                # 开放时段(新增, 默认关闭): 游戏机制决定的硬约束。
                # 不在时段内的任务入 waiting 而不是 pending, 避免白跑一趟 ——
                # 这正是用户此前只能靠"缩短轮询间隔碰运气"绕过的那个问题。
                if not func.in_window():
                    logger.info(f'{func.command} 暂缓: {func.window_reason}')
                    waiting_task.append(func)
                    continue
                pending_task.append(func)
            else:
                waiting_task.append(func)

        # f = Filter(regex=r"(.*)", attr=["command"])
        # f.load(self.SCHEDULER_PRIORITY)
        if pending_task:
            pending_task = TaskScheduler.schedule(rule=self.model.script.optimization.schedule_rule,
                                                  pending=pending_task)
            # 防止正在运行的任务被新上来的pending队列中的任务给顶替掉
            if self.model.running_task and pending_task:
                for i, obj in enumerate(pending_task):
                    if obj.command == self.model.running_task:
                        pending_task.insert(0, pending_task.pop(i))
                        logger.info(f'{self.model.running_task} is running')
                        break
        if waiting_task:
            # waiting_task = f.apply(waiting_task)
            waiting_task = sorted(waiting_task, key=operator.attrgetter("next_run"))
        if error:
            pending_task = error + pending_task

        self.pending_task = pending_task
        self.waiting_task = waiting_task

    def _skip_by_period(self, task_key: str, task_value: dict) -> bool:
        """
        完成记忆: 判断该任务是否"本周期已成功完成", 若是则跳过本次调度。

        task_value 是 model.dict() 里该任务的原始 dict, 其中 scheduler.period /
        reset_at 可能是枚举或字符串(取决于序列化方式), 这里都兼容。

        任何异常都返回 False(即照常运行), 保证记忆功能不会让任务跑不了。
        """
        try:
            # model.dict() 里除任务外还有 config_name / running_task 等字符串字段
            if not isinstance(task_value, dict):
                return False
            scheduler = task_value.get('scheduler')
            if not isinstance(scheduler, dict):
                return False
            period = scheduler.get('period')
            if not period:
                return False
            period_str = getattr(period, 'value', period)
            if str(period_str).lower() in ('none', ''):
                return False

            reset_at = scheduler.get('reset_at')
            if reset_at is None:
                reset_at = time(hour=0)
            elif isinstance(reset_at, str):
                reset_at = time.fromisoformat(reset_at)

            from module.config.task_state import is_completed_in_period, period_start
            if not is_completed_in_period(self.config_name, task_key, period_str, reset_at):
                return False

            # 已在本周期完成 -> 把 next_run 推到下个周期起点, 避免每轮重复判断
            next_start = period_start(period_str, reset_at)
            self.model.deep_set(self.model, keys=f'{task_key}.scheduler.next_run',
                                value=next_start)
            logger.info(f'任务 `{task_key}` 本周期({period_str})已完成, 跳过; '
                        f'下次运行 {next_start}')
            return True
        except Exception as exc:
            logger.warning(f'_skip_by_period({task_key}) 异常 '
                           f'({type(exc).__name__}: {exc}), 按未完成处理')
            return False

    def _record_task_success(self, task_key: str, scheduler) -> None:
        """
        完成记忆: 任务成功结束时, 记录"本周期已完成"。

        仅在 scheduler.period 不为 none 时才需要记录; 异常只告警, 不影响任务本身。

        :param task_key: 下划线形式的任务名
        :param scheduler: 该任务的 scheduler 配置对象
        """
        try:
            period = getattr(scheduler, 'period', None)
            if not period:
                return
            period_str = getattr(period, 'value', period)
            if str(period_str).lower() in ('none', ''):
                return
            reset_at = getattr(scheduler, 'reset_at', None) or time(hour=0)
            if isinstance(reset_at, str):
                reset_at = time.fromisoformat(reset_at)

            from module.config.task_state import record_success
            record_success(self.config_name, task_key, period_str, reset_at)
        except Exception as exc:
            logger.warning(f'_record_task_success({task_key}) 异常 '
                           f'({type(exc).__name__}: {exc}), 忽略')

    def get_next(self) -> Function:
        """
        获取下一个要执行的任务
        :return:
        """
        self.update_scheduler()

        if self.pending_task:
            logger.info(f"Pending tasks: {[f.command for f in self.pending_task]}")
            task = self.pending_task[0]
            self.task = task
            logger.attr("Task", task)
            return task

        # 哪怕是没有任务，也要返回一个任务，这样才能保证调度器正常运行
        if self.waiting_task:
            logger.info("No task pending")
            task = copy.deepcopy(self.waiting_task[0])
            # task.next_run = (task.next_run + self.hoarding).replace(microsecond=0)
            logger.attr("Task", task)
            return task
        else:
            logger.critical("No task waiting or pending")
            logger.critical("Please enable at least one task")
            raise RequestHumanTakeover

    def get_schedule_data(self) -> dict[str, dict]:
        """
        获取调度器的数据， 但是你必须使用update_scheduler来更新信息
        :return:
        """
        # 根据调度器更新时间来判断是否有可运行的任务,保证逻辑一致性
        scheduler_update_dt = getattr(self, 'scheduler_update_dt', datetime.now())
        running = {}
        if self.task is not None and self.task.next_run < scheduler_update_dt:
            running = {"name": self.task.command, "next_run": str(self.task.next_run)}

        pending = []
        for p in self.pending_task[1:]:
            item = {"name": p.command, "next_run": str(p.next_run)}
            pending.append(item)

        waiting = []
        for w in self.waiting_task:
            item = {"name": w.command, "next_run": str(w.next_run)}
            waiting.append(item)

        data = {"running": running, "pending": pending, "waiting": waiting}
        return data

    def task_call(self, task: str = None, force_call=True):
        """
        回调任务，这会是在任务结束后调用
        :param task: 调用的任务的大写名称
        :param force_call:
        :return:
        """
        task = convert_to_underscore(task)
        if self.model.deep_get(self.model, keys=f'{task}.scheduler.next_run') is None:
            raise ScriptError(f"Task to call: `{task}` does not exist in user config")

        task_enable = self.model.deep_get(self.model, keys=f'{task}.scheduler.enable')
        if force_call or task_enable:
            logger.info(f"Task call: {task}")
            next_run = datetime.now().replace(
                microsecond=0
            )
            self.model.deep_set(self.model, keys=f'{task}.scheduler.next_run', value=next_run)
            self.save()
            return True
        else:
            logger.info(f"Task call: {task} (skipped because disabled by user)")
            return False

    def task_delay(self, task: str, start_time: datetime = None,
                   success: bool = None, server: bool = True, target: datetime = None) -> None:
        """
        设置下次运行时间  当然这个也是可以重写的
        :param target: 可以自定义的下次运行时间
        :param server: True
        :param success: 判断是成功的还是失败的时间间隔
        :param task: 任务名称，大驼峰的
        :param finish: 是完成任务后的时间为基准还是开始任务的时间为基准
        :return:
        """
        # 加载配置文件
        # reload() 会用磁盘内容重建整个 model, 因此会把"运行时状态"也一起换成磁盘旧值。
        # running_task 由 Script.loop() 在内存里设置(script.py:688/691), 一旦被 reload
        # 覆盖成上一次 save() 落盘的旧任务名, 就会污染后续的 save() 并让任务名与任务目录
        # 不一致。触发路径: _wait_close_game() 内 self.run('Restart'), 此时 model 残留
        # FrogBoss 而 path 是 Restart。故 reload 前后需要保护这类运行时字段。
        _runtime_task = getattr(self.model, 'running_task', '')
        self.reload()
        if getattr(self.model, 'running_task', '') != _runtime_task:
            self.model.running_task = _runtime_task
        # 任务预处理
        if not task:
            task = self.task.command
        task = convert_to_underscore(task)
        task_object = getattr(self.model, task, None)
        if not task_object:
            logger.warning(f'No task named {task}')
            return
        scheduler = getattr(task_object, 'scheduler', None)
        if not scheduler:
            logger.warning(f'No scheduler in {task}')
            return

        # 任务开始时间
        if not start_time:
            start_time = datetime.now().replace(microsecond=0)

        # 依次判断是否有自定义的下次运行时间
        run = []
        if success is not None:
            interval = (
                scheduler.success_interval
                if success
                else scheduler.failure_interval
            )
            if isinstance(interval, str):
                interval = timedelta(interval)
            run.append(start_time + interval)
            # 完成记忆: 仅在成功时记录"本周期已完成"
            if success:
                self._record_task_success(task_key=task, scheduler=scheduler)
        # if server is not None:
        #     if server:
        #         server = scheduler.server_update
        #         run.append(get_server_next_update(server))
        if target is not None:
            target = [target] if not isinstance(target, list) else target
            target = nearest_future(target)
            run.append(target)

        next_run = None
        # 排序
        if not len(run):
            raise ScriptError(
                "Missing argument in delay_next_run, should set at least one"
            )

        run = min(run).replace(microsecond=0)
        next_run = run

        if server and hasattr(scheduler, 'server_update'):
            # 加入随机延迟时间
            float_seconds = (scheduler.float_time.hour * 3600 +
                             scheduler.float_time.minute * 60 +
                             scheduler.float_time.second)
            random_float = random.randint(0, float_seconds)
            # 如果有强制运行时间
            if scheduler.server_update == time(hour=9):
                next_run += timedelta(seconds=random_float)
            else:
                next_run = parse_tomorrow_server(scheduler.server_update, scheduler.delay_date, random_float)

        # 将这些连接起来，方便日志输出
        kv = dict_to_kv(
            {
                "success": success,
                "server_update": server,
                "target": target,
            },
            allow_none=False,
        )
        logger.info(f"Delay task `{task}` to {next_run} ({kv})")

        # 保证线程安全的
        self.lock_config.acquire()
        try:
            scheduler.next_run = next_run
            self.save()
        finally:
            self.lock_config.release()
        # 设置
        logger.attr(f'{task}.scheduler.next_run', next_run)


if __name__ == '__main__':
    config = Config(config_name='oas1')
    config.notifier.push(title="0000", content="dddddddd")

    # print(config.get_next())
