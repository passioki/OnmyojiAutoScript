# -*- coding: utf-8 -*-
"""任务元数据目录(task catalog)。

**这个模块回答一个此前到处散落、反复出错的问题: "某个任务的'次数'到底是哪个字段?"**

背景(2026-10-08 实测)
---------------------
OAS 里"打满 N 次就停"的字段**命名极不统一**:

    FallenSun/Orochi/...        limit_count
    Exploration                 minions_cnt
    Hyakkiyakou                 hya_limit_count   (脚本里映射成 limit_count)
    RealmRaid                   number_attack     (脚本里映射成 limit_count)
    WantedQuests                **硬编码 30**     (用户改不了, 是 bug)

于是任何"想统一展示/修改次数"的地方(总览页、任务列表、API)都得自己判断,
每处都要重新踩一遍坑。本模块把这份知识**集中一处**, 并提供统一访问接口。

数据来源(不手写、不靠猜)
------------------------
`task_catalog_data.json` 由 `dev_tools/gen_task_catalog.py` 生成:
  * 中文名     <- OASX `lib/config/translation/i18n_cn.dart`(权威)
  * 次数字段   <- 扫描 `tasks/*/script_task.py` 里 `current_count >= X` 实测
  * 其它字段   <- 解析 `tasks/*/config.py` 的 Field(default=...)
  * 充能周期   <- 用户配置里的 `scheduler.success_interval`

因此**升级 OAS 或改动任务后, 应重新生成该 JSON**, 而不是改这个文件。

用法
----
    from module.config import task_catalog

    task_catalog.get('FallenSun').name_zh          # '日轮之陨'
    task_catalog.get('FallenSun').category         # Category.FIXED
    task_catalog.target_field('FallenSun')         # 'limit_count'
    task_catalog.all_names()                       # {task: 中文名}
    task_catalog.by_category(Category.LIMITED)     # [TaskMeta, ...]
"""
import dataclasses
import json
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path

from module.config.resource import Period  # ★ ⑥ 要用
from module.logger import logger

DATA_FILE = Path(__file__).with_name('task_catalog_data.json')

# 统一后的"目标次数"字段名。所有固定任务最终都应暴露这个名字。
UNIFIED_COUNT_FIELD = 'limit_count'


class Category(str, Enum):
    """任务类别。

    划分依据是**游戏机制**, 不是 OAS 的内部实现:

    FIXED    固定任务 —— 有"打满 N 次"的语义, 可设目标次数
    TOPPA    结界突破 —— 两个子分类(寮突破 / 个人突破), 定点开放 + 次数上限
    LIMITED  限时活动 —— 隔一段时间才推出, 非常驻
    TIMED    定时任务 —— 其余按周期调度的任务
    """

    FIXED = 'fixed'
    TOPPA = 'toppa'
    LIMITED = 'limited'
    TIMED = 'timed'


# 有"目标次数"语义的类别(可展示/修改次数)
COUNTABLE_CATEGORIES = (Category.FIXED, Category.TOPPA)

# 类别中文名(界面用)
CATEGORY_LABEL = {
    Category.FIXED: '固定任务',
    Category.TOPPA: '结界突破',
    Category.LIMITED: '限时活动',
    Category.TIMED: '定时任务',
}


