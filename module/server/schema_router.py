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
        # ★★ T4（审计修复）: **删掉 `window_fields`** ★★
        #
        # ## 为什么删
        #
        # 它返回 4 个**已删除**的单值字段（`window_enable` / `window_start` /
        # `window_end` / `window_days`）, 注释还写着"界面据此渲染表单" ——
        # 但:
        #   1. S3 已改成 **`windows` 列表**（`List[TaskWindow]`）,
        #      这 4 个字段在 `Scheduler.model_fields` 里**已经不存在**
        #      （`tests/module/config/test_multi_window_storage.py` 反向断言）
        #   2. 前端**根本不用它** —— 窗口编辑器走
        #      `GET/PUT /{script}/tasks/{task}/windows`（5 个按 `id` 的端点）
        #   3. 更糟: **有一个测试断言这 4 个字段必须存在**
        #      （`test_schema_router.py::test_...window_fields...`）——
        #      于是"死代码 + 锁死它的断言"**互相印证地一起过时**
        #
        # ★ 这是审计里最有解释力的一条: 文档与死代码互相印证, 看着自洽、
        #   实则全失效。**删掉它, 漂移就少一个来源。**
        #
        # ★ 窗口的正确契约: 见 `docs/scheduler-architecture.md`
        #   （`TaskWindow` 的 7 个字段 + 5 个按 id 的 CRUD 端点）。
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
    | **定时调度器** | timed / limited | window、剩余时间、预计耗时、自定义优先级 |

    见 `docs/architecture.md` §5.4 与 `module/config/timed_schedule.py`。
    """
    # ★ 待办 #5: 不再需要 `ScheduleRule` / `TimedPriority`（死链已删）

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
        # ★★ 第二轮复审（待办 #5）: **删掉三个已废弃的死键** ★★
        #
        # 原来这里发 `mode_value` / `modes` / `current_mode` —— 那四个调度模式
        # (`Filter`/`FIFO`/`Priority`/`List`) 在 **T1** 删掉
        # `TaskScheduler.schedule()` 调用后就**彻底不再影响排序**了,
        # 又在 **S6** 被 `priority_mode` 三模式取代。
        #
        # ★ 危害: 它们是"**已死的读写链**"—— 前端仍在读
        #   (`task_list_controller.dart` 的 `modes`/`mode_value`/
        #   `current_mode`), 后端仍在发, 只差**有人再调一次**
        #   `setScheduleRule()`（它**会写配置**）就复活"两个排序权威"。
        #   而 `ui-api-mapping.md` 还在教人调 `PUT .../schedule_rule/value`。
        #
        # ★ 现行做法: 模式从 **`global_fields` 的 `priority_mode`** 读
        #   （三选一, 见 `_global_fields()` 与前端 `priorityMode*`）。
        #
        # 用户编排写入的字段
        'order_field': 'run_list',
        'order_group': 'script.optimization',
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
    from tasks.Script.config_optimization import WhenTaskQueueEmpty

    # ★★★ 「调度优先级三模式」**已整簇删除**（用户裁定）★★★
    #
    # 用户原话:
    # > "我觉得……这个**固定任务优先和定时任务优先以及不能跨类别拖动
    # >  太蠢了**。我只需要保持**可以自由拖动/改变执行顺序**就行,
    # >  固定任务优先和定时任务优先**直接作为一个快捷排序**就好,
    # >  而不是定义一些没有意义的不能跨类别拖动以及**单独的调度优先级**。"
    #
    # ★ 所以这里**不再暴露 `priority_mode` / `drag_within_group_only`**。
    #   排序改成**一个动作**（`PUT /{script}/queue/sort`）, 见下面的端点。
    queue_labels = {
        WhenTaskQueueEmpty.GOTO_MAIN.value: '回庭院待命',
        WhenTaskQueueEmpty.CLOSE_GAME.value: '关闭游戏',
        # ★ P-3（用户裁定）: 队列整体循环 —— "跑完最后一条后从头再来"
        WhenTaskQueueEmpty.LOOP.value: '队列循环',
    }

    return {
        # ---- 两个总开关 ----
        #
        # ★★★ 改名（用户裁定）★★★
        #
        # 用户原话: "`period` 不限时是**固定**（固定任务改名为**临时任务**）,
        #   其他是**定时**（定时任务名字改为**周期任务**）"
        #
        # ★ 旧名"定时/固定"**没表达出"周期"这回事** —— 于是同一个任务会被
        #   理解成两种意思, 用户核对 54 个任务后指出"**分类不对**"。
        #   新名直接说清判据: **有没有周期记忆**。
        'enable_fixed': {
            'group': 'script.optimization', 'field': 'enable_fixed',
            'type': 'boolean', 'label': '启用临时任务',
            'current': bool(_opt_value(config_name, 'enable_fixed', True)),
            'help': '临时任务 = **没有周期记忆**（`period=none`）的任务, '
                    '想跑就跑, 不按周期重置',
        },
        'enable_timed': {
            'group': 'script.optimization', 'field': 'enable_timed',
            'type': 'boolean', 'label': '启用周期任务',
            'current': bool(_opt_value(config_name, 'enable_timed', True)),
            'help': '周期任务 = **有周期记忆**（`period` = 每天/每周）的任务, '
                    '到周期才该再做一次',
        },
        # ★★ S6: 调度优先级三模式 **已删除**（用户裁定）★★
        #
        # 原来这里是 `priority_mode` 三选一（含 `drag_within_group_only`）。
        # 用户裁定: "我只需要保持**可以自由拖动/改变执行顺序**就行,
        # 固定任务优先和定时任务优先**直接作为一个快捷排序**就好"。
        #
        # ★ 现在**没有"模式"这个状态** —— 排序是
        #   `PUT /{script}/queue/sort` 的**一次性动作**。
        # ⚠ `timed_priority` / `schedule_rule` 这两个更旧的字段也不再暴露
        #   （它们原来被并进 `priority_mode`, 现在整簇都没了）。
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
        # ★★★ P-3b: 循环**跑几轮**（用户裁定）★★★
        #
        # 用户原话:
        # > "我觉得选中后应该加一个**跑几次**的额外输入框, **0代表一直跑**,
        # >   **1、2……代表跑几次**。"
        #
        # ★ 这是**用户设置**（进配置 JSON）;
        #   "已经跑了几轮"是**运行进度**（`task_state` 里, 存盘）——
        #   ★ 两个都暴露给界面: 用户要能看到"还剩几轮"才会想点重置。
        'loop_times': {
            'group': 'script.optimization',
            'field': 'loop_times',
            'type': 'integer',
            'label': '循环轮数',
            'current': int(_opt_value(config_name, 'loop_times', 0) or 0),
            'min': 0,
            'max': 9999,
            'help': '0 = 一直跑；1、2…… = 循环几轮后停下（回庭院待命）。'
                    '★ 「跑空后」选「队列循环」时才生效。',
        },
        # ★ 只读进度 —— 用户点「重置循环计数」看的就是它
        'loop_rounds_done': {
            'group': 'script.optimization',
            'field': 'loop_rounds_done',
            'type': 'integer',
            'label': '已跑轮数',
            'readonly': True,
            'current': _loop_rounds_of(config_name),
            'help': '本次已经跑了几轮（存盘，重启不丢）。'
                    '点「重置循环计数」可清 0 -> 又能跑满「循环轮数」。',
        },
    }


def _loop_rounds_of(config_name: str) -> int:
    """★ 队列循环**已跑轮数**（运行进度，见 `task_state.get_loop_rounds`）。

    任何异常返回 0 —— 进度读不到不该让整个 schema 失败。
    """
    try:
        from module.config import task_state
        return int(task_state.get_loop_rounds(config_name) or 0)
    except Exception as exc:
        logger.debug(f'读循环轮数失败({type(exc).__name__}: {exc}), 按 0')
        return 0


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


# ★★★ `_current_priority_mode()` **已删除**（用户裁定）★★★
#
# 它读 `Script.optimization.priority_mode` 并返回三模式之一 —— 唯一消费者是
# `_global_fields()` 的 `priority_mode` 字段, 那个字段**刚被删**。
#
# ★ 用户原话:
# > "固定任务优先和定时任务优先以及**不能跨类别拖动太蠢了**……而不是定义
# >  一些没有意义的不能跨类别拖动以及**单独的调度优先级**。"
#
# ★ 现行做法: **没有"模式"** —— 执行顺序就是 `run_list` 的顺序;
#   「定时/固定排前面」是 `PUT /{script}/queue/sort` 的**一次性动作**。
#

# ★★ 第二轮复审（待办 #5）: `_current_schedule_rule()` **已删除** ★★
#
# 它读 `Script.optimization.schedule_rule` 并返回那四个旧模式之一 ——
# 唯一消费者是 `_list_meta()` 的 `current_mode`, 那个键**刚被删**。



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
    # ★★ S5: 存量（`charges`）已删除 —— 用户裁定去掉存量机制 ★★
    #
    #   原来这里调 `task_state.summarize()` 取 `charges`, 再按**压缩小写**归一
    #   （`experienceyoukai` vs `experience_youkai`）。现在 `summarize()` 只返回
    #   `global`（完成记忆）, 总览页也**不再有"存量"列**。

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
            # ★★ 审计修复（H2/⑥）: 给出**最终类别**与**优先级段** ★★
            #
            # ## 为什么必须给（这是个真 bug）
            #
            # `category` 是 `meta.py` 里**声明**的类别; 而真正决定"它算定时还是
            # 固定"的是 `category_effective`（⑥: `timed` + `period=none`
            # -> `fixed`）。实测: **54 个任务里 17 个**声明 `timed` 却
            # `category_effective == fixed`（DemonEncounter / GoldYoukai /
            # Tako / Duel / …）。
            #
            # 前端拿不到这两个字段, 只能**自己用 `category` 复算**段名 ->
            # **17 个任务的分段条、类别色条、拖动范围全错**, 且"拖动预检"与
            # 后端 `_check_drag_allowed` 的判定**可能相反**（用户看到
            # "不能跨类别拖动"却看不出原因）。
            #
            # ★ 这里把**权威值**直接给前端 —— 前端不再复算（符合 §7
            #   "前端不重新推导调度规则"）。
            'category_effective': (meta.category_effective.value
                                   if meta else 'timed'),
            'category_effective_label': TC.CATEGORY_LABEL.get(
                meta.category_effective if meta else None, ''),
            # 优先级段: `'timed'` / `'fixed'` —— 与 `Config._segment_of()`
            # 以及 `build_queue()` 的 `_tag_and_place_rest()` 用**同一处**判据。
            #
            # ★★★ 判据已改为读**配置**里的 `scheduler.period`（用户裁定）★★★
            #
            # 用户原话:
            # > "**窗口必须在选了周期后才能设置。这样子判断依据就可以按有没有
            # >  周期来判断**"
            # > "周期是 period 啊！… 是**每天、每周每月、不限**那个"
            #
            # ★ 原来这里读 `meta.priority_group`（`meta.py` 的 `TaskSpec.period`,
            #   **写死源码、前端改不了**）-> 用户"在前端改了 period, 队列标签不动"。
            # ★ 现在走 `config.priority_group_of()`（= 读配置的 `scheduler.period`,
            #   拿不到才回退出厂默认值）-> **改一处, 全联动**。
            #
            # ★ S7: 它**只用于显示**（类别色条/标签）与 `sort_run_list(by=...)`
            #   的排序依据 —— **不再限制拖动**（拖动永远自由）。
            'priority_group': config.priority_group_of(command),
            # ★ `scheduler.period` 本身也暴露出去（前端要显示/编辑"周期"下拉,
            #   也需要它来提示"选了周期才能配窗口"）。
            'period': config.task_period(command),
            # ★★★ 优先级段的**中文名** —— 界面显示"定时/固定"**只用这一个** ★★★
            #
            # ## 为什么必须由后端给（实机验收发现的**口径不一致**）
            #
            # 用户原话:
            # > "执行顺序下边的任务统计数量显示：**定时任务2条，固定任务14条**,
            # >  但是**任务上的标签**显示的几乎都是紫色的定时, 红色的次数只有四个"
            #
            # **根因**: 界面有**三个口径**各读不同字段 ——
            #   * 「执行顺序」分段条 -> `priority_group`（有效分段, 权威）
            #   * 任务表格「类型」列 -> `category_label`（**声明**类别）
            #   * 队列行色条/标签   -> `auto_queue`（会不会自动进队列）
            # ★ 实测 16 条队列里有 **10 条**声明 `timed` 而有效分段是 `fixed`
            #   -> 界面同时说它"是定时"又说"按 fixed 排", 看起来**自相矛盾**。
            #
            # ★ 修法: 后端给出**这一个**标签, 前端三处都用它 ——
            #   "同一知识三处定义" 收敛成**一处**。
            #
            # ⚠ 必须用 `config.priority_group_of(command)`（同上, 读配置）,
            #   **不能**再用 `meta.priority_group` —— 否则标签与
            #   `priority_group` 又不同源（那正是上面那个矛盾的成因）。
            'priority_group_label': TC.PRIORITY_GROUP_LABEL.get(
                config.priority_group_of(command), ''),
            # ★ 当前是否**在开放时段内** —— 供界面区分"能跑/还没到点",
            #   也是 `sort_run_list()` 把"跑不了的任务"排到后面的依据。
            'in_window_now': bool(in_window),
            # 类别的中文标签 —— 界面不必自己维护一份映射。
            #
            # ★ 元数据缺失的任务(如尚未写 `meta.py` 的)也要给出标签,
            #   否则界面会出现"类型"列为空的行。用 FALLBACK_CATEGORY 兜底。
            #
            # ⚠ **注意**: 这是**声明类别**（`TaskMeta.category`）, 与
            #   `priority_group`（**有效分段**）**不是一回事** ——
            #   实测 54 个任务里 17 个两者不同。界面要显示"定时/固定"时
            #   请用 `priority_group_label`, **不要**用这个（会自相矛盾）。
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
            # ★★★ 不能跑的原因（界面可直接显示）★★★
            #
            # ## ★ 实机验收修复: 原来**漏了"不在执行队列"这一态**
            #
            # 用户原话:
            #   "**契灵之境为什么显示等待到点?** 这个是次数任务, 不应该有
            #    [还未到点]这种[拥有 window 的任务类]的属性啊"
            #
            # **原来的三分支**:
            # ```python
            # 'reason': window_reason or (
            #     '' if can_run else ('未启用' if not enabled else '等待到点'))
            # ```
            # -> 凡是"已启用但 `can_run=False`"的, 一律说成 **"等待到点"**。
            #
            # ★ 而 `can_run` 只在 `slot == 'pending'` 时为真, 而 `slot` 来自
            #   `update_scheduler()` 分的 `pending` / `waiting` ——
            #   **不在执行队列**的任务（`auto_queue=False` 且用户没编排）
            #   被 `_order_by_queue()` **剔除**, 于是它**既不在 `pending`
            #   也不在 `waiting`** -> `slot=''` -> **`reason` 恒为"等待到点"**。
            #
            # ★★ **铁证**: `Orochi` 的 `next_run` 是 **`2023-01-01`（三年前）**,
            #   界面**照样**显示"等待到点" —— 证明这个标签**根本不是从
            #   `next_run` 推出来的**, 它只是那个 `else` 分支的默认值。
            #
            # ★ 这也正是用户说的"**次数任务不该有'未到点'这种属性**"的
            #   **直接成因**: 一个从没进过队列的次数任务, 被贴上了
            #   "定时任务才有的"说法。
            #
            # ★ 修法: 补上**第四态** `不在执行队列`（并说清怎么办）。
            #   ⚠ 顺序很重要: "不在队列"要排在"等待到点"**之前**判断 ——
            #     否则队列外的任务永远命中不了这一态。
            'reason': window_reason or (
                '' if can_run
                else ('未启用' if not enabled
                      else ('不在执行队列' if command not in queued_commands
                            else '等待到点'))),
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
            # ★★ S5: `'charges'`（"存量 x / 上限 y", 如金币妖怪 1/2）已删除 ★★
            #   用户裁定去掉存量机制 —— 总览页**不再有"存量"列**。
            #   何时能跑只看**窗口**（用户在 `/args` 的 `windows` 字段里配）。
            #
            # ⚠ 这里**不新增** `windows` 字段: 前端已经有
            #   `GET /{script}/tasks/{task}/windows` 与窗口编辑器,
            #   总览页也不需要它 —— 加字段属于**未要求的接口变更**。
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
            'auto_queue': _auto_queue_of(meta, config),
            'queued': command in queued_commands,
            # 该任务的效果说明(供界面展示"这个任务是干什么的")
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


def _auto_queue_of(meta, config=None):
    """该任务是否**自动进队列**。

    ★★★ 已改为与「周期 / 临时」**同源**（用户裁定: "联动还不完善"）★★★

    ## 为什么改（实测到的真漂移）

    原来读 `TaskSpec.auto_queue_effective` —— 那个属性的推导依据是
    **`category`**（`category not in COUNTABLE_CATEGORIES`），
    而 `category` 正是**被废弃的判据**（分类已改为按 `scheduler.period`）。

    ★ 于是两者**必然漂移**，实测 **4 个任务不一致**:

    | 任务 | `period` | 界面分类 | 旧 `auto_queue` |
    |---|---|---|---|
    | `OtherWorldTwilight` | daily | **周期** | `False` |
    | `RyouToppa` | daily | **周期** | `False` |
    | `SixRealms` | daily | **周期** | `False` |
    | `TalismanPass` | none | **临时** | `True` |

    -> 界面上"周期任务"躺在【添加任务】池子里、"临时任务"却自动进了队列。

    ## 现在

    ★ 走 `config.auto_queue_of()`（= `period != 'none'` = 周期任务），
      与 `priority_group_of()` **同一处判据** —— 界面显示什么, 行为就是什么。

    :param config: 可选 `Config`; 传了就用它（同源）；不传则退回旧的 meta 判据
                   （仅为向后兼容那些没传 config 的调用点）。
    """
    if config is not None:
        try:
            # ⚠ `TaskMeta` 上**没有 `command` 也没有 `name`**（实测字段是
            #   `task`）—— 第一版我写成 `getattr(meta, 'command', '')` ->
            #   拿到空串 -> `auto_queue_of('')` 返回 False
            #   -> **41 个任务全被误判**（实测）。
            # ★ 修法: `command`（`/overview` 行里有）优先, 否则用 `meta.task`。
            name = str(getattr(meta, 'command', '')
                       or getattr(meta, 'task', '') or '')
            if name:
                return bool(config.auto_queue_of(name))
        except Exception as exc:
            logger.debug(f'auto_queue 同源判定失败({type(exc).__name__}: {exc}), '
                         f'退回 meta 判据')
    # ---- 以下为**兼容回退**（新代码都应传 `config`）----
    spec = _spec_of(meta)
    if spec is not None:
        try:
            return bool(spec.auto_queue_effective)
        except Exception:
            pass
    if meta is None:
        return True          # 元数据缺失 -> 保守当"定时类"（放行）
    return not bool(getattr(meta, 'countable', False))


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

    ★★ S7: **拖动永远自由**（用户裁定）★★

    ★ 这里原来写着「S6 拖动约束」: `priority_mode == custom` 不校验,
      另两模式校验段序并返回 `drag_blocked`。**那整条已删除** ——
      用户原话:

      > "固定任务优先和定时任务优先以及**不能跨类别拖动太蠢了**。
      >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
      >  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有
      >  意义的不能跨类别拖动以及**单独的调度优先级**。"

    ★ 现在**任意次序都能存**（含跨类别、含把 rest 拖到最前）。
    ★ 唯一保留的硬约束: 「休息」条目**归一化到最后**
      （`config.place_rest_last(rl)` —— 是**挪位**而不是**拒绝**）。
    """
    try:
        from module.config.run_list import RunList
        from module.server.main_manager import mm

        bad = []
        rl = RunList.from_list(entries, on_bad=lambda i, e: bad.append(
            {'entry': i, 'error': str(e)}))
        config = mm.config_cache(script_name)

        # ★★ 审计修复: `group` 是**派生**字段, 不信任前端传的值 ★★
        #
        # 前端为了渲染分段条会在 entries 里带 `group`。但它是
        # `build_queue()` 的**派生结果**（`_tag_and_place_rest()` 刻意**不回写**）。
        # 若原样存盘: ① 破坏"单一数据源" ② 前端判据与后端不一致时会存下**错的段名**。
        # -> 这里**丢掉传进来的**, 用后端的权威值。
        rl = _assign_groups(config, rl)

        # ★★★ 拖动约束**已删除**（用户裁定）★★★
        #
        # 用户原话: "固定任务优先和定时任务优先以及**不能跨类别拖动太蠢了**。
        #   我只需要保持**可以自由拖动/改变执行顺序**就行。"
        #
        # ★ 这里原来是 `blocked, reason = _check_drag_allowed(...)`, 命中就
        #   返回 `{'error': ..., 'drag_blocked': True, 'entries': ...}`。
        #   **前端曾把带 `entries` 的返回当成"保存成功"** -> 用户看到的是
        #   "三种模式都能随便拖, 而且没有任何提示"（后端一直在拒绝）。
        #
        # ★ 现在**唯一**的硬约束是「休息」条目**恒最后** —— 而且它是
        #   **归一化**（挪到最后）而不是**拒绝**: 用户拖到哪都接受。
        #   用户确认: "任意拖，但「休息」条目仍强制排最后"。
        rl = config.place_rest_last(rl)

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


