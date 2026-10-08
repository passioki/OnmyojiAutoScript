# -*- coding: utf-8 -*-
"""任务知识接口 —— 让前端**不再内置任务知识**。

## 为什么要这样

设计原则是"前端不内置任务知识, 全部从接口拉"(见 `docs/architecture.md` §7.2)。
否则每加一个任务、每改一个类别, 都要同步改前端, 又变成"同一知识多处"。

本模块提供两个接口:

* `GET /{script_name}/schema`
    任务的**静态元数据**: 中文名、类别、资源规则(能跑几次/怎么补充)、
    可配的次数字段、开放时段字段。
    **与账号无关** —— 同一份 schema 对所有配置都成立, 因此结果可缓存。

* `GET /{script_name}/overview`
    **动态运行态**: 每个任务现在能不能跑、为什么不能跑、下次什么时候能跑、
    本周期是否已完成、是否在开放时段内。
    这是界面"总览页"需要的全部信息, 一次取全(避免每行一个请求)。

## 与既有接口的关系

* `GET /{script_name}/task_status` —— 已有的状态接口(调度器时间 + 完成记忆 +
  次数 + 队友)。`overview` 与它**互补**: `task_status` 偏"状态明细",
  `overview` 偏"现在该不该跑 + 为什么", 且带静态元数据。
* `GET /{script_name}/{task}/args` —— 单个任务的完整 pydantic schema。

本模块**不改动**既有接口, 纯新增。
"""
from datetime import datetime

from fastapi import APIRouter

from module.logger import logger

schema_app = APIRouter()


# --------------------------------------------------------------------------- 静态 schema
def build_schema(config_name: str = '') -> dict:
    """
    构造任务静态元数据。

    数据来源: `module/config/task_catalog`(它以 `tasks/<Name>/meta.py` 为权威)。
    **不重复定义任何知识** —— 这里只是把已有的 catalog 转成 JSON。
    """
    from module.config import task_catalog as TC

    tasks = {}
    for meta in TC.all_meta():
        spec = TC.get_spec(meta.task)
        resource = getattr(spec, 'resource', None) if spec else None

        item = {
            'name': meta.task,
            'name_zh': meta.name_zh or meta.task,
            'category': meta.category.value,
            'category_label': TC.CATEGORY_LABEL.get(meta.category, ''),
            # 界面是否显示"目标次数"输入框
            'countable': meta.countable,
            'count_field': meta.count_field_effective,
            'count_default': meta.count_default,
            # 需要的平台能力(跨平台用; 见 docs/architecture.md §7.4)
            'requires': list(getattr(spec, 'requires', ()) or ()),
            # 任务列表里的**默认位置**。None = 未编排(排最后)。
            # 用户拖拽后写入 Script.optimization.task_order 覆盖它。
            'list_pos': getattr(spec, 'list_pos', None) if spec else None,
        }

        if resource is not None:
            item['resource'] = {
                'capacity': resource.capacity,
                'consume': resource.consume,
                'refill': resource.refill,
                'period': resource.period.value,
                'amount': resource.amount,
                'refill_to_full': resource.recharge.refill_to_full,
                'interval': list(resource.interval),
                'slots': [f'{h:02d}:{m:02d}' for h, m in resource.slots],
                'describe': resource.describe(),
                # 开放时段由用户配置, 默认关闭; 这里只暴露"有这个能力"
                'window_supported': True,
            }
        tasks[meta.task] = item

    return {
        'source': 'tasks/<Name>/meta.py',
        'count': len(tasks),
        'categories': [
            {'value': c.value,
             'label': TC.CATEGORY_LABEL.get(c, ''),
             'countable': c in TC.COUNTABLE_CATEGORIES}
            for c in TC.Category
        ],
        # 次数字段的统一名(界面只需认这一个)
        'unified_count_field': TC.UNIFIED_COUNT_FIELD,
        # 开放时段的可配字段(界面据此渲染表单, 不必硬编码字段名)
        'window_fields': [
            {'name': 'window_enable', 'type': 'bool', 'default': False,
             'label': '启用开放时段'},
            {'name': 'window_start', 'type': 'time', 'default': '17:00',
             'label': '开放开始'},
            {'name': 'window_end', 'type': 'time', 'default': '23:00',
             'label': '开放结束'},
            {'name': 'window_days', 'type': 'str', 'default': '0,1,2,3,4,5,6',
             'label': '开放星期(周一=0)'},
        ],
        # 任务列表: 列表就是**调度器的一种模式**, 不是新子系统
        # (见 docs/architecture.md §5)。
        'list': _list_meta(),
        'tasks': tasks,
    }