@dataclass(frozen=True)
class TaskMeta:
    """单个任务的静态元数据。"""

    task: str                       # 任务名, 如 'FallenSun'(与 tasks/ 目录名一致)
    name_zh: str                    # 中文名, 如 '日轮之陨'
    category: Category
    count_field: str or None        # "目标次数"字段名; None 表示该任务没有次数概念
    count_default: int or None      # 该字段的默认值
    needs_unify: bool               # count_field 是否还不是 limit_count
    has_limit_time: bool
    success_interval: str or None   # 充能周期原文, 如 '00 03:00:00'

    # ---- 便捷属性 ----
    @property
    def category_effective(self) -> Category:
        """**最终类别** —— 转发给 `TaskSpec.category_effective`（⑥）。

        ## 为什么需要转发

        `schema_router` 用的是 **`TaskMeta`**（`TC.get()`）, 而
        `category_effective` 定义在 **`TaskSpec`**（`TC.get_spec()`）上。
        不加转发 -> `AttributeError`（我实测踩过: **53 errors**）。

        ★ 判定逻辑**只有一处**（`TaskSpec.category_effective`）—— 这里只转发,
          保持**单一数据源**（台账 §10.8）。
        """
        try:
            spec = get_spec(self.task)
            if spec is not None:
                return spec.category_effective
        except Exception:
            pass
        return self.category

    @property
    def countable(self) -> bool:
        """是否可以设"目标次数"(界面是否显示次数输入框)。"""
        return self.category in COUNTABLE_CATEGORIES and bool(self.count_field)

    @property
    def display_name(self) -> str:
        return self.name_zh or self.task

    @property
    def count_field_effective(self) -> str or None:
        """
        对外统一的次数字段名。

        不论该任务实际用的是 minions_cnt 还是 limit_count, 调用方都拿
        `limit_count`(见 UNIFIED_COUNT_FIELD), 由这里做适配 —— 这样
        上层(API/界面/调度器)不必再关心别名。
        """
        return UNIFIED_COUNT_FIELD if self.countable else None


