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

#: 排序兜底值 —— `next_run` 缺失时用它把该任务压到最后。
#:
#: ★ 为什么不能直接用 `None`: 排序键里混入 `None` 与 `datetime`
#:   会在 Python 3 抛 `TypeError: '<' not supported between instances`。
_FAR_FUTURE = datetime(2099, 1, 1)


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
            # ★ 两个总开关（用户确认的设计）:
            #   固定任务（fixed/toppa）看 `enable_fixed`,
            #   定时任务（timed/charge/limited）看 `enable_timed`。
            #   两者**互不影响** —— 关掉固定任务不该影响定时任务。
            #
            #   类别由 `tasks/<Name>/meta.py` 声明（`TaskMeta.category`）,
            #   这里只做"该不该考虑"的判断, 不重复定义知识。
            if not self._category_enabled(func.command):
                waiting_task.append(func)
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
            _opt = self.model.script.optimization
            pending_task = TaskScheduler.schedule(
                rule=_opt.schedule_rule,
                pending=pending_task,
                run_list=self.build_run_list())
            # ★ 定时任务**内部**排序 + 定时优先时提到最前（见 docs §5.4.1）
            pending_task = self._order_by_timed_priority(pending_task)
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

    # ------------------------------------------------------------------ 定时任务排序
    def _order_by_timed_priority(self, pending):
        """
        定时任务排序, 并在 `timed_priority=timed` 时**提到最前**。

        ## 为什么定时任务要单独排

        固定任务由**用户拖拽的顺序**决定（`run_list`）；
        定时任务有 window / 存量 / 周期, 该按 `timed_sort_key` 排
        （能否跑 > 到点程度 > 窗口快关 > 耗时短 > 用户优先级）。

        把两者混在一个序列里用同一个规则排, 必然有一方不合理。

        ## 为什么 `timed` 模式下要提到最前

        定时任务有 **window 约束** —— 错过了今天就做不了；
        而固定任务什么时候跑都行。所以定时优先时让它们先跑。

        ★ 这是"让位"的**调度侧**实现（谁排在前面）；
          "什么时候切过去"仍由 `script.py` 在**战斗边界**判断 ——
          这里只决定顺序, 不会打断正在跑的战斗。
        """
        try:
            from module.config import task_catalog as TC
            from module.config import timed_schedule as TS

            def cat_of(cmd):
                m = TC.get(cmd)
                return m.category.value if m else ''

            def meta_of(cmd):
                return TC.get(cmd)

            timed, others = TS.partition_pending(pending, cat_of)
            if not timed:
                return pending

            # 定时任务内部排序
            #
            # ⚠ 排序键里**不要混入不可比较的对象**（如 `None` 与 `datetime`）——
            #   Python 3 会抛 `TypeError`。`next_run` 缺失时用一个远期值兜底。
            def key_of(item):
                cmd = getattr(item, 'command', '') or ''
                nr = getattr(item, 'next_run', None) or _FAR_FUTURE
                exp = 0
                pri = getattr(item, 'priority', 5)
                try:
                    sub = getattr(self, convert_to_underscore(cmd), None)
                    sch = getattr(sub, 'scheduler', None) if sub else None
                    exp = int(getattr(sch, 'expected_minutes', 0) or 0)
                    pri = int(getattr(sch, 'priority', pri) or pri)
                except Exception:
                    pass
                return TS.timed_sort_key(
                    next_run=nr,
                    # 能进 pending 就说明已经过了"在不在 window"这道关
                    in_window=True,
                    window_end=None,
                    expected_minutes=exp,
                    priority=pri)

            timed = TS.sort_timed(timed, key_of)

            if str(self.opt_value('timed_priority', 'timed')).lower() == 'timed':
                logger.info('定时优先: 定时任务排到固定任务之前'
                            f'（{len(timed)} 个）')
                return timed + others
            # 列表优先: 保持固定任务的用户顺序, 定时任务附在后面
            return others + timed
        except Exception as exc:
            logger.warning(f'定时任务排序失败({type(exc).__name__}: {exc}), '
                           f'保持原顺序')
            return pending

    # ------------------------------------------------------------------ 运行列表
    def build_run_list(self):
        """
        把配置里的 `run_list`(原始 JSON 数组)解析成 `RunList`。

        坏条目**跳过**并记 warning —— 列表是用户编辑的内容,
        一条写坏不该让整个配置加载失败。
        """
        from module.config.run_list import RunList

        raw = getattr(self.model.script.optimization, 'run_list', None) or []

        def _on_bad(item, exc):
            logger.warning(f'运行列表里有无法解析的条目, 已跳过: {item!r} ({exc})')

        return RunList.from_list(raw, on_bad=_on_bad)

    def save_run_list(self, run_list) -> bool:
        """把 `RunList` 写回配置(供界面排序 / 条目增减调用)。"""
        try:
            self.model.script.optimization.run_list = run_list.to_list()
            self.save()
            logger.info(f'运行列表已保存({len(run_list)} 个条目)')
            return True
        except Exception as exc:
            logger.error(f'保存运行列表失败({type(exc).__name__}: {exc})')
            return False

    def apply_run_list_blocker(self, now=None) -> bool:
        """
        处理运行列表里的**阻塞条目**(`rest` / `delay`)。

        语义(见 `module/config/run_list.py`):

        | 条目 | 效果 | 是否影响定时任务 |
        |---|---|---|
        | `rest`  | **全部停止** N 分钟 | ✅ 连定时任务一起停 |
        | `delay` | **只停列表** N 分钟 | ❌ 定时任务照常 |

        实现: `rest` 写 `run_control.rest_until`(全局暂停, 与手动"全部停止"同一处),
        `delay` 写 `run_control.list_resume_at`。

        :return: True 表示"现在被阻塞, 不该派发任务"
        """
        from datetime import datetime

        from module.config import run_control

        now = now or datetime.now()
        rl = self.build_run_list()
        blocker = rl.blocking_entry()
        if blocker is None:
            return False

        from module.config.run_list import EntryKind

        if blocker.kind != EntryKind.REST:
            # v2 只有 rest 会阻塞 —— 别的情况不该走到这里
            logger.warning(f'运行列表: 未知的阻塞条目 {blocker!r}, 已移除')
            rl.remove_blocker()
            self.save_run_list(rl)
            return False

        until = run_control.rest_until()
        if until is None:
            # 该条目还没生效 -> 起算并写状态
            run_control.rest(minutes=blocker.minutes)
            until = run_control.rest_until()
            logger.info(f'运行列表: 「{blocker.describe()}」生效'
                        f'（休息 = 去庭院待着）')
        if until is not None and now < until:
            # ★ 「休息时可穿插定时任务」: 若有能在休息剩余时间内**跑完**的
            #   到点定时任务, 就**不阻塞** —— 让那个任务先跑。
            #
            #   用户确认的判据: 定时任务的预期完成时间 < 休息剩余时间。
            #   目的: 保护**组队任务**（休息期间在庭院干等会让组队很难凑齐人）。
            candidate = self.pick_interleave_candidate(now)
            if candidate:
                logger.info(f'运行列表: 休息中穿插定时任务 {candidate}'
                            f'（剩余 {self.rest_remaining_minutes(now)} 分钟）')
                return False
            return True
        # 到点了 -> 移除条目, 列表继续
        rl.remove_blocker()
        self.save_run_list(rl)
        logger.info(f'运行列表: 「{blocker.describe()}」已结束, 条目移除')
        return False

    def pick_interleave_candidate(self, now=None) -> str:
        """
        挑一个"能在休息剩余时间内跑完"的**到点定时任务**；没有则 ''。

        判据（用户确认）:

            定时任务的 `scheduler.expected_minutes` < 休息剩余分钟数

        ★ `expected_minutes == 0`（用户没配）-> **不穿插** ——
          拿未知值去比会得出错误结论, 宁可少穿插。
        """
        if not self.can_interleave_timed(now):
            return ''
        try:
            from module.config import task_catalog as TC
            from module.config import timed_schedule as TS

            left = self.rest_remaining_minutes(now)
            if left <= 0:
                return ''
            # 只看到点的（`pending_task` 就是"已到点"的集合）
            for func in (self.pending_task or []):
                cmd = getattr(func, 'command', '') or ''
                meta = TC.get(cmd)
                if meta is None or not TS.is_timed(meta.category.value):
                    continue
                exp = self._expected_minutes(cmd)
                if TS.can_interleave(
                        rest_interleave=True,
                        enable_timed=True,
                        is_due=True,
                        expected_minutes=exp,
                        rest_remaining_minutes=left):
                    return cmd
        except Exception as exc:
            logger.warning(f'挑穿插候选失败({type(exc).__name__}: {exc}), 放弃穿插')
        return ''

    def _expected_minutes(self, task_command: str) -> int:
        """读某任务的 `scheduler.expected_minutes`（读不到给 0 = 未知）。"""
        try:
            from module.config.utils import convert_to_underscore
            sub = getattr(self, convert_to_underscore(task_command), None)
            sch = getattr(sub, 'scheduler', None) if sub else None
            return int(getattr(sch, 'expected_minutes', 0) or 0)
        except Exception:
            return 0

    # ------------------------------------------------------------------ 固定/定时 分开管理
    def fixed_enabled(self) -> bool:
        """固定任务总开关。"""
        try:
            return bool(getattr(self.model.script.optimization,
                                'enable_fixed', True))
        except Exception:
            return True

    def timed_enabled(self) -> bool:
        """定时任务总开关。"""
        try:
            return bool(getattr(self.model.script.optimization,
                                'enable_timed', True))
        except Exception:
            return True

    def opt_value(self, field: str, default=None):
        """读 `Script.optimization.<field>`（枚举取 `.value`）。"""
        try:
            v = getattr(self.model.script.optimization, field, None)
        except Exception:
            return default
        if v is None:
            return default
        return getattr(v, 'value', v)

    def should_schedule(self, category_value: str) -> bool:
        """
        该**类别**的任务现在是否参与调度。

        固定任务看 `enable_fixed`，定时任务看 `enable_timed` ——
        两个开关**互不影响**。
        """
        from module.config.timed_schedule import should_consider
        return should_consider(category_value,
                               enable_fixed=self.fixed_enabled(),
                               enable_timed=self.timed_enabled())

    def _category_enabled(self, task_command: str) -> bool:
        """
        该**任务**现在是否参与调度（按它在 `meta.py` 里声明的类别）。

        ★ 元数据缺失的任务（还没写 `meta.py` 的）**默认放行** ——
          否则新加的任务会因为"没登记"而被静默跳过, 很难排查。
        """
        try:
            from module.config import task_catalog as TC
            meta = TC.get(task_command)
            if meta is None:
                return True
            return self.should_schedule(meta.category.value)
        except Exception as exc:
            logger.warning(f'{task_command}: 判断类别开关失败'
                           f'({type(exc).__name__}: {exc}), 按放行处理')
            return True

    def rest_remaining_minutes(self, now=None) -> int:
        """休息还剩多少分钟（不在休息则 0）。供"休息时穿插"判定。"""
        from datetime import datetime

        from module.config import run_control

        now = now or datetime.now()
        until = run_control.rest_until()
        if until is None or now >= until:
            return 0
        return max(0, int((until - now).total_seconds() // 60))

    def can_interleave_timed(self, now=None) -> bool:
        """
        **当前**是否处于"休息且允许穿插"的状态。

        具体某个定时任务能不能塞进去，还要看它自己的
        `scheduler.expected_minutes`（见 `pick_interleave_candidate`）。
        """
        if not bool(self.opt_value('rest_interleave', False)):
            return False
        if not self.timed_enabled():
            return False
        return self.rest_remaining_minutes(now) > 0

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