def _list_meta() -> dict:
    """
    任务列表的元信息(供界面渲染排序控件)。

    顺序来源分两级:
      1. `Script.optimization.task_order` —— **用户编排**(逗号分隔任务名)
      2. 各任务 `meta.py` 的 `list_pos` —— 内置默认顺序

    只改 pending(已到点)任务的先后; 没到点的任务本来就不参与。
    """
    from tasks.Script.config_optimization import ScheduleRule
    return {
        # 列表模式的取值(界面把它填进 Script.optimization.schedule_rule)
        'mode_value': ScheduleRule.LIST.value,
        'modes': [
            {'value': ScheduleRule.FILTER.value, 'label': '过滤器(内置默认顺序)'},
            {'value': ScheduleRule.FIFO.value, 'label': '定时优先(先到点先跑)'},
            {'value': ScheduleRule.PRIORITY.value, 'label': '优先级'},
            {'value': ScheduleRule.LIST.value, 'label': '列表优先(自定义顺序)'},
        ],
        # 用户编排写入的字段(界面据此 PUT)
        'order_field': 'task_order',
        'order_group': 'script.optimization',
        'note': '顺序只影响已到点任务的先后; 未编排的任务排最后',
    }


# --------------------------------------------------------------------------- 动态总览
def build_overview(config_name: str) -> dict:
    """
    构造运行态总览。

    对每个任务给出: 现在能不能跑 / 为什么不能 / 下次什么时候 /
    本周期是否已完成 / 是否在开放时段内。
    """
    from module.config import task_catalog as TC
    from module.server.main_manager import mm

    config = mm.config_cache(config_name)
    now = datetime.now()

    try:
        config.update_scheduler()
    except Exception as exc:
        logger.warning(f'overview: update_scheduler 失败: {exc}')

    # 当前在哪个桶里(pending=可跑 / waiting=等待)
    slot_of = {}
    for bucket, attr in (('pending', 'pending_task'), ('waiting', 'waiting_task')):
        for f in getattr(config, attr, None) or []:
            cmd = getattr(f, 'command', None)
            if cmd:
                slot_of[cmd] = bucket

    model_dump = config.model.model_dump()
    rows = []
    runnable = 0

    # 充能类任务的存量(如金币妖怪 1/2) —— 从状态文件一次取全, 避免逐任务查询
    #
    # ⚠ `task_state.summarize()` 返回的键是**压缩小写**形式(如
    #   `experienceyoukai`), 而 model_dump 的键是**下划线**形式
    #   (`experience_youkai`)。两者不通用, 需归一化后再查(踩过:
    #   直接查会全部拿不到, 但不会报错, 只是静默为空)。
    charges_raw = {}
    try:
        from module.config import task_state
        summary = task_state.summarize(config_name, now=now)
        charges_raw = summary.get('charges') or {}
    except Exception as exc:
        logger.warning(f'overview: 充能状态获取失败({type(exc).__name__}: {exc})')

    def _norm(k: str) -> str:
        return str(k or '').lower().replace('_', '')

    charges = {_norm(k): v for k, v in charges_raw.items()}

    for key, value in model_dump.items():
        if not isinstance(value, dict):
            continue
        sch = value.get('scheduler')
        if not isinstance(sch, dict):
            continue

        meta = TC.get_by_key(key) if hasattr(TC, 'get_by_key') else None
        if meta is None:
            # 由下划线键还原任务名
            command = ''.join(p.capitalize() for p in key.split('_'))
            meta = TC.get(command)
        command = meta.task if meta else \
            ''.join(p.capitalize() for p in key.split('_'))

        func = None
        for f in (getattr(config, 'pending_task', None) or []) + \
                 (getattr(config, 'waiting_task', None) or []):
            if getattr(f, 'command', None) == command:
                func = f
                break

        in_window = True
        window_reason = None
        if func is not None:
            try:
                in_window = func.in_window(now)
                window_reason = func.window_reason
            except Exception:
                pass

        enabled = bool(sch.get('enable'))
        slot = slot_of.get(command, '')
        can_run = enabled and slot == 'pending'
        if can_run:
            runnable += 1

        period = sch.get('period')
        rows.append({
            'name': key,
            'command': command,
            'name_zh': (meta.name_zh if meta else '') or command,
            'category': meta.category.value if meta else 'timed',
            # 类别的中文标签 —— 界面不必自己维护一份映射
            'category_label': TC.CATEGORY_LABEL.get(meta.category, '')
                if meta else '',
            'enable': enabled,
            'priority': sch.get('priority'),
            'next_run': str(sch.get('next_run') or ''),
            'snapshot': str(sch.get('last_run') or ''),
            'period': getattr(period, 'value', period) or 'none',
            'slot': slot,
            # 现在能不能跑
            'can_run': can_run,
            # 不能跑的原因(界面可直接显示)
            'reason': window_reason
                or ('' if can_run else ('未启用' if not enabled else '等待到点')),
            'in_window': in_window,
            'countable': bool(meta.countable) if meta else False,
            'count': value.get('limit_count') if meta and meta.countable else None,
            # ---- 界面渲染需要的补充字段(避免前端再发一次请求) ----
            # 充能类任务的"存量 x / 上限 y"(如金币妖怪 1/2)
            'charges': charges.get(_norm(key)),
            # 列表里的位置(来自 meta.py 的 TaskSpec); 用户编排在 task_order
            # ⚠ `list_pos` 在 **TaskSpec** 上, 不在 TaskMeta 上 ——
            #   用 `getattr(meta, ...)` 会静默拿到 None(踩过)。
            'list_pos': _spec_list_pos(meta),
            'in_list': _spec_list_pos(meta) is not None,
            # 该任务的效果说明(供界面展示"这个任务是干什么的")
            'resource_describe': _resource_describe(meta),
        })

    # 按 可跑 -> 优先级 -> 名称 排序, 便于界面直接渲染
    rows.sort(key=lambda r: (not r['can_run'], r['priority'] or 99, r['name']))

    return {
        'config': config_name,
        'at': now.strftime('%Y-%m-%d %H:%M:%S'),
        'runnable': runnable,
        'total': len(rows),
        'tasks': rows,
        'teams': _team_snapshot(config_name, now),
    }


