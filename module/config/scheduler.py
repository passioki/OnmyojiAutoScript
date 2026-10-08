# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
import datetime
import operator

from cached_property import cached_property

from module.base.filter import Filter

from module.config.config_manual import ConfigManual
from module.logger import logger

from tasks.Script.config_optimization import ScheduleRule


class TaskScheduler:
    filter = Filter(regex=r"(.*)", attr=["command"])
    filter.load(ConfigManual.SCHEDULER_PRIORITY)

    @staticmethod
    def schedule(rule: ScheduleRule, pending: list["Function"],
                 task_order: str = '') -> list["Function"]:
        """
        执行 任务的调度
        :param rule:
        :param pending:
        :param task_order: 用户编排的列表顺序(逗号分隔任务名); 仅 LIST 规则使用
        :return:
        """
        if rule not in (ScheduleRule.FILTER, ScheduleRule.FIFO,
                        ScheduleRule.PRIORITY, ScheduleRule.LIST):
            logger.error(f"Invalid rule: {rule}")
            return pending
        if isinstance(pending, list) is False:
            logger.error(f"Invalid pending: {pending}")
            return pending

        # 第一种
        if rule == ScheduleRule.FILTER:
            pending_task = TaskScheduler.filter.apply(pending)
            return pending_task

        # 第二种
        if rule == ScheduleRule.FIFO:
            pending_task = TaskScheduler.fifo(pending)
            return pending_task

        # 第三种
        if rule == ScheduleRule.PRIORITY:
            pending_task = TaskScheduler.priority(pending)
            return pending_task

        # 第四种: 用户编排的任务列表
        if rule == ScheduleRule.LIST:
            return TaskScheduler.list_order(pending, task_order)

    @staticmethod
    def list_order(pending: list["Function"], task_order: str = '') -> list["Function"]:
        """
        **列表模式**: 按用户编排的任务列表顺序调度(见 docs/architecture.md §5)。

        顺序来源(优先级从高到低):
          1. `task_order` 参数 —— 界面写入的**用户编排**(逗号分隔任务名)
          2. 各任务 `meta.py` 的 `TaskSpec.list_pos` —— 内置默认顺序
             (源自原先硬编码在 `config_manual.py` 的 `SCHEDULER_PRIORITY`)
          3. 都没给 -> 排最后, 按名称稳定排序

        ★ 与 FIFO 的区别: FIFO 按 `next_run`(先到点先跑), 仍是"定时优先";
          本方法按列表位置, 是真正的"列表优先"。
        ★ 与 FILTER 的区别: FILTER 的顺序**用户改不了**; 本方法可改。

        只影响 **pending**(已到点)任务的先后 —— 没到点的任务本来就不参与。
        """
        # 用户编排
        from module.config.utils import convert_to_underscore

        explicit = []
        for part in str(task_order or '').split(','):
            part = part.strip()
            if part:
                explicit.append(part)
        order_index = {}
        for i, name in enumerate(explicit):
            order_index[name] = i
            # 同时接受下划线形式, 免得界面传 'fallen_sun' 而 command 是 'FallenSun'
            order_index[convert_to_underscore(name)] = i

        # 内置默认顺序(取自 meta.py 的 list_pos)
        default_index = {}
        try:
            from module.config import task_catalog as TC
            for spec in TC.all_specs().values():
                if spec.list_pos is not None:
                    default_index[spec.task] = spec.list_pos
        except Exception as exc:
            logger.warning(f'读取 list_pos 失败({type(exc).__name__}: {exc}), '
                           f'列表顺序退化为按名称')

        def _key(task):
            name = getattr(task, 'command', '') or ''
            # 归一化后再查: 界面可能写 'fallen_sun' 而 command 是 'FallenSun'
            name_snake = convert_to_underscore(name)
            if name in order_index:
                return (0, order_index[name], name)
            if name_snake in order_index:
                return (0, order_index[name_snake], name)
            if name in default_index:
                return (1, default_index[name], name)
            return (2, 0, name)

        tasks_pending = sorted(pending, key=_key)
        # 永远保证 Restart 任务在最前(与 fifo 的既有约定一致)
        for task in tasks_pending:
            if getattr(task, 'command', '') == 'Restart':
                tasks_pending.remove(task)
                tasks_pending.insert(0, task)
                break
        return tasks_pending

    @staticmethod
    def fifo(pending: list["Function"]) -> list["Function"]:
        """
        先来后到，（按照任务的先后顺序进行调度）
        :param pending:
        :return:
        """
        tasks_pending = sorted(pending, key=operator.attrgetter("next_run"))
        for task in tasks_pending:
            # 永远保证 Restart 任务在第一个
            if task.command == 'Restart':
                tasks_pending.remove(task)
                tasks_pending.insert(0, task)
                break
        return tasks_pending

    @staticmethod
    def priority(pending: list["Function"]) -> list["Function"]:
        """
        基于优先级，同一个优先级的任务按照先来后到的顺序进行调度，优先级高的任务先调度
        :param pending:
        :return:
        """
        # 1. 按照优先级进行分组
        sorted(pending, key=operator.attrgetter("priority"))
        groups = {}
        for task in pending:
            if groups.get(task.priority) is None:
                groups[task.priority] = []
            groups[task.priority].append(task)
        # 2. 对每一组进行先来后到的排序
        for priority, tasks in groups.items():
            groups[priority] = TaskScheduler.fifo(tasks)

        # 3.按照顺序合并所有的任务
        tasks_pending = []
        for priority in sorted(groups.keys()):
            tasks_pending.extend(groups[priority])

        return tasks_pending


# 测试代码
if __name__ == '__main__':
    pass