def _assign_groups(config, rl):
    """**权威地**给条目重算段名（`'timed'` / `'fixed'`）—— 审计修复。

    ## 为什么必须有这一步

    `group` 是 `build_queue()` 的**派生结果**（`Config._tag_and_place_rest()`
    刻意**不回写**配置；S7 前它叫 `_segment_queue()`）。但前端为了渲染分段条,
    会在 `entries` 里**带上** `group`。若原样存盘:

    1. **破坏"单一数据源"**（台账 §10.8）—— 段名就有了两个来源。
    2. 前端按 `category` 算, 后端按 `TaskSpec.priority_group` 算; 两者判据
       万一不一致, 配置里会**躺着错的段名**, 而 `_tag_and_place_rest()`
       又会覆盖它 —— 于是"存了但没用", 白白污染配置。

    ★ 所以: **丢掉前端传的 `group`**, 一律用后端的权威判据重算。

    :return: 同一个 `RunList`（就地改写 `RunEntry.group`; 它是 frozen dataclass,
             用 `object.__setattr__` 写）。
    """
    try:
        for e in rl.entries:
            task = getattr(e, 'task', '') or ''
            if not task:
                continue          # `rest` / `delay` 不进段
            try:
                object.__setattr__(e, 'group', config._segment_of(task))
            except Exception:
                pass
    except Exception as exc:
        logger.warning(f'重算段名失败({type(exc).__name__}: {exc}), 跳过')
    return rl