def _spec_of(meta):
    """取任务的 `TaskSpec`(在 `tasks/<Name>/meta.py` 里声明的那个)。"""
    if meta is None:
        return None
    try:
        from module.config import task_catalog as TC
        return TC.get_spec(meta.task)
    except Exception:
        return None


def _spec_list_pos(meta):
    """
    任务在列表里的**默认位置**。

    ⚠ 这个字段在 `TaskSpec` 上, 而**不在** `TaskMeta` 上。
    写成 `getattr(meta, 'list_pos', None)` 会静默返回 None(踩过 ——
    表现是"所有任务的 list_pos 都是 None", 很难发现)。
    """
    spec = _spec_of(meta)
    return getattr(spec, 'list_pos', None) if spec else None


def _resource_describe(meta) -> str:
    """
    任务资源规则的可读描述(如 "每天 00:00、12:00"、"每 3 小时")。

    数据来自 `tasks/<Name>/meta.py` 的 `TaskSpec.resource`;
    这里只做转发, **不重复定义知识**。
    """
    spec = _spec_of(meta)
    res = getattr(spec, 'resource', None) if spec else None
    try:
        return res.describe() if res is not None else ''
    except Exception:
        return ''


def _team_snapshot(config_name: str, now: datetime) -> list:
    """队友状态(组队协同用)。失败时返回空表, 不影响总览。"""
    try:
        from module.config import task_state
        return task_state.peers_status(config_name, now=now)
    except Exception as exc:
        logger.warning(f'overview: 队友状态获取失败: {exc}')
        return []


