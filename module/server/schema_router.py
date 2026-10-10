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

from fastapi import APIRouter, Body

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
        'list': _list_meta(config_name),
        'tasks': tasks,
    }


def _list_meta(config_name: str = '') -> dict:
    """
    任务列表的元信息(供界面渲染排序控件)。

    ## 列表 = **固定任务 + 休息**（有序条目）

    条目只有两种 —— 按**行为**命名:

        task   跑一个**固定任务**
        rest   **休息** —— 去**庭院**待着 N 分钟

    ## ★ 为什么定时任务不在列表里

    定时任务有它自己的 window / 存量 / 周期, "放进列表按顺序执行" 与那些
    机制冲突。所以**固定与定时分开管理**:

    | 谁来管 | 内容 | 排序依据 |
    |---|---|---|
    | **运行列表** | 固定任务 + 休息 | 用户拖拽的顺序 |
    | **定时调度器** | timed / charge / limited | window、剩余时间、预计耗时、自定义优先级 |

    见 `docs/architecture.md` §5.4 与 `module/config/timed_schedule.py`。
    """
    from tasks.Script.config_optimization import ScheduleRule, TimedPriority

    try:
        from module.config.run_list import (DURATION_CHOICES, EntryKind,
                                            KIND_HELP, KIND_LABEL)
        kinds = [
            {'value': k.value,
             'label': KIND_LABEL[k],
             'help': KIND_HELP[k],
             # 该条目是否需要 minutes(界面据此决定显示时长选择器还是任务选择器)
             'needs_minutes': k != EntryKind.TASK,
             'needs_task': k == EntryKind.TASK,
             'blocks_list': k != EntryKind.TASK,
             }
            for k in EntryKind
        ]
        durations = list(DURATION_CHOICES)
    except Exception:
        kinds, durations = [], []

    return {
        # 列表模式的取值(界面把它填进 Script.optimization.schedule_rule)
        'mode_value': ScheduleRule.LIST.value,
        'modes': [
            {'value': ScheduleRule.FILTER.value, 'label': '过滤器(内置默认顺序)'},
            {'value': ScheduleRule.FIFO.value, 'label': '定时优先(先到点先跑)'},
            {'value': ScheduleRule.PRIORITY.value, 'label': '优先级'},
            {'value': ScheduleRule.LIST.value, 'label': '列表优先(自定义顺序)'},
        ],
        # 用户编排写入的字段
        'order_field': 'run_list',
        'order_group': 'script.optimization',
        # 当前的调度模式 —— ★ 界面**不能硬编码**默认值, 否则会显示成
        # "顺序不生效"的样子(实际用户早就设成 List 了)
        'current_mode': _current_schedule_rule(config_name),
        # 条目类型(界面据此渲染"添加条目"选择器)
        'entry_kinds': kinds,
        'duration_choices': durations,
        # 当前用户编排(原始数组; 空表示未编排)
        'entries': _current_run_list(config_name),
        'note': ('task 条目**不阻塞**列表(未就绪就跳过); '
                 'rest 条目**阻塞**列表, 生效后自动移除'),
        # 全局开关 —— 界面直接渲染, 不必知道字段名
        'global_fields': _global_fields(config_name),
        # 运行记录汇总（次数 + 耗时），供总览页与列表页展示。
        # 与 `/run_record` 端点同一份数据 —— 放这里是为了让"进页面"只发
        # 一次请求；需要归档明细时才去调那个端点。
        'run_record': _run_record_summary(config_name),
        # 「运行一次」当前队列 —— 界面据此显示"排队中"与取消按钮
        'manual_run': _manual_run_summary(config_name),
        # 失败冷却 —— 界面据此显示"哪些任务在冷却"与"清除失败"
        'failure_state': _failure_summary(config_name),
    }


def _failure_summary(config_name: str = '') -> dict:
    """失败冷却摘要（**失败返回空**, 不影响页面）。"""
    if not config_name:
        return {}
    try:
        from module.config import failure_state
        return failure_state.summarize(config_name)
    except Exception as exc:
        logger.warning(f'失败状态读取失败({type(exc).__name__}: {exc}), 忽略')
        return {}


def _manual_run_summary(config_name: str = '') -> dict:
    """「运行一次」队列摘要（**失败返回空**, 不影响页面）。"""
    if not config_name:
        return {'tasks': [], 'count': 0}
    try:
        from module.config import manual_run
        return manual_run.summarize(config_name)
    except Exception as exc:
        logger.warning(f'运行一次队列读取失败({type(exc).__name__}: {exc}), 忽略')
        return {'tasks': [], 'count': 0}


def _run_record_summary(config_name: str = '') -> dict:
    """
    运行记录汇总（**失败返回空 dict**, 不影响页面其它部分）。

    统计只是报表 —— 它坏了不该让整个配置页打不开。
    """
    if not config_name:
        return {}
    try:
        from module.config import run_record

        summary = run_record.summarize(config_name)
        for row in summary.values():
            row['seconds_text'] = run_record.format_duration(row['seconds'])
        return summary
    except Exception as exc:
        logger.warning(f'运行记录汇总失败({type(exc).__name__}: {exc}), 忽略')
        return {}


