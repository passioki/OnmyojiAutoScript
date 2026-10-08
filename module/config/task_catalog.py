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

from module.logger import logger

DATA_FILE = Path(__file__).with_name('task_catalog_data.json')

# 统一后的"目标次数"字段名。所有固定任务最终都应暴露这个名字。
UNIFIED_COUNT_FIELD = 'limit_count'


class Category(str, Enum):
    """任务类别。

    划分依据是**游戏机制**, 不是 OAS 的内部实现:

    FIXED    固定任务 —— 有"打满 N 次"的语义, 可设目标次数
    CHARGE   充能任务 —— 按存量, 在固定时刻补充(如金币妖怪 0/12 点各 1 次)
    TOPPA    结界突破 —— 两个子分类(寮突破 / 个人突破), 定点开放 + 次数上限
    LIMITED  限时活动 —— 隔一段时间才推出, 非常驻
    TIMED    定时任务 —— 其余按周期调度的任务
    """

    FIXED = 'fixed'
    CHARGE = 'charge'
    TOPPA = 'toppa'
    LIMITED = 'limited'
    TIMED = 'timed'


# 有"目标次数"语义的类别(可展示/修改次数)
COUNTABLE_CATEGORIES = (Category.FIXED, Category.TOPPA)

# 类别中文名(界面用)
CATEGORY_LABEL = {
    Category.FIXED: '固定任务',
    Category.CHARGE: '充能任务',
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
    has_charge: bool
    charge_max: int or None
    charge_slots: str or None       # 如 '0,12'
    charge_consume: int or None
    has_limit_time: bool
    success_interval: str or None   # 充能周期原文, 如 '00 03:00:00'

    # ---- 便捷属性 ----
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
    resource: object = None          # Resource; 用 object 避免循环 import
    requires: tuple = ()
    note: str = ''

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
            has_charge=bool(r.get('has_charge')),
            charge_max=_int(r.get('charge_max')),
            charge_slots=r.get('charge_slots'),
            charge_consume=_int(r.get('charge_consume')),
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
                has_charge=False,
                charge_max=None,
                charge_slots=None,
                charge_consume=None,
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