# ★★★ `_check_drag_allowed()` **已整函数删除**（用户裁定）★★★
#
# ## 它原来做什么
#
# 在 `timed_first` / `fixed_first` 下校验"段序单调", 跨类别拖动就返回
# `(True, 可读原因)`, 调用方据此返回 `{'error': ..., 'drag_blocked': True}`。
#
# ## 为什么删
#
# 用户原话:
# > "固定任务优先和定时任务优先以及**不能跨类别拖动太蠢了**。
# >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
# >  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有
# >  意义的不能跨类别拖动以及**单独的调度优先级**。"
#
# ★ 唯一的硬约束（「休息」恒最后）现在由 `Config.place_rest_last()`
#   负责 —— 而且是**归一化**（挪到最后）而不是**拒绝**。
#
# ★★ 为什么不保留一个"恒返回放行"的空壳 ★★
#
# 我一度留了空壳（`return False, ''`）"以防有旧调用点"。但实测**没有任何
# 调用点**, 而且空壳有个真实风险: **未来有人把它接回某个分支**, 它恒放行
# **不会有任何提示** —— 那就变成"看起来在校验、其实没有"的静默假守卫。
# ★ 本项目纪律是"**让静默失败变成看得见**" -> 直接删干净, 要恢复就得
#   重新写一遍（那时自然会想清楚"知识为什么要在两处定义"）。
#
# ★ 反向守卫见 `tests/module/server/test_drag_is_free.py`。


# ★★★ `GET`/`PUT /{script_name}/priority_mode` **已删除**（用户裁定）★★★
#
# 用户原话:
# > "固定任务优先和定时任务优先以及**不能跨类别拖动太蠢了**。
# >  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
# >  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有
# >  意义的不能跨类别拖动以及**单独的调度优先级**。"
#
# ★ 取而代之的是下面的 `PUT /{script_name}/queue/sort` ——
#   **一个动作, 不是一个状态**。排完之后队列就是新顺序, 用户可以随意再拖。