def _config_of(config_name: str):
    """
    按**脚本名**取配置。

    ⚠ 不要用 `mm.config_cache_list()[0]` —— 那会读到**另一个账号**的配置。
      (踩过: 第一版就是这样, 结果是"current"字段永远为空或串号。)
    """
    if not config_name:
        return None
    try:
        from module.server.main_manager import mm
        return mm.config_cache(config_name)
    except Exception:
        return None


def _opt_value(config_name: str, field: str, default=None):
    """
    读 `Script.optimization.<field>` 的**当前值**。

    ★ 枚举必须取 `.value` —— 直接 `str(枚举)` 会得到
      `'WhenTaskQueueEmpty.GOTO_MAIN'`（枚举名）而不是 `'goto_main'`,
      前端拿去比对会永远不匹配。(踩过。)
    """
    config = _config_of(config_name)
    if config is None:
        return default
    try:
        v = getattr(config.model.script.optimization, field, None)
    except Exception:
        return default
    if v is None:
        return default
    return getattr(v, 'value', v)


def _global_fields(config_name: str = '') -> dict:
    """
    `Script.optimization` 里值得放到「全局设置」面板的字段。

    ★ **不给假字段**: 原型里画了"跑完循环整表", 但后端没有这个字段。
      造一个假的会**静默失效**（`script_set_arg` 返回 False 并记 error,
      界面看不出来）。所以这里只暴露后端真实支持的字段。

    ## 字段分组

    | 组 | 字段 |
    |---|---|
    | **总开关** | `enable_fixed` / `enable_timed` |
    | **两者关系** | `timed_priority` / `rest_interleave` |
    | **杂项** | `when_task_queue_empty` |
    """
    from tasks.Script.config_optimization import (TimedPriority,
                                                  WhenTaskQueueEmpty)

    priority_labels = {
        TimedPriority.TIMED.value: '定时优先（打完当前这场就让位）',
        TimedPriority.LIST.value: '列表优先（等固定任务跑完）',
    }
    queue_labels = {
        WhenTaskQueueEmpty.GOTO_MAIN.value: '回庭院待命',
        WhenTaskQueueEmpty.CLOSE_GAME.value: '关闭游戏',
    }

    return {
        # ---- 两个总开关 ----
        'enable_fixed': {
            'group': 'script.optimization', 'field': 'enable_fixed',
            'type': 'boolean', 'label': '启用固定任务',
            'current': bool(_opt_value(config_name, 'enable_fixed', True)),
            'help': '固定任务 = 有"打满 N 次"语义的, 由运行列表管',
        },
        'enable_timed': {
            'group': 'script.optimization', 'field': 'enable_timed',
            'type': 'boolean', 'label': '启用定时任务',
            'current': bool(_opt_value(config_name, 'enable_timed', True)),
            'help': '定时任务 = 有开放时段/存量的, 由定时调度器管',
        },
        # ---- 两者关系 ----
        'timed_priority': {
            'group': 'script.optimization', 'field': 'timed_priority',
            'type': 'string', 'label': '定时任务优先级',
            'current': str(_opt_value(config_name, 'timed_priority',
                                      TimedPriority.TIMED.value)),
            'choices': [
                {'value': k.value, 'label': priority_labels.get(k.value, k.value)}
                for k in TimedPriority
            ],
            'help': '定时任务到点时, 固定任务要不要在**战斗边界**让位',
        },
        'rest_interleave': {
            'group': 'script.optimization', 'field': 'rest_interleave',
            'type': 'boolean', 'label': '休息时可穿插定时任务',
            'current': bool(_opt_value(config_name, 'rest_interleave', False)),
            'help': '判据: 定时任务的预期完成时间 < 休息剩余时间。'
                    '用于保护组队任务（避免在庭院干等）。'
                    '默认关 —— 因为"预期完成时间"没配(为 0)时不能瞎比。',
        },
        # ---- 杂项 ----
        'when_task_queue_empty': {
            'group': 'script.optimization',
            'field': 'when_task_queue_empty',
            'type': 'string',
            'label': '队列跑空后',
            'current': str(_opt_value(config_name, 'when_task_queue_empty',
                                      WhenTaskQueueEmpty.GOTO_MAIN.value)),
            'choices': [
                {'value': k.value, 'label': queue_labels.get(k.value, k.value)}
                for k in WhenTaskQueueEmpty
            ],
        },
    }


def _current_run_list(config_name: str = '') -> list:
    """读**指定配置**的 `run_list`。"""
    config = _config_of(config_name)
    if config is None:
        return []
    try:
        return list(getattr(config.model.script.optimization,
                            'run_list', []) or [])
    except Exception:
        return []