@dataclass(frozen=True)
class TaskSpec:
    """
    **任务自描述** —— 任务与调度器之间的唯一契约。

    设计目标(见 `docs/architecture.md` §7):
        新增一个游戏活动 = **只写 `tasks/<New>/meta.py`**, 零改动其它文件。

    为什么需要它: 早期任务元数据散落在 4 处(任务 config / OAS i18n / OASX i18n /
    本模块的 JSON), 新增一个活动要改 5 个地方, 且**漏一处就出问题**
    (本轮实测: `MetaDemon` 等任务在两个 i18n 里都缺条目, 界面显示英文 key)。

    现在把"这个任务是什么"收进**任务自己的目录**:

        tasks/MetaDemon/
            meta.py          <- 本文件(SPEC)
            config.py
            script_task.py
            assets.py

    字段:
        task:       任务名(与目录名一致)
        name_zh:    中文名(i18n 由此生成, 不再手写两份)
        category:   类别(见 `Category`)
        resource:   资源规则(`Resource`); None 表示由旧字段推导
        requires:   需要的平台能力(见 `docs/architecture.md` §7.4);
                    框架启动时校验, 不足则优雅禁用并提示
        note:       备注(供维护者)
    """

    task: str
    name_zh: str
    category: Category = Category.TIMED
    # ★★ S5: **周期**（原来只能从 `resource.recharge.period` 拿到）★★
    #
    # 用户裁定: "去除旧的充能存量说法。现在靠 window 的**多次设置**完全可以
    #          做到正常运行。" -> `Resource` / `Recharge`（= 存量机制）已**删除**。
    #
    # 而 `period` 本身**仍然需要**（"这是每天/每周/每月的任务"）,
    # 所以 S5 把它提升为**独立字段**（54 个 `meta.py` 各加一行）。
    period: Period = Period.NONE
    requires: tuple = ()
    note: str = ''
    # ★★ 是否**自动进入执行队列**（用户确认的"任务类别属性"）★★
    #
    # | 值 | 含义 | 例 |
    # |---|---|---|
    # | `True`  | **定时类** —— 启用后自动进队列（充能 / 时间窗口 / 周期调度）| 逢魔之时、地域鬼王、金币妖怪 |
    # | `False` | **次数类** —— 启用后**不**自动进队列, 需用户【添加任务】 | 探索、八岐大蛇、个人突破 |
    #
    # ★ 判定依据（用户原话 + 实测核对）:
    #
    #   用户: "除了定时任务（有充能、次数限制、或时间窗口限制）,
    #          其他的一般都是次数任务（可以随时设置挑战几次的任务）"
    #
    #   实测: 充能 / 窗口 / 周期 都是**配置开关**（用户当前配置里全是 0 个）,
    #   不能当任务属性用。稳定的依据是 **`countable`**:
    #
    #     `countable == True`  -> "能设挑战几次" = 次数任务 -> **不**自动进队列
    #     `countable == False` -> 定时 / 充能 / 限时类      -> 自动进队列
    #
    #   `None` = 按 `category` 推导（默认行为）。任务可显式覆盖,
    #   将来个别任务想例外时**只改它自己的 `meta.py`**。
    auto_queue: bool = None
    # ★★ **游戏开放时段**（硬约束）—— 从任务代码里搬过来的游戏机制事实 ★★
    #
    # 类型是 `AvailabilityWindow`（见 `module/config/availability.py`）,
    # 但用 `object` 标注以避免循环 import。
    #
    # ## 为什么要搬到这里
    #
    # 此前**16 个任务**把开放时段**硬编码在自己的 `script_task.py`** 里, 例:
    #
    #     DemonRetreat/script_task.py:
    #         if current_date.weekday() == 5:   # 只有周六
    #             pass
    #         else:
    #             days_until_saturday = ...
    #             self.custom_next_run(..., time_delta=days_until_saturday)
    #             raise TaskEnd
    #
    # 这带来三个问题:
    #
    #   1. **两套机制**: 调度器有 `AvailabilityWindow`（默认全关、且不参与
    #      `next_run` 计算）, 任务里又自己判一次 -> 用户与维护者都说不清
    #      到底谁说了算（本项目已因"知识存在两处"栽过多次）。
    #   2. **时段不是"用户偏好"**, 是**游戏机制** —— 不该散落在任务逻辑里,
    #      更不该让用户在 54 个界面各填一遍。
    #   3. 硬编码的 `raise TaskEnd` 让任务"跑一次就退出", 调度器只能靠
    #      `custom_next_run` 猜下次什么时候 —— 猜不准就白跑。
    #
    # 现在统一: **时段写在任务的 `meta.py` 里**, 由调度器
    # `next_available()` 统一裁决; 任务代码里的日期判断全部删除。
    #
    # **可以是单个 `AvailabilityWindow`, 也可以是它的 list/tuple** ——
    # 有些任务一天里有**两段不连续**的开放时间, 例如:
    #
    #     Hunt  周一~周四 06:00 起（麒麟）
    #           周五~周日 17:00 起（阴界之门）
    #
    # 单个 `AvailabilityWindow` 只能表达一段, 所以这里支持多段。
    #
    # `None`（默认）= 不限时段（行为与改造前一致, 不改变任何既有任务）。
    window: object = None
    # 任务列表里的默认位置。None = 未编排(排最后)。
    #
    # ★ 为什么默认 None 而不是给每个任务一个序号: 列表是**用户自己编排**的,
    #   我们不该预设"哪个任务该先跑"。默认全部未编排 -> 界面按类别/名称排序,
    #   用户拖拽后才写入位置。
    list_pos: int = None

    @property
    def period_effective(self):
        """该任务的**周期**（`Period`）—— 直接读**独立字段** `self.period`。

        ## ★★ S5 完成: 过渡期的 `resource` 兜底已删除 ★★

        原来 `period` 只能从 `resource.recharge.period` 拿 —— 那是"存量机制"的
        一部分。用户裁定:

            "去掉组队协同，去掉存量次数。"
            "去除旧的充能存量说法。现在靠 window 的**多次设置**完全可以做到正常运行。"
            "连 `charge_*` 字段和存量逻辑一起删"

        所以 S5 分两步: ① 先把 `period` 提升为独立字段（54 个 `meta.py` 各加一行）
        ② 再删 `Resource` / `Recharge`。

        ★ 现在 `resource` 字段**也已删除**, 这个属性就是**一层直读**。
        """
        return self.period if self.period is not None else Period.NONE

    @property
    def declared_window(self):
        """**显式声明**的窗口（`meta.py` 里写了才有）; 没写返回 `None`。

        ★ 与 `windows_effective` 的区别: 后者会**回退到周期推导**。
          校验脚本要用本属性来判断"哪些任务没显式声明"。
        """
        return self.window

    @property
    def windows_effective(self) -> tuple:
        """该任务的开放时段**列表**。

        ## 取值顺序（用户新澄清的设计）

        1. **`meta.py` 显式声明的 `window`**（游戏机制, 最权威）
        2. **由周期推导** —— `Period.DAILY` -> 每天 0-24;
           `Period.WEEKLY` -> 周一 0 点到周日 24 点（即全周）;
           `Period.MONTHLY` -> 当月 1 日到月末
           （见 `availability.window_for_period`）
        3. 都没有（`Period.NONE` 且没显式声明）-> 一个 `enabled=False` 的窗口

        ★ **用户原话**: "所有的定时都有着 window 属性" —— 所以第 2 步是
          **正常路径**, 不是兜底; 第 3 步才是"这个任务确实还没声明节奏"。

        ★ 为什么统一成 list: 调用方不必关心"单段还是多段", 一律遍历即可。
        """
        from module.config.availability import AvailabilityWindow, window_for_period

        w = self.window
        if isinstance(w, AvailabilityWindow):
            return (w,)
        if isinstance(w, (list, tuple)):
            got = tuple(x for x in w if isinstance(x, AvailabilityWindow))
            if got:
                return got
        # 没显式声明 -> 按周期推导
        derived = window_for_period(self.period_effective)
        if derived is not None:
            return (derived,)
        return (AvailabilityWindow(),)

    @property
    def window_effective(self):
        """第一个窗口（兼容旧调用方）。多段场景请用 `windows_effective`。"""
        return self.windows_effective[0]

    @property
    def window_describe(self) -> str:
        """人类可读的时段描述（供界面 / 日志）。多段用 ` 与 ` 连接。"""
        try:
            parts = [w.describe() for w in self.windows_effective]
            parts = [p for p in parts if p != '不限时段']
            return ' 与 '.join(parts) if parts else '不限时段'
        except Exception:
            return '不限时段'

    def in_window(self, at=None) -> bool:
        """`at`（默认现在）是否落在**任意一段**开放时段内。"""
        from datetime import datetime
        at = at or datetime.now()
        return any(w.contains(at) for w in self.windows_effective)

    def next_opening(self, at=None):
        """下一次开放时刻（多段里取**最早**的那个）。"""
        from datetime import datetime
        at = at or datetime.now()
        return min(w.next_opening(at) for w in self.windows_effective)


    @property
    def category_effective(self) -> Category:
        """**最终类别** —— `period=不限` 的**定时**任务算**固定任务**（⑥）。

        ## 用户反馈

        > "OrochiMoans 设置中, period 设置的是**不限**, 为什么还是**定时任务**呢。"

        ## ★ 规则（选项 ii）—— **只对原本 `timed` 的生效**

        | 声明类别 | `period_effective` | 最终类别 |
        |---|---|---|
        | `timed` | `NONE` | **`fixed`**（"不限"就不是定时任务）|
        | `timed` | 其它 | `timed` |
        | `toppa` / `limited` / `fixed` | 任意 | **保持声明** |

        ## 为什么**不**无条件跟随（我实测过 (i) 并回退了）

        无条件跟随会让 `RealmRaid`（**toppa 结界突破**）也变成 `fixed`
        —— 那是**类别混淆**: 结界突破是独立类别, 不该因为 `period` 而被改判。

        ★ 所以规则**限定在 `timed`**: 只有"声明为定时、但 `period` 不限"的才落到
          `fixed`。`toppa` / `limited` / `fixed` **永远保持声明**。

        ★ S5 后 `GoldYoukai` / `ExperienceYoukai` / `Tako` 从 `charge` 改判为
          `timed`（它们的 `period=NONE`）, 因此**最终也是 `fixed`** ——
          与用户此前裁定的"**period=none 时算'固定'**"一致。

        ★ 「充能（按存量在固定时刻补充）」与「固定（打满 N 次）」是**不同的
          游戏机制**, 被 `period=none` 抹平会丢语义。所以规则收窄到
          **只影响原本是 `timed` 的**（那才是用户说的"不该是定时任务"）。

        ★ 单一数据源: `cat_of` / schema / 前端**都读这里**（台账 §10.8）。
        """
        if self.category == Category.TIMED and \
                self.period_effective == Period.NONE:
            return Category.FIXED
        return self.category

    @property
    def auto_queue_effective(self) -> bool:
        """最终判定: 显式 `auto_queue` 优先, 否则按 `category` 推导。

        为什么用 `category` 而不是 `countable`:
        `TaskMeta.countable = category in COUNTABLE_CATEGORIES and bool(count_field)`,
        即 `countable` 已由 `category` 决定(前提是任务声明了 `count_field`)。
        这里只看 `category`, 避免 `TaskSpec` 反向依赖 catalog JSON。

        ⚠ 两者不一致时**以显式 `auto_queue` 为准** —— 所以批量落值时
        把真实 `countable` 写进了各 `meta.py`, 不依赖这里的推导。
        """
        if self.auto_queue is not None:
            return bool(self.auto_queue)
        return self.category not in COUNTABLE_CATEGORIES

    def __post_init__(self):
        if not self.task:
            raise ValueError('TaskSpec.task 不能为空')
        if not isinstance(self.category, Category):
            try:
                object.__setattr__(self, 'category', Category(self.category))
            except ValueError as exc:
                raise ValueError(
                    f'{self.task}: 非法 category {self.category!r}; '
                    f'应为 {[c.value for c in Category]}') from exc
        if self.list_pos is not None:
            try:
                object.__setattr__(self, 'list_pos', int(self.list_pos))
            except (TypeError, ValueError):
                object.__setattr__(self, 'list_pos', None)