# --------------------------------------------------------------------------- 路由
@schema_app.get('/{script_name}/schema')
async def script_schema(script_name: str):
    """
    任务静态元数据(中文名 / 类别 / 资源规则 / 可配字段)。

    前端据此渲染任务列表与表单, **无需内置任务知识**。
    """
    try:
        return build_schema(script_name)
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'tasks': {}}


# --------------------------------------------------------------------------- 平台能力
@schema_app.get('/capabilities')
async def get_capabilities():
    """
    当前平台的设备能力(跨平台用)。

    为什么要暴露: 有些功能在非 Windows 上**根本不存在**
    (窗口消息点击、后台截图、模拟器管理都依赖 Windows API)。
    此前是靠散落的 `if IS_WINDOWS` 判断, 且 `emulator.py` 顶层硬
    `import winreg` —— 在 Linux/macOS 上**直接崩**。

    现在前端可据此**明确禁用**相关控件, 而不是让用户点了没反应。
    """
    try:
        from module.device.capabilities import (ALL_CAPABILITIES,
                                                CAPABILITY_LABEL,
                                                capabilities, platform_name,
                                                startup_report)
        caps = capabilities()
        return {
            'platform': platform_name(),
            'report': startup_report(),
            'capabilities': [
                {'name': n,
                 'label': CAPABILITY_LABEL.get(n, n),
                 'available': caps.has(n)}
                for n in ALL_CAPABILITIES
            ],
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'platform': 'unknown', 'capabilities': []}


# --------------------------------------------------------------------------- 运行控制
@schema_app.get('/{script_name}/run_control')
async def get_run_control(script_name: str):
    """
    当前运行控制状态(暂停 / 休息 / 延后)。

    返回: {paused, pause_mode, pause_mode_label, rest_until, rest_remaining,
           delayed, list_resume_at, list_remaining, can_run}
    """
    try:
        from module.config import run_control
        return run_control.state()
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'can_run': True}


@schema_app.put('/{script_name}/run_control/pause')
async def put_pause(script_name: str, mode: str = 'battle', reason: str = ''):
    """
    **暂停**调度。

    :param mode: `battle`(默认, ⏸ 跑完当前这场战斗) 或 `round`(⏭ 本轮跑完再停)
    :param reason: 可选备注(便于排障: 谁在什么时候暂停的)

    ⚠ 语义: 立即置位, 但脚本会在**安全点**(战斗 + 结算 + 领奖完成)才停 ——
    这样不会卡在半途(战斗中 / 组队房间中)。**不提供"立即停"**: 不安全。
    """
    try:
        from module.config import run_control
        if mode not in (run_control.PAUSE_BATTLE, run_control.PAUSE_ROUND):
            return {'error': f'非法 mode: {mode!r}; 应为 battle / round'}
        return run_control.request_pause(mode=mode, reason=reason)
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.put('/{script_name}/run_control/resume')
async def put_resume(script_name: str):
    """**继续**调度(解除暂停)。"""
    try:
        from module.config import run_control
        return run_control.resume()
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.put('/{script_name}/run_control/rest')
async def put_rest(script_name: str, minutes: int = 0):
    """
    **休息**: 全局暂停 N 分钟(定时任务也不跑)。`minutes=0` 取消。

    与"延后"的区别: 休息影响**所有**任务; 延后只推迟**列表**推进。
    """
    try:
        from module.config import run_control
        return run_control.rest(minutes=minutes)
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.put('/{script_name}/run_control/delay')
async def put_delay(script_name: str, minutes: int = 0):
    """
    **延后**: 只推迟**列表**推进 N 分钟(定时任务照常)。`minutes=0` 取消。
    """
    try:
        from module.config import run_control
        return run_control.delay(minutes=minutes)
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.get('/{script_name}/overview')
async def script_overview(script_name: str):
    """
    运行态总览: 每个任务现在能不能跑 / 为什么不能 / 下次什么时候。

    这是"总览页"的单一数据源 —— 一次取全, 避免每行一个请求。
    """
    try:
        return build_overview(script_name)
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'tasks': []}