def _current_schedule_rule(config_name: str = '') -> str:
    """读**指定配置**的调度模式。取不到时给 `Filter`(后端的默认值)。"""
    from tasks.Script.config_optimization import ScheduleRule
    config = _config_of(config_name)
    if config is not None:
        try:
            v = getattr(config.model.script.optimization,
                        'schedule_rule', None)
            if v is not None:
                return str(getattr(v, 'value', v))
        except Exception:
            pass
    return ScheduleRule.FILTER.value


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

    # ★ 队列成员（用户编排 + 自动进队列）—— 一次算好, 循环里查集合即可。
    #
    #   为什么用 `queued_commands()` 而不是逐个任务判断:
    #   它内部要把 `run_list` 解析 + 补齐自动任务, 逐个判断会重复做 N 次。
    try:
        queued_commands = config.queued_commands()
    except Exception as exc:
        logger.warning(f'overview: 队列成员获取失败({type(exc).__name__}: {exc})')
        queued_commands = set()

    for key, value in model_dump.items():
        if not isinstance(value, dict):
            continue
        sch = value.get('scheduler')
        if not isinstance(sch, dict):
            continue

        meta = _meta_of_key(key)
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
            # 类别的中文标签 —— 界面不必自己维护一份映射。
            #
            # ★ 元数据缺失的任务(如尚未写 `meta.py` 的)也要给出标签,
            #   否则界面会出现"类型"列为空的行。用 FALLBACK_CATEGORY 兜底。
            'category_label': TC.CATEGORY_LABEL.get(
                meta.category if meta else TC.FALLBACK_CATEGORY, ''),
            'enable': enabled,
            'priority': sch.get('priority'),
            # ★ 预期完成时间（分钟）—— "休息时可穿插"的判据输入，
            #   也是界面上要让用户可编辑的字段。
            'expected_minutes': sch.get('expected_minutes', 0),
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
            # ★★ **用户编排的次数**（`scheduler.target`）★★
            #
            # ⚠ 这个字段**之前漏了** —— 界面上"次数"输入框读它, 于是**永远显示 0
            #   （= "默认"）**, 用户改了也看不到, 看起来像"接错了字段"。
            #
            #   与另外两个的区别必须分清:
            #
            #   | 字段 | 含义 |
            #   |---|---|
            #   | `target` | **用户设的**（0 = 用默认值）—— 界面**编辑**的就是它 |
            #   | `count` | 任务配置里的**能力默认值**（`limit_count` 等）|
            #   | `effective_target` | **本次真正会用**的（target > count > meta 默认）|
            'target': sch.get('target', 0),
            # ★ `count` = **任务配置里的值**（不一定是根层的 `limit_count` ——
            #   各任务把它放在不同层级: `orochi_config.limit_count` 等）。
            #   曾经这里写 `value.get('limit_count')`, 于是**所有任务都返回 None**
            #   （因为值嵌套在子 dict 里）—— 界面上就看不到默认次数。
            #   现在用与 `effective_target` 同一套遍历。
            'count': _count_from_value(meta, value),
            # ★ **实际生效的次数**: 三级回落（`scheduler.target` > 任务配置 > 默认）。
            #
            #   界面上该显示的是**真正会用的那个** —— 否则用户改了 `target`
            #   却看到旧数字, 会以为没生效。
            #   见 `tasks/base_task.py` 的 `effective_target()`。
            'effective_target': _effective_target_of(meta, sch, value),
            # ---- 界面渲染需要的补充字段(避免前端再发一次请求) ----
            # 充能类任务的"存量 x / 上限 y"(如金币妖怪 1/2)
            'charges': charges.get(_norm(key)),
            # 列表里的位置(来自 meta.py 的 TaskSpec); 用户编排在 task_order
            # ⚠ `list_pos` 在 **TaskSpec** 上, 不在 TaskMeta 上 ——
            #   用 `getattr(meta, ...)` 会静默拿到 None(踩过)。
            'list_pos': _spec_list_pos(meta),
            'in_list': _spec_list_pos(meta) is not None,
            # ---- ★ 执行队列的三个判定字段（用户确认的分类模型）----
            #
            # | 字段 | 含义 |
            # |---|---|
            # | `auto_queue` | **是否自动进队列**（任务类别属性, 来自 meta.py）|
            # | `queued`     | **当前是否在队列里**（= 用户编排了 OR 自动进队列）|
            # | `category`   | 类别（界面分组用）|
            #
            # 前端的四类分区就是靠它们:
            #
            #   正在运行  <- WebSocket `runningTask`
            #   待运行    <- `queued == True`（可拖）
            #   启用但不运行 <- `enable && !queued`（**只在【添加任务】里出现**）
            #   未启用    <- `enable == False`
            'auto_queue': _auto_queue_of(meta),
            'queued': command in queued_commands,
            # 该任务的效果说明(供界面展示"这个任务是干什么的")
            'resource_describe': _resource_describe(meta),
            # ---- 连续失败冷却（见 `module/config/failure_state.py`）----
            # 到阈值时不再 `exit(1)`, 而是给该任务加冷却。界面上要让用户
            # **看见**并**能清除**（修好之后不想等 1 小时）。
            **_failure_fields(config_name, command, now),
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