# meta.py 约定的变量名。任务目录里写 `SPEC = TaskSpec(...)` 即被发现。
SPEC_VAR = 'SPEC'
# 未提供 meta.py 时的降级类别
FALLBACK_CATEGORY = Category.TIMED


def _discover_specs() -> dict:
    """
    扫描 `tasks/*/meta.py`, 收集任务自描述。

    **这是"新增任务零改动"的关键**: catalog 不再依赖一份中心化的 JSON,
    而是去每个任务目录里读它自己的声明。

    未提供 `meta.py` 的任务**不报错**, 只是不被发现(调用方会退回到
    `task_catalog_data.json` 或默认值) —— 这样渐进迁移不会导致系统不可用。
    """
    import importlib
    import inspect

    tasks_dir = Path(__file__).resolve().parent.parent.parent / 'tasks'
    if not tasks_dir.is_dir():
        return {}

    out = {}
    for d in sorted(tasks_dir.iterdir()):
        if not d.is_dir() or not (d / 'meta.py').exists():
            continue
        mod_name = f'tasks.{d.name}.meta'
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            logger.warning(f'{d.name}/meta.py 导入失败'
                           f'({type(exc).__name__}: {exc}), 已跳过')
            continue
        spec = getattr(mod, SPEC_VAR, None)
        if not isinstance(spec, TaskSpec):
            logger.warning(f'{d.name}/meta.py 缺少 {SPEC_VAR}(或类型不对), 已跳过')
            continue
        if spec.task != d.name:
            logger.warning(f'{d.name}/meta.py 的 task={spec.task!r} 与目录名不符, '
                           f'以目录名为准')
            spec = dataclasses.replace(spec, task=d.name)
        out[spec.task] = spec
    return out