@schema_app.put('/{script_name}/queue/sort')
async def put_queue_sort(script_name: str, body: dict = Body(...)):
    """★ **一次性排序执行顺序**（用户裁定: "直接作为一个快捷排序"）。

    body: `{"by": "timed"}` 或 `{"by": "fixed"}`
      * `timed` -> **定时段**排到前面, 固定段在后
      * `fixed` -> **固定段**排到前面, 定时段在后

    ## ★★★ 它为什么不是"模式" ★★★

    旧实现是一个 `priority_mode` **状态**: 一旦设定, **每次** `build_queue()`
    都按它排, 而且**限制拖动范围**（不能跨类别拖）。用户裁定那太蠢:

    > "我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
    >  定时任务优先**直接作为一个快捷排序**就好。"

    ★ 所以: **点一次, 排一次, 不留状态**。排完之后:
      * 队列顺序 = 新的 `run_list` 顺序
      * 用户**可以随意再拖**（跨类别也行）—— 没有东西拦他

    ## 规则

    * **段内相对顺序不变**（`sorted` 稳定）—— 保住用户既有的编排
    * 「休息」条目**恒最后**（用户确认的唯一硬约束）

    :return `{ok, by, entries, count}` 或 `{error}`
    """
    from module.server.main_manager import mm

    by = str((body or {}).get("by") or "").strip().lower()
    if by not in ("timed", "fixed"):
        return {"error": f"非法 by: {by!r}; 应为 timed / fixed"}
    try:
        config = mm.config_cache(script_name)
        if not config.sort_run_list(by):
            return {"error": "排序失败(见后端日志)"}
        rl = config.build_run_list()
        return {"ok": True, "by": by,
                "count": len(rl.entries),
                "entries": rl.to_list()}
    except Exception as exc:
        logger.exception(exc)
        return {"error": str(exc)}


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

        # ★ 与 `PUT /run_list` **同一套契约**: 清洗派生字段 `group`
        # ★★ 拖动约束**已删除**（用户裁定）★★ —— 见 `PUT /run_list` 的说明。
        #    唯一的硬约束是「休息」恒最后, 且是**归一化**不是拒绝。
        rl = _assign_groups(config, rl)
        rl = config.place_rest_last(rl)

        if not config.save_run_list(rl):
            return {'error': '保存失败(见日志)'}

        # ★★ 实机验收修复: **"重新添加"也清掉该任务的失败冷却** ★★
        #
        # ★ 用户原话: "契灵之境运行失败后的冷却状态**应该只在连续运行时
        #   生效**, 我都**打断过了重新添加了**, 还显示在冷却中。"
        #
        # ★ 语义: 「连续失败」的"连续"以**一次不间断的运行**为单位。
        #   用户主动把任务**重新加进队列** = 明确表示"我要再试一次"
        #   -> 继续拿旧冷却拦他, 只会让他以为"加了也没用"。
        #
        # ⚠ 只清**这个条目对应的任务**（`rest`/`delay` 没有 task, 跳过）。
        # ⚠ 清失败**不影响**插入结果（不该因为清冷却出错而回滚插入）。
        task_of_entry = getattr(e, 'task', None)
        if task_of_entry:
            try:
                from module.config import failure_state
                failure_state.clear(script_name, task_of_entry)
            except Exception as exc:
                logger.warning(f'清失败冷却失败({task_of_entry}): {exc}')

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

    ## ★★★ 判据已改为「周期 / 临时」（用户 2026-10-10 本轮裁定）★★★

    用户原话:
    > "**显示周期的不应该移除队列后回退到添加任务的池子里而是直接停用**,
    >  这说明目前的**[联动]还不完善**。"

    | 任务类型 | 判据 | 移除后 |
    |---|---|---|
    | ★ **周期任务** | `scheduler.period != 'none'` | 出队列 **且 `enable=false`**（**直接停用**）|
    | ★ **临时任务** | `scheduler.period == 'none'` | **只出队列**, `enable` **保持** -> 回到【添加任务】池子 |

    ## ★ 为什么这次要改判据（原来按 `auto_queue`）

    原来按 **`auto_queue`**（"会不会自动进队列"）分:

    | 任务类型 | `auto_queue` | 移除后（旧）|
    |---|---|---|
    | 定时任务 | `True` | 出队列 + `enable=false` |
    | 固定/次数任务 | `False` | **只出队列** -> 回池子 |

    ★ 但用户看到的分类是 **`priority_group`**（周期/临时），而它与
      `auto_queue` **不是同一个东西** —— 于是一批**周期任务**（`period != none`
      但 `auto_queue == False`）被当成"次数任务"丢回了池子
      -> ★ **界面分类与实际行为不一致**，正是用户说的"联动不完善"。

    ★ 现在两处**同源**: 界面显示什么（周期/临时），移除行为就按什么。

    ## 为什么周期任务必须同时停用

    自动进队列的任务只要 `enable=true` 就会被 `Config.build_queue()`
    **重新补进队列**。只从 `run_list` 删掉是**无效的** —— 下次刷新它又回来了。

    ## 为什么临时任务不能停用

    它们**不在自动补齐范围内**, 出队列后不会被补回来。若也停用, 用户想再跑
    就得先去任务列表启用 —— 那是**多余的步骤**。

    ## ★★ `entry_id`: 精确移除**某一条**（⑨ 的修复）★★

    队列里同一任务可以出现**多次**（"重复跑整个任务"）。只按任务名删会
    **一删全删**（实测: 两条「个人突破」删一条, 两条都没了）。

    所以请求体可以再带 `entry_id`:
    * **带了** -> 只删 `entry_id` 匹配的那一条（精确）
    * **没带** -> 删该任务的**所有**条目（旧行为, 向后兼容）

    :param data: {"task": "RealmRaid", "entry_id": "20261010T...-RealmRaid"}
                 —— `task` 必填; `entry_id` 可选（精确移除用）
    :return: {"ok": True, "task": ..., "removed_entries": n,
              "enable": bool, "priority_group": str, "message": 中文提示}
    """
    try:
        from module.server.main_manager import mm
        from module.config.config_model import convert_to_underscore

        task = str((data or {}).get('task') or '').strip()
        if not task:
            return {'error': '缺少 task'}

        config = mm.config_cache(script_name)

        # ① 判定类别（决定要不要停用）
        #
        # ★★ 判据 = `period`（= 界面的「周期 / 临时」），**不再是 `auto_queue`** ★★
        #
        # 用户裁定: "**显示周期的不应该移除队列后回退到添加任务的池子里
        #            而是直接停用**"
        # ★ 让"界面显示的分类"与"移除行为"**同源**。
        group = config.priority_group_of(task)
        is_cycle = (group == 'timed')     # 周期任务 = period != none
        auto = is_cycle                   # 兼容字段名, 供老前端读

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

        # ③ 判据见 docstring: **周期任务**才停用（否则会被自动补齐）
        key = convert_to_underscore(task)
        node = getattr(config.model, key, None)
        if node is None:
            return {'error': f'找不到任务配置: {key}'}
        sch = getattr(node, 'scheduler', None)
        if sch is None:
            return {'error': f'{key} 没有 scheduler'}

        if is_cycle:
            sch.enable = False
            config.save()

        if is_cycle:
            msg = (f'已把周期任务「{task}」移出队列并**停用**。'
                   f'（周期任务启用后会自动回到队列, 所以必须停用才真的移除）')
        else:
            msg = (f'已把临时任务「{task}」移出队列。'
                   f'它仍在【添加任务】里, 可随时加回。')

        return {
            'ok': True,
            'task': task,
            'entry_id': entry_id,
            'removed_entries': removed_n,
            'enable': bool(sch.enable),
            # ★ 新字段（前端应读这个）; `auto_queue` 保留供老前端兼容
            'priority_group': group,
            'auto_queue': auto,
            'message': msg,
        }
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.post('/{script_name}/running/cancel')
async def post_cancel_running(script_name: str):
    """★★★ **取消正在运行的任务** —— 现在只是 `put_pause` 的**兼容别名** ★★★

    ## ★★ 用户最终裁定: 这个功能已**聚合到「暂停调度」按钮**上 ★★

    > "**就把这个功能聚合到暂停调度按钮上好了**, 点击暂停调度,
    >  正在运行的任务**自动回退到队列首位, 视作等待执行**,
    >  这样是不是更优雅。"

    ★ 是更优雅。所以:
      * 界面上**不再有**单独的「取消任务」按钮
      * 「暂停调度」按钮**自己做**"退回队首"（见 `put_pause` 的 docstring）
      * 本端点**保留**（不删）—— 供脚本/旧客户端调用, 行为与 `put_pause`
        **逐字一致**（它就直接转调 `put_pause`, 保证**只有一处实现**）

    ## 语义（与 `put_pause` 相同）

    1. **请求暂停调度**（`mode='battle'`）—— 让正在跑的在**跑完当前这场战斗**
       后于安全点停下（`TaskPaused`, 见 `module/exception.py`）
    2. **把它挪到 `run_list` 首位**（不在列表里就新建一条）
    3. ★ **`enable` 保持不动** —— **不停用**（它不是移出队列）

    ## ⚠ 一个必须让用户知道的后果（前端文案要写清）

    因为 `enable` 保持为真、且条目仍在队列里, 所以用户点「**继续**」之后
    这个任务会在**第一时间重新开始**（它就是队首）。
    ★ 也就是说: "取消" = **先停下来**（回到队首待命）, **不是**"以后都不跑了"。
    想让它以后不跑, 用队列里的「移除」（周期任务会被停用）。

    :return: 与 `put_pause` 同构（另加 `was_running` / `task` / `moved_to_front`
              三个兼容字段）
    """
    # ★★ 只转调 `put_pause` —— **不重复实现** ★★
    #
    # 为什么: 用户已把语义改为"暂停时自动退回队首"（见 `put_pause`）。
    # 若这里再写一份, 两处规则**必然分叉**（本轮刚修过同类问题:
    # `auto_queue` 与 `period` 漂移）。★ 所以这里是**薄封装**。
    res = await put_pause(script_name, mode='battle',
                          reason='取消正在运行的任务（等价于暂停）')
    if not isinstance(res, dict):
        return {'error': 'put_pause 返回异常'}
    if res.get('error'):
        return res

    task = str(res.get('requeued') or '')
    out = dict(res)
    out.update({
        'ok': True,
        'was_running': bool(task),
        'task': task,
        'moved_to_front': bool(task),
        'created_entry': bool(res.get('requeued_created_entry')),
    })
    if task:
        out['message'] = (
            f'已取消「{task}」: **暂停调度**, 并把它放回**队列首位**。\n'
            f'★ 它会**跑完当前这场战斗后**停下（不是立即打断, '
            f'否则会卡在战斗中/组队房间里）。\n'
            f'★ **未停用** —— 点「继续」后它会**第一个**重新开始。\n'
            f'（想让它以后都不跑, 请用队列里的「移除」）')
    else:
        out['message'] = '已暂停调度（当前没有正在运行的任务）'
    return out


# ============================================================ 执行顺序**配置页**
#
# 用户原话:
#   "添加**执行顺序配置页 1/2/3/……**，可以添加、删除和切换配置页"
#
# ## 语义
#
# 一页 = **一套执行顺序**（`run_list` 的快照）。★ `run_list` 永远是
# **当前生效**的那份; `profiles` 只是**存档** —— 与"切列/切筛选"那种
# UI 偏好不同, 它改的是**调度依据**。
#
# ## 为什么复用 `run_list` 的形状
#
# ★ 每页的 `entries` 就是 `run_list` 的样子（同一套 `RunEntry` 序列化）,
#   所以"应用一页"= 把 `entries` 写回 `optimization.run_list` ——
#   **复用同一个写入路径**（`Config.save_run_list`）。
#   ⚠ 本轮刚修过"两套定义打架"（`meta` vs 推荐窗口表）的教训, 不再造第二套。
#
# ## 自动保存（重要）
#
# 切换页之前会**先把当前 `run_list` 存回当前页** —— 否则用户拖了半天、
# 一切页就丢了。★ 这是"切换"语义的一部分, 由后端保证（不指望前端记得）。


#: ★ 页快照里保存的**全局开关**字段（`script.optimization` 上）。
#:
#: 用户裁定 **1甲（全都算）**: "每个页面都相当于当前的执行顺序页,
#: 包含所有的功能, 只需要当做不同的页切换"。
#:
#: ⚠ 只放**方案相关**的开关; 下面这些**故意不算**:
#:   * `screenshot_interval` / `combat_screenshot_interval` —— 设备性能参数
#:   * `task_hoarding_duration` / `close_game_wait_duration` /
#:     `close_emulator_wait_duration` —— 设备/模拟器参数
#:   * `schedule_rule` / `timed_priority` —— **已废弃**（只为读旧配置保留）
#:   * `period_backfilled` / `profiles` —— 内部标记与容器本身
SNAPSHOT_GLOBAL_FIELDS = (
    'enable_fixed',           # 启用临时任务
    'enable_timed',           # 启用周期任务
    'rest_interleave',        # 休息时可穿插周期任务
    'when_task_queue_empty',  # 队列跑空后
    'queue_mode',             # 多实例排队模式
    'queue_idle_threshold',   # 空闲阈值（queue_mode 的下游）
)

#: ★ 页快照里保存的**每任务调度**字段（每个 `scheduler` 上）。
#: ⚠ **不含** `next_run` / `windows` / `period` / `reset_at` ——
#:   那些是"这套方案怎么跑出来的**运行时排期**", 换方案时应当由目标页的
#:   自己的值决定; 而 `next_run` 尤其**不能**跨页搬（它是绝对时刻,
#:   搬过去会立刻过期或推迟）。★ 与"任务级长期开关"是两回事。
SNAPSHOT_SCHEDULER_FIELDS = (
    'enable',             # 启停
    'target',             # 次数
    'priority',           # 优先级
    'expected_minutes',   # 预期耗时
)


def _snapshot_global(config) -> dict:
    """截取当前的**全局开关**（见 `SNAPSHOT_GLOBAL_FIELDS`）。"""
    opt = getattr(getattr(config.model, 'script', None), 'optimization', None)
    out = {}
    if opt is None:
        return out
    for f in SNAPSHOT_GLOBAL_FIELDS:
        v = getattr(opt, f, None)
        # 枚举 -> 取值字符串（JSON 友好; 回写时由 pydantic 再转回枚举）
        out[f] = getattr(v, 'value', v)
    return out


def _snapshot_scheduler(config) -> dict:
    """截取**每任务**的调度字段（`{任务键: {字段: 值}}`）。"""
    out = {}
    for key, value in config.model.model_dump().items():
        if not isinstance(value, dict):
            continue
        sch = value.get('scheduler')
        if not isinstance(sch, dict):
            continue
        out[key] = {f: sch.get(f) for f in SNAPSHOT_SCHEDULER_FIELDS}
    return out


def _make_snapshot(config) -> dict:
    """★ 当前**整页**的快照（队列 + 每任务调度 + 全局开关）。"""
    return {
        'queue': [e.to_dict() if hasattr(e, 'to_dict') else e
                  for e in config.build_run_list()],
        'scheduler': _snapshot_scheduler(config),
        'global': _snapshot_global(config),
    }


def _coerce_for_field(config, keys: str, value):
    """★ 把 `value` 转成目标字段**注解要求**的类型（主要处理**枚举**）。

    ## 为什么需要它（实测踩到）

    快照里枚举存的是**取值字符串**（`'goto_main'` —— 为了 JSON 友好）。
    回写时直接 `deep_set(..., value='goto_main')` 会触发 pydantic 警告:

        Expected `enum` but got `str` with value `'goto_main'` -
        serialized value may not be as expected

    ⚠ 本项目**已多次踩同一个坑**（`TaskPeriod` 那次也是 —— 于是
      `migrate_task_period_once` 里专门包了一层 `TaskPeriod(want)`）。
      ★ 这里**统一**处理: 取字段注解, 若是 `Enum` 子类就把字符串转回枚举。
    """
    try:
        import enum

        node = config.model
        parts = keys.split('.')
        for p in parts[:-1]:
            node = getattr(node, p, None)
            if node is None:
                return value
        fields = getattr(type(node), 'model_fields', None)
        field = fields.get(parts[-1]) if isinstance(fields, dict) else None
        ann = getattr(field, 'annotation', None)
        if isinstance(ann, type) and issubclass(ann, enum.Enum):
            if isinstance(value, ann):
                return value
            return ann(str(value))
    except Exception as exc:
        logger.debug(f'类型归一化失败({keys}={value!r}: '
                     f'{type(exc).__name__}: {exc}), 原样写入')
    return value


def _apply_snapshot(config, snap: dict) -> int:
    """★ 把快照写回配置。返回写入的队列条目数。

    ## 顺序（重要）

    1. **队列** —— 走 `Config.save_run_list`（与别处同一路径）
    2. **每任务调度** —— 逐字段 `deep_set`
    3. **全局开关** —— 逐字段 `deep_set`

    ⚠ 只写快照里**存在**的键 —— 旧页（没有 `scheduler`/`global`）不会把
      现在的值清掉（向后兼容）。

    ⚠ 为什么最后**只 `save()` 一两次**: 每个 `deep_set` 之后不立刻 save,
      统一在末尾由调用方 save（避免 N 次落盘）。
    """
    from module.config.run_list import RunEntry, RunList

    snap = snap or {}
    # ---- ① 队列 ----
    raw = snap.get('queue')
    if raw is None:
        raw = snap.get('entries') or []      # ★ 旧页形状（只有顺序）
    entries = []
    for e in raw:
        if not isinstance(e, dict):
            continue
        try:
            entries.append(RunEntry.from_dict(e))
        except Exception as exc:
            logger.warning(f'配置页里有一条非法条目, 已跳过: {exc}')
    config.save_run_list(RunList(entries))

    n = len(entries)

    # ---- ② 每任务调度 ----
    sched = snap.get('scheduler')
    if isinstance(sched, dict):
        for key, fields in sched.items():
            if not isinstance(fields, dict):
                continue
            # ⚠ 只写该任务**确实存在**的键（配置里没有的任务名 -> 跳过）
            if getattr(config.model, str(key), None) is None:
                logger.info(f'配置页含未知任务 {key!r}, 已跳过')
                continue
            for f, v in fields.items():
                if f not in SNAPSHOT_SCHEDULER_FIELDS or v is None:
                    continue
                try:
                    config.model.deep_set(
                        config.model, keys=f'{key}.scheduler.{f}',
                        value=_coerce_for_field(
                            config, f'{key}.scheduler.{f}', v))
                except Exception as exc:
                    logger.warning(f'写 {key}.scheduler.{f} 失败: {exc}')

    # ---- ③ 全局开关 ----
    g = snap.get('global')
    if isinstance(g, dict):
        for f, v in g.items():
            if f not in SNAPSHOT_GLOBAL_FIELDS or v is None:
                continue
            try:
                config.model.deep_set(
                    config.model, keys=f'script.optimization.{f}',
                    value=_coerce_for_field(
                        config, f'script.optimization.{f}', v))
            except Exception as exc:
                logger.warning(f'写全局开关 {f} 失败: {exc}')

    return n


def _profiles_store(config, *, auto_create: bool = True):
    """取（并在需要时初始化）`script.optimization.profiles`。

    ## ★ 首次访问**自动建页1**（用户裁定）

    > "这个问题在问题2的前提下不存在，因为**当前的执行顺序就是页1**"

    ★ 所以没有"无页"状态: `items` 为空时，立刻把当前状态**原样快照**
      成页1 并置为 active —— 之后切页逻辑统一, 不用特判"第一次"。
    ★ 幂等: 只要 `items` 非空就跳过（不会覆盖用户后来改的页）。
    """
    opt = getattr(getattr(config.model, 'script', None), 'optimization', None)
    if opt is None:
        return None
    p = getattr(opt, 'profiles', None)
    if not isinstance(p, dict):
        p = {}
        config.model.deep_set(
            config.model, keys='script.optimization.profiles', value=p)
    p.setdefault('items', [])
    p.setdefault('active_id', '')

    if auto_create and not p['items']:
        p['items'].append({
            'id': 'p1',
            'name': '1',
            'snapshot': _make_snapshot(config),
        })
        p['active_id'] = 'p1'
        config.model.deep_set(
            config.model, keys='script.optimization.profiles', value=p)
        config.save()
        logger.info('执行顺序配置页: 首次访问, 已把当前状态建为「页1」')
    return p


def _profiles_view(config) -> list:
    """给前端的页列表（含 `active` 标记与条目数）。"""
    store = _profiles_store(config)
    if store is None:
        return []
    active = str(store.get('active_id') or '')
    out = []
    for it in (store.get('items') or []):
        if not isinstance(it, dict):
            continue
        pid = str(it.get('id') or '')
        snap = it.get('snapshot')
        if isinstance(snap, dict):
            cnt = len((snap.get('queue') or snap.get('entries') or []))
        else:
            cnt = len(it.get('entries') or [])     # ★ 旧页形状
        out.append({
            'id': pid,
            'name': str(it.get('name') or pid),
            'count': cnt,
            'active': pid == active,
        })
    return out


@schema_app.get('/{script_name}/queue/profiles')
async def get_queue_profiles(script_name: str):
    """**列出执行顺序配置页**。

    :return: {"profiles": [{id,name,count,active}], "active_id": str}
    """
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        store = _profiles_store(config)
        if store is None:
            return {'profiles': [], 'active_id': ''}
        return {'profiles': _profiles_view(config),
                'active_id': str(store.get('active_id') or '')}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc), 'profiles': []}


@schema_app.post('/{script_name}/queue/profiles')
async def post_queue_profile(script_name: str, data: dict = Body(default={})):
    """**新建一页** —— 把**当前** `run_list` 存为新页并切过去。

    :param data: {"name": "可选名字"}；不传则自动编号（1/2/3/…）
    """
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        store = _profiles_store(config)
        if store is None:
            return {'error': '配置里没有 optimization'}

        items = store['items']
        # ★ 自动编号: 找第一个没被占用的正整数
        used = {str(it.get('name')) for it in items if isinstance(it, dict)}
        n = 1
        while str(n) in used:
            n += 1
        name = str((data or {}).get('name') or n)
        pid = f'p{n}' + ('' if all(
            str(it.get('id')) != f'p{n}' for it in items) else f'_{len(items)}')

        # ★★★ 整页快照（用户裁定 1甲: "包含所有的功能"）★★★
        #
        # = 队列 + 每任务调度（启停/次数/优先级/预期耗时）+ 全局开关
        snap = _make_snapshot(config)
        items.append({'id': pid, 'name': name, 'snapshot': snap})
        store['active_id'] = pid

        config.model.deep_set(
            config.model, keys='script.optimization.profiles', value=store)
        config.save()
        n = len(snap['queue'])
        return {'ok': True, 'created': pid, 'name': name,
                'count': n,
                'profiles': _profiles_view(config),
                'message': (f'已新建配置页「{name}」'
                            f'（{n} 条队列 · 含启停/次数/全局开关）')}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.put('/{script_name}/queue/profiles/activate')
async def put_queue_profile_activate(script_name: str,
                                     data: dict = Body(...)):
    """**切换到某一页**。

    ## ★★ 两步（顺序重要, 且必须在**同一个请求**里完成）★★

    1. ★ **先把当前整页**（队列 + 每任务调度 + 全局开关）**存回当前页**
       —— 否则用户刚拖的顺序 / 刚改的启停与总开关会**丢**
    2. 再把目标页的**整页快照**写回配置

    ⚠ 不能拆成两个请求: 中途失败会留下"半新半旧"的状态（原子性）。

    ⚠ 向后兼容: 旧页只有 `entries`（纯顺序）-> 只写队列,
      调度/全局**不动**（不会把现在的值清掉）。

    :param data: {"id": "p2"}
    """
    try:
        from module.server.main_manager import mm

        pid = str((data or {}).get('id') or '').strip()
        if not pid:
            return {'error': '缺少 id'}
        config = mm.config_cache(script_name)
        store = _profiles_store(config)
        if store is None:
            return {'error': '配置里没有 optimization'}

        items = store['items']
        target = next((it for it in items
                       if isinstance(it, dict) and str(it.get('id')) == pid),
                      None)
        if target is None:
            return {'error': f'找不到配置页 {pid!r}'}

        # ★★★ ① 先把**当前整页**存回当前页（用户裁定: "切页时自动保存"）★★★
        #
        # ⚠ 这一步**必须**在载入目标页**之前** —— 否则用户刚拖的顺序
        #   / 刚改的启停与总开关会**丢**。
        # ⚠ 也**必须**在同一个请求里完成（原子）—— 不能拆成两个请求,
        #   否则中途失败会留下"半新半旧"的状态。
        cur = str(store.get('active_id') or '')
        cur_item = next((it for it in items
                         if isinstance(it, dict)
                         and str(it.get('id')) == cur), None)
        if cur_item is not None and cur != pid:
            cur_item['snapshot'] = _make_snapshot(config)

        # ★★ ② 再把目标页的**整页快照**写回配置 ★★
        snap = target.get('snapshot')
        if not isinstance(snap, dict):
            # ★ 向后兼容: 旧页只有 `entries`（纯顺序）-> 包成快照形状,
            #   队列照写, 调度/全局**不动**（不会把现在的值清掉）
            snap = {'queue': target.get('entries') or []}
        n = _apply_snapshot(config, snap)

        store['active_id'] = pid
        config.model.deep_set(
            config.model, keys='script.optimization.profiles', value=store)
        config.save()
        return {'ok': True, 'active_id': pid,
                'name': str(target.get('name') or pid),
                'count': n,
                'profiles': _profiles_view(config),
                'message': (f'已切到配置页「{target.get("name") or pid}」'
                            f'（{n} 条 · 含启停/次数/全局开关）'
                            f'；上一页已自动保存')}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.put('/{script_name}/queue/profiles/rename')
async def put_queue_profile_rename(script_name: str, data: dict = Body(...)):
    """**给配置页改名**（用户要求: "需要重命名"）。

    用户原话:
    > "添加**执行顺序配置页 1/2/3/……**，可以添加、删除和切换配置页"
    > "4：**需要重命名**"

    ★ 页名只是**显示用**（默认是自动编号 `1/2/3/…`）—— 改成
      「日常 / 周末 / 肝活动」这类有意义的名字, 一眼知道那页是干什么的。
    ★ 改名**不动**页的内容（快照原样保留）。

    :param data: {"id": "p2", "name": "周末"}
    """
    try:
        from module.server.main_manager import mm

        pid = str((data or {}).get('id') or '').strip()
        name = str((data or {}).get('name') or '').strip()
        if not pid:
            return {'error': '缺少 id'}
        if not name:
            return {'error': '名字不能为空'}
        if len(name) > 24:
            return {'error': f'名字太长（{len(name)} 字，最多 24）'}

        config = mm.config_cache(script_name)
        store = _profiles_store(config)
        if store is None:
            return {'error': '配置里没有 optimization'}

        target = next((it for it in (store.get('items') or [])
                       if isinstance(it, dict)
                       and str(it.get('id')) == pid), None)
        if target is None:
            return {'error': f'找不到配置页 {pid!r}'}

        old = str(target.get('name') or pid)
        target['name'] = name
        config.model.deep_set(
            config.model, keys='script.optimization.profiles', value=store)
        config.save()
        return {'ok': True, 'id': pid, 'name': name,
                'profiles': _profiles_view(config),
                'message': f'已把配置页「{old}」改名为「{name}」'}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.delete('/{script_name}/queue/profiles/{profile_id}')
async def delete_queue_profile(script_name: str, profile_id: str):
    """**删除一页**。★ 至少要留一页（否则用户就没有可切换的了）。"""
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        store = _profiles_store(config)
        if store is None:
            return {'error': '配置里没有 optimization'}
        items = store['items']
        kept = [it for it in items
                if not (isinstance(it, dict)
                        and str(it.get('id')) == profile_id)]
        if len(kept) == len(items):
            return {'error': f'找不到配置页 {profile_id!r}'}
        if not kept:
            return {'error': '至少要保留一个执行顺序配置页'}
        store['items'] = kept
        if str(store.get('active_id') or '') == profile_id:
            store['active_id'] = str(kept[0].get('id') or '')
        config.model.deep_set(
            config.model, keys='script.optimization.profiles', value=store)
        config.save()
        return {'ok': True, 'removed': profile_id,
                'active_id': str(store.get('active_id') or ''),
                'profiles': _profiles_view(config),
                'message': '已删除该配置页（未改动当前执行顺序）'}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


# ============================================================ 窗口 CRUD（S4）
#
# 设计: `docs/scheduler-architecture.md` §5.1。
# ★ **按 `id`** 定位（"身份不是位置" —— 踩过按下标删错条目）。

def _windows_of(config, task: str):
    """取某任务的 `windows` 列表（`[{...}]`）与 `scheduler` 对象。

    :return: `(scheduler_obj, [窗口dict...])`; 任务不存在时 `(None, None)`
    """
    from module.config.config_model import convert_to_underscore
    key = convert_to_underscore(task)
    node = getattr(config.model, key, None)
    if node is None:
        return None, None
    sch = getattr(node, 'scheduler', None)
    if sch is None:
        return None, None
    ws = [w.model_dump() if hasattr(w, 'model_dump') else dict(w)
          for w in (getattr(sch, 'windows', None) or [])]
    return sch, ws


def _to_task_window(item: dict, *, new_id: bool = False):
    """把 dict 转成 `TaskWindow`（**显式**校验 + 类型正确）。

    ★ 必须先转: `sch.windows = [dict, ...]` 时 pydantic v2 **默认不在赋值时
      校验** -> 列表里躺着 dict -> 序列化警告
      （`Expected TaskWindow but got dict`, 实测踩过）。
    """
    from tasks.Component.config_scheduler import TaskWindow
    return TaskWindow.model_validate(_normalize_window(item, new_id=new_id))


def _normalize_window(item: dict, *, new_id: bool = False) -> dict:
    """把前端传来的一条窗口**规范化**（补 id / 补默认）。

    ★ 不做业务校验（交给 pydantic `TaskWindow`）—— 这里只保证"有 id"。
    """
    import uuid
    d = dict(item or {})
    if new_id or not str(d.get('id') or '').strip():
        d['id'] = uuid.uuid4().hex[:8]
    return d


@schema_app.get('/{script_name}/tasks/{task}/windows')
async def get_task_windows(script_name: str, task: str):
    """查某任务的**窗口列表**。"""
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        sch, ws = _windows_of(config, task)
        if sch is None:
            return {'error': f'找不到任务 {task!r}'}
        return {'script': script_name, 'task': task, 'windows': ws,
                'count': len(ws)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


def _require_period_for_windows(config, task: str):
    """★★★ 窗口的**前置条件**: 任务的周期不能是「不限」（用户裁定）★★★

    ## 用户原话

    > "**窗口必须在选了周期后才能设置。这样子判断依据就可以按有没有周期来
    >  判断**"

    ★ 也就是: `scheduler.period == 'none'`（不限 = **临时任务**）**不允许新增窗口**。
      这样"分类判据（有没有周期）"与"窗口能不能配"**说的是同一件事** ——
      不会再出现"有窗口却算临时"的矛盾。

    ## 为什么**只在新增时**拦（已存在的窗口不拦）

    ★ 用户的配置里**已经有**一批"有窗口但 period=none"的任务
      （逢魔/道馆/狩猎战/阴界之门/神秘商店/经验妖怪/金币妖怪/章鱼 ——
       本轮已按窗口规律给它们补上了周期）。
    ★ 但**别的账号/别的任务**可能还有历史窗口。若在"编辑/保存"时无条件拦,
      用户会被**锁死**（连删都改不了）—— 那不是约束, 是砖。

    ★ 所以规则是:
      * **新增**窗口（`POST`, 或 `PUT` 里出现了**新 id**）-> 必须 `period != none`
      * **编辑已有**窗口（id 集合不变）-> 放行
      * **删除**窗口 -> 放行（否则用户删不掉）

    :return `None` 表示允许; 否则返回**错误文案**
    """
    try:
        period = config.task_period(task)
    except Exception as exc:
        logger.warning(f'判 {task} 的周期失败({type(exc).__name__}: {exc}), '
                       f'放行窗口操作')
        return None
    if period != 'none':
        return None
    return (f'「{task}」的周期是「不限」（= 临时任务）—— '
            f'**请先在调度器的「周期」里选每天/每周/每月**, 之后才能设置窗口。\n'
            f'★ 理由: 窗口是"这个周期里的哪几段时刻能跑"; 没有周期就没有'
            f'可依附的周期边界。')


@schema_app.put('/{script_name}/tasks/{task}/windows')
async def put_task_windows(script_name: str, task: str,
                           windows: list = Body(...)):
    """**整单替换**窗口列表（前端列表编辑器一次提交全部）。

    ★ 为什么也提供整单替换: 前端编辑多条后一次保存最简单可靠,
      也避免"改到一半只写了一半"的中间态（与 `PUT run_list` 同理）。
    ★ `id` 缺失的项会自动补 —— 前端新增行可以不生成 id。

    ★ 约束: **只在新出现 id（= 新增窗口）时**要求 `period != 'none'`;
      纯粹编辑已有窗口放行（见 `_require_period_for_windows`）。
    """
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        sch, before = _windows_of(config, task)
        if sch is None:
            return {'error': f'找不到任务 {task!r}'}
        # ★ 先转 `TaskWindow`（显式校验 + 类型正确）
        cleaned = [_to_task_window(w) for w in (windows or [])]
        # ★ 判"是不是新增": 提交里出现了原先没有的 id
        old_ids = {str(w.get('id')) for w in before if w.get('id')}
        new_ids = {str(w.id) for w in cleaned if w.id}
        adding = bool(new_ids - old_ids)
        if adding:
            err = _require_period_for_windows(config, task)
            if err:
                return {'error': err, 'needs_period': True}
        sch.windows = cleaned
        config.save()
        _, ws = _windows_of(config, task)
        return {'ok': True, 'script': script_name, 'task': task,
                'windows': ws, 'count': len(ws)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.post('/{script_name}/tasks/{task}/windows')
async def post_task_window(script_name: str, task: str,
                           window: dict = Body(...)):
    """**新增**一条窗口（后端生成 `id`）。

    ★ 约束: `period != 'none'` 才允许（用户裁定: "窗口必须在选了周期后才能设置"）。
    """
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        sch, _ = _windows_of(config, task)
        if sch is None:
            return {'error': f'找不到任务 {task!r}'}
        # ★★ 新增窗口的前置条件: 必须已经选了周期
        err = _require_period_for_windows(config, task)
        if err:
            return {'error': err, 'needs_period': True}
        item = _to_task_window(window, new_id=True)
        sch.windows = list(getattr(sch, 'windows', None) or []) + [item]
        config.save()
        _, ws = _windows_of(config, task)
        return {'ok': True, 'added': item.model_dump(), 'windows': ws, 'count': len(ws)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.put('/{script_name}/tasks/{task}/windows/{window_id}')
async def put_task_window(script_name: str, task: str, window_id: str,
                          window: dict = Body(...)):
    """**改**一条窗口（**按 `id`**）。

    ★ **不**要求周期 —— 这是**编辑已有窗口**, 拦了用户就改不动了
      （连把历史窗口改对都不行）。见 `_require_period_for_windows`。
    """
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        sch, ws = _windows_of(config, task)
        if sch is None:
            return {'error': f'找不到任务 {task!r}'}
        idx = next((i for i, w in enumerate(ws)
                    if str(w.get('id')) == window_id), None)
        if idx is None:
            return {'error': f'找不到窗口 id={window_id!r}'}
        item = _to_task_window(window)
        item.id = window_id                       # ★ id 不可改
        ws[idx] = item
        sch.windows = ws
        config.save()
        _, after = _windows_of(config, task)
        return {'ok': True, 'updated': item.model_dump(), 'windows': after,
                'count': len(after)}
    except Exception as exc:
        logger.exception(exc)
        return {'error': str(exc)}


@schema_app.delete('/{script_name}/tasks/{task}/windows/{window_id}')
async def delete_task_window(script_name: str, task: str, window_id: str):
    """**删**一条窗口（**按 `id`**）。

    ★ **不**要求周期 —— 否则"周期是不限"的任务连窗口都删不掉。
    """
    try:
        from module.server.main_manager import mm
        config = mm.config_cache(script_name)
        sch, ws = _windows_of(config, task)
        if sch is None:
            return {'error': f'找不到任务 {task!r}'}
        kept = [w for w in ws if str(w.get('id')) != window_id]
        if len(kept) == len(ws):
            return {'error': f'找不到窗口 id={window_id!r}'}
        sch.windows = kept
        config.save()
        _, after = _windows_of(config, task)
        return {'ok': True, 'removed': window_id, 'windows': after,
                'count': len(after)}
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
                if meta is None or not _auto_queue_of(meta, config):
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
              count, effective_target}], "count": n}
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
            if _auto_queue_of(meta, config):
                continue            # 自动进队列的 -> 不该出现在这里

            out.append({
                'command': command,
                'name': key,
                'name_zh': meta.name_zh,
                'category': meta.category.value,
                'category_label': TC.CATEGORY_LABEL.get(
                    meta.category, meta.category.value),
                'count': meta.count_default,
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

    ## ★★ 实机验收修复: 重置**必须同时清掉失败冷却** ★★

    ★ 用户原话: "契灵之境运行失败后的冷却状态**应该只在连续运行时生效**,
      我都打断过了重新添加了, 还显示在冷却中, **即使我重置了契灵之境**!"

    **根因**: 「重置」只调 `run_record.reset_many()` —— 那是**运行记录**
    （`log/.run_record.json`）; 而**失败冷却**在**另一个文件**
    （`log/.failure_state.json`, `failure_state`）里, **没人清**。
    -> 用户重置了, 冷却**照旧倒计时**。

    ★ 语义上也**应该**清: 「连续失败」的"连续"以**一次不间断的运行**
      为单位; 用户主动**重置**就是明确表示"我修好了, 重新开始数"
      —— 这正是 `failure_state.clear()` 的用途（它的 docstring 写着
      "供界面'我修好了, 让我立刻重试'用"）。

    ★ 失败**不影响** `archived_rounds` 的返回（清冷却失败也不该让整批失败）。
    """
    try:
        from module.config import failure_state, run_record

        names = [str(t) for t in (tasks or []) if t]
        archived = run_record.reset_many(script_name, names)
        # ★ 同时解除这些任务的失败冷却 **并把 `next_run` 拉回现在**
        #
        # ★★ 为什么还要改 `next_run`（实机验收发现的真 bug）★★
        #
        # 用户原话: "**契灵之境为什么显示等待到点?** 这个是次数任务,
        #   不应该有[还未到点]这种[拥有 window 的任务类]的属性啊"
        #
        # **根因**: 进冷却时 `script.py:846-850` 会
        #   ```python
        #   self.config.task_delay(task, success=False, server=True,
        #                          target=res['cooldown_until'])
        #   ```
        #   -> 把 `next_run` **写成冷却结束时刻**（实测 `18:44:00`）。
        #
        # ★ 于是**只清失败记录是不够的**: `next_run` 还停在冷却结束时那一刻,
        #   而该任务的 `period=none`（没有周期 -> **没有任何东西会重排它**）
        #   -> **永久**卡在"等待到点", 界面就显示成一个次数任务却"未到点"。
        #
        # ★ 修法: 清了冷却就把 `next_run` 设成**现在**（"立刻可以跑"）。
        #   这正是"清除失败"按钮语义的一部分 ——
        #   `failure_state.clear()` 的 docstring 写着
        #   "供界面'我修好了, 让我立刻重试'用", **"立刻"就该包括 next_run**。
        from module.server.main_manager import mm
        _cfg = mm.config_cache(script_name)
        for n in names:
            try:
                failure_state.clear(script_name, n)
            except Exception as exc:
                logger.warning(f'清失败冷却失败({n}): {exc}')
            try:
                _cfg.scheduler_next_run_now(n)
            except Exception as exc:
                logger.warning(f'恢复 {n} 的 next_run 失败: {exc}')
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

    ## ★★ 实机验收修复: 还要把 `next_run` 拉回现在 ★★

    ★ 光清失败记录**不够** —— 进冷却时 `script.py` 把 `next_run` 写成了
      **冷却结束时刻**; 而 `period=none` 的任务**没有任何东西会重排它**
      -> 会**永久**显示"等待到点"（用户实测: 契灵之境）。

    ★ 所以"立刻重试"必须**两件事都做**: 清记录 + 把 `next_run` 拉回现在。
    """
    try:
        from module.config import failure_state
        from module.server.main_manager import mm

        failure_state.clear(script_name, task or None)
        # ★ 把 `next_run` 拉回现在（否则仍会显示"等待到点"）
        if task:
            try:
                mm.config_cache(script_name).scheduler_next_run_now(task)
            except Exception as exc:
                logger.warning(f'恢复 {task} 的 next_run 失败: {exc}')
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
    **暂停调度**。

    :param mode: `battle`(默认, ⏸ 跑完当前这场战斗) 或 `round`(⏭ 本轮跑完再停)
    :param reason: 可选备注(便于排障: 谁在什么时候暂停的)

    ⚠ 语义: 立即置位, 但脚本会在**安全点**(战斗 + 结算 + 领奖完成)才停 ——
    这样不会卡在半途(战斗中 / 组队房间中)。**不提供"立即停"**: 不安全。

    ## ★★★ 暂停时会把**正在运行的任务退回队列首位**（用户裁定）★★★

    用户原话:
    > "**就把这个功能聚合到暂停调度按钮上好了**, 点击暂停调度,
    >  正在运行的任务**自动回退到队列首位, 视作等待执行**, 这样是不是更优雅。"

    ★ 是更优雅 —— 它让"暂停"成为一个**完整的动作**:
      停手（不派发新任务）+ 手头这个**退回队首待命**。
    于是界面上**不再需要**单独的「取消任务」按钮（那个语义与暂停重复）。

    ## 为什么"退回队首"是安全的（不会又跑起来）

    ★ 顺序: **先置暂停** -> `is_paused()` 立刻为真。
    正在跑的任务在安全点停下（`TaskPaused`）后, 调度循环回到
    `_handle_run_control()`, 那里 `while is_paused(): sleep` **阻塞等待**
    -> **不会**把队首刚退回的这个任务又派发一遍。
    ★ 用户点「继续」后, 它在**队首**第一个跑（"视作等待执行"）。

    ## 不停用

    ★ **不动 `enable`** —— 它不是移出队列, 只是"退回去等着"。
      想让它以后都不跑, 用队列里的「移除」（周期任务会被停用）。

    :return: 暂停状态 + `requeued`（退回了哪个任务, 没在跑则空）
    """
    try:
        from module.config import run_control
        from module.config.config_model import convert_to_underscore
        from module.config.run_list import RunEntry, RunList
        from module.server.main_manager import mm
        if mode not in (run_control.PAUSE_BATTLE, run_control.PAUSE_ROUND):
            return {'error': f'非法 mode: {mode!r}; 应为 battle / round'}

        # ① 先置暂停（顺序关键 —— 见 docstring）
        st = run_control.request_pause(mode=mode, reason=reason)

        # ② 把正在运行的任务退回 `run_list` 首位
        requeued = ''
        created = False
        requeue_err = ''
        try:
            config = mm.config_cache(script_name)
            task = str(getattr(config.model, 'running_task', '') or '').strip()
            # ★★★ P-1: **优先按 `entry_id` 精确匹配**（用户裁定）★★★
            #
            # > "点击暂停调度, 正在运行的任务**自动回退到队列首位, 视作等待执行**"
            #
            # ## 为什么不能只按任务名找（实测踩到）
            #
            # 队列里同一任务可以有**多条条目**（用户用重复条目表达
            # "重复跑整个任务"）。实测:
            #   队列 = [Exploration(e1), Orochi(e2), Exploration(e3)]
            #   正在跑 e3（第 2 条 Exploration）
            #   ★ 只按任务名 -> `next(...)` 命中 **e1** -> **退错那一条**。
            #
            # ## 身份从哪来
            #
            # `script.py` 在任务开始运行时把 `self.config.task.entry_id`
            # 落盘到 `model.running_entry_id`（脚本在独立进程, HTTP 端
            # 拿不到内存 -> **必须落盘**）。
            #
            # ⚠ **向后兼容**: 老配置 / 拿不到 `entry_id` 时 -> 退回按任务名找
            #   （那时的行为与改动前**完全一致**, 不会更糟）。
            if task:
                rl = config.build_run_list()
                entries = list(rl)
                # ★ 内存里的 `config.task` 最权威（与脚本同进程时可用）;
                #   跨进程时用落盘的 `running_entry_id`。
                eid = str(getattr(config.model, 'running_entry_id', '') or '').strip()
                if not eid:
                    try:
                        eid = str(getattr(config.task, 'entry_id', '') or '').strip()
                    except Exception:
                        eid = ''

                idx = None
                if eid:
                    idx = next((i for i, e in enumerate(entries)
                                if str(getattr(e, 'entry_id', '') or '') == eid
                                and getattr(e, 'task', None) == task), None)
                    if idx is None:
                        logger.info(f'按 entry_id={eid!r} 没找到条目 -> '
                                    f'退回按任务名 {task!r} 找（向后兼容）')
                if idx is None:
                    idx = next((i for i, e in enumerate(entries)
                                if getattr(e, 'task', None) == task), None)

                if idx is None:
                    entries.insert(0, RunEntry(task=task))
                    created = True
                elif idx != 0:
                    entries.insert(0, entries.pop(idx))
                if idx != 0:
                    if not config.save_run_list(RunList(entries)):
                        requeue_err = 'save_run_list 返回 False（见日志）'
                requeued = task
                # ★ P-1: "退回队首"= 视作**等待执行** —— 显式把 `next_run`
                #   拉回现在, 不依赖"别处顺手修"（见 P-1 记录:
                #   `Config.__init__` 的修坏值机制**恰好**也会做这件事,
                #   但那是**巧合**, 不该由它承担语义）。
                try:
                    if config.scheduler_next_run_now(task):
                        logger.info(f'「{task}」的 next_run 已拉回现在'
                                    f'（视作等待执行）')
                except Exception as exc:
                    logger.debug(f'拉回 next_run 失败({type(exc).__name__}: {exc})')
        except Exception as exc:
            requeue_err = f'{type(exc).__name__}: {exc}'
            logger.exception(exc)

        out = dict(st) if isinstance(st, dict) else {'paused': True}
        out.update({
            'requeued': requeued,
            'requeued_created_entry': created,
            'requeue_error': requeue_err,
        })
        if requeued and not requeue_err:
            out['message'] = (
                f'已暂停调度。「{requeued}」已**退回队列首位**, 视作等待执行 —— '
                f'它会**跑完当前这场战斗后**停下。\n'
                f'★ **未停用**: 点「继续」后它第一个跑。\n'
                f'（想让它以后都不跑, 请用队列里的「移除」）')
        return out
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