def _count_from_value(meta, value: dict):
    """
    任务配置里的次数（**按字段名遍历嵌套 dict**）。

    ★ 这里曾经是 `value.get('limit_count')` —— 于是**所有任务都返回 None**,
      因为值嵌套在子 dict 里（`orochi_config.limit_count` /
      `bondling_config.limit_count` / …）。界面上就看不到默认次数。

    ★★ 两个字段名都要试 ★★

    各任务的字段名不统一, 而且 `meta` 上正好有**两个**:

    | meta 字段 | 值 | 例子 |
    |---|---|---|
    | `count_field` | 任务**实际用的**字段名 | `number_attack` / `minions_cnt` / `hya_limit_count` |
    | `count_field_effective` | **归一化后**的名字 | `limit_count` |

    只查归一化名会漏掉那三个用别名的任务
    （`RealmRaid` / `Exploration` / `Hyakkiyakou` —— 实测 `count` 全为 `None`）。
    所以**先查实际名, 再查归一化名**。
    """
    if meta is None or not meta.countable:
        return None
    for field in (getattr(meta, 'count_field', None),
                  getattr(meta, 'count_field_effective', None)):
        if not field:
            continue
        v = _find_in_mapping(value, field)
        if isinstance(v, int):
            return v
    return None


def _failure_fields(config_name: str, command: str, now=None) -> dict:
    """
    连续失败 / 冷却字段（供界面显示铭牌与"清除失败"）。

    ★ 读不到就给"正常"值 —— 失败记录坏了不该让任务列表打不开。

    见 `module/config/failure_state.py`: 到阈值时不再 `exit(1)`，
    而是给该任务加冷却。界面上要让用户**看见**并**能清除**
    （修好之后不想等 1 小时）。
    """
    try:
        from module.config import failure_state

        until = failure_state.cooldown_until(config_name, command, now)
        return {
            'failure_count': failure_state.failure_count(config_name, command),
            'in_cooldown': until is not None,
            'cooldown_minutes': failure_state.cooldown_remaining_minutes(
                config_name, command, now) if until else 0,
            'cooldown_until': until.strftime('%Y-%m-%d %H:%M:%S')
                              if until else None,
        }
    except Exception:
        return {'failure_count': 0, 'in_cooldown': False,
                'cooldown_minutes': 0, 'cooldown_until': None}


def _effective_target_of(meta, sch: dict, value: dict):
    """
    该任务**这一次真正会用**的目标次数（三级回落）。

    与 `BaseTask.effective_target()` **同一套规则**，但这里是纯 dict 运算
    （`/overview` 里没有任务对象可调）:

        1. `scheduler.target > 0`  ->  用它
        2. 否则                    ->  任务配置里的 `count_field`
        3. 再否则                  ->  `meta.count_default`

    ★ 为什么界面要这个而不是 `count`: `count` 只是"任务配置里的值"，
      用户在界面上改的是 `scheduler.target`。若显示 `count`，
      用户改完会看到旧数字，**以为没生效**。
    """
    if meta is None or not meta.countable:
        return None
    try:
        target = int((sch or {}).get('target', 0) or 0)
        if target > 0:
            return target
    except (TypeError, ValueError):
        pass
    # 任务配置里的值 —— 与 `_count_from_value` 同一套查找（两个字段名都试）
    v = _count_from_value(meta, value)
    if v is not None:
        return v
    return getattr(meta, 'count_default', None)


def _find_in_mapping(data, field: str):
    """
    在**嵌套 dict** 里按字段名找值（BFS）。

    为什么遍历而不是硬编码路径: 各任务把 `limit_count` 放在不同层级
    （`orochi_config.limit_count` / `bondling_config.limit_count` / 根上…），
    硬编码路径必然漏。这一点与 `BaseTask._find_count_field` 同理。

    ★ 带上限（200 个节点）—— 配置对象树可能有环或非常深。
    """
    if not isinstance(data, dict):
        return None
    if field in data:
        return data[field]
    queue = list(data.values())
    seen = 0
    while queue and seen < 200:
        seen += 1
        obj = queue.pop(0)
        if isinstance(obj, dict):
            if field in obj:
                return obj[field]
            queue.extend(obj.values())
    return None


def _meta_of_key(key):
    """由 `model_dump()` 的**下划线键**取 `TaskMeta`（取不到返回 None）。

    ## ★ 为什么要单独一个函数（修一个静默 bug）

    原来两处写的是:

        meta = TC.get_by_key(key) if hasattr(TC, 'get_by_key') else None

    **`TC.get_by_key` 根本不存在** —— `hasattr` 恒为 `False`,
    于是 `meta` **永远是 `None`**。`build_overview` 下面有回退所以没出事,
    但"添加任务候选"端点没有回退 -> **候选永远为空**。

    这正是本项目反复踩到的"**静默降级**"模式: 加了 `hasattr` 守卫,
    看起来"很稳", 实际把**逻辑错误藏起来了**。

    `TC.get()` 本身已支持下划线形式与全小写容错, 直接用它。
    """
    if not key:
        return None
    try:
        from module.config import task_catalog as TC
        return TC.get(key)
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


def _auto_queue_of(meta):
    """该任务是否**自动进队列**（任务类别属性, 见 `TaskSpec.auto_queue`）。

    ⚠ 与 `_spec_list_pos` 同理: 字段在 **`TaskSpec`** 上, 不在 `TaskMeta` 上。
      但这里**退回 `countable`**（在 `TaskMeta` 上）作为兜底 ——
      没写 `meta.py` 的任务也要有合理行为, 而不是静默 `None`。

    规则（用户确认）: 可计数 = 次数任务 = **不**自动进队列。
    """
    spec = _spec_of(meta)
    if spec is not None:
        try:
            return bool(spec.auto_queue_effective)
        except Exception:
            pass
    if meta is None:
        return True          # 元数据缺失 -> 保守当"定时类"（放行）
    return not bool(getattr(meta, 'countable', False))


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