def zombie_task_keys() -> set:
    """**僵尸任务**的任务目录名（存在目录, 但**缺 `meta.py`**）。

    ★ **不加 `@lru_cache`** —— 任务目录会随开发变化（新增/删除 `meta.py`）,
      缓存住会让"明明补了 meta.py 还被当僵尸"这种诡异问题出现。
      本函数只在 `Config.__init__` 的迁移里调用一次/配置, 开销可忽略。

    ## 为什么要它

    用户要求"**僵尸配置节点清理掉**"。

    实测: `tasks/OrochiMoans/` 只有 `assets.py` + `config.py` ——
    **没有 `meta.py`**（-> 没类别、没窗口）, **也没有 `script_task.py`**
    （-> 根本跑不了）。它在配置里留下的 `scheduler` 节点就是**僵尸**:
    界面上会显示成一个没有类别、永远跑不动的任务。

    ★ **只认"有目录但缺 `meta.py`"的**。资源库目录
      （`Component` / `GameUi` / `GlobalGame` / `Script` / `Utils` / `General`）
      **本来就不该有** `meta.py`, 且配置里也没有它们的 `scheduler` 节点 ——
      不能误判成僵尸（踩过这个坑的邻居: `test_task_list.py` 里把
      `OrochiMoans` / `OrochiJudgement` 记为"任务早已不存在"）。

    ## ★★ 必须排除**必需的非任务配置节点**（我第一版踩过）★★

    我第一版判据只有"有 `config.py` 但缺 `meta.py`" -> 把 **`Script`** 与
    **`GlobalGame`** 也当僵尸**删掉了**。但它们**不是任务**:
    * `module/config/config_model.py:44`: `EXTRA_GLOBAL = ('Script', 'GlobalGame')`
    * 继承 `BaseModel`（非 `ConfigBase`）, **本来就不该有 `meta.py`**
    * 删掉 -> 脚本设置 / 全局设置整块丢失

    :return: 形如 `{'OrochiMoans'}` 的**目录名**集合
    """
    out = set()
    try:
        tasks_dir = Path(__file__).resolve().parent.parent.parent / 'tasks'
        if not tasks_dir.is_dir():
            return out

        # ★ 白名单: 必需的**非任务**配置节点 / 资源库目录
        keep = {'Script', 'GlobalGame', 'Component', 'GameUi', 'Utils',
                'General', '_Template'}
        try:
            from module.config.config_model import EXTRA_GLOBAL
            keep |= set(EXTRA_GLOBAL)
        except Exception:
            pass

        for d in tasks_dir.iterdir():
            if not d.is_dir() or d.name.startswith('_'):
                continue
            if d.name in keep:
                continue                 # ★ 必需节点 -> 绝不是僵尸
            if not (d / 'config.py').exists():
                continue                 # 不是配置型任务目录
            if (d / 'meta.py').exists():
                continue                 # 有 meta -> 是正常任务
            # ★ 双保险: 它必须**查不到**（真僵尸才会有这个特征）
            if get_spec(d.name) is not None:
                continue
            out.add(d.name)
    except Exception as exc:
        logger.warning(f'zombie_task_keys 失败'
                       f'（{type(exc).__name__}: {exc}）, 返回空集')
    return out


