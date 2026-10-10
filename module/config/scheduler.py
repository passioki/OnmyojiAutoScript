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
                 run_list=None) -> list["Function"]:
        """
        执行 任务的调度
        :param rule:
        :param pending:
        :param run_list: 用户编排的**条目清单**(`module/config/run_list.py` 的
                         `RunList`); 也可传旧的逗号分隔字符串, 会被自动兼容
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

        # 第四种: 用户编排的条目清单
        if rule == ScheduleRule.LIST:
            return TaskScheduler.list_order(pending, run_list)

    @staticmethod
    def list_order(pending: list["Function"], run_list=None) -> list["Function"]:
        """
        **列表模式**: 按用户编排的**条目清单**顺序调度
        (见 `module/config/run_list.py` 与 docs/architecture.md §5)。

        顺序来源(优先级从高到低):
          1. `run_list` 里的 **task 条目** —— 用户编排
          2. 各任务 `meta.py` 的 `TaskSpec.list_pos` —— 内置默认顺序
             (源自原先硬编码在 `config_manual.py` 的 `SCHEDULER_PRIORITY`)
          3. 都没给 -> 排最后, 按名称稳定排序

        ★ 与 FIFO 的区别: FIFO 按 `next_run`(先到点先跑), 仍是"定时优先";
          本方法按列表位置, 是真正的"列表优先"。
        ★ 与 FILTER 的区别: FILTER 的顺序**用户改不了**; 本方法可改。

        ★ 只影响 **pending**(已到点)任务的先后 —— 没到点的任务本来就不参与。
          `rest` / `delay` 条目的**阻塞**效果不在这里处理, 而在
          `Config.get_next()` 里(见 `blocking_entry` 的用法) ——
          因为"阻塞整个调度"是调度器级别的事, 不是排序能表达的。
        """
        from module.config.run_list import RunList
        from module.config.utils import convert_to_underscore

        # 兼容: 允许传旧的逗号分隔字符串
        if isinstance(run_list, str):
            run_list = RunList.from_task_order(run_list)
        if run_list is None:
            run_list = RunList()

        # ★★ B: 按**条目**位置建映射（不再用 `task_order()` 去重保首）★★
        #
        # 用户要求"**可以重复添加相同的任务**"（变相实现多次跑）。
        # 而 `task_order()` 是"去重保首"的, 重复条目的第二条**拿不到位置**。
        #
        # 这里遍历**条目**, 取每个任务的**最早**出现位置（一个 `Function`
        # 对象只能对应一个排序位置 —— 见台账 §21.3 障碍 3）。
        order_index = {}
        dup_count = {}
        entries = getattr(run_list, 'entries', None) or []
        pos = 0
        for e in entries:
            if getattr(e, 'kind', None) is not None and \
                    str(getattr(e, 'kind', '')) not in ('task', 'EntryKind.TASK'):
                continue
            name = getattr(e, 'task', None)
            if not name:
                continue
            dup_count[name] = dup_count.get(name, 0) + 1
            # 最早出现的位置生效（重复条目不覆盖）
            for key in (name, convert_to_underscore(name)):
                if key not in order_index:
                    order_index[key] = pos
            pos += 1
        if any(v > 1 for v in dup_count.values()):
            repeats = {k: v for k, v in dup_count.items() if v > 1}
            logger.info(
                f'执行队列里有**重复条目** {repeats} —— 用户用重复条目表达'
                f'"这个任务跑多次"（见 docs/SESSION-LEDGER.md §21）')

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