# ★★★ P-3b: 「重置循环计数」按钮（用户裁定 乙）★★★
#
# 用户原话:
# > "如果要重跑这几次循环要怎么设置呢，我没想好，
# >  是不是得有个**手动重置计数到设定值的按钮**"
# > -> 用户选 **乙**: ★ 加一个「重置循环计数」按钮
#
# ★ 语义: 把"**已经跑了几轮**"清 0 -> 于是又能跑满 `loop_times` 轮。
#
# ⚠ 为什么是"清 0"而不是"设成 `loop_times`":
#   计数是"已经跑了几轮" —— 清 0 = "一轮都还没跑" = 可以再跑 N 轮。
#   "设成 N" 会让 `已跑 >= 目标` 仍然成立 -> **还是不会跑**（是反的）。
@schema_app.put('/{script_name}/run_control/loop_reset')
async def put_loop_reset(script_name: str):
    """★ **重置队列循环计数** —— 让"跑 N 轮"可以再来一次。

    配合 `script.optimization.when_task_queue_empty == 'loop'` 使用:
      * `loop_times = 0` -> 一直跑（本端点无影响）
      * `loop_times = N` -> 跑满 N 轮后停止循环；★ 点这里清 0 后可再跑 N 轮
    """
    try:
        from module.config import task_state
        from module.server.main_manager import mm
        # ★ 先确保配置存在（拿不到也不致命 —— 计数是全局状态）
        try:
            mm.config_cache(script_name)
        except Exception:
            pass
        before = task_state.get_loop_rounds(script_name)
        task_state.reset_loop_rounds(script_name)
        after = task_state.get_loop_rounds(script_name)
        return {'script': script_name, 'reset': True,
                'before': before, 'rounds': after,
                'message': f'循环计数已重置（{before} -> {after}）—— '
                           f'可以重新跑设定的轮数'}
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
