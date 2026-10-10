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
        """构造开放时段（**可能是多段**）。返回 `AvailabilityWindow` 的 tuple。

        ## ★★ S3: 只读 `scheduler.windows`（结构化多窗口）★★

        用户裁定:
          "不是 window slots, 而是**设置多个 window**！slots 不是已经废弃了吗"
          "一天跑两次 = **两个窗口**"

        设计: `docs/scheduler-architecture.md` §1.1 / §3。

        ## 优先级

        1. **用户配置**（`sch['windows']` 里 `enabled` 的那些）—— 用户**偏好**
        2. **`meta.py` 的 `TaskSpec.window`** —— 游戏机制**兜底**
        3. 都没有 -> `AvailabilityWindow()`（**`enabled=False`**）

        ★ 已**删除**的单值字段（不再读）:
          `window_enable` / `window_start` / `window_end` / `window_days` /
          `window_period` / `window_dom` / `window_slots`
          —— 旧值由 `migrate_windows_once()` **一次性**折成一条 `windows`。

        ⚠ 依赖 `self.command`, 而它在 `__init__` 里先于本方法设置。
        """
        from module.config.availability import (
            ALL_DAYS, AvailabilityWindow, parse_time, parse_weekday)

        # ---------- 1. **用户配置的多窗口**（最权威）----------
        raw_windows = sch.get('windows')
        if isinstance(raw_windows, (list, tuple)) and raw_windows:
            segs = []
            for item in raw_windows:
                try:
                    # `item` 可能是 dict（model_dump）或 `TaskWindow`
                    get = (item.get if isinstance(item, dict)
                           else lambda k, d=None, _it=item: getattr(_it, k, d))
                    if not get('enabled', True):
                        continue              # 这一段不生效
                    period = get('period', 'daily')
                    period = str(
                        getattr(period, 'value', period) or 'daily'
                    ).strip().lower()
                    start = parse_time(get('start'))
                    end = parse_time(get('end'))

                    days, bad = [], []
                    for part in str(get('days') or '').split(','):
                        part = part.strip()
                        if not part:
                            continue
                        try:
                            d = parse_weekday(part)
                        except ValueError:
                            bad.append(part)
                            continue
                        if 0 <= d <= 6:
                            days.append(d)
                        else:
                            bad.append(part)
                    if bad:
                        logger.warning(f'{self.command}: 窗口 days 无效项已忽略 '
                                       f'{bad}（应为 0-6, 周一=0）')

                    dom, bad_dom = [], []
                    for part in str(get('days_of_month') or '').split(','):
                        part = part.strip()
                        if not part:
                            continue
                        if part.isdigit() and 1 <= int(part) <= 31:
                            dom.append(int(part))
                        else:
                            bad_dom.append(part)
                    if bad_dom:
                        logger.warning(f'{self.command}: 窗口 days_of_month '
                                       f'无效项已忽略 {bad_dom}（应为 1-31）')

                    segs.append(AvailabilityWindow(
                        enabled=True,
                        start=start,
                        end=end,
                        # `weekly` 才用 days; 其它周期保持全周
                        days=(tuple(sorted(set(days))) or ALL_DAYS)
                        if period == 'weekly' else ALL_DAYS,
                        # `monthly` 才用 days_of_month; 其它周期保持不限
                        days_of_month=(tuple(sorted(set(dom)))
                                       if period == 'monthly' else ()),
                    ))
                except Exception as exc:
                    logger.warning(
                        f'{self.command}: 一条窗口配置非法, 已跳过'
                        f'（{type(exc).__name__}: {exc}）')
            if segs:
                return tuple(segs)

        # ---------- 2. 兜底: `meta.py` 的游戏机制窗口 ----------
        spec = None
        try:
            from module.config import task_catalog as TC
            spec = TC.get_spec(self.command)
        except Exception as exc:      # 防御: catalog 坏掉不该让调度崩
            logger.warning(f'{self.command}: 读 task_catalog 失败'
                           f'({type(exc).__name__}: {exc}), 按不限时段处理')
        if spec is not None:
            ws = list(getattr(spec, 'windows_effective', []) or [])
            real = [w for w in ws if getattr(w, 'enabled', False)]
            if real:
                # ★ 精确返回**所有段**, 不做有损并集
                #   （踩过: `Hunt` 两段被并成"每天 06:00-23:00",
                #    于是周五 10:00 被误判成在窗口内）
                return tuple(real)

        # ---------- 3. 都没有 -> 不限时段 ----------
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


# ★★ T5（审计修复）: `name_to_function()` **已删除** ★★
#
# 它是模块级函数:
#     def name_to_function(name):
#         function = Function({})        # ✗ `Function.__init__` 需要 data 参数
#         function.command = name
#         function.enable = True
#         return function
#
# 两个问题:
#   1. **一调就崩**: `Function({})` 缺 `data` -> `TypeError:
#      Function.__init__() missing 1 required positional argument: 'data'`
#   2. **生产代码 0 调用**（只有定义, 没有任何引用点）
#
# ★ 而且它要构造的那种"只有 command/enable 的空 Function" 现在已经不需要:
#   队列顺序的唯一权威是 `Config.build_queue()` + `_order_by_queue()`,
#   它们都从**真实配置**构造 `Function`。


def _spec_of(task_command: str):
    """按任务名取 `TaskSpec`（容错）。

    ## ★ 为什么需要它（实测踩到的坑）

    `TC.get_spec(name)` 的键**不是** `TC.all_specs()` 返回的每一个名字 ——
    实测 `GotoMain` 在 `all_specs()` 里**有**, 但 `get_spec('GotoMain')`
    **返回 None**（两者对"名字"的归一化口径不同）。

    ★ 所以拿 spec 要**先按精确名、再按归一化名**试两次, 否则会静默拿到
      `None` -> 出厂默认值退化成 `'none'` -> 任务被误判成"临时"。
      （本项目一贯纪律: **让静默失败变成看得见** —— 所以这里保守回退, 但
       调用方 `task_period_default` 会把"取不到"如实返回 `'none'`。）
    """
    try:
        from module.config import task_catalog as TC

        spec = TC.get_spec(task_command)
        if spec is not None:
            return spec
        # 归一化后重试（下划线 <-> 大驼峰）
        from module.config.config_model import convert_to_underscore

        key = convert_to_underscore(task_command)
        for cand in (key, key.replace('_', ''), task_command.lower()):
            for n in TC.all_specs():
                if convert_to_underscore(n).replace('_', '') == \
                        str(cand).replace('_', ''):
                    spec = TC.get_spec(n)
                    if spec is not None:
                        return spec
        return None
    except Exception as exc:
        logger.debug(f'取 TaskSpec 失败({task_command}: '
                     f'{type(exc).__name__}: {exc})')
        return None


def task_period_default(task_command: str) -> str:
    """该任务的**出厂默认周期** —— 读 `tasks/<Name>/meta.py` 的 `TaskSpec.period`。

    ## ★ 它现在的定位（用户裁定）

    > "`meta.py` 降级为**出厂默认值**"

    ★ 也就是说: **它不再是"分类依据"** —— 分类由配置里的
      `scheduler.period` 决定（见 `Config.task_period()`）。
      它只在"配置里还没有这个键"时用来**回填**。

    :return `'none'` / `'daily'` / `'weekly'` / `'monthly'`（取不到时 `'none'`）
    """
    spec = _spec_of(task_command)
    if spec is None:
        return 'none'
    try:
        v = spec.period_effective
        s = str(getattr(v, 'value', v) or '').strip().lower()
        return s if s in ('none', 'daily', 'weekly', 'monthly') else 'none'
    except Exception as exc:
        logger.debug(f'取出厂默认周期失败({task_command}, '
                     f'{type(exc).__name__}: {exc})')
        return 'none'