def is_zombie_config_key(key: str) -> bool:
    """配置里的**下划线键**是否属于僵尸任务。

    例: `'orochi_moans'` -> `True`（`OrochiMoans` 缺 `meta.py`）。
    """
    z = zombie_task_keys()
    if not z:
        return False
    from module.config.config_model import convert_to_underscore
    key = str(key or '')
    for name in z:
        if convert_to_underscore(name) == key:
            return True
    return False


@lru_cache(maxsize=1)
def _load_specs() -> dict:
    return _discover_specs()


def reload_specs() -> None:
    """丢弃 meta.py 发现缓存(测试与热更新用)。"""
    _load_specs.cache_clear()


def all_specs() -> dict:
    """{任务名: TaskSpec} —— 所有**自描述**的任务。"""
    return dict(_load_specs())


def get_spec(task: str) -> TaskSpec or None:
    """取某个任务的自描述; 未提供 meta.py 时返回 None。"""
    return _load_specs().get(task)


@lru_cache(maxsize=1)
def _load() -> tuple:
    """(按任务名索引的 dict, 有序任务名列表)。首次访问时读取并缓存。"""
    if not DATA_FILE.exists():
        logger.error(f'任务目录数据缺失: {DATA_FILE}。'
                     f'请执行 `python dev_tools/gen_task_catalog.py` 生成。')
        return {}, []

    try:
        payload = json.loads(DATA_FILE.read_text(encoding='utf-8'))
    except Exception as exc:
        logger.error(f'任务目录数据解析失败({type(exc).__name__}: {exc}): {DATA_FILE}')
        return {}, []

    rows = payload.get('tasks') if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        logger.error(f'任务目录数据格式异常(期望 list): {DATA_FILE}')
        return {}, []

    index = {}
    for r in rows:
        try:
            cat = Category(r.get('category') or Category.TIMED.value)
        except ValueError:
            cat = Category.TIMED

        def _int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        meta = TaskMeta(
            task=r['task'],
            name_zh=r.get('name_zh') or r['task'],
            category=cat,
            count_field=r.get('count_field'),
            count_default=_int(r.get('count_default')),
            needs_unify=bool(r.get('needs_unify')),
            has_limit_time=bool(r.get('has_limit_time')),
            success_interval=r.get('success_interval'),
        )
        index[meta.task] = meta

    # ---- 合并 `tasks/*/meta.py` 的任务自描述 ----
    #
    # 自描述**优先**: 它是任务自己声明的, 比中心化 JSON 权威。
    # 同时把"只在 meta.py 里、JSON 里没有"的任务也纳入 —— 这正是
    # "新增任务零改动"的落地点: 写一个 meta.py 就能被系统发现。
    for task, spec in _load_specs().items():
        base = index.get(task)
        if base is None:
            # 全新任务(尚未进入 JSON) —— 用自描述构造 TaskMeta
            base = TaskMeta(
                task=task,
                name_zh=spec.name_zh or task,
                category=spec.category,
                count_field=None,
                count_default=None,
                needs_unify=False,
                has_limit_time=False,
                success_interval=None,
            )
        else:
            # 已存在: 自描述覆盖"名称 + 类别"这两项权威信息,
            # 其余(次数字段/充能参数等)仍取自 JSON, 直到该任务也把
            # resource 写进 meta.py。
            base = dataclasses.replace(
                base,
                name_zh=spec.name_zh or base.name_zh,
                category=spec.category,
            )
        index[task] = base

    return index, sorted(index.keys())