# ------------------------------------------------------------------- 任务完成汇报
@schema_app.get('/{script_name}/report')
async def get_task_report(script_name: str):
    """**任务完成汇报**（用户 2026-10-10 新需求）。

    用户原话:
        "添加一个**任务完成汇报 tab**, 现在的日志属于原始日志, 应该**转移到
         单独界面**用来 debug, 当前日志位置替换为**任务完成汇报**的 tab,
         只会报完成了哪些、**出错任务标注**等等其它可以作为简报的内容"

    ## 为什么不新增状态存储

    现有三份状态文件已经够用（见 `module/config/report.py` 的说明）:
    `run_record`（几次/多久）· `task_state`（本周期完成/充能）·
    `failure_state`（失败/冷却）。

    :return: {"config", "at", "summary": {...}, "tasks": [...], "errors": [...]}
    """
    try:
        from module.config.report import build_report
        return build_report(script_name)
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'tasks': [], 'errors': [],
                'summary': {}, 'config': script_name}


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


# --------------------------------------------------------------------------- 运行列表
@schema_app.get('/{script_name}/run_list')
async def get_run_list(script_name: str):
    """
    读当前**运行列表**(用户编排的有序条目清单)。

    返回: `{entries: [...], task_order: [...], blocking: {...}|null}`

    `entries` 里可以有三种条目(按**效果**命名):
      * `{"kind":"task","task":"FallenSun"}`   执行任务
      * `{"kind":"rest","minutes":30}`         **全部停止** 30 分钟(连定时任务一起停)
      * `{"kind":"delay","minutes":30}`        **只停列表** 30 分钟(定时任务照常)
    """
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        rl = config.build_run_list()
        b = rl.blocking_entry()
        return {
            'script': script_name,
            'entries': rl.to_list(),
            'task_order': rl.task_order(),
            'blocking': b.to_dict() if b is not None else None,
            'count': len(rl),
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'entries': [], 'count': 0}


