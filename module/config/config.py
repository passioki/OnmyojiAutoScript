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
from module.config.availability import (  # ★ (b) 动态窗口解析
    parse_weekday, parse_time)

#: 排序兜底值 —— `next_run` 缺失时用它把该任务压到最后。
#:
#: ★ 为什么不能直接用 `None`: 排序键里混入 `None` 与 `datetime`
#:   会在 Python 3 抛 `TypeError: '<' not supported between instances`。
_FAR_FUTURE = datetime(2099, 1, 1)


# ★ ⑥(b): `window_slots` 里每个时刻的窗口跨度（分钟）。
#   "12:00" -> 窗口 12:00-13:59。够跑一次任务, 又不至于整天开放。
_SLOT_SPAN_MINUTES = 120


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
            self.windows = ()
            self.window = None
            self.entry_id = None
            self.node = None
            return
        if data.get("scheduler") is None:
            self.enable = False
            self.command = "Unknown"
            self.next_run = DEFAULT_TIME
            self.windows = ()
            self.window = None
            self.entry_id = None
            self.node = None
            return

        # ★★ (b) 动态窗口: 存**任务节点**, 供 `resolve_windows()` 读配置路径 ★★
        #
        # `_build_windows()` 只拿到**任务级**数据（不含根配置）, 所以动态路径
        # 是**相对任务**的（如 `guild_banquet_time.day_1`）。
        # 踩过: 原来没有这个字段, `resolve_windows()` 拿到 `None` ->
        #       路径永远解析失败 -> 动态 days **静默失效**。
        self.node = data

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
        #
        # ★★ C: 现在是**一串**（可能多段, 如 Hunt 的早/晚两段）★★
        #   `in_window()` 逐段取或; `self.window` 保留为**第一段**（兼容旧调用方）。
        self.windows = self._build_windows(data.get('scheduler') or {})
        self.window = self.windows[0] if self.windows else None

        # ★★ C(选项 2 · 显式): **条目身份** ★★
        #
        # 队列里同一任务可以出现**多次**（用户用重复条目表达"重复跑整个任务"）。
        # 要按**条目**追踪"这条跑过没有", `Function` 必须带上它是**哪一条**。
        #
        # 由 `_order_by_queue()` 在排完序后逐条写入（见那里的说明）;
        # 不在队列里的任务保持 `None`。
        self.entry_id = None

        # self.enable = deep_get(data, keys="Scheduler.Enable", default=False)
        # self.command = deep_get(data, keys="Scheduler.Command", default="Unknown")
        # self.next_run = deep_get(data, keys="Scheduler.NextRun", default=DEFAULT_TIME)

    def _build_windows(self, sch: dict) -> tuple:
        """
        构造开放时段（**可能是多段**）。**优先读任务 `meta.py` 的
        `TaskSpec.window`**。

        ## ★★ 为什么必须优先读 `meta.py`（此前的严重缺陷）★★

        原实现**只**从 `scheduler.window_enable` / `window_start` / `window_end` /
        `window_days` 构建。但那些字段是**内部字段**（4-E 已从界面移除）,
        **全 54 个任务都是 `False`** —— 于是:

            TaskSpec.window (meta.py)    : DemonEncounter = 每天 17:00-23:00
            Function.window (调度器用的)  : **不限时段**      <- 真正生效的是这个
            DemonEncounter.in_window()   : True（07:36 本该 False）

        即 **`meta.py` 里写的时段是死代码**, 调度器完全看不到它
        （`pending = 27` / `waiting = 0`, 没有任何任务因窗口被拦）。

        ## 现在的优先级

        1. **`TaskSpec.window`（游戏机制, 权威）** —— 用户明确: 所有定时任务都有 window
        2. 退回 `scheduler.window_*`（用户/旧配置覆盖, 兼容用）
        3. 都没有 -> `AvailabilityWindow()`（**`enabled=False`**）

        ⚠ 依赖 `self.command`, 而它在 `__init__` 里是先于本方法设置的
          （`self.command = ConfigModel.type(key)` 在 L54, 本方法在 L73 调用）。
        """
        from module.config.availability import ALL_DAYS, AvailabilityWindow

        # ---------- 1. 优先: 任务元数据里的 window（游戏机制）----------
        spec = None
        try:
            from module.config import task_catalog as TC
            spec = TC.get_spec(self.command)
        except Exception as exc:      # 防御: catalog 坏掉不该让调度崩
            logger.warning(f'{self.command}: 读 task_catalog 失败'
                           f'({type(exc).__name__}: {exc}), 退回配置项')
        if spec is not None and not sch.get('window_enable'):
            # ★★ #1: **用户配置优先** ★★
            #
            # 只有用户**没启用**窗口时才用 `meta.py` 的**游戏机制窗口**兜底。
            # 用户启用了 -> 走下面的配置分支（那是他的**偏好**, 更权威）。
            #
            # 用户原话: "用户可以选择每天, 然后把时间改为 17-23 点"
            # 此前是反的（meta 永远压过用户）-> 实测用户把窗口改成
            # 17:00-23:00 **完全没用**（meta 的整天窗口生效）。
            ws = list(getattr(spec, 'windows_effective', []) or [])
            real = [w for w in ws if getattr(w, 'enabled', False)]
            if real:
                # ★★ #7: **精确返回所有段**, 不再做有损并集 ★★
                #
                # 此前多段被压成"最早开始~最晚结束 + 天的并集",
                # 于是 `Hunt`（周一~周四 06:00-23:00 与 周五~周日 17:00-23:00）
                # 变成"每天 06:00-23:00" —— **周五 10:00 被误判成在窗口内**。
                #
                # 现在保留每一段, 由 `in_window()` **逐段取或**判定。
                return tuple(real)

        # ---------- 2. 退回: 配置项（用户覆盖 / 旧配置）----------
        #
        # ★★ #1: 读用户配置的**周期 / 周几 / 几号**（用户裁定的结构）★★
        #
        # 用户原话:
        #   "窗口开始: 下拉选择：每天、每周、每月 /
        #    下拉选择：时:分、周几：时：分、几号：时：分"
        #   "窗口语义：(B) 两端必须同周期"
        #
        # 三者关系（按 `window_period`）:
        #   * `daily`   -> 每天, 用 `window_start` / `window_end`
        #   * `weekly`  -> 用 `window_days`（周几）, 时刻同上
        #   * `monthly` -> 用 `window_dom`（几号）, 时刻同上
        if not sch.get('window_enable'):
            return (AvailabilityWindow(),)

        # ★★ ⑥(b): **每日固定时刻**（`window_slots`）★★
        #
        # 例: `'12:00,20:00'` -> 每天 12:00 与 20:00 各开一个窗口段
        #     （每段默认 2 小时, 由 `_SLOT_SPAN_MINUTES` 控制）。
        #
        # ★ 与 `window_start` / `window_end` **互斥** —— 填了 slots 就用它。
        #   这样"一天跑两次"由**窗口开放次数**表达, 不引入新的"次数"概念
        #   （用户裁定: 窗口只回答"这个时间可不可以跑"）。
        slots_raw = str(sch.get('window_slots') or '')
        slots = []
        bad_slots = []
        for part in slots_raw.split(','):
            part = part.strip()
            if not part:
                continue
            try:
                hh, mm = part.split(':')
                hh, mm = int(hh), int(mm)
                if not (0 <= hh <= 23 and 0 <= mm <= 59):
                    raise ValueError(part)
                slots.append(time(hour=hh, minute=mm))
            except Exception:
                bad_slots.append(part)
        if bad_slots:
            logger.warning(f'{self.command}: window_slots 无效项已忽略 '
                           f'{bad_slots}（应为 `时:分`, 逗号分隔）')
        if slots:
            segs = []
            for st in sorted(set(slots)):
                end_min = st.hour * 60 + st.minute + _SLOT_SPAN_MINUTES
                end_min = min(end_min, 23 * 60 + 59)
                segs.append(AvailabilityWindow(
                    enabled=True, start=st,
                    end=time(hour=end_min // 60, minute=end_min % 60),
                    days=ALL_DAYS))
            return tuple(segs)

        wperiod = sch.get('window_period')
        wperiod = getattr(wperiod, 'value', wperiod) or 'daily'
        wperiod = str(wperiod).lower()

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

        dom, bad_dom = [], []
        for part in str(sch.get('window_dom') or '').split(','):
            part = part.strip()
            if part == '':
                continue
            if part.isdigit() and 1 <= int(part) <= 31:
                dom.append(int(part))
            else:
                bad_dom.append(part)
        if bad_dom:
            logger.warning(f'{self.command}: window_dom 无效项已忽略 {bad_dom}'
                           f'（应为 1-31）')

        try:
            return (AvailabilityWindow(
                enabled=True,
                start=sch['window_start'],
                end=sch['window_end'],
                # `weekly` 才用 days; 其它周期保持全周
                days=(tuple(sorted(set(days))) or ALL_DAYS)
                if wperiod == 'weekly' else ALL_DAYS,
                # `monthly` 才用 days_of_month; 其它周期保持不限
                days_of_month=(tuple(sorted(set(dom)))
                               if wperiod == 'monthly' else ()),
            ),)
        except Exception as exc:
            logger.warning(f'{self.command}: 开放时段配置非法'
                           f'({type(exc).__name__}: {exc}), 按不限时段处理')
            return (AvailabilityWindow(),)

    def resolve_windows(self):
        """把**动态** `days`（`days_from_config`）在**运行时**解析成实际星期。

        ★ 用户裁定 (b):
          "AvailabilityWindow 支持动态 days（运行时从配置读）, 让窗口能引用配置字段"
          "窗口是唯一排期依据, 这个 B 并不冲突"

        例: `GuildBanquet` 的宴会日是**用户在任务配置里选的**:
            guild_banquet.guild_banquet_time.day_1 = 星期三
            guild_banquet.guild_banquet_time.day_2 = 星期六

        本方法读成 0-6 的整数, 与静态 `days` **取并集**, 返回新的元组。
        没有动态项时**原样返回**（零开销）。解析失败 -> WARNING + 跳过该项。
        """
        # ★ 必须**函数内导入**: `_build_windows()` 的导入是局部名字,
        #   这里看不到（踩过 -> `NameError` 被下面的 except 吞成 WARNING,
        #   表现为"动态 days 不生效", 极难查）。
        from module.config.availability import AvailabilityWindow
        from datetime import time as _time

        ws = tuple(self.windows or ())
        if not any(getattr(w, 'days_from_config', ()) or
                   getattr(w, 'times_from_config', ()) for w in ws):
            return ws                      # 零开销快路径
        out = []
        for w in ws:
            days_paths = tuple(getattr(w, 'days_from_config', ()) or ())
            time_paths = tuple(getattr(w, 'times_from_config', ()) or ())
            if not days_paths and not time_paths:
                out.append(w)
                continue

            def _read(path, parser, what):
                """读一个配置路径并解析; 失败记 WARNING 并跳过（**不猜**）。

                ★ `self.node` 是 `model.dict()` 里的**普通 dict**, 不是对象 ——
                  所以要先试 `getattr`, 失败再试 `[]`（踩过: 只用 getattr ->
                  永远 `AttributeError` -> 动态窗口**静默失效**）。
                """
                try:
                    node = self.node
                    for part in str(path).split('.'):
                        if isinstance(node, dict):
                            node = node[part]
                        else:
                            node = getattr(node, part)
                    return parser(node)
                except Exception as exc:
                    logger.warning(
                        f'{self.command}: 动态窗口{what} {path!r} 解析失败'
                        f'（{type(exc).__name__}: {exc}）, 已跳过')
                    return None

            extra = {d for d in (_read(p, parse_weekday, '星期')
                                 for p in days_paths) if d is not None}
            start, end = w.start, w.end
            if time_paths:
                got = _read(time_paths[0], parse_time, '时刻')
                if got is not None:
                    start = got
                    # 只给起点 -> 终点 = 起点 + `_SLOT_SPAN_MINUTES`
                    if len(time_paths) < 2:
                        mins = got.hour * 60 + got.minute + _SLOT_SPAN_MINUTES
                        mins = min(mins, 23 * 60 + 59)
                        end = _time(hour=mins // 60, minute=mins % 60)
                if len(time_paths) >= 2:
                    got2 = _read(time_paths[1], parse_time, '结束时刻')
                    if got2 is not None:
                        end = got2
            try:
                # ★ 静态 `days` 为空 = "没有静态约束" -> 只用动态值
                #   （若并上 `ALL_DAYS` 会把动态 days 抹掉 —— 踩过）
                if not w.days and extra:
                    merged = tuple(sorted(extra))
                else:
                    merged = tuple(sorted(set(w.days) | extra))
                out.append(AvailabilityWindow(
                    enabled=w.enabled, start=start, end=end,
                    days=merged,
                    days_of_month=w.days_of_month))
            except Exception as exc:
                logger.warning(f'{self.command}: 合并动态窗口失败'
                               f'（{type(exc).__name__}: {exc}）, 用原窗口')
                out.append(w)
        return tuple(out)

    def in_window(self, now: datetime = None) -> bool:
        """当前是否落在开放时段内。

        ★★ #7: **多段逐段取或** —— 任一段命中即算在窗口内 ★★

        此前只有**一段**（多段被压成有损并集）, 于是 `Hunt` 的
        "周五~周日 17:00-23:00" 被并成"每天 06:00-23:00",
        **周五 10:00 被误判成可以跑**。

        没有启用中的时段 -> 恒为 True（不限时段）。
        """
        when = now or datetime.now()
        # ★ (b): 先解析**动态 days**（来自任务配置的星期）
        ws = [w for w in self.resolve_windows()
              if getattr(w, 'enabled', False)]
        if not ws:
            return True
        return any(w.contains(when) for w in ws)

    @property
    def window_reason(self) -> str or None:
        """若因开放时段不可跑, 返回可读原因; 否则 None。"""
        ws = [w for w in (self.resolve_windows() or ()) if getattr(w, 'enabled', False)]
        if not ws:
            return None
        now = datetime.now()
        if any(w.contains(now) for w in ws):
            return None
        # 下次开放取**最早**的那一段
        openings = []
        for w in ws:
            try:
                openings.append(w.next_opening(now))
            except Exception:
                continue
        opening = min(openings) if openings else None
        desc = ' 与 '.join(w.describe() for w in ws)
        if opening is None:
            return f'不在开放时段（{desc}）'
        return f'不在开放时段（{desc}，{opening:%m-%d %H:%M} 开放）'

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
        # ★★ 一次性窗口迁移（用户要求: "帮我配好窗口" + "适配好现有的软件"）★★
        #
        # 放在 `__init__` 末尾: 每次加载配置都会跑, 但
        # `migrate_windows_once()` **自身幂等**（`window_slots` 非空就跳过）
        # —— 不会覆盖用户后续在界面上的修改。
        self.migrate_windows_once()
        # ★★ S1: 清理**僵尸配置节点**（用户要求）★★
        #
        # `tasks/<Name>/` 有 `config.py` 但**缺 `meta.py`** -> 没类别、没窗口、
        # 也跑不了（`script_task.py` 同样缺）。它在配置里会显示成一个永远
        # 跑不动的任务。实测: 4 个配置里各有一个 `orochi_moans`。
        self.clean_zombie_nodes()

    def clean_zombie_nodes(self) -> bool:
        """把**僵尸任务**的配置节点从这份配置里**删掉**（用户要求）。

        ★ 判定标准见 `task_catalog.zombie_task_keys()`（**不猜**:
          只认"有目录但缺 `meta.py`"的, 资源库目录不算）。
        ★ 幂等: 没有僵尸键时不做任何事、不写盘。
        """
        try:
            from module.config import task_catalog as TC
            zombies = TC.zombie_task_keys()
            if not zombies:
                return False
            from module.config.config_model import convert_to_underscore
            keys = {convert_to_underscore(z) for z in zombies}
            raw = self.model.model_dump()
            hit = sorted(k for k in raw if k in keys)
            if not hit:
                return False
            for k in hit:
                # 从模型里摘掉该字段（`ConfigModel` 是 pydantic 模型）
                try:
                    delattr(self.model, k)
                except Exception:
                    pass
            self.save()
            logger.info(f'{self.config_name}: 已清理僵尸配置节点 {hit}')
            return True
        except Exception as exc:
            logger.warning(f'{self.config_name}: 清理僵尸节点失败'
                           f'（{type(exc).__name__}: {exc}）, 跳过')
            return False

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

    # ------------------------------------------------------------------ 一次性迁移
    def migrate_windows_once(self) -> bool:
        """把**推荐窗口**写进这份配置（**只做一次**, 用户要求）。

        用户原话: "你直接帮我配好窗口就好, **改用户配置**。
                  顺带帮我把**现有的配置适配好现有的软件**。"

        推荐值（用户裁定）:
            restart      `window_slots = '12:00,20:00'` -> 12:00-14:00 + 20:00-22:00
            ryou_toppa   `window_slots = '07:00'`       -> 07:00-09:00
            guild_banquet **不设**（用 `days_from_config` 引用宴会日）

        ★ 幂等: **不能**用自定义键做标记 —— pydantic v2 的 `extra='ignore'`
          会把它从 `model_dump()` 丢掉 -> 每次启动都覆盖（踩过）。
          改用**语义本身**: `window_slots` 非空 = 已配过。

        ★ 写回必须**按字段类型转换** —— `model_dump()` 里 `Time` 是**字符串**,
          直接 `deep_set` 会 (a) 类型错 (b) 保存时 `.strftime` 崩（踩过）。
        """
        try:
            from datetime import time as _time
            from tasks.Component.config_scheduler import (
                apply_recommended_windows)

            raw = self.model.model_dump()
            changed = apply_recommended_windows(raw)
            if not changed:
                return False

            def _to_time(v, default):
                if isinstance(v, _time):
                    return v
                try:
                    return _time.fromisoformat(str(v))
                except Exception:
                    return default

            for key in changed:
                sch = raw[key]['scheduler']
                self.model.deep_set(
                    self.model, keys=f'{key}.scheduler.window_enable',
                    value=bool(sch['window_enable']))
                self.model.deep_set(
                    self.model, keys=f'{key}.scheduler.window_slots',
                    value=str(sch['window_slots']))
                self.model.deep_set(
                    self.model, keys=f'{key}.scheduler.window_period',
                    value=str(sch['window_period']))
                self.model.deep_set(
                    self.model, keys=f'{key}.scheduler.window_start',
                    value=_to_time(sch.get('window_start'), _time(12, 0)))
                self.model.deep_set(
                    self.model, keys=f'{key}.scheduler.window_end',
                    value=_to_time(sch.get('window_end'), _time(22, 0)))
            # ★ 真正落盘（否则只在内存里, 下次启动又"没配"）
            self.save()
            logger.info(f'{self.config_name}: 已配好推荐窗口 -> {changed}（已保存）')
            return True
        except Exception as exc:
            logger.warning(f'{self.config_name}: 窗口迁移失败'
                           f'（{type(exc).__name__}: {exc}）, 跳过')
            return False

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
            # ★ 连续失败冷却（见 `module/config/failure_state.py`）:
            #   在冷却中的任务**不入 pending**, 并把 next_run 推到冷却结束。
            #
            #   这是"到阈值不退出进程"之后的**兜底**: 即使
            #   `task_delay()` 那一步失败了（比如配置保存异常）,
            #   也不会被调度器反复选中 -> 不会变成热循环。
            if self._in_failure_cooldown(func.command):
                waiting_task.append(func)
                continue
            if not isinstance(func.next_run, datetime):
                error.append(func)
            elif func.next_run < self.scheduler_update_dt:
                # ★★ C: "完成记忆"门槛**已移到 `_order_by_queue` 之后** ★★
                #
                # 原来在这里判 `_skip_by_period(...)` —— 但那时
                # `func.entry_id` 还是 `None`（条目身份由 `_order_by_queue`
                # 在后文逐条写入）-> 门槛退化成"按任务名" ->
                # **重复条目会被合并**（第二条也被跳过, 只跑 1 次）。
                #
                # 现在改为在排完序之后**逐条**按 `entry_id` 复查
                # （见下面 "完成记忆（按条目）" 那一段）。
                #
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
            _rule = _opt.schedule_rule
            pending_task = TaskScheduler.schedule(
                rule=_rule,
                pending=pending_task,
                # ★ 用 `build_queue()`（用户编排 + **自动补齐**）而不是
                #   `build_run_list()`（只有用户编排）—— 否则
                #   `auto_queue=True` 的定时任务启用后**不会**自动获得顺序,
                #   用户还得手动拖一次才生效, 与设计不符。
                run_list=self.build_queue())
            # ★★ F3: **`LIST` 规则下, 队列顺序就是最终次序, 且队列外的不跑** ★★
            #
            # 用户明确的设计:
            #
            #   "待执行里为什么不能和执行顺序一样拖动呢, 他俩应该并在一起啊"
            #   "定时任务的拖动代表执行顺序发生了变化。完成上一个任务就会接着
            #    完成下一个。正在运行 a, 执行顺序 bcd, 待执行 efg, 我把 g 拖到
            #    bgcd, 这样运行完 B 就会运行 g。"
            #
            # ## 此前为什么不按队列顺序跑
            #
            # `TaskScheduler.schedule(LIST, ...)` **确实**按队列位置排好了,
            # 但紧接着 `_order_by_timed_priority()` 又用 `timed_sort_key`
            # （到点程度 / 窗口快关 / 耗时短）**把整个列表重排** ——
            # 用户拖的顺序**被完全覆盖**。
            #
            # 实测（2026-10-10）: 队列第 9 位的 `ExperienceYoukai`
            # 被排到 pending **第 1 位**; 队列第 1 位的 `Delegation` 掉到第 4。
            #
            # ★★ 还发现**队列外的任务也会跑** ★★
            #   `pending = 25` 而 `queue = 18`, 多出的 9 个
            #   （`EternitySea`/`Exploration`/`Orochi`/`FallenSun`/…）
            #   都是 `auto_queue=False` 的次数任务 —— **不在队列里却在跑**。
            #   这与"队列是唯一调度依据"直接矛盾, 本方法一并修掉。
            #
            # ★ 踩过: 一开始写成 `str(_rule).lower() not in ('schedule_rule.list', 'list')`
            #   —— `str(ScheduleRule.LIST)` 是 **`'ScheduleRule.LIST'`**（不是 `'List'`）,
            #   于是判断**永远为 False**, 改动**静默失效**（派发顺序一点没变）。
            #   改用 `_is_list_rule()` 统一处理（`enum` 用 `.value`, `str` 直接比）。
            #
            # ## 现在
            #
            # * **`LIST` 规则** -> 队列顺序**就是**执行顺序; **队列外的不参与**
            # * 其它规则（`FILTER`/`FIFO`/`PRIORITY`）-> 保留 `timed_sort_key`
            #   行为（那些规则本来就是"按机制排", 不是"按用户顺序排"）
            #
            # ★ 用户原话（A 选项）: "间隔完全废弃" —— 曾经的
            #   `timed_priority='timed'`（定时任务插到最前）是"谁到点先跑"
            #   的残留; 在"队列顺序为唯一依据"的模型下它**会让用户拖的顺序失效**。
            if self._is_list_rule(_rule):
                pending_task = self._order_by_queue(pending_task)
                # ★★ C: **完成记忆（按条目）** ★★
                #
                # `_order_by_queue()` 刚给每个 `Function` 写好了 `entry_id`
                # （重复条目是**不同的对象、不同的 id**）。这里逐条判断
                # "这一条本周期做过没有":
                #
                # * 做过 -> 移出 pending（同任务**下一条**不受影响）
                # * 旧数据 / 无 entry_id -> 退回按任务名判断（向后兼容）
                kept = []
                for f in pending_task:
                    tk = convert_to_underscore(getattr(f, 'command', '') or '')
                    tv = self.model.dict().get(tk) or {}
                    if self._skip_by_period(
                            tk, tv,
                            entry_id=getattr(f, 'entry_id', None)):
                        waiting_task.append(f)
                        continue
                    kept.append(f)
                pending_task = kept
            else:
                # ★★ F3 修: **先按队列过滤, 再按规则排序** ★★
                #
                # 实测（2026-10-10）: `schedule_rule=Filter` 时
                # `_order_by_timed_priority()` **只排序、不剔除** ->
                # 队列外的任务（未加入队列的 `auto_queue=False` 任务）照样进
                # pending 被执行。实测泄漏 8 个:
                # `Orochi` / `FallenSun` / `EternitySea` / `Exploration` /
                # `BondlingFairyland` / `GoryouRealm` / `Hyakkiyakou` / `Sougenbi`
                # —— 全是 `enable=True` 但**用户没加进队列**的次数任务。
                #
                # 这与"**队列是唯一调度依据**"直接冲突（用户原话）。
                # 所以这里**先**用 `_order_by_queue()` 剔除非队列任务（它同时
                # 写入 `entry_id`）。
                #
                # ★★ 关于 `Filter` 模式还要不要 `_order_by_timed_priority()` ★★
                #
                # 用户的设计是"**队列顺序 = 执行顺序**"（F3, 见
                # `tests/module/config/test_queue_is_authority.py` 的**不变量**:
                # `pending == 队列剔除 waiting 后的保序子序列`）。
                #
                # 而 `_order_by_timed_priority()` 会**重排**（按
                # `timed_sort_key`: 到点程度 / 窗口快关 / 耗时 / 优先级）——
                # 那会让"保序子序列"不成立, 即**用户拖的顺序失效**。
                # 所以这里**不再**调用它。
                #
                # ★ 需要"定时优先/固定优先"的**类别**偏序时, 由 `window`
                #   与**类别分段**表达（见 S6 的设计）——
                #   不在排序函数里偷偷重排。
                pending_task = self._order_by_queue(pending_task)
            # ★ 「运行一次」: 手动请求的任务提到**最前**（按点击顺序）
            #
            # 这一条**保留**: 它是用户的**显式即时指令**（"现在就给我跑一次"）,
            # 不是"按机制自动插队", 与队列顺序不冲突。
            pending_task = self._order_by_manual_run(pending_task)
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
    def _order_by_manual_run(self, pending):
        """
        「运行一次」: 把手动请求的任务提到**最前**（按点击顺序）。

        ★ 用**队列**而不是布尔标记: 用户要求"按点击先后顺序",
          而 `set` 会丢顺序。

        ★ 这里**只排序、不消耗队列** —— 队列在任务真正被派发时才
          `take()`（见 `script.py`）。否则 `get_next()` 每被调一次就
          消耗一个, 用户点了 3 个却只跑 1 个。
        """
        try:
            from module.config import manual_run

            queue = manual_run.pending(self.config_name)
            if not queue:
                return pending
            ordered = manual_run.order_first(pending, queue)
            head = getattr(ordered[0], 'command', '') if ordered else ''
            if head and manual_run.is_pending(self.config_name, head):
                logger.info(f'运行一次: 优先派发 {head}'
                            f'（队列剩余 {len(queue)} 个）')
            return ordered
        except Exception as exc:
            logger.warning(f'运行一次排序失败({type(exc).__name__}: {exc}), '
                           f'保持原顺序')
            return pending

    @staticmethod
    def _is_list_rule(rule) -> bool:
        """判断是否"列表优先"（`ScheduleRule.LIST`）。

        ★ 为什么需要它: `ScheduleRule` 是 `str` 枚举,
          但 **`str(ScheduleRule.LIST)` 得到的是 `'ScheduleRule.LIST'`**,
          **不是** `'List'` —— 直接拿 `str()` 去比会**永远不匹配**,
          改动**静默失效**（实测踩过: 派发顺序一点没变, 也不报错）。

          所以: 枚举取 `.value`, 字符串直接比, 都转小写。
        """
        val = getattr(rule, 'value', rule)
        return str(val).strip().lower() == 'list'

    def _order_by_queue(self, pending):
        """把 `pending` 按**执行队列顺序**排好, 并**剔除队列外的任务**。

        ★★ C(选项 2 · 显式): 同时把**条目身份**写回 `Function.entry_id` ★★

        队列里同一任务可以出现多次（用户用重复条目表达"重复跑整个任务"）。
        这里按队列**条目**逐条分配:

        * 第 1 条 -> `Function.entry_id = <第 1 条的 id>`
        * 同一任务的第 2 条 -> **一个副本** `Function`（`copy.deepcopy`）,
          `entry_id` = 第 2 条的 id

        为什么要副本: `pending` 里同一任务的多个 `Function` 必须**各自独立**
        （否则一个是同一个对象, `entry_id` 会被覆盖, 而且
        `_skip_by_period` 按条目判断时两条会互相影响）。

        ## 依据

        ＊ 顺序: `Config.build_queue()`（用户拖的 `run_list` + 自动补齐）
        ＊ 成员: 同理 —— **不在队列里就不该跑**

        ## 为什么必须"剔除"

        实测（2026-10-10）: `pending=25` 而 `queue=18`, 多出的 9 个
        （`EternitySea`/`Exploration`/`Orochi`/`FallenSun`/`GoryouRealm`/
        `Hyakkiyakou`/`RealmRaid`/`RyouToppa`/`Sougenbi`）
        都是 `auto_queue=False` 的**次数任务** —— 用户**没有**把它们加进队列,
        它们却在跑。这与"队列是唯一调度依据"直接矛盾。

        ## 不在队列里的任务会怎样

        被**排除出 pending**（不会跑）, 但**不会被停用** ——
        它们仍在【添加任务】里, 用户随时可以加进队列。
        见 `docs/SESSION-LEDGER.md` §10（移出队列的分类型语义）。

        ## 稳定排序

        同名的多个条目（理论上不该有）保持原相对顺序;
        队列里查不到的（理论上被剔除了）排最后, 保证不吞任务。
        """
        try:
            import copy as _copy

            queue = self.build_queue()
            # ★★ C(选项 2 · 显式): 按**条目**收集 ★★
            #   任务名 -> 该任务所有条目的 (队列序号, entry_id)
            #   （**不去重** —— 重复条目就是"重复跑整个任务"）
            entries_of = {}
            for idx, entry in enumerate(queue):
                cmd = getattr(entry, 'task', None)
                if not cmd:
                    continue
                entries_of.setdefault(cmd, []).append(
                    (idx, getattr(entry, 'entry_id', None) or ''))
            if not entries_of:
                return pending

            by_cmd = {}
            for f in pending:
                by_cmd.setdefault(getattr(f, 'command', None), []).append(f)

            kept = []
            dropped = []
            for cmd, items in entries_of.items():
                sources = by_cmd.get(cmd) or []
                if not sources:
                    continue
                for n, (idx, eid) in enumerate(items):
                    # 第 1 条用原对象; 第 2 条起用**副本**
                    # （各自独立的 entry_id —— 否则会互相覆盖）
                    f = sources[0] if n == 0 else _copy.deepcopy(sources[0])
                    f.entry_id = eid or None
                    kept.append((idx, f))
            for cmd, sources in by_cmd.items():
                if cmd not in entries_of:
                    dropped.extend(getattr(s, 'command', None) for s in sources)

            if dropped:
                logger.info(
                    f'F3: 这些任务不在执行队列里, 本次不参与调度: {dropped}')
            kept.sort(key=lambda x: x[0])
            return [f for _, f in kept]
        except Exception as exc:
            logger.warning(f'_order_by_queue 失败({type(exc).__name__}: {exc}), '
                           f'保持原顺序')
            return pending
            kept = [f for f in pending
                    if getattr(f, 'command', None) in order]
            dropped = [getattr(f, 'command', None) for f in pending
                       if getattr(f, 'command', None) not in order]
            if dropped:
                logger.info(
                    f'F3: 这些任务不在执行队列里, 本次不参与调度: {dropped}')
            return sorted(
                kept, key=lambda f: order.get(getattr(f, 'command', None), 10 ** 6))
        except Exception as exc:
            logger.warning(f'_order_by_queue 失败({type(exc).__name__}: {exc}), '
                           f'保持原顺序')
            return pending

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

        ## 两条护栏（都是踩过坑之后加的）

        1. **只跳过真正坏的条目**（结构错误 / 未知类型 / 数字非法）,
           不是"跳过不合我心意的条目"。列表**接受任意任务名** ——
           详见 `module/config/run_list.py` 的"踩过的坑"。
        2. 解析后条目数若少于原始条数, **每次都记 ERROR 级日志**（不是 debug）,
           让"静默丢弃"变成"看得见"。

        ★ 为什么第 2 条重要: 曾经一个过滤器把用户 7 个条目全跳过,
          而日志是 WARNING、埋在几千行里, 用户与我都**很久没发现**。

        ## ★ 不做自动补齐（职责分离）

        这里**只**解析用户编排的 `run_list`。自动任务（`auto_queue=True`）的
        补齐在 `build_queue()` 里做 —— 分开的原因是:

        * `build_run_list()` 的结果会被 `save_run_list()` **写回配置**。
          若在这里补齐, 自动任务会被**持久化**进用户的列表, 于是
          "用户没编排过"与"用户确实想要它在列表里"就分不清了。
        * 补齐是**派生结果**, 不该回写。
        """
        from module.config.run_list import RunList

        raw = getattr(self.model.script.optimization, 'run_list', None) or []
        dropped = []

        def _on_bad(item, exc):
            dropped.append((item, exc))
            logger.error(f'运行列表条目无法解析, 已跳过: {item!r} ({exc})')

        rl = RunList.from_list(raw, on_bad=_on_bad)

        # ★★ C: 兜底唯一化 `entry_id`（所有构造路径都会经过这里）★★
        #
        # `RunList.add()` 会唯一化, 但 `from_list` / `from_dict` /
        # `RunList([...])` 这些路径**绕过**它 —— 实测同一秒构造两条同任务
        # 会得到**相同**的 id, 而按条目追踪（选项 2）依赖 id 唯一。
        self._ensure_unique_entry_ids(rl)

        # 护栏: 数量对不上就是有东西被丢了 —— 这不是"正常解析"
        if len(rl) != len(raw):
            logger.error(
                f'运行列表解析后条目数变少: 原始 {len(raw)} -> 解析 {len(rl)}, '
                f'丢弃 {len(dropped)} 条。'
                f'若这不是你预期的, 请检查列表内容是否被写坏。')

        return rl

    # ------------------------------------------------------------------ 执行队列
    def auto_queue_tasks(self) -> list:
        """所有 `auto_queue=True` 的任务命令名（按 catalog 顺序）。

        这些任务**启用后自动进队列**, 不需要用户【添加任务】。
        与 `countable` 的关系见 `module/config/task_catalog.py` 的
        `TaskSpec.auto_queue`。
        """
        try:
            from module.config import task_catalog as TC
            specs = TC._load_specs()
            return [t for t, s in sorted(specs.items())
                    if s.auto_queue_effective]
        except Exception as exc:
            logger.warning(f'auto_queue_tasks 失败({type(exc).__name__}: {exc})')
            return []

    def queued_commands(self) -> set:
        """**队列成员** = 运行列表里的任务 + **已启用**的自动进队列任务。

        定义（用户确认）:
            * `auto_queue=True` 的任务: **启用后**必定在队列里
            * `auto_queue=False`（次数任务）: 只有被用户【添加任务】后才在队列里

        ★ 与 `build_run_list()` 的区别: 后者是"用户编排的清单",
          这里是"实际会跑的清单"。`queued` 判断用这个。

        ## ★★ ② 修: 必须**过滤 `enable`** ★★

        用户反馈: "执行队列-执行顺序页面, 这里出现了很多**未启用**的任务"。

        **实测**: `queued_commands()` 返回 **41** 个, 其中 **23 个未启用**;
        而权威的 `build_queue()` 只有 **19** 条。

        **根因**: `build_queue()` 里有这个过滤 ——
        ```python
        for task in self.auto_queue_tasks():
            if not self._task_enabled(task):
                continue
        ```
        而这里 `out.update(self.auto_queue_tasks())` **漏了**。
        **同一个知识（"队列成员"）在两处定义, 其中一处漏了 `enable`**
        —— 正是台账 §10.8"单一数据源"要防的那类 bug。

        现在改用**同一个过滤**。
        """
        out = set()
        for e in self.build_run_list():
            task = getattr(e, 'task', None)
            if task:
                out.add(task)
        for task in self.auto_queue_tasks():
            # ★ 未启用的**不在队列里**（`build_queue()` 也是这么判的）
            if self._task_enabled(task):
                out.add(task)
        return out

    @staticmethod
    def _ensure_unique_entry_ids(rl) -> None:
        """兜底: 保证 `RunList` 里**每个 task 条目**的 `entry_id` 唯一。

        ## 为什么需要

        `RunList.add()` 会唯一化, 但 **`from_dict` / `from_list` /
        `RunList([...])`** 这些路径**绕过**它 —— 实测:

            RunList([RunEntry(kind='task', task='RealmRaid'),
                     RunEntry(kind='task', task='RealmRaid')])
            -> 两条 entry_id **完全相同**（同一秒构造）

        而按条目追踪（C 选项 2）**依赖 id 唯一**。所以在"读配置"这一处
        统一兜底（重复的**追加序号**, 如 `...-RealmRaid-2`）。

        ★ 已经是唯一的 id **不动**（保持上游/用户给的身份）。
        """
        try:
            from module.config.run_list import EntryKind, new_entry_id
            used = set()
            for e in (getattr(rl, 'entries', None) or []):
                if getattr(e, 'kind', None) != EntryKind.TASK:
                    continue
                eid = getattr(e, 'entry_id', None) or ''
                if not eid:
                    eid = new_entry_id(e.task)
                if eid in used:
                    n = 2
                    while f'{eid}-{n}' in used:
                        n += 1
                    eid = f'{eid}-{n}'
                used.add(eid)
                if eid != getattr(e, 'entry_id', None):
                    object.__setattr__(e, 'entry_id', eid)
        except Exception as exc:
            logger.warning(f'_ensure_unique_entry_ids 失败'
                           f'({type(exc).__name__}: {exc}), 跳过')

    def build_queue(self):
        """**执行队列** = 用户编排 + 自动补齐。

        顺序（用户确认的"疑点1 = a"）:
            1. 用户在 `run_list` 里编排的条目, **保持用户顺序**
            2. 自动进队列、但用户**没编排过**的任务, **追加在后面**

        ★ 为什么追加而不是插入: 用户手动排的必须**优先**;
          自动的垫在后面等他调。

        ★ **不回写配置** —— 这是派生结果。回写会让
          "用户没编排过"与"用户确实想要它在列表里"分不清。
        """
        from module.config.run_list import RunEntry

        rl = self.build_run_list()
        existing = {getattr(e, 'task', None) for e in rl}
        try:
            for task in self.auto_queue_tasks():
                if task in existing:
                    continue
                # 只补**已启用**的任务 —— 未启用的不该出现在队列里
                if not self._task_enabled(task):
                    continue
                rl.add(RunEntry(kind='task', task=task))
                existing.add(task)
        except Exception as exc:
            logger.warning(f'build_queue 自动补齐失败'
                           f'({type(exc).__name__}: {exc}), 只返回用户编排部分')
        return rl

    def _task_enabled(self, task_command: str) -> bool:
        """任务级 `enable` 开关（失败时保守返回 False —— 不启用就不补进队列）。

        ⚠ 名字里带 `_task_` 是为了与既有的 `_category_enabled()`
          （判断**类别**开关, 见 `should_schedule`）区分开 ——
          两者含义不同, 别混。
        """
        try:
            from module.config.config_model import convert_to_underscore
            key = convert_to_underscore(task_command)
            node = getattr(self.model, key, None)
            if node is None:
                return False
            sch = getattr(node, 'scheduler', None)
            return bool(getattr(sch, 'enable', False))
        except Exception:
            return False

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

        | 条目 | 效果 |
        |---|---|
        | `rest` | **休息** —— 去庭院待着 N 分钟（阻塞列表）|
        | `task` | 跑一个固定任务（**不阻塞**，未就绪就跳过）|

        ★ v1 还有一个 `delay`（"只停列表"，定时任务照常）——
          v2 之后**固定与定时分开管理**（各有总开关），
          这个概念不再需要，条目类型已删除。
          `run_control.delay()` 留着只是"手动临时只停列表"的
          后端能力，**界面上不再暴露**（见 `docs/architecture.md` §5.1）。

        实现: `rest` 写 `run_control.rest_until`（与手动暂停同一处）。

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

    def _in_failure_cooldown(self, task_command: str) -> bool:
        """
        该任务是否处于**连续失败冷却**中。

        在冷却中的任务不入 pending —— 这样调度器不会反复选中它,
        也就不会变成热循环。

        ★ 这是"到阈值**不退出进程**"之后的**兜底**: 即使
          `task_delay()` 那一步失败了（配置保存异常等），也不会热循环。

        ★ 任何读取异常都返回 `False`（照常调度）——
          失败记录坏了不该让任务跑不起来。
        """
        try:
            from module.config import failure_state

            until = failure_state.cooldown_until(self.config_name, task_command)
            if until is None:
                return False
            minutes = failure_state.cooldown_remaining_minutes(
                self.config_name, task_command)
            logger.info(f'{task_command}: 处于失败冷却中, 还剩 {minutes} 分钟'
                        f'（到 {until:%Y-%m-%d %H:%M}）')
            return True
        except Exception as exc:
            logger.warning(f'{task_command}: 判断失败冷却时出错'
                           f'({type(exc).__name__}: {exc}), 按未冷却处理')
            return False

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

    def _skip_by_period(self, task_key: str, task_value: dict,
                        entry_id: str = None) -> bool:
        """
        完成记忆: 判断该**条目**是否"本周期已成功完成", 若是则跳过本次调度。

        ★★ C(选项 2): 按 **`entry_id`** 判断, 不再只看任务名 ★★

        队列里同一任务可以出现**多次**（"重复跑整个任务"）:
        * 传了 `entry_id` -> 按**该条目**判断（各条目独立）
        * 没传 -> 退化为按任务名判断（旧行为, 兼容既有调用与旧状态文件）
        

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
            if not is_completed_in_period(self.config_name, task_key,
                                          period_str, reset_at,
                                          entry_id=entry_id):
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

    # ------------------------------------------------------------------ 开放时段
    def task_window(self, task_command: str):
        """该任务的**生效**开放时段（`AvailabilityWindow` 的 list）。

        ## 来源: `meta.py`（游戏机制事实）

        时段写在 `tasks/<Name>/meta.py` 的 `TaskSpec.window`（4-A 搬过来的）。
        这里是**唯一**来源, 没有第二处。

        ## ★ 为什么**没有**在这里合并"用户配置的时刻"

        第一版我写了 `_configured_start_times()`, 拿任务的
        `custom_run_time_friday` / `kirin_time` / `banquet_day_1_start_time`
        等字段去**收窄/移动** meta 的窗口。实测立刻出问题:

            AbyssShadows 的 meta 窗口是 周五六日 19:00-19:15
            配置里 custom_run_time_* = 19:30
            -> 收窄后变成 19:30-19:45
            -> 输入 19:05（**本来在 meta 窗口内**）被推到 19:30 起
            -> 更糟: 连"周五 19:05 已在窗口内"也被改掉了

        **根因**: "`custom_run_time_friday` 到底指什么" —— 是游戏开始时刻、
        还是应用该去跑的时刻、还是"提前多久开始准备"? **我从代码里看不出
        唯一答案**（不同任务用法不同）。拿它去移动窗口就是在**猜**,
        而猜错会**静默改变调度行为**。

        按本项目纪律（§10.10 工程纪律: 不猜、不静默降级）: **不做**这件事,
        先把 meta 的窗口**放宽**到足以容纳用户配置的常见取值
        （见各 `meta.py` 的注释）, 并把"精确合并用户时刻"记为**未完成**,
        等有明确语义依据再做。

        :param task_command: 大驼峰任务名（如 `AbyssShadows`）
        :return: `AvailabilityWindow` 的 list（任务没有 window 时返回 `()`）
        """
        from module.config import task_catalog as TC

        spec = TC.get_spec(task_command)
        if spec is None:
            return ()
        return list(spec.windows_effective)

    def _next_run_from_resource(self, task_key: str, start_time: datetime):
        """用新模型（`Resource` + `RunState` + `next_available()`）算下次运行时刻。

        :return: `datetime`, 或 `None`（任务没声明 `Resource` / 算不出来 -> 调用方回退）

        ## 为什么这是"接线"而不是"重写"

        `module/config/resource.py` 与 `module/config/scheduler_core.py` 早就写好了
        （`Resource` / `Recharge` / `RunState` / `next_available()`，47 个单测),
        但**从没接进调度** —— 本会话实测: 在 `config.py`/`script.py` 里搜
        `next_available\\|Resource\\|RunState` 得到 **0 处**。这里就是把它接上。

        ## 状态从哪来（不新建存储）

        `RunState.refill_anchor` = **本轮的起点**（`start_time`）。
        语义: "池子从这个时刻开始计补充"。这正是"跑完一次后要等多久"的锚点,
        与旧 `next_run = start_time + interval` 同一锚点, 所以**行为可对齐**。

        ★ 为什么不在这里读 `task_state` 的存量: 那是**另一件事**
          （"还剩几次"由 `task_state.py` 负责）。这里只算"下次什么时候能跑",
          保持单一职责; 两者在 `update_scheduler` 里汇合。

        ## 为什么只对 `interval` / `slots` 生效

        * `refill == 'interval'` —— 按间隔补充（逢魔之时 每小时 1 次）
        * `refill == 'slots'`    —— 固定时刻补充（金币妖怪 0/12 点）
        * `refill == 'none'` + `period` —— **周期回满**。这类任务的"下次运行"
          由**完成记忆**（`_skip_by_period`）在周期边界决定, 不是"间隔到了就再跑";
          若在这里返回 `now + 一点点`, 会变成**热循环**。所以交给旧逻辑 + 窗口对齐。
        * `refill == 'window'` —— **活动期**开放。何时开始是**外部信息**
          （探针才知道）, 核心只能返回"稍后再问"; 用它当排期会变成轮询,
          也不合适。同样交给旧逻辑 + 窗口对齐。
        """
        try:
            from module.config import task_catalog as TC
            from module.config.scheduler_core import RunState, next_available

            task_command = ''.join(p.capitalize() for p in task_key.split('_'))
            spec = TC.get_spec(task_command)
            if spec is None:
                return None
            res = getattr(spec, 'resource', None)
            if res is None:
                return None
            if getattr(res, 'refill', 'none') not in ('interval', 'slots'):
                return None

            state = RunState(refill_anchor=start_time)
            planned = next_available(res, state, start_time)

            # `next_available` 在"现在就可行"时返回 `now` —— 那是"立刻再跑",
            # 对"跑完一次后的排期"没有意义（会热循环）。这类情况交给调用方回退。
            if planned <= start_time:
                return None

            logger.info(f'{task_command}: Resource({res.refill}) 算出下次运行 '
                        f'{planned:%m-%d %H:%M:%S}')
            return planned
        except Exception as exc:
            logger.warning(f'{task_key}: Resource 排期失败'
                           f'({type(exc).__name__}: {exc}), 回退到 interval')
            return None

    def next_run_after(self, task_key: str, after: datetime = None,
                       strict: bool = False) -> datetime:
        """**下次允许运行的时刻** —— 由任务的**窗口**决定（不再用 interval 近似）。

        ## 为什么需要它

        有些任务需要知道"我下次大概什么时候跑", 用来判断**是否跨了周期边界**:

        * `DailyTrifles` —— 跨月就重置"神秘图案"开关
        * `TrueOrochi`  —— 跨周就重置本周成功次数

        它们此前用 `now + scheduler.success_interval` **近似**这个时刻。
        用户要求"**间隔完全废弃**"（A 选项），所以改成**从窗口精确算**:

            若 `after` 落在窗口内 -> 取该窗口的**结束**时刻
              （`strict=True` 的 `next_opening` 就是"下一次开放",
                对当前窗口而言即"本窗口结束后重新开放的时刻"）
            若不在窗口内 -> 取 `next_opening`（下次开放）

        ## 为什么不直接用任务的 `next_run`

        `next_run` 是**落盘的状态**, 在任务**刚跑完、还没 `set_next_run`**
        的那一刻可能是**旧值**（甚至在过去）。而本方法的语义是
        "从 `after` 开始, 下次什么时候能跑" —— 是**纯函数**视角,
        不依赖任何落盘状态。

        :param task_key: 任务键（下划线或大驼峰都行, `TC.get` 会归一化）
        :param after: 起算时刻; 默认"现在"
        :param strict: `True` -> **总是**返回"下一次窗口开放"
                       （排期用; 语义 = "这轮跑完了, 下次什么时候能再跑"）
                       `False`（默认）-> 若 `after` 已在窗口内, 返回**本窗口结束**
                       （周期边界判断用; 语义 = "我这轮做完大概到几点"）
        """
        from datetime import timedelta

        from module.config import task_catalog as TC

        when = (after or datetime.now()).replace(microsecond=0)
        spec = TC.get_spec(task_key)
        if spec is None:
            return when

        spans = []      # (下次开放, 本窗口结束)
        for w in spec.windows_effective:
            if not getattr(w, 'enabled', False):
                continue
            try:
                nxt = w.next_opening(when, strict=True)
            except Exception:
                continue
            if strict:
                spans.append((nxt, None))
                continue
            # 非 strict: 在窗口内 -> 本窗口结束（≈ 下次开放 - 1 分钟,
            # 因为 `contains` 是 [start, end) 半开区间）
            close = nxt - timedelta(minutes=1) if w.contains(when) else nxt
            spans.append((nxt, close))
        if not spans:
            return when
        if strict:
            return min(s[0] for s in spans)
        # 优先"本窗口结束"（更贴近"这轮什么时候结束"）; 没在窗口内就用下次开放
        closes = [s[1] for s in spans if s[1] is not None]
        if closes:
            return min(closes)
        return min(s[0] for s in spans)

    def _align_to_window(self, task_key: str, when: datetime) -> datetime:
        """把 `when` 对齐到任务的开放时段内（不在窗口内则推到下一次开放）。

        * 任务没有窗口 -> 原样返回（行为不变）
        * `when` 已在窗口内 -> 原样返回
        * 否则 -> `next_opening(when)`

        ★ 这是**唯一**推进 `next_run` 时考虑窗口的地方 —— 避免"窗口只在
          `update_scheduler` 里当闸门、却不影响下次排期"的不一致。
        """
        try:
            task_command = ''.join(p.capitalize() for p in task_key.split('_'))
            from module.config import task_catalog as TC
            spec = TC.get_spec(task_command)
            if spec is None or spec.window is None:
                return when

            windows = self.task_window(task_command)
            active = [w for w in windows if w.enabled]
            if not active:
                return when

            if any(w.contains(when) for w in active):
                return when

            opening = min(w.next_opening(when) for w in active)
            if opening != when:
                logger.info(
                    f'{task_command}: 下次运行 {when:%m-%d %H:%M} 不在开放时段'
                    f'（{spec.window_describe}）, 已对齐到 {opening:%m-%d %H:%M}')
            return opening
        except Exception as exc:
            logger.warning(f'{task_key}: 窗口对齐失败'
                           f'({type(exc).__name__}: {exc}), 保持原 next_run')
            return when

    def _record_task_success(self, task_key: str, scheduler,
                             entry_id: str = None) -> None:
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
            record_success(self.config_name, task_key, period_str, reset_at,
                           entry_id=entry_id)
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
            # ★★ 4-D: **优先**用新模型 `Resource` + `next_available()` ★★
            #
            # 旧做法: `next_run = start_time + success_interval`
            #   —— 把"游戏机制的补充规则"（充能/固定时刻/周期）**压扁**成一个
            #      用户配置的间隔。见 `docs/architecture.md` §3 的说明。
            #
            # 新做法: 从任务的 `meta.py` 取 `Resource`, 用它算出"下次可运行的
            #   最早时刻"。`Resource` 能表达旧字段表达不了的东西:
            #     * `slots`  —— 每天 0/12 点各补 1 次（旧字段要 4 个才勉强表达）
            #     * `window` —— 只在活动期（顺带被 `next_available` 处理）
            #     * `capacity/consume` —— 池子还剩几次
            #
            # ★ 失败仍用 `failure_interval`（**退避重试**是独立概念, 与
            #   资源补充无关 —— 台账 7.6「次数与冷却解耦」说的就是这个）。
            if success:
                planned = self._next_run_from_resource(task, start_time)
            else:
                planned = None

            if planned is not None:
                run.append(planned)
            elif success:
                # ★★ 用户裁定（2026-10-10）: **排期用窗口算** ★★
                #
                #   "排期应该是用具体的 **window** 来算, **period 只是 window 的
                #    一个粗粒度**, 下边还有具体的时间区间如几点到几点呢。
                #    应该用**整体的任务开放窗口 window** 来计算"
                #
                # 所以这里**不再退回 `success_interval`**（那是"用户轮询节奏",
                # 不是游戏机制）—— 改为取**下次窗口开放**。
                #
                # 实测影响（§17.2）: 27 个启用任务里原本 **22 个**走 interval 回退,
                # 现在全部由窗口决定。
                run.append(self.next_run_after(task, after=start_time,
                                               strict=True))
            else:
                # 失败仍用 `retry_interval`（**退避重试**是独立概念, 台账 7.6;
                # 与"什么时候允许跑"(窗口) 无关）。
                interval = scheduler.retry_interval
                if isinstance(interval, str):
                    interval = timedelta(interval)
                run.append(start_time + interval)

            # 完成记忆: 仅在成功时记录"本周期已完成"
            if success:
                # ★ C: 记在**当前运行的条目**上（不是任务名上）——
                #   这样同一任务的重复条目各记各的
                self._record_task_success(
                    task_key=task, scheduler=scheduler,
                    entry_id=getattr(self.task, 'entry_id', None))
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

        # ★★ 4-C / F3: `next_run` **必须落在任务的开放时段内**（用户要求）★★
        #
        # ## 修的是什么
        #
        # 此前 `next_run = 开始时间 + success_interval`, **完全没看窗口**。
        # 窗口只在 `update_scheduler()` 里当"闸门"用（不在时段内就入 waiting）,
        # 但**不改 `next_run`**。于是会出这种事（以狭间暗域为例, 窗口只有
        # 周五六日 19:00-19:15）:
        #
        #     周日 19:05 成功 -> next_run = 周一 19:05（+1 天）
        #     周一 19:05 到点 -> 不在窗口 -> 入 waiting, next_run **不变**
        #     周二、周三、周四 同理
        #     周五 19:05 -> 终于落回窗口
        #
        # 看起来"刚好对上", 但只是因为间隔恰好 1 天。若间隔是 6 小时/3 小时,
        # `next_run` 会**漂移**, 可能长期落在窗外 —— **永远错过那 15 分钟**。
        #
        # ## 修法
        #
        # 算出候选 `next_run` 后, 若它**不在**窗口内, 就**对齐到
        # `next_opening()`**（下一次开放时刻）。`AvailabilityWindow` 早就
        # 实现了这个方法, 只是**从来没人调**。
        #
        # 用户原话: "任务调度解决了，K 就没什么问题了，下次的运行应该要落在 window 中"。
        #
        # ★★ 修一个**顺序 bug**（本轮发现）★★
        #
        # 原来这一段在 `server_update` **之前**, 于是后面那一步会把
        # `next_run` **覆盖掉**, 对齐**白做**:
        #
        #     `server_update` 默认是 `09:00`（`Scheduler` 的默认值）
        #     -> 走 `else` 分支 -> `next_run = parse_tomorrow_server(...)`
        #     -> **直接变成"明天的 09:00"**, 完全无视窗口
        #
        # 所以必须**放在最后**, 让"落在窗口内"成为不可被覆盖的终态。
        next_run = self._align_to_window(task, next_run)

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