def reload() -> None:
    """丢弃缓存, 强制重新读盘(测试与热更新用)。"""
    _load.cache_clear()


def all_tasks() -> list:
    """全部任务名(按目录名排序)。"""
    return list(_load()[1])


def all_meta() -> list:
    """全部 TaskMeta(按目录名排序)。"""
    index, order = _load()
    return [index[t] for t in order]


def get(task: str) -> TaskMeta or None:
    """按任务名取元数据; 不存在返回 None。"""
    if not task:
        return None
    index, _ = _load()
    meta = index.get(task)
    if meta is not None:
        return meta
    # 容错: 允许传下划线形式或全小写
    lowered = str(task).lower()
    for k, v in index.items():
        if k.lower() == lowered or k.lower() == lowered.replace('_', ''):
            return v
    return None


def exists(task: str) -> bool:
    index, _ = _load()
    return bool(task) and (task in index or any(
        k.lower() == str(task).lower() for k in index))


def by_category(*categories) -> list:
    """按类别筛选。可传多个 Category 或字符串。"""
    wanted = set()
    for c in categories:
        try:
            wanted.add(c if isinstance(c, Category) else Category(c))
        except ValueError:
            continue
    return [m for m in all_meta() if m.category in wanted]


def countable_tasks() -> list:
    """所有可设"目标次数"的任务(固定任务 + 结界突破)。"""
    return [m for m in all_meta() if m.countable]


def all_names() -> dict:
    """{任务名: 中文名}。"""
    return {m.task: m.display_name for m in all_meta()}


def target_field(task: str) -> str or None:
    """
    取该任务"目标次数"应使用的**统一字段名**; 不可设次数则返回 None。

    这是本模块最重要的接口 —— 上层只需调它, 不必知道 minions_cnt 之类的别名。
    """
    meta = get(task)
    return meta.count_field_effective if meta else None


def needs_unify_tasks() -> list:
    """尚未统一的次数字段(供迁移/排障使用)。"""
    return [m for m in all_meta() if m.needs_unify]


def summary() -> dict:
    """类别分布统计(供 API/界面使用)。返回形如 {'fixed': 13, ..., 'total': 54}。"""
    out = {c.value: 0 for c in Category}
    for m in all_meta():
        out[m.category.value] += 1
    out['total'] = sum(out[c.value] for c in Category)
    return out