@schema_app.put('/{script_name}/run_list')
async def put_run_list(script_name: str, entries: list = Body(...)):
    """
    **整体替换**运行列表。

    为什么是整体替换而不是逐条增删:
      界面拖拽后拿到的是**完整清单**(含控制条目的位置), 整体写入最简单可靠,
      也不会出现"拖到一半只写了一半"的中间态。

    ★ 坏条目会被**跳过**并记 warning(列表是用户编辑的内容,
      一条写坏不该让整份配置加载失败); 返回体里会给出跳过了几条。
    """
    try:
        from module.config.run_list import RunList
        from module.server.main_manager import mm

        bad = []
        rl = RunList.from_list(entries, on_bad=lambda i, e: bad.append(
            {'entry': i, 'error': str(e)}))
        config = mm.config_cache(script_name)
        ok = config.save_run_list(rl)
        if not ok:
            return {'error': '保存失败(见日志)', 'entries': rl.to_list()}
        return {
            'script': script_name,
            'entries': rl.to_list(),
            'count': len(rl),
            'skipped': bad,
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.post('/{script_name}/run_list/entry')
async def post_run_list_entry(script_name: str,
                              entry: dict = Body(...),
                              index: int = -1):
    """
    在指定位置**插入一个条目**。

    :param index: 插入位置(0 起); `-1`(默认)表示追加到末尾。
                  ★ 模型 B 的关键能力: 控制条目可插到**任意位置**。
    """
    try:
        from module.config.run_list import RunEntry
        from module.server.main_manager import mm

        e = RunEntry.from_dict(entry)
        config = mm.config_cache(script_name)
        rl = config.build_run_list()
        rl.add(e, index=None if index < 0 else index)
        if not config.save_run_list(rl):
            return {'error': '保存失败(见日志)'}
        return {'entries': rl.to_list(), 'count': len(rl)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.delete('/{script_name}/run_list/entry')
async def delete_run_list_entry(script_name: str, index: int):
    """删除指定位置的条目。"""
    try:
        from module.server.main_manager import mm

        config = mm.config_cache(script_name)
        rl = config.build_run_list()
        removed = rl.remove_at(index)
        if removed is None:
            return {'error': f'下标越界: {index}'}
        if not config.save_run_list(rl):
            return {'error': '保存失败(见日志)'}
        return {'entries': rl.to_list(), 'count': len(rl),
                'removed': removed.to_dict()}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.post('/{script_name}/queue/remove')
async def post_queue_remove(script_name: str, data: dict = Body(...)):
    """**把任务移出执行队列**。

    ## ★★ 行为**分两类**（用户 2026-10-10 明确修正）★★

    | 任务类型 | `auto_queue` | 移除后 |
    |---|---|---|
    | **定时任务** | `True` | 出队列 **且 `enable=false`** |
    | **固定/次数任务** | `False` | **只出队列**, `enable` **保持** -> 回到【添加任务】池子 |

    **为什么定时任务必须同时停用**:
    自动进队列的任务只要 `enable=true` 就会被
    `Config.build_queue()` **重新补进队列**。只从 `run_list` 删掉是**无效的**
    —— 下次刷新它又回来了。所以"移出"必须落地为 `enable=false`。

    **为什么次数任务不能停用**:
    它们**不在自动补齐范围内**, 出队列后不会被补回来。若也停用, 用户想再跑
    就得先去任务列表启用 —— 那是**多余的步骤**, 而且用户明确要求它
    "**返回添加任务的池子里**"。

    ★ 我此前把它写成"**无条件停用**" —— 那是**错的**, 已修正。
      用户原话:
        "执行队列中移除后自动停用只针对定时任务, 固定任务移除后应该返回
         添加任务的池子里。"

    ## ★★ `entry_id`: 精确移除**某一条**（⑨ 的修复）★★

    队列里同一任务可以出现**多次**（"重复跑整个任务"）。只按任务名删会
    **一删全删**（实测: 两条「个人突破」删一条, 两条都没了）。

    所以请求体可以再带 `entry_id`:
    * **带了** -> 只删 `entry_id` 匹配的那一条（精确）
    * **没带** -> 删该任务的**所有**条目（旧行为, 向后兼容）

    :param data: {"task": "RealmRaid", "entry_id": "20261010T...-RealmRaid"}
                 —— `task` 必填; `entry_id` 可选（精确移除用）
    :return: {"ok": True, "task": ..., "removed_entries": n,
              "enable": bool, "auto_queue": bool, "message": 中文提示}
    """
    try:
        from module.server.main_manager import mm
        from module.config.config_model import convert_to_underscore

        task = str((data or {}).get('task') or '').strip()
        if not task:
            return {'error': '缺少 task'}

        config = mm.config_cache(script_name)

        # ① 判定类别（决定要不要停用）
        auto = False
        try:
            from module.config import task_catalog as TC
            spec = TC.get_spec(task)
            auto = bool(spec.auto_queue_effective) if spec else False
        except Exception:
            pass

        entry_id = str((data or {}).get('entry_id') or '').strip()

        # ② 从 run_list 里移除。
        #
        # ★★ ⑨: 带了 `entry_id` 就**只删那一条** ★★
        #
        # 原来无条件删"所有该任务的条目" —— 同名重复条目会**一删全删**
        # （实测: 两条「个人突破」删一条, 两条都没了）。
        rl = config.build_run_list()
        if entry_id:
            kept, hit = [], 0
            for e in rl:
                same_task = getattr(e, 'task', None) == task
                same_id = (getattr(e, 'entry_id', None) or '') == entry_id
                if same_task and same_id and not hit:
                    hit = 1          # 只跳过**第一条**匹配的
                    continue
                kept.append(e)
            if not hit:
                # 没找到 -> 不静默成功（否则界面"没反应"却报 OK）
                return {'error': f'队列里找不到 entry_id={entry_id!r} 的条目',
                        'task': task, 'entry_id': entry_id}
        else:
            kept = [e for e in rl
                    if not (getattr(e, 'task', None) == task)]
        removed_n = len(rl) - len(kept)
        if removed_n:
            from module.config.run_list import RunList
            new_rl = RunList(kept)
            if not config.save_run_list(new_rl):
                return {'error': '保存运行列表失败(见日志)'}

        # ③ 只有**定时任务**才停用（否则会被自动补齐）
        key = convert_to_underscore(task)
        node = getattr(config.model, key, None)
        if node is None:
            return {'error': f'找不到任务配置: {key}'}
        sch = getattr(node, 'scheduler', None)
        if sch is None:
            return {'error': f'{key} 没有 scheduler'}

        if auto:
            sch.enable = False
            config.save()

        if auto:
            msg = (f'已把「{task}」移出队列并停用。'
                   f'它启用后会自动回到队列。')
        else:
            msg = (f'已把「{task}」移出队列。'
                   f'它仍在【添加任务】里, 可随时加回。')

        return {
            'ok': True,
            'task': task,
            'entry_id': entry_id,
            'removed_entries': removed_n,
            'enable': bool(sch.enable),
            'auto_queue': auto,
            'message': msg,
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.post('/{script_name}/queue/clear')
async def post_queue_clear(script_name: str):
    """**一键清空执行队列**（用户要求, ⑦）。

    ## 为什么需要**专用**端点（不能只 `PUT run_list = []`）

    `auto_queue=True` 的定时任务只要 `enable=true` 就会被 `build_queue()`
    **重新补进队列** —— 只清 `run_list` 的话它们下次刷新**又回来了**。

    这与 `post_queue_remove` 的语义**一致**: 定时任务"移出"必须落地为
    `enable=false`（见那里的说明）。

    ## 做法

    ① `run_list` 置空（清掉用户编排的次数任务 / 休息条目）
    ② 把所有 `auto_queue` 任务的 `enable` 设为 `false`（否则会被补回）

    ★ 只影响**执行队列**, **不删任何任务配置** —— 用户随时可以重新启用 +
      【添加任务】加回来。

    :return: {"ok": True, "cleared_entries": n, "disabled": [任务名...],
              "message": 中文提示}
    """
    try:
        from module.config.run_list import RunList
        from module.server.main_manager import mm

        config = mm.config_cache(script_name)

        # ① run_list 置空
        rl = config.build_run_list()
        n = len(rl)
        if not config.save_run_list(RunList([])):
            return {'error': '清空运行列表失败(见日志)'}

        # ② 停用所有 auto_queue 任务（否则 build_queue 会把它们补回来）
        disabled = []
        try:
            from module.config.config_model import convert_to_underscore
            from module.config import task_catalog as TC
            for key, value in config.model.model_dump().items():
                if not isinstance(value, dict):
                    continue
                sch = value.get('scheduler')
                if not isinstance(sch, dict) or not sch.get('enable'):
                    continue
                meta = _meta_of_key(key)
                if meta is None or not _auto_queue_of(meta):
                    continue
                node = getattr(config.model, key, None)
                if node is None:
                    continue
                s = getattr(node, 'scheduler', None)
                if s is None:
                    continue
                s.enable = False
                disabled.append(meta.task)
            if disabled:
                config.save()
        except Exception as exc:
            logger.warning(f'清空队列时停用自动任务失败'
                           f'（{type(exc).__name__}: {exc}）')

        return {
            'ok': True,
            'cleared_entries': n,
            'disabled': disabled,
            'message': (f'已清空队列（{n} 条条目）'
                        + (f', 并停用 {len(disabled)} 个定时任务'
                           if disabled else '')),
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.get('/{script_name}/queue/candidates')
async def get_queue_candidates(script_name: str):
    """
    【添加任务】的**候选列表**。

    规则（用户确认）:
        `enable == True` **且** `auto_queue == False` **且** `queued == False`

    ★ 即: **已启用的次数任务, 且还没进队列的**。

    ★ 为什么未启用的**不出现**:
      用户原话 —— "剩余的 34 个任务未启用，其中的次数任务并不会出现在
      添加任务按钮中，如果需要进队列，那么需要先在任务列表启用，
      再添加任务才能进队列"。

    :return: {"candidates": [{command, name, name_zh, category_label,
              count, effective_target, resource_describe}], "count": n}
    """
    try:
        from module.server.main_manager import mm
        from module.config import task_catalog as TC

        config = mm.config_cache(script_name)
        queued = config.queued_commands()
        model_dump = config.model.model_dump()
        out = []

        for key, value in model_dump.items():
            if not isinstance(value, dict):
                continue
            sch = value.get('scheduler')
            if not isinstance(sch, dict) or not sch.get('enable'):
                continue            # 未启用 -> 不是候选

            meta = _meta_of_key(key)
            if meta is None:
                continue
            command = meta.task
            # ★★ A: **不再排除"已在队列"的任务** ★★
            #
            # 用户要求"**可以重复添加相同的任务**"（变相实现多次跑）——
            # 原来排除 `queued` 会让任务加入后**从候选里消失**,
            # 于是**无法再加第二次**。
            #
            # 仍然排除"自动进队列"的: 它们由 `build_queue()` 补齐,
            # 不需要用户手动重复（重复了也没用 —— 补齐按任务名去重）。
            if _auto_queue_of(meta):
                continue            # 自动进队列的 -> 不该出现在这里

            out.append({
                'command': command,
                'name': key,
                'name_zh': meta.name_zh,
                'category': meta.category.value,
                'category_label': TC.CATEGORY_LABEL.get(
                    meta.category, meta.category.value),
                'count': meta.count_default,
                'resource_describe': _resource_describe(meta),
            })

        out.sort(key=lambda r: r['name_zh'])
        return {'script': script_name, 'candidates': out, 'count': len(out)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'candidates': [], 'count': 0}


@schema_app.get('/{script_name}/run_list/preview')
async def get_run_list_preview(script_name: str):
    """
    「预期执行流程」的**推算**。

    ★ 这是推算, 不是保证 —— 实际还受体力/网络/开放时段影响。
      界面必须标注"推算", 不能让用户以为精确。
    """
    try:
        from datetime import datetime

        from module.server.main_manager import mm

        config = mm.config_cache(script_name)
        rl = config.build_run_list()
        running = str(getattr(config.model, 'running_task', '') or '')
        pv = rl.preview(datetime.now(),
                        running_lookup=lambda t: t == running)
        return {
            'script': script_name,
            'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'disclaimer': '推算, 不是保证 —— 实际还受体力/网络/开放时段影响',
            'flow': [{'at': p['at'].strftime('%Y-%m-%d %H:%M:%S'),
                      'kind': p['kind'], 'text': p['text'], 'note': p['note']}
                     for p in pv],
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'flow': []}


# --------------------------------------------------------------------------- 运行记录与归档
@schema_app.get('/{script_name}/run_record')
async def get_run_record(script_name: str, task: str = ''):
    """
    读**运行记录**（次数 + 耗时 + 归档）。

    不传 `task` 时返回该账号**所有任务**的汇总（供总览页）；
    传了则返回该任务的一条（含归档明细）。

    ★ 「重置」= **归档后重开**，不是删除 —— 所以这里有 `archive`。
    """
    try:
        from module.config import run_record

        if task:
            return {
                'script': script_name,
                'task': task,
                'current': run_record.current(script_name, task),
                'archive': run_record.archive(script_name, task),
                'total': run_record.total(script_name, task),
            }
        summary = run_record.summarize(script_name)
        # 顺带给出可读的耗时文本, 免得每个前端各写一份格式化
        for row in summary.values():
            row['seconds_text'] = run_record.format_duration(row['seconds'])
            row['current_seconds_text'] = run_record.format_duration(
                row['current_seconds'])
        return {
            'script': script_name,
            'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'tasks': summary,
            'count': len(summary),
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'tasks': {}, 'count': 0}


@schema_app.put('/{script_name}/run_record/reset')
async def put_run_record_reset(script_name: str, tasks: list = Body(...)):
    """
    「重置选中」—— **归档后重开**（不是删除）。

    body: `["Orochi", "FallenSun"]`（任务名数组）

    ★ 用户明确要求: "点击重置选中后**不是清除记录, 而是归档记录后开始
      新的记录**。这样后续可以分析运行记录和展示运行结果"。

    ★ 单个任务出错**不中断**其余的（批量操作里一个坏名字不该让整批失败）。
    """
    try:
        from module.config import run_record

        names = [str(t) for t in (tasks or []) if t]
        archived = run_record.reset_many(script_name, names)
        return {
            'script': script_name,
            'archived_rounds': archived,
            'tasks': names,
            'count': len(names),
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.get('/{script_name}/run_record/{task}/archive')
async def get_task_archive(script_name: str, task: str):
    """读某个任务的**归档明细**（供"运行历史"展示）。"""
    try:
        from module.config import run_record

        arch = run_record.archive(script_name, task)
        for row in arch:
            row['seconds_text'] = run_record.format_duration(
                row.get('seconds', 0))
        return {
            'script': script_name,
            'task': task,
            'archive': arch,
            'total': run_record.total(script_name, task),
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'archive': []}


# --------------------------------------------------------------------------- 运行一次
@schema_app.get('/{script_name}/manual_run')
async def get_manual_run(script_name: str):
    """读「运行一次」队列（按点击顺序）。"""
    try:
        from module.config import manual_run

        return {'script': script_name, **manual_run.summarize(script_name)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'tasks': [], 'count': 0}


@schema_app.put('/{script_name}/manual_run')
async def put_manual_run(script_name: str, tasks: list = Body(...)):
    """
    请求「运行一次」（body 是任务名数组，**按数组顺序**排队）。

    ★ 用户确认的语义: "点击后按照点击先后顺序，直接排在最高优先级
      （就是跑完当前任务/战斗后插队运行）"。

    ★ **不是立即打断** —— 插队点在**任务边界**。
      立即打断会卡在半途（战斗中 / 组队房间里），
      与「暂停调度」同样的理由。
    """
    try:
        from module.config import manual_run

        manual_run.request_many(script_name, tasks)
        return {'script': script_name, **manual_run.summarize(script_name)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.delete('/{script_name}/manual_run')
async def delete_manual_run(script_name: str, task: str = ''):
    """取消排队（`task` 留空则清空整个队列）。"""
    try:
        from module.config import manual_run

        if task:
            ok = manual_run.cancel(script_name, task)
            return {'script': script_name, 'cancelled': ok,
                    **manual_run.summarize(script_name)}
        manual_run.clear(script_name)
        return {'script': script_name, 'cleared': True,
                **manual_run.summarize(script_name)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


# --------------------------------------------------------------------------- 失败冷却
@schema_app.get('/{script_name}/failure_state')
async def get_failure_state(script_name: str):
    """
    读**连续失败 / 冷却**状态（供界面显示"哪些任务在冷却"）。

    ★ 为什么需要它: `script.py` 原先在任务连续失败 3 次时 `exit(1)`
      退出整个子进程, 而计数在**内存**里 —— 进程一重启计数归零,
      于是"失败 3 次 -> 重启 -> 计数归零 -> 又失败 3 次"**无限循环**。
      一次 7 小时的运行有 90+ 次进程重启。

      现在计数**落盘**, 到阈值只给该任务加冷却（默认 1 小时）,
      界面上要能看到这件事。
    """
    try:
        from module.config import failure_state

        return {'script': script_name,
                'tasks': failure_state.summarize(script_name)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'tasks': {}}


@schema_app.delete('/{script_name}/failure_state')
async def delete_failure_state(script_name: str, task: str = ''):
    """
    清除失败记录（**同时解除冷却**）。

    * `task` 留空 -> 清空该账号全部
    * 给了 `task` -> 只清那一个

    ★ 用途: 用户修好了问题（改配置 / 换素材）之后
      **不想等 1 小时冷却**, 点一下就能立刻重试。
    """
    try:
        from module.config import failure_state

        failure_state.clear(script_name, task or None)
        return {'script': script_name, 'cleared': task or 'all',
                'tasks': failure_state.summarize(script_name)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


# --------------------------------------------------------------------------- 运行控制
@schema_app.get('/{script_name}/run_control')
async def get_run_control(script_name: str):
    """
    当前运行控制状态（暂停 / 休息）。

    返回: `{paused, pause_mode, pause_mode_label, pause_at, pause_reason,
            rest_until, rest_remaining, can_run}`

    ★ v2 去掉了 `delayed` / `list_resume_at` / `list_remaining` ——
      那是 v1「只停列表」的字段；固定与定时分开管理后（各有总开关），
      前端不再需要它（见 `docs/architecture.md` §5.1）。
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