def _all_task_names() -> list:
    """可遍历的**任务键**清单（供迁移遍历 `scheduler` 节点用）。

    ⚠ **不要用 `TC.all_specs().keys()`**: 实测那里面有 `GotoMain` 之类的
      "有名字但 `get_spec` 取不到 spec" 的项, 而**配置里也没它的节点** ——
      遍历它只会白跑。这里用 `_load_specs()`（真正建好 spec 的那张表）。

    ★ 配置里**存在但这里没有**的任务（如 `Restart` / `GotoMain`）由
      `migrate_task_period_once()` 的"取不到 spec -> 用出厂默认 `none`"兜底,
      不会漏。
    """
    try:
        from module.config import task_catalog as TC

        return list(TC._load_specs().keys())
    except Exception as exc:
        logger.warning(f'取任务键清单失败({type(exc).__name__}: {exc})')
        return []


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
        # ★★★ 一次性回填 `scheduler.period`（用户确认要做）★★★
        #
        # 用户原话:
        # > "首次自动把 `scheduler.period` 按 meta 的出厂值补上
        # >  （避免 52 个任务突然全变临时）" —— **对**
        #
        # ★ 为什么必须: 分类判据已改成读**配置**里的 `scheduler.period`
        #   （这样前端一改就联动）。但老配置里**没有这个键** ->
        #   若不回填, 绝大多数任务会突然变成「临时任务」, 分类被打乱。
        #
        # ★ 幂等: 每个任务只要已有**合法值**就跳过 ——
        #   **包括 `none`**（那是用户选的"不限", 不能被默认值覆盖）。
        self.migrate_task_period_once()
        # ★★★ 修正"全天窗口却被排到未来"的 next_run（用户报的"等待到点"）★★★
        #
        # 用户原话:
        # > "**契灵之境为什么显示等待到点**? 这个是次数任务, 不应该有
        # >  [还未到点]这种[拥有 window 的任务类]的属性啊"
        #
        # ★ 为什么需要它: 坏值**已经落盘**（`next_run` = 明天）,
        #   而 `update_scheduler` 只读不重算 -> 光修排期算法**不够**
        #   （实测: 修了 `next_run_after` 之后界面仍显示"等待到点"）。
        # ★ 幂等: 修正后 `next_run` 不再是未来 -> 第二次无改动。
        self.fix_stale_next_run_once()
        # ★★★ S7: **调度优先级三模式已整簇删除**（用户裁定）★★★
        #
        # 用户原话:
        # > "固定任务优先和定时任务优先以及**不能跨类别拖动太蠢了**。
        # >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
        # >  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有
        # >  意义的不能跨类别拖动以及**单独的调度优先级**。"
        #
        # ★ 所以 `migrate_priority_mode_once()` **连同它的调用一起删掉** ——
        #   连同 `Optimization.priority_mode` / `priority_mode_explicit` 字段。
        #
        # ⚠ 那配置里遗留的 `priority_mode` 键怎么办?
        #   pydantic 模型不再声明它 -> **加载时被忽略**（多余键不报错）,
        #   下次 `save()` 时**自然消失**。★ 不需要专门写迁移。
        #
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
        self.model.write_json(self.config_name, self.model.model_dump())

    # ------------------------------------------------- S6 优先级三模式
    # ★★★ `migrate_priority_mode_once()` **已删除**（用户裁定）★★★
    #
    # 用户原话:
    # > "固定任务优先和定时任务优先以及**不能跨类别拖动太蠢了**。
    # >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
    # >  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有
    # >  意义的不能跨类别拖动以及**单独的调度优先级**。"
    #
    # ★ 它原来把 `schedule_rule` + `timed_priority` 折成 `priority_mode`。
    #   现在三模式整簇没了 -> 这个迁移**没有目标字段** -> 一并删除。
    #
    # ⚠ 老配置里遗留的 `priority_mode` / `priority_mode_explicit` 键:
    #   `Optimization` 不再声明它们 -> pydantic 加载时**静默忽略多余键**
    #   -> 下次 `save()` 时从磁盘上**自然消失**。不需要专门写清理迁移。

    # ------------------------------------------------------------------ 一次性迁移
    # ------------------------------------------------------------------ 任务周期（唯一权威）
    def task_period(self, task_command: str) -> str:
        """★ 该任务**当前生效的周期** —— `'none'` / `'daily'` / `'weekly'` / `'monthly'`。

        ## ★★★ 为什么需要它（用户裁定, 本轮核心）★★★

        用户原话:
        > "**周期是 period 啊！**你联系下上下文行不, 是**每天、每周每月、不限**那个"

        ★ 那个下拉在 **`/args` 的 `scheduler` 组**：
        ```
        GET /{script}/{task}/args  ->  组 'scheduler'  ->  字段 'period'
          type='enum'   enumEnum=['none','daily','weekly','monthly']
        ```
        前端 `args_view.dart` 的通用枚举渲染 -> `DropdownButton`（选项正是这 4 个）。

        ## 取值顺序（★ 用户确认）

        1. ★ **配置里的 `scheduler.period`**（用户在前端选的）—— **优先**
        2. `tasks/<Name>/meta.py` 的 `TaskSpec.period` —— ★ **降级为「出厂默认值」**

        > 用户裁定: "判据改成读 `scheduler.period`（配置）, `meta.py` 降级为出厂默认值"

        ## 为什么必须这样（原来不联动的根因）

        | | 用户改的 | 标签原来读的 |
        |---|---|---|
        | 字段 | **`scheduler.period`**（配置, **有前端入口**）| **`TaskSpec.period`**（`meta.py`, **写死源码**）|

        ★ **同名、不同字段、不同来源** -> 用户"在前端改了 period, 队列标签不动"。
        ★ 实测两边 **31/53 不一致**（配置里 52 个 `none`, `meta.py` 里 29 个 `daily`）。

        ## 它驱动什么

        * `_segment_of()` -> `priority_group` -> 界面「**周期 / 临时**」标签与分段条
        * ★ 与**窗口约束**配套: `period == 'none'` 时**不允许新增窗口**
          （见 `schema_router` 的窗口端点 + `window_editor.dart` 的提示）
        """
        # ① 配置优先
        try:
            from module.config.config_model import convert_to_underscore
            key = convert_to_underscore(task_command)
            sch = getattr(getattr(self.model, key, None), 'scheduler', None)
            v = getattr(sch, 'period', None) if sch is not None else None
            s = str(getattr(v, 'value', v) or '').strip().lower()
            if s in ('none', 'daily', 'weekly', 'monthly'):
                # ⚠ `none` 也要**认**（它就是"不限"）—— 不能当成"没设过"。
                return s
        except Exception as exc:
            logger.debug(f'取 {task_command} 的配置 period 失败'
                         f'({type(exc).__name__}: {exc})')
        # ② 回退出厂默认值
        return task_period_default(task_command)

    def priority_group_of(self, task_command: str) -> str:
        """★★ 段名 —— `'timed'`（**周期任务**）/ `'fixed'`（**临时任务**）。

        用户裁定:
        > "窗口必须在选了周期后才能设置。**这样子判断依据就可以按有没有周期来判断**"

        ★ 判据**一条**: `task_period() != 'none'` -> 周期任务。
        ★ 这就是"改一个属性, 全联动"的**唯一那处判断** —— 不再有
          `category` -> `category_effective` -> `priority_group` 三层推导。
        """
        return 'fixed' if self.task_period(task_command) == 'none' else 'timed'

    def migrate_task_period_once(self) -> bool:
        """★ 一次性把 `scheduler.period` **按出厂默认值回填**（用户确认要做）。

        ## 用户裁定

        > "首次自动把 `scheduler.period` 按 meta 的出厂值补上
        >  （避免 52 个任务突然全变临时）" —— **对**
        > 剩下 45 个 `none`: "把剩下的 `none` 也按 meta 内置值**全部回填**"

        ## 为什么必须回填

        分类判据已改成读**配置**里的 `scheduler.period`（这样前端一改就联动）。
        而老配置里那 52 个任务写的都是 `none` —— 若不回填,
        **绝大多数任务会突然变成「临时任务」**, 与改造前的分类不一致。

        ## ★ 回填规则（用户确认）

        * `scheduler.period` **是 `none` 或缺失** -> ★ 写成出厂默认值
        * `scheduler.period` **是 `daily`/`weekly`/`monthly`** -> ★ **不动**
          （那是用户在前端明确选的, 必须尊重）

        ⚠ 为什么 `none` 也要回填（而不是当成"用户选了不限"）:
          `none` 恰好就是 `template.json` 里的**默认值** —— 老配置里那 52 个
          `none` **无法区分**"用户选的"与"从没设过"。★ 用户已明确选择
          "**按 meta 全部回填**", 所以这里按 `none` -> 出厂默认值处理。

        ## ★★★ 但它**必须只跑一次**（否则用户改不动"不限"）★★★

        实测踩到的坑: `Config()` **每个 HTTP 请求都会新建**, 而本方法在
        `__init__` 里调用 —— 若只看"当前是 `none` 就回填", 那么用户把某任务
        改成「不限」后, **下一次请求就被改回出厂值**:
        ```
        写入 period='none'  ->  Config(cfg)  ->  task_period() 返回 'daily'
                                            ->  ★ 磁盘也被改回 'daily'
        ```
        ★ **用户完全改不动「不限」** —— 这正是"分类永远不联动"的另一种形态。

        ★ 修法: `Optimization.period_backfilled` **一次性标记** ——
          回填只做第一次, 之后永不再碰（用户想设 `none` 就设得动）。
        """
        try:
            from module.config.config_model import convert_to_underscore

            opt = getattr(getattr(self.model, 'script', None),
                          'optimization', None)
            if opt is None:
                return False
            # ★ 已经回填过 -> 彻底不管（用户后续的任何选择都必须尊重）
            if bool(getattr(opt, 'period_backfilled', False)):
                return False

            changed = []
            for name in _all_task_names():
                key = convert_to_underscore(name)
                sch = getattr(getattr(self.model, key, None), 'scheduler', None)
                if sch is None:
                    continue
                cur = getattr(sch, 'period', None)
                s = str(getattr(cur, 'value', cur) or '').strip().lower()
                # ★ 用户明确选过的周期 -> 不动
                if s in ('daily', 'weekly', 'monthly'):
                    continue
                want = task_period_default(name)
                if s == want:
                    continue        # 值没变（如出厂值本来就是 none）-> 不写
                # ★★ 必须写**枚举对象**, 不能写裸字符串 ★★
                #
                # `Scheduler.period` 是 `TaskPeriod` 枚举。写字符串会触发
                # pydantic 警告（实测 30 条）:
                #   `Expected 'enum' but got 'str' with value 'daily' -
                #    serialized value may not be as expected`
                # ⚠ 本项目**已踩过同一个坑**（`put_priority_mode` 那里也写着
                #   "传枚举对象而不是裸字符串"）。这里照同一做法。
                from tasks.Component.config_scheduler import TaskPeriod

                try:
                    self.model.deep_set(
                        self.model, keys=f'{key}.scheduler.period',
                        value=TaskPeriod(want))
                except ValueError:
                    # 出厂默认值不在枚举里（不该发生）-> 跳过并告警
                    logger.warning(f'{name}: 出厂周期 {want!r} 不是合法 '
                                   f'TaskPeriod, 跳过')
                    continue
                changed.append((name, s or '<缺失>', want))

            # ★ 无论有没有改动, 都要**置上标记** —— 否则"出厂值本来就是 none"
            #   的那 14 个任务会让本方法每次启动都白跑一遍。
            self.model.deep_set(
                self.model, keys='script.optimization.period_backfilled',
                value=True)
            self.save()
            if changed:
                logger.info(
                    f'已按出厂默认值回填 {len(changed)} 个任务的 '
                    f'scheduler.period（用户明确选过 daily/weekly/monthly 的'
                    f'不动; 之后不再回填）')
            else:
                logger.info('任务周期回填: 无需改动, 已置一次性标记')
            return bool(changed)
        except Exception as exc:
            logger.warning(f'回填 scheduler.period 失败'
                           f'({type(exc).__name__}: {exc}) —— '
                           f'下次启动会重试')
            return False

    def migrate_windows_once(self) -> bool:
        """把**窗口**迁移/配好（**只做一次**, 用户要求）。

        用户原话: "你直接帮我配好窗口就好, **改用户配置**。
                  顺带帮我把**现有的配置适配好现有的软件**。"

        ## ★★ S3: 旧的单值 / `window_slots` -> **`windows` 列表** ★★

        用户裁定: "不是 window slots, 而是**设置多个 window**！
                  slots 不是已经废弃了吗"
                 "**一天跑两次 = 两个窗口**"

        所以本方法:
        1. 把旧的 `window_enable` / `window_start` / `window_end` /
           `window_days` / `window_period` / `window_dom` /
           **`window_slots`** 折成 `windows` 里的若干项
        2. 用户**没配过**的 -> 给推荐值（`restart` 两个窗口 / `ryou_toppa` 一个）
        3. **删掉**被替代的旧字段（避免"两个来源"）

        ★ 幂等: `windows` 非空 -> 跳过（**不能**每次启动都覆盖用户设置）。
          踩过: 用自定义键做标记 —— pydantic v2 的 `extra='ignore'` 会把它从
          `model_dump()` 丢掉 -> 每次启动都覆盖。
        """
        try:
            from tasks.Component.config_scheduler import (
                apply_recommended_windows)

            raw = self.model.model_dump()
            changed = apply_recommended_windows(raw)
            if not changed:
                return False

            for key in changed:
                sch = raw[key]['scheduler']
                # ★ `windows` 是 `List[TaskWindow]` -> 直接给 list[dict],
                #   pydantic 会按 `TaskWindow` 校验/转换（`Time` 也认字符串）。
                self.model.deep_set(
                    self.model, keys=f'{key}.scheduler.windows',
                    value=list(sch['windows']))
                # ★ 旧字段已从模型里**删除**, 不再写回；
                #   `model_dump()` 里若还有残留, 留 `extra='ignore'` 丢弃。
            # ★ 真正落盘（否则只在内存里, 下次启动又"没配"）
            self.save()
            logger.info(f'{self.config_name}: 已配好窗口 -> {changed}（已保存）')
            return True
        except Exception as exc:
            logger.warning(f'{self.config_name}: 窗口迁移失败'
                           f'（{type(exc).__name__}: {exc}）, 跳过')
            return False

    def fix_stale_next_run_once(self) -> bool:
        """★★★ 一次性修正"全天窗口却被排到未来"的 `next_run`（用户报的 bug）★★★

        ## 用户原话

        > "**契灵之境为什么显示等待到点**? 这个是次数任务, 不应该有
        >  [还未到点]这种[拥有 window 的任务类]的属性啊"

        ## 根因（实测三层）

        1. `next_run_after(strict=True)` 对**全天窗口**（`00:00-23:59`）
           算出的是"**下一次**窗口开放" = ★ **明天 00:00**
           （`next_opening(strict=True)` 先跳到 `next_closing` 今天 23:59,
            再找下一次开放）。
           ✅ 已在 `next_run_after` 修（`is_unrestricted` 特判 -> 返回 `when`）。
        2. 但**已经落盘**的 `next_run` 是修复前算出来的坏值
           （实测 `RealmRaid` = 明天 00:00, `MemoryScrolls` = 明天 22:21）。
           `update_scheduler` 只**读**它 -> 修复后仍卡在 `waiting`
           -> 界面继续显示「等待到点」。
           ✅ **本条修**。

        ## 判据（只改**确凿矛盾**的值）

        对每个**启用**的任务, 三条同时成立才改:

        * 它的窗口**此刻是开放的**（游戏机制允许跑）
        * ★ 它**所有**有效窗口都是 `is_unrestricted`（= 全天窗口, 无时段约束）
        * 而 `next_run` 却在**未来**

        -> ★ 这是**矛盾**: 一个"全天可跑"的任务没有任何理由把自己推到明天。
          **把 `next_run` 拉回现在**。

        ⚠ 为什么只动"全天窗口": 受限窗口（如逢魔 `17:00-23:00`）的
          `next_run` 落在未来是**正确**的（明天 17:00 才开放）
          —— 那些**绝不能**动（实测: 修完后 `DemonEncounter` 仍是明天 17:00 ✓）。
        ⚠ 幂等: 修正后 `next_run == now`, 不再是"未来" -> 第二次跑无改动。
        """
        try:
            from module.config import task_catalog as TC

            changed = []
            now = datetime.now().replace(microsecond=0)
            for name in _all_task_names():
                key = convert_to_underscore(name)
                node = getattr(self.model, key, None)
                sch = getattr(node, 'scheduler', None)
                if sch is None or not getattr(sch, 'enable', False):
                    continue
                nr = getattr(sch, 'next_run', None)
                if not isinstance(nr, datetime) or nr <= now:
                    continue                    # 不在未来 -> 没什么可修
                # 只处理"全是全天窗口"的任务
                spec = TC.get_spec(name)
                if spec is None:
                    continue
                ws = [w for w in (spec.windows_effective or [])
                      if getattr(w, 'enabled', False)]
                if not ws:
                    continue                    # 没窗口 -> 走别的分支
                if not all(bool(getattr(w, 'is_unrestricted', False))
                           for w in ws):
                    continue                    # ★ 有受限窗口 -> 未来值是**对的**
                # ★ 矛盾: 全天可跑却排在明天 -> 拉回现在
                self.model.deep_set(self.model,
                                    keys=f'{key}.scheduler.next_run',
                                    value=now)
                changed.append((name, str(nr)))

            if not changed:
                return False
            self.save()
            logger.info(f'已修正 {len(changed)} 个"全天窗口却被排到未来"的 '
                        f'next_run（见 fix_stale_next_run_once）')
            for n, old in changed:
                logger.info(f'  {n}: {old} -> 现在')
            return True
        except Exception as exc:
            logger.warning(f'修正 next_run 失败({type(exc).__name__}: {exc}) '
                           f'—— 下次启动会重试')
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
        for key, value in self.model.model_dump().items():
            func = Function(key, value)
            if not func.enable:
                continue
            # ★ 两个总开关（用户确认的设计）:
            #   固定任务（fixed/toppa）看 `enable_fixed`,
            #   定时任务（timed/limited）看 `enable_timed`。
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
            # ★★★ 修: "等待到点"必须**真的有依据**（用户报的真 bug）★★★
            #
            # 用户原话:
            # > "**契灵之境为什么显示等待到点**? 这个是次数任务, 不应该有
            # >  [还未到点]这种[拥有 window 的任务类]的属性啊"
            #
            # ## 为什么"时刻已过 + 窗口开着"的还要看 `next_run`?
            #
            # 不该看。★ 两条成因:
            #
            # 1. ★ **排期算法错**: `next_run_after(strict=True)` 对**全天窗口**
            #    （`00:00-23:59`）算出的是"**明天** 00:00" -> `next_run` 落在
            #    未来 -> 归入 `waiting` -> 界面显示"等待到点"。
            #    ✅ 已在 `next_run_after` 修（`is_unrestricted` 特判）。
            # 2. ★ **落盘的旧坏值**: 已经写进配置的 `next_run` 是**修复前**
            #    算出来的（实测 `RealmRaid` = 明天 00:00）。`update_scheduler`
            #    只**读**它 -> 修复后仍卡在 `waiting`。
            #    ✅ 本条修。
            #
            # ## 本条规则（一句话）
            #
            # ★ **窗口开着 + `next_run` 已过 -> 就是可跑**。
            #
            # ⚠ 依据: `next_run` 是"我上次跑完给自己定的下次时间"（**自定节奏**）;
            #   `in_window()` 才是"**游戏机制允许**"。
            #   当自定节奏与机制允许**矛盾**时, 机制优先 ——
            #   这正是用户说的"次数任务不该有『未到点』属性"。
            #
            # ⚠ 行为安全性: 这个分支只在 `next_run < now` **之后**才可能命中,
            #   所以**不会**让"刚跑完、还没到点"的任务提前重跑;
            #   它只影响那些"被错误推远"的任务。
            if isinstance(func.next_run, datetime) \
                    and func.next_run < self.scheduler_update_dt \
                    and func.in_window():
                pending_task.append(func)
            elif not isinstance(func.next_run, datetime):
                error.append(func)
            elif func.next_run < self.scheduler_update_dt:
                #
                # 原来在这里判 `_skip_by_period(...)` —— 但那时
                # `func.entry_id` 还是 `None`（条目身份由 `_order_by_queue`
                # 在后文逐条写入）-> 门槛退化成"按任务名" ->
                # **重复条目会被合并**（第二条也被跳过, 只跑 1 次）。
                #
                # 现在改为在排完序之后**逐条**按 `entry_id` 复查
                # （见下面 "完成记忆（按条目）" 那一段）。
                #
                # 开放时段: 游戏机制决定的硬约束。
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
            # ★★ T1/T2（审计修复）: **不再调 `TaskScheduler.schedule()`** ★★
            #
            # 原来这里是:
            #     _opt = self.model.script.optimization
            #     _rule = _opt.schedule_rule
            #     pending_task = TaskScheduler.schedule(rule=_rule, ...)
            #
            # ## 为什么删（两个真 bug）
            #
            # **T2 —— FILTER 白名单会吞掉队列内的任务。**
            #   出厂默认 `schedule_rule=Filter` -> `TaskScheduler.schedule`
            #   -> `Filter.apply(pending)` 按 `ConfigManual.SCHEDULER_PRIORITY`
            #   白名单过滤。实测: `FindJade` / `GotoMain` **不在白名单**却被丢掉
            #   —— 而它们 `auto_queue=True`（**启用即自动进队列**）
            #   -> **在队列里却永不执行**。白名单里还有 2 个**已不存在**的任务名。
            #
            # **T1 —— 两个排序权威互相牵制。**
            #   `schedule_rule` 与 `priority_mode` 都在回答"谁先跑":
            #   用户拖了顺序, 却因为 `schedule_rule != List` 而不生效。
            #
            # ## 现在
            #
            # **唯一的顺序权威是队列**（下面 `_order_by_queue()`),
            # 不论 `schedule_rule` 是什么。`ScheduleRule` 枚举保留, 仅为
            # **读**旧配置（迁移用）—— 它不再影响行为。
            # ★ 用户裁定: "**三个选项: 定时任务优先、固定任务优先、自定义**"。
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
            # ★★ T1（审计修复）: `schedule_rule` **不再参与排序** ★★
            #
            # ## 原来这里是 `if self._is_list_rule(_rule): ... else: ...`
            #
            # 两个分支的**实际动作已经一样**（都只 `_order_by_queue()`）——
            # 差别只在"要不要按条目复查完成记忆"。而 E3（完成状态**按条目**
            # 记）是**不变量**（设计文档 §4）, 却原来**只在 `List` 规则下成立**：
            # 几乎所有用户的 `schedule_rule` 都是出厂默认 `Filter` -> **E3 不成立**。
            #
            # ★ 而且前端那个「优先级依据」四选一下拉仍在渲染, 与 `priority_mode`
            #   构成**两个互相牵制的控件** —— 用户拖了顺序却不生效
            #   （台账 §27.3 那类"拖了没用"陷阱的复现）。
            #
            # ## 现在（用户裁定: 三个选项合并成一个「调度优先级」）
            #
            # * **唯一的顺序权威是队列**（`_order_by_queue()`）—— 不论规则
            # * **无条件**按条目复查完成记忆（E3 处处成立）
            # * `TaskScheduler.schedule()` **不再被调用**
            #   （`ScheduleRule` 枚举保留, 仅为**读**旧配置）
            #
            # ★ 这条同时守住 F3 的不变量: `pending` 是"队列剔除 waiting 后的
            #   **保序子序列**"（`tests/module/config/test_queue_is_authority.py`）。
            pending_task = self._order_by_queue(pending_task)

            # ★★ C: **完成记忆（按条目）** —— 现在**无条件**执行 (T1) ★★
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
                tv = self.model.model_dump().get(tk) or {}
                if self._skip_by_period(
                        tk, tv,
                        entry_id=getattr(f, 'entry_id', None)):
                    waiting_task.append(f)
                    continue
                kept.append(f)
            pending_task = kept
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


    # ------------------------------------------------------------------ 分段
    #
    # ★★★ 「调度优先级三模式」整簇 **已删除**（用户裁定）★★★
    #
    # ## 用户原话
    #
    # > "我觉得……这个**固定任务优先和定时任务优先以及不能跨类别拖动太蠢了**。
    # >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
    # >  定时任务优先**直接作为一个快捷排序**就好, **而不是定义一些没有意义的
    # >  不能跨类别拖动以及单独的调度优先级**。"
    #
    # ## 所以删掉了什么
    #
    # | 删除 | 原来在哪 |
    # |---|---|
    # | `priority_mode()` | 本方法（曾读 `Optimization.priority_mode`）|
    # | `_order_by_priority_mode()` | 紧跟其后（**本来就是死代码**: 生产 0 调用）|
    # | `PriorityMode` 枚举 | `tasks/Script/config_optimization.py` |
    # | `priority_mode` / `priority_mode_explicit` 字段 | 同上 |
    # | `migrate_priority_mode_once()` | 本文件 `Config.__init__` 里调 |
    # | `_check_drag_allowed()` | `module/server/schema_router.py` |
    # | `drag_within_group_only` | `/schema` + 前端 |
    # | 前端的「调度优先级」下拉与全部拖动判据 | `task_list_*` |
    #
    # ## 留下来的（新的单一权威）
    #
    # **执行顺序 = `run_list` 的顺序本身**。没有任何"模式"能改变它。
    # 「定时排前面 / 固定排前面」变成一个**一次性动作**
    # （`sort_run_list(by=...)`）, 点一次排一次, **不留状态**。
    #
    # ★ 唯一保留的约束: 「休息」条目**恒排最后**（用户确认）——
    #   它排在中间会挡住后面所有任务。见 `_tag_and_place_rest()`。

    def _segment_of(self, command: str) -> str:
        """任务属于哪个**段** —— `'timed'`（周期任务）/ `'fixed'`（临时任务）。

        ## ★★★ 判据（用户裁定, 本轮核心）★★★

        用户原话:
        > "**窗口必须在选了周期后才能设置。这样子判断依据就可以按有没有周期
        >  来判断**"
        > "周期是 period 啊！… 是**每天、每周每月、不限**那个"

        ★ 所以**只看 `Config.task_period()`**（= 配置里的 `scheduler.period`,
          用户能在前端改的那个; 拿不到才回退出厂默认值）。

        ★★ **为什么这是"能联动"的关键**: 原来这里读 `TC.get(command)`
          （`meta.py` 的 `TaskSpec.priority_group`, **写死源码、前端改不了**）
          -> 用户"在前端改了 period, 队列标签不动"。
          现在读配置 -> **改一处, 全联动**。

        ## 用途（只剩两个）

        * `/overview` 的 `priority_group` / `priority_group_label`（界面显示）
        * `sort_run_list(by=...)` 的**一次性排序**依据
        ⚠ **不再**用于"限制拖动范围" —— 拖动永远自由。
        """
        try:
            return self.priority_group_of(command)
        except Exception as exc:
            logger.debug(f'取分段失败({type(exc).__name__}: {exc})')
        return 'fixed'

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
            result = [f for _, f in kept]

            # ★★ 第二轮复审修复: **恢复 `Restart` 置顶**（T1 静默丢掉的约定）★★
            #
            # ## 为什么会丢
            #
            # 这条约定原来在 `TaskScheduler.schedule()` 里, **两处**都写死了:
            #   * `scheduler.py:143-148`（`list_order`）
            #   * `scheduler.py:159-164`（`fifo`）
            #   注释原话: "**永远保证 Restart 任务在最前(与 fifo 的既有约定一致)**"
            #
            # T1 把 `TaskScheduler.schedule()` 的**调用**删了（那是对的 ——
            # 它带来 FILTER 白名单吞任务）。但那条**行为保证**随之消失,
            # **没有任何地方接管** -> 静默回归。
            #
            # ## 为什么这条约定重要（不是随便加的）
            #
            # `Restart` 是"**重启 / 领体力**"（`tasks/Restart/meta.py`:
            # `auto_queue=True`、`list_pos=0`、`period=DAILY`），而它自己的
            # 开放窗口是**每天两段 2 小时**（12:00-14:00 / 20:00-22:00）。
            # ★ 窗口一开就该**立刻**领 —— 排在前面任务之后就可能在窗口内
            #   排不上, 于是"体力没领到"。
            #
            # ## 实测（复审时）
            #
            # 本机 `queue = ['MetaDemon','AbyssShadows','Restart', ...]`
            # -> `Restart` 掉到**第 2 位**（旧行为恒为 0）。
            #
            # ## 与"队列是唯一顺序权威"冲不冲突
            #
            # **不冲突**。队列权威说的是"**谁在队列里、用户排的相对次序**"；
            # 这是**一条写死的例外**（"领体力的先跑"）, 且**只影响 `Restart`
            # 一个任务**。用户仍可以让它不跑（从队列移除 / 停用）。
            # ★ 若将来要删这条约定, 应**显式**写进 `docs/deprecated.md`
            #   并告知用户, 而不是静默丢掉。
            for i, f in enumerate(result):
                if getattr(f, 'command', '') == 'Restart':
                    if i:
                        result.insert(0, result.pop(i))
                    break
            return result
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

    # ★★★ S6/S7: `_order_by_timed_priority()` 与 `_order_by_priority_mode()`
    # **都已删除** ★★★
    #
    # 两个都是**死代码**（实测: 只有定义、无调用）—— `update_scheduler()`
    # 早就不调它们了。★ 这很关键: **调度路径上没有任何"按优先级重排"**,
    # 用户拖的顺序才是权威。
    #
    # ★ 历史: 它们曾分别用 `timed_sort_key` 与 `priority_mode` 三模式排序。
    #   实测事故: `_order_by_timed_priority()` 把整个 `pending` 重排, 队列
    #   第 9 位的 `ExperienceYoukai` 被排到第 1 位 —— 用户拖的顺序**被完全
    #   覆盖**。
    #
    # ★ 现行做法（S7）:
    #   * **执行顺序 = `run_list` 的顺序本身**（`_order_by_queue()` 只按它排）
    #   * 想让"定时/固定"排前面 -> 用户**点按钮** -> `sort_run_list(by)`
    #     （**一次性动作**, 不留状态）
    #   * 队列层只做两件事: 打 `group` 段名 + 把 rest 挪到最后
    #     （`_tag_and_place_rest()`, 由 `_segment_queue()` 改名而来 ——
    #      这样 `pending` 作为队列的保序子序列, 不变量才成立）

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
    def auto_queue_of(self, task_command: str) -> bool:
        """★★★ 该任务是否**自动进队列** —— **与「周期 / 临时」同源** ★★★

        ## 用户裁定（本轮）

        > "**显示周期的不应该移除队列后回退到添加任务的池子里而是直接停用**,
        >  这说明目前的**[联动]还不完善**。"

        ## 为什么必须同源（实测到的**真漂移**）

        `TaskSpec.auto_queue` 在 **54 个 `meta.py` 里都显式声明**，而它的
        **推导依据是 `category`**（`auto_queue_effective`：显式值优先,
        否则 `category not in COUNTABLE_CATEGORIES`）。

        ★ 但 `category` 正是**被废弃的那个判据**（分类已改为按 `period`）。
        ★ 于是两者**必然漂移** —— 实测 **4 个不一致**:

        | 任务 | `period` | 界面分类 | `auto_queue` | 后果 |
        |---|---|---|---|---|
        | `OtherWorldTwilight` | daily | **周期** | `False` | 界面说周期, 却不自动入队 |
        | `RyouToppa` | daily | **周期** | `False` | 同上 |
        | `SixRealms` | daily | **周期** | `False` | 同上 |
        | `TalismanPass` | none | **临时** | `True` | 界面说临时, 却自动入队 |

        ★ 这就是用户看到的"**添加任务里还显示着固定任务标签**"与
          "**联动不完善**"的根因。

        ## 判据（一条, 与 `priority_group_of` 同源）

        * `period != 'none'`（**周期任务**）-> **自动进队列**（用户不用手动加）
        * `period == 'none'`（**临时任务**）-> 只有用户【添加任务】后才进队列

        ★ 注意: `meta.py` 里那个显式 `auto_queue` **不再参与判定** ——
          它只作为历史记录保留（避免大批量改 54 个文件的风险）。
        """
        try:
            return self.priority_group_of(task_command) == 'timed'
        except Exception as exc:
            logger.debug(f'判 auto_queue 失败({task_command}: '
                         f'{type(exc).__name__}: {exc})')
            return False

    def auto_queue_tasks(self) -> list:
        """所有**自动进队列**的任务命令名（按 catalog 顺序）。

        ★ 判据已改为 **`auto_queue_of()`（= 周期任务）** —— 见它的 docstring:
          原来读 `TaskSpec.auto_queue_effective`（依据**已废弃的 `category`**）,
          与界面显示的"周期 / 临时"**漂移**（实测 4 个不一致）。
        """
        try:
            from module.config import task_catalog as TC
            specs = TC._load_specs()
            return [t for t, _s in sorted(specs.items())
                    if self.auto_queue_of(t)]
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
            if not task:
                continue
            # ★★ 第二轮复审（自查）修复: **手动编排的条目也要过滤 `enable`** ★★
            #
            # 原来这里**无条件** `out.add(task)`, 于是:
            #   * 用户把 `MetaDemon` 加进过 `run_list`, 后来**关掉**了它
            #     （`enable=False`）
            #   * `build_queue()` **不**收它（`_task_enabled` 过滤）
            #   * `queued_commands()` **收**它 -> 两处**不一致**
            #
            # 后果（用户可见）:
            #   1. `/overview` 把它标成 `queued=True` —— 明明不会跑
            #   2. 前端【添加任务】把它**排除**（"已在队列"）-> 用户**加不回来**
            #   3. `test_queue_membership_and_category.py` 的
            #      `test_no_disabled_auto_task_in_queue` 直接报
            #      "② 回归: 未启用的自动任务出现在队列成员里: ['MetaDemon']"
            #
            # ★ 实测证据: 队列 19 条 / pending 14 / waiting 6 ——
            #   **`MetaDemon` 既不在 pending 也不在 waiting**（`enable=False`
            #   在 `update_scheduler` 最早就被 `continue` 掉了）。它是
            #   "**在队列成员里但根本不会被调度**"的那一个。
            #
            # ★ 判据统一为 **`_task_enabled()`** —— 与 `build_queue()`、
            #   与下面那段 `auto_queue_tasks()` 的过滤**同一个函数**。
            if self._task_enabled(task):
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

        ## ★★ 第二轮复审修复: 用户编排的**未启用**条目也跳过 ★★

        `build_queue()` 的语义是"**实际会跑的清单**"（与
        `queued_commands()` 的 docstring 同义）。而 `update_scheduler()`
        在**最早就** `if not func.enable: continue` —— 未启用的任务
        **永远不会跑**。

        ⚠ 原来这里只对**自动补齐**的过滤 `_task_enabled`, 而
        `build_run_list()` 返回的用户条目**照收**。后果（实测）:
          * `MetaDemon` 在 `run_list` 里但 `enable=False`
          * `build_queue()` **收**它 -> 它出现在【执行顺序】页
          * `queued_commands()`（已修）**不收** -> `/overview` 标 `queued=False`
          * ★ 两处**不一致** -> 页面自相矛盾
          * ★ 而 `pending` 里**根本没有它**（最早被 `continue` 掉）
            -> 用户看到"在队列里却永远不跑、还排在第一"

        ★ 判据统一为 **`_task_enabled()`**（与自动补齐那一支、与
          `queued_commands()` **同一个函数**）。
        ★ 这不影响"用户能保留未启用的编排" —— 条目**还在
          `run_list`**（配置里没动），只是**不进执行队列**;
          用户重新启用它, 它立刻回到队列的**原位置**。
        """
        from module.config.run_list import RunEntry, RunList

        rl = self.build_run_list()
        # ★ 先剔除**未启用**的用户条目（保留在配置里, 只是不排队）
        try:
            rl = RunList([e for e in rl
                          if not getattr(e, 'task', None)
                          or self._task_enabled(e.task)])
        except Exception as exc:
            logger.warning(
                f'过滤未启用条目失败({type(exc).__name__}: {exc}), 保持原样')
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
        return self._tag_and_place_rest(rl)

    # ------------------------------------------------------------------ 队列分段
    def _tag_and_place_rest(self, rl):
        """给队列条目**打段名**，并把「休息」条目**挪到最后**。

        ## ★★★ 用户裁定（这一版是简化后的）★★★

        > "**我只需要保持可以自由拖动/改变执行顺序就行**, 固定任务优先和
        >  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有意义
        >  的**不能跨类别拖动**以及**单独的调度优先级**。"

        ★ 所以这个方法**不再按模式排段** —— 队列顺序 = **`run_list` 的顺序**,
          一个字都不动。排序是**另一个动作**（`sort_run_list(by=...)`）。

        ## 只做两件事

        1. **打段名** `group`（`'timed'` / `'fixed'`）—— 界面靠它渲染
           类别色条与标签。★ 这是**派生值, 永不落盘**
           （`RunEntry.to_dict()` 刻意不序列化它）。
        2. ★★ **不再对「休息」做任何排序**（用户裁定 P-2）★★

           ⚠ 这里原来写着"用户确认保留的唯一硬约束: 任意拖，但「休息」条目
             仍强制排最后 …… 任何模式、任何情况都排最后"。
             ★ **那句话不是用户的裁定**，是某次简化时写下的临时约束被误记
             成了长期规则。用户已澄清:

             > "休息**也是任务**, 只不过可以选择插入定时任务。"
             > "休息当然就是**挡住后边的**, 本质为了**防封**, **符合预期**。"

           ★ 休息仍**阻塞列表**（`blocking_entry()`）—— 那是它的**功能**；
             但它**不再是"恒最后"的排序约束**，用户可以把它拖到任意位置。

        ## 为什么在**队列层**做（不是排序 `pending`）

        因为 `pending` 必须是 `queue` 的**保序子序列**（§W4 / Z1）。
        `pending` 是从 `queue` **筛**出来的（只留已到点的）；事后重排它
        就不再是子序列了。★ 让队列本身正确, 子序列**天然**成立。

        ⚠ 与 `sort_run_list()` 的区别:
          * 本方法**不改** `run_list`, 只影响 `build_queue()` 的返回
            （`_tag_and_place_rest` 的结果**不回写配置**）
          * `sort_run_list()` 是**用户点按钮**触发的, 它**会**写盘
        """
        try:
            for e in rl.entries:
                if getattr(e, 'task', ''):
                    try:
                        object.__setattr__(e, 'group',
                                           self._segment_of(e.task))
                    except Exception:
                        pass
            # ★★ P-2: **不再把「休息」排到最后**（用户裁定）★★
            #
            # 用户原话:
            #   "休息**也是任务**, 只不过可以选择插入定时任务。"
            #   "休息当然就是**挡住后边的**, 本质为了**防封**, **符合预期**。"
            #
            # ★ 所以休息就是一个**普通条目**: 用户把它拖到哪, 它就在哪。
            #   它仍然**阻塞列表**（`blocking_entry()` 返回第一个 `REST`）——
            #   那是它的**功能**, 不是排序约束: 拖到中间时它后面的任务
            #   会等到休息结束才跑。★ 这是**用户明确要的效果**。
            #
            # ⚠ 曾经这里有一句"任意拖, 但休息仍强制排最后 / 任何模式任何情况
            #   都排最后"—— 那句话**不是用户的裁定**, 是某次简化时写下的
            #   临时约束被误记成了长期规则。已删除。
        except Exception as exc:
            logger.warning(f'队列分段失败({type(exc).__name__}: {exc}), '
                           f'保持原顺序')
        return rl

    def sort_run_list(self, by: str) -> bool:
        """★ **一次性排序** `run_list`: 把 `by` 这一段排到前面, 并写盘。

        ## ★★★ 这就是用户要的"快捷排序"（不是模式）★★★

        > "固定任务优先和定时任务优先**直接作为一个快捷排序**就好,
        >  而不是定义一些没有意义的不能跨类别拖动以及**单独的调度优先级**。"

        ★ 关键区别: **它不留状态**。
          旧实现是"设一个 `priority_mode`, 然后**每次** `build_queue()` 都按它排,
          还**限制拖动范围**"。现在是"**点一下, 排一次**" ——
          排完之后队列就是新顺序, 用户可以**随意再拖**, 没有任何东西拦他。

        ## 参数

        :param by: `'timed'` -> 定时段在前; `'fixed'` -> 固定段在前;
                   其它值 -> 报错返回 `False`（不猜）

        ## 规则（与用户确认过的一致）

        * **段内相对顺序不变**（`sorted` 是**稳定**的）—— 用户之前的编排
          在段内被保留
        * 「休息」条目**恒最后**（用户确认的唯一硬约束）
        * `custom` / 模式概念**已删除** —— 没有"自定义模式"这回事了,
          队列本来就是完全自定义的

        ## ★★★ 「当前跑不了」的任务排到**后面**（实机验收反馈）★★★

        用户原话:
        > "有个**不在开放时段内的秘闻副本也参与了定时排前面的排序,
        >  排到了最前边**"

        **根因**: 原来只按 `priority_group`（定时/固定）排, **不看能不能跑**。
        于是 `Secret`（秘闻副本, 窗口"周一 08:00-23:59"）在**非开放时段**仍被
        当成"定时段第一条"排到**最前** —— 可它**根本跑不了**, 顶在最前面只是
        把能跑的任务全挤到后面。

        ★ 修法: rank 从 2 档变 4 档 ——
            ① 属于 `by` 段 **且在开放时段内**   -> rank 0（能跑, 优先）
            ② 属于 `by` 段 **但不在开放时段内** -> rank 1
            ③ 另一段 **且在开放时段内**         -> rank 2
            ④ 另一段 **且不在开放时段内**       -> rank 3

        ★★ P-2:「休息」条目**不再被特殊处理**（用户裁定）★★

        用户原话:
        > "休息**也是任务**, 只不过可以选择插入定时任务。"
        > "休息当然就是**挡住后边的**, 本质为了**防封**, **符合预期**。"
        > "1 **全删**"

        ⚠ 这里原来是 `⑤ 「休息」条目 -> rank 9（恒最后）`。
          ★ 那是"休息恒排最后"那条**被误记成裁定**的临时约束的一部分。
          现在休息按**它自己的位置**参与：`sorted` 是**稳定**排序, 所以
          ★ 休息在哪个相对位置, 排序后**仍在那个相对位置** —— 不会被甩到最后。
          （它没有 `task`, 所以走"另一段"那一档, 与普通任务同规则。）

        ★ 这样"**能跑的优先**", 与调度器实际行为一致（不在窗口的会入 waiting）。
        ★ **段内保序**仍然成立（`sorted` 稳定）—— 用户编排不被搅乱。

        :return 是否成功（写盘失败返回 `False`, 调用方负责上屏）
        """
        if by not in ('timed', 'fixed'):
            logger.warning(f'sort_run_list: 非法 by={by!r}, 应为 timed/fixed')
            return False
        try:
            from module.config import task_catalog as TC

            def _rank(e) -> int:
                """★ 见上面「当前跑不了的排到后面」那一段的 ①~④。

                ★★ P-2: **不再给「休息」单独的 rank**（用户裁定）★★

                原来这里开头是:
                    if not task:
                        return 9              # 休息条目恒最后
                ★ 那是"休息恒排最后"的一部分（那句**不是**用户的裁定,
                  是误记的临时约束）。现在删掉 ——
                  休息与普通任务**同一套规则**参与排序（`sorted` 稳定,
                  所以它的相对位置不会被甩到最后）。
                """
                task = getattr(e, 'task', '') or ''
                try:
                    spec = TC.get_spec(task) if task else None
                    runnable = bool(spec.in_window()) if spec else False
                except Exception:
                    # 判不出来就当成"能跑" —— 保守: 不因为一个异常把用户的
                    # 编排踢到后面
                    runnable = True
                seg = self._segment_of(task) if task else ''
                if seg == by:
                    return 0 if runnable else 1
                return 2 if runnable else 3

            rl = self.build_run_list()
            rl.entries = sorted(rl.entries, key=_rank)
            if not self.save_run_list(rl):
                return False
            logger.info(f'已按「{"定时" if by == "timed" else "固定"}排前面」'
                        f'重排执行顺序（{len(rl.entries)} 条）'
                        f'—— 不在开放时段的排到后面')
            return True
        except Exception as exc:
            logger.warning(f'排序 run_list 失败({type(exc).__name__}: {exc})')
            return False

    def place_rest_last(self, rl):
        """★ **已废弃的"把休息挪到最后"** —— 现在**什么都不做**。

        ## 为什么保留这个函数

        `PUT /run_list` / `POST /run_list/entry` 两个端点都在调它
        （见 `schema_router.py`）。★ 保留名字与调用点，**行为改为直通**，
        这样调用方不用改、也不会有人以为"漏了"。

        ## 为什么不再挪位（用户裁定 P-2）

        用户原话:
        > "休息**也是任务**, 只不过可以选择插入定时任务。"
        > "休息当然就是**挡住后边的**, 本质为了**防封**, **符合预期**。"

        ★ 休息就是**普通条目**: 用户拖到哪它就在哪，后端**不再**兜底挪位。
          它仍然**阻塞列表**（那是它的功能），所以拖到中间时它后面的任务
          会等到休息结束才跑 —— ★ 这正是用户要的效果。

        ⚠ 曾经的 docstring 写着"用户确认: 任意拖, 但「休息」条目仍强制排
          最后"—— ★ 那句**不是**用户的裁定，是误记。已删除。
        """
        try:
            pass                      # ★ P-2: 直通（不再排序）
        except Exception as exc:
            logger.warning(f'rest 归位失败({type(exc).__name__}: {exc})')
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

    def scheduler_next_run_now(self, task_command: str) -> bool:
        """把某任务的 `next_run` 拉回**现在**（= "立刻可以跑"）。

        ## ★★ 为什么需要它（实机验收发现的真 bug）★★

        用户原话: "**契灵之境为什么显示等待到点?** 这个是次数任务,
          不应该有[还未到点]这种[拥有 window 的任务类]的属性啊"

        **根因**: 任务进冷却时 `script.py` 会
        ```python
        self.config.task_delay(task, success=False, server=True,
                               target=res['cooldown_until'])
        ```
        -> 把 `next_run` **写成冷却结束时刻**（实测 `18:44:00`）。

        ★ 于是**只清失败记录是不够的**: `next_run` 还停在那一刻, 而该任务
          的 `period=none`（无周期 -> **没有任何东西会重排它**）-> **永久**
          卡在"等待到点"。
        ★ 用户看到的就是: 一个**次数任务**却带着"未到点"的属性。

        :return 是否改动成功（**失败只记日志, 不抛** —— 调度不该被它带崩）
        """
        try:
            import copy
            from datetime import datetime

            key = self._config_key_of(task_command)
            if not key:
                return False
            now = datetime.now().replace(microsecond=0)
            self.model.deep_set(
                self.model, keys=f'{key}.scheduler.next_run', value=now)
            self.save()
            logger.info(f'{task_command}: `next_run` 已拉回现在（{now}）'
                        f'—— 解除冷却后立刻可跑')
            return True
        except Exception as exc:
            logger.warning(f'{task_command}: 恢复 next_run 失败'
                           f'({type(exc).__name__}: {exc})')
            return False

    @staticmethod
    def _config_key_of(task_command: str) -> str:
        """任务名 -> 配置里的键（下划线形式）。取不到返回 `''`。"""
        try:
            from module.config.config_model import convert_to_underscore
            return convert_to_underscore(task_command) or ''
        except Exception:
            return ''

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

    # ★★ S5/审计: _next_run_from_resource() **已删除** ★★
    #
    # 它内部 import 的 module.config.scheduler_core（连同 Resource /
    # Recharge）已在 S5 **删除存量机制**时一并删掉 —— 所以它每次调用都
    # 抛 ImportError、被自己的 except 吞掉、返回 None，**等于没调**。
    #
    # 排期的权威实现是 **窗口**（TaskSpec.windows_effective +

    # Config.next_run_after()）—— 见 docs/scheduler-architecture.md。
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
            # ★★★ "全天窗口"特判（修一个用户报的真 bug）★★★
            #
            # 用户原话:
            # > "**契灵之境为什么显示等待到点**? 这个是次数任务, 不应该有
            # >  [还未到点]这种[拥有 window 的任务类]的属性啊"
            #
            # ## 根因（实测）
            #
            # `strict=True` 的语义是"**下一次**窗口开放"。对
            # `00:00-23:59` 这种**全天窗口**, `next_opening(strict=True)` 会先跳到
            # `next_closing`（今天 23:59）, 再找"下一次开放" -> ★ **明天 00:00**。
            #
            # ★ 于是排期把任务推到**明天** -> `next_run` 落在未来
            #   -> `update_scheduler` 把它归入 `waiting` -> 界面显示
            #   **「等待到点」**。实测 `RealmRaid`（个人突破, `period=none`）与
            #   `MemoryScrolls`（绘卷）都是这个成因 —— 但它们明明"全天可跑"。
            #
            # ★ 修法: 全是**不受限**（`is_unrestricted`）的窗口时, 答案就是
            #   "**现在就能跑**"。★ 这与下面 `if not spans: return when`
            #   （**没有**窗口时）的语义**天然一致** —— 全天窗口本来就该等价于
            #   "没有时段限制"。
            # ⚠ `is_unrestricted` 是 **property（返回 bool）**, 不是方法 ——
            #   我第一版写成 `w.is_unrestricted()` -> **运行时 TypeError**
            #   （`'bool' object is not callable`）。
            #   ★ 实测抓到: `availability.py:165` 是 `@property`。
            if getattr(w, 'is_unrestricted', False):
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
            # ★ 没有**受限**窗口（无窗口 / 只有全天窗口）-> 现在就能跑
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
            #
            # ★★ 审计修复: 这里原本调 `self._next_run_from_resource(task, ...)`,
            #   而那个方法内部 `from module.config.scheduler_core import ...`
            #   —— `scheduler_core`（以及 `Resource` / `Recharge`）在 S5 已**删除**。
            #   于是**每次都抛 ImportError** -> 被 `_next_run_from_resource` 自己的
            #   `except Exception` 吞掉 -> 打一条 warning -> 返回 None -> 再走下面的
            #   窗口分支。**功能上等价于"没调", 但白刷日志。**
            #   -> 直接删掉这个死调用（正确的排期是下面的**窗口**分支）。
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
