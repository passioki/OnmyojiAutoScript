# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum

# ★ S3: `TaskWindow` 是 pydantic 模型（进 JSON / 进 schema）
from typing import List

from pydantic import AliasChoices, BaseModel, Field

from module.logger import logger
from tasks.Component.config_base import ConfigBase, TimeDelta, DateTime, Time


class TaskPeriod(str, Enum):
    """
    任务完成周期。

    - NONE   : 不启用完成记忆, 行为与改造前完全一致(用 next_run + success_interval)
    - DAILY  : 本(游戏)日已成功完成 -> 不再入队; 跨日自动失效
    - WEEKLY : 本(游戏)周已成功完成 -> 不再入队; 跨周自动失效

    周期边界按 reset_at(游戏重置时间, 默认 05:00)计算, 因此在 04:00 仍算作前一天。
    """
    NONE = 'none'
    DAILY = 'daily'
    WEEKLY = 'weekly'
    # ★ 与 `resource.Period` 对齐（用户要求"每月以此类推"）
    MONTHLY = 'monthly'


class WindowPeriod(str, Enum):
    """**窗口周期** —— 每天 / 每周 / 每月（用户裁定）。

    ## 用户原话

    > "窗口开始: 下拉选择：每天、每周、每月 / 下拉选择：时:分、周几：时：分、几号：时：分"

    ## ★ 为什么**两端共用**一个

    用户裁定窗口语义是 **(B) 两端必须同周期** —— 所以"开始"和"结束"共用一个
    `window_period`, 不各自带一个（那会表达出不存在的语义）。
    """

    DAILY = 'daily'
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'


# ★★★ 一次性窗口迁移（用户要求: "帮我配好窗口" + "适配好现有的软件"）★★★
#
# 用户裁定的"推荐窗口":
#
#   Restart        window_slots = '12:00,20:00'   -> 12:00-14:00 + 20:00-22:00
#                  （每天两次领体力; 用户原话: "(a) Restart 用两个窗口段"）
#   RyouToppa      window_slots = '07:00'         -> 07:00-09:00
#                  （用户原话: "RyouToppa也同理"）
#   GuildBanquet   **不设** —— 它用 `days_from_config` 引用宴会日
#                  （周三/周六 19:00 来自 `guild_banquet_time`）
#
# ★ 只做**一次**: 用配置顶层的 `_window_migration` 标记。
#   否则每次启动都会覆盖用户在界面上改的窗口（本会话踩过这个坑）。
# ★ S3: 推荐窗口 —— 用 **(start, end) 字符串对**表达（`windows` 里的两项）
RECOMMENDED_WINDOWS = {
    # ★ `restart`: **两个窗口** = 一天两次领体力（12:00-14:00 / 20:00-22:00）
    #   用户原话: "一天跑两次 = 两个窗口"
    'restart': ((12, 0), (20, 0)),
    # 'ryou_toppa': **一个窗口** 07:00-09:00（用户原话: "RyouToppa 也同理"）
    'ryou_toppa': ((7, 0),),
}

# ★ 每个时刻的窗口跨度（分钟）—— 只在迁移 `window_slots` 时用
_SLOT_SPAN_MINUTES = 120

# 推荐窗口的具体起止（由 `RECOMMENDED_WINDOWS` 的起点 + 跨度算出）
RECOMMENDED_SECONDS = {
    'restart': (('12:00:00', '14:00:00'), ('20:00:00', '22:00:00')),
    'ryou_toppa': (('07:00:00', '09:00:00'),),
}


def apply_recommended_windows(node_map: dict) -> list:
    """给 `node_map`（`{任务键: 节点dict}`）里**未迁移过**的任务配好窗口。

    ## 迁移（S3）

    旧的**单值**窗口字段 -> **一条** `windows` 项:
      `window_enable` / `window_start` / `window_end` / `window_days` /
      `window_period` / `window_dom` / **`window_slots`**

    ★ `window_slots`（我此前的绕法, 用户已裁定**废弃**）会被折成
      **多个窗口**（每个时刻一段, 跨度 `_SLOT_SPAN_MINUTES`）——
      这正是"**一天跑两次 = 两个窗口**"的正确表达。

    ## 推荐值（用户裁定）

    | 任务 | 窗口 |
    |---|---|
    | `restart` | **两个**: 12:00-14:00 与 20:00-22:00（每天两次领体力）|
    | `ryou_toppa` | **一个**: 07:00-09:00 |
    | `guild_banquet` | **不设**（`meta.py` 用 `days_from_config` 引用宴会日）|

    ★ 幂等: `windows` 非空 -> 已迁移, 跳过（不能每次启动都覆盖用户设置）。
    """
    import uuid as _uuid
    from datetime import time as _time

    def _wid() -> str:
        return _uuid.uuid4().hex[:8]

    def _to_time(v, default):
        if isinstance(v, _time):
            return v
        try:
            return _time.fromisoformat(str(v))
        except Exception:
            return default

    changed = []
    for key, slots in RECOMMENDED_WINDOWS.items():
        node = node_map.get(key)
        if not isinstance(node, dict):
            continue
        sch = node.get('scheduler')
        if not isinstance(sch, dict):
            continue
        # ★ 幂等: 已有 windows -> 用户配过或已迁移, 不动
        if sch.get('windows'):
            continue

        # ① 先把**旧的单值 / `window_slots`** 折成 windows
        migrated = []
        old_slots = str(sch.get('window_slots') or '').strip()
        if old_slots:
            for part in old_slots.split(','):
                part = part.strip()
                if not part:
                    continue
                try:
                    hh, mm = part.split(':')
                    st = _time(hour=int(hh), minute=int(mm))
                except Exception:
                    continue
                m = st.hour * 60 + st.minute + _SLOT_SPAN_MINUTES
                m = min(m, 23 * 60 + 59)
                migrated.append({
                    'id': _wid(), 'enabled': True, 'period': 'daily',
                    'start': st.strftime('%H:%M:%S'),
                    'end': _time(hour=m // 60, minute=m % 60).strftime('%H:%M:%S'),
                    'days': '', 'days_of_month': '',
                })
        elif sch.get('window_enable'):
            # ⚠ `window_period` 可能是**枚举**, 也可能是**字符串**
            #   （`model_dump()` 给枚举, 旧 JSON 给字符串）。
            #   ★ 不能写 `getattr(x, 'value', 'daily')` —— 对**字符串**它会
            #     返回默认值 `'daily'`，把真实的 `'weekly'` **吞掉**（我踩过）。
            _wp = sch.get('window_period')
            migrated.append({
                'id': _wid(), 'enabled': True,
                'period': str(getattr(_wp, 'value', _wp) or 'daily').lower(),
                'start': _to_time(sch.get('window_start'),
                                  _time(17, 0)).strftime('%H:%M:%S'),
                'end': _to_time(sch.get('window_end'),
                                _time(23, 0)).strftime('%H:%M:%S'),
                'days': str(sch.get('window_days') or ''),
                'days_of_month': str(sch.get('window_dom') or ''),
            })

        # ② 用户没配过 -> 给推荐值（两个窗口 = 一天两次）
        if not migrated:
            for st, en in RECOMMENDED_SECONDS.get(key, ()):
                migrated.append({
                    'id': _wid(), 'enabled': True, 'period': 'daily',
                    'start': st, 'end': en, 'days': '', 'days_of_month': '',
                })

        if not migrated:
            continue
        sch['windows'] = migrated
        # ③ 删掉被替代的旧字段（避免"两个来源"）
        for dead in ('window_enable', 'window_start', 'window_end',
                     'window_days', 'window_period', 'window_dom',
                     'window_slots'):
            sch.pop(dead, None)
        changed.append(key)
    return changed


class TaskWindow(BaseModel):
    """**一个开放窗口**（原子实体, 有稳定 `id`）。

    设计依据: `docs/scheduler-architecture.md` §1.1。

    ## 用户裁定

    > "不是 window slots, 而是**设置多个 window**！"
    > "一天跑两次 = **两个窗口**"

    ## 字段

    | 字段 | 含义 |
    |---|---|
    | `id` | **稳定身份**（增删改都按它, 不按下标 —— "身份不是位置"）|
    | `enabled` | 这一段是否生效（合起来取并集）|
    | `period` | **每天 / 每周 / 每月**（两端**共用**, 落实 (B)）|
    | `start` / `end` | 起止**时刻**（可跨午夜, `end < start` 即跨夜）|
    | `days` | `period=weekly` 时的**周几**（0=周一 … 6=周日）；空 = 全周 |
    | `days_of_month` | `period=monthly` 时的**几号**（1-31）；空 = 整月 |

    ★ 与 `AvailabilityWindow`（`module/config/availability.py`）的分工:
      那个是**纯逻辑**的判定对象（无 pydantic 依赖, 便于单测）;
      这个是**持久化**模型（进 JSON / 进 schema）。转换见
      `Scheduler.to_availability()`。
    """

    id: str = Field(default='', description='窗口标识')
    enabled: bool = Field(default=True, description='启用这一段')
    period: WindowPeriod = Field(
        default=WindowPeriod.DAILY, description='窗口周期')
    start: Time = Field(
        default=Time(hour=17, minute=0, second=0), description='开始时刻')
    end: Time = Field(
        default=Time(hour=23, minute=0, second=0), description='结束时刻')
    # 周几: 逗号分隔 0-6（周一=0）; 空 = 全周
    days: str = Field(default='', description='开放星期')
    # 几号: 逗号分隔 1-31; 空 = 整月
    days_of_month: str = Field(default='', description='开放几号')


class Scheduler(ConfigBase):
    """
    ## ★★ 用户配置面 vs 内部排期字段 ★★

    `Scheduler` 里混着**两类**东西, 必须分清:

    | 类别 | 字段 | 谁能改 |
    |---|---|---|
    | **用户配置** | `enable` / `priority` / `target` / `expected_minutes` | 用户 |
    | **内部排期状态** | `next_run` / `success_interval` / `failure_interval` / `period` / `reset_at` / `server_update` / `delay_date` / `float_time` / `window_*` | **不由用户直接填** |

    ### 为什么内部字段仍在模型里

    `task_delay()` 要把算出来的 `next_run` **落盘**, 重启后才知道"下次什么时候跑";
    `_skip_by_period()` 要读 `period`/`reset_at`。所以它们**必须存在**。

    ### 但它们**不该出现在界面上**

    台账 10.7/7.7 声称"用户配置面 10 → 3 个字段", 实际界面上**16 个字段全暴露**
    （虚报, 见 `docs/SESSION-LEDGER.md` §0.2）。用户面对 `success_interval` /
    `window_*` / `next_run` 这类字段无从下手 —— 它们要么是**游戏机制**
    （已收进各任务 `meta.py` 的 `Resource` / `window`）, 要么是**软件内部状态**。

    做法: 给内部字段打 `json_schema_extra={'internal': True}`,
    `config_model.script_task()` 生成界面字段时**跳过**它们
    （与既有的 `0xABCDEF` 排除机制同一处）。
    这样**不删字段**（`task_delay` 照常读写）, 只是**不再让用户看到**。
    """

    # ---------------- 用户配置 ----------------
    enable: bool = Field(default=False, description='enable_help')
    priority: int = Field(default=5, description='priority_help')

    # ---------------- 内部排期状态（界面隐藏）----------------
    next_run: DateTime = Field(
        default=DateTime.fromisoformat("2023-01-01 00:00:00"),
        description='next_run_help',
        json_schema_extra={'internal': True})

    # ★★ #4c: `success_interval` **已删除**（2026-10-10）★★
    #
    # 它曾表达"成功后再隔多久跑一次"—— 也就是**用户轮询节奏**。
    # 用户裁定（§20.2）: "排期应该是用具体的 **window** 来算" ——
    # 于是 `task_delay()` 的成功路径改为**窗口兜底**（§21.5）,
    # 没有任何执行代码再读它。
    #
    # ⚠ 与 `failure_interval` -> `retry_interval` 的改名**不同**:
    #   那个要保旧配置的值（用户覆盖不能丢）-> 用了 `validation_alias`;
    #   这个是**彻底不用** -> 旧 JSON 里的键会被 pydantic 静默忽略
    #   （`extra='ignore'`）, **这是预期的**。
    # ★★ 台账 7.3: `failure_interval` → `retry_interval` ★★
    #
    # 为什么改名: 它的语义是"**失败后隔多久重试**"（退避重试）,
    # 与"资源补充"无关（台账 7.6「次数与冷却解耦」）。旧名 `failure_interval`
    # 容易与 `success_interval`(轮询节奏) 混淆。
    #
    # ## ★ 为什么必须带 `validation_alias`
    #
    # `Scheduler.model_config = {}` -> pydantic v2 **默认 `extra='ignore'`**。
    # 实测: 给改名后的模型传旧键 `failure_interval`, **不报错、也不生效**
    # —— 会被静默忽略, 于是**磁盘上 54 个配置里的该字段全部失效**。
    #
    # 影响不只是"回落默认值": **8 个任务覆盖了它**
    # （`KekkaiActivation` 10 小时 · `KekkaiUtilize`/`TalismanPass` 6 小时 ·
    #  `FloatParade`/`Secret`/`WeeklyTrifles` 3~7 天 …）——
    # 静默忽略会让它们的失败重试节奏**悄悄变成默认 1 天**。
    #
    # `validation_alias` 让**读**时接受旧名（不用迁移任何配置文件）。
    #
    # ★ **不设 `serialization_alias`** —— 让写到磁盘时用**新名**
    #   `retry_interval`。这样旧配置在第一次 `save()` 后**自然迁移**到新名,
    #   不需要单独的迁移脚本。（设了 `serialization_alias` 会让 dump 出旧名,
    #   旧名永远留着 —— 实测 `model_dump()` 的键会变成 `failure_interval`。）
    retry_interval: TimeDelta = Field(
        default=TimeDelta(days=1), description='retry_interval_help',
        validation_alias=AliasChoices('retry_interval', 'failure_interval'),
        json_schema_extra={'internal': True})
    server_update: Time = Field(
        default=Time(hour=9, minute=0, second=0), description='server_update_help',
        json_schema_extra={'internal': True})
    delay_date: int = Field(
        default=1, description='delay_date_help', ge=1, le=31,
        json_schema_extra={'internal': True})
    float_time: Time = Field(
        default=Time(hour=0, minute=0, second=0), description='float_time_help',
        json_schema_extra={'internal': True})

    # 完成记忆。默认 none -> 新字段不改变既有行为
    period: TaskPeriod = Field(
        default=TaskPeriod.NONE, description='period_help')
    # 周期边界(游戏每日重置时刻)。阴阳师以凌晨 0 点为界, 故默认为 00:00
    reset_at: Time = Field(
        default=Time(hour=0, minute=0, second=0), description='reset_at_help',
        json_schema_extra={'internal': True})

    # ------------------------------------------------------------------ 开放时段
    #
    # 阴阳师很多玩法**不是随时能做**, 而有固定开放时段(如逢魔之时 17:00-23:00)。
    # 此前软件没有这个概念, 用户只能把 success_interval 设短(如 1 小时)让任务
    # **频繁醒来碰运气** —— 于是"用户轮询节奏"混进了本该表达游戏机制的字段。
    #
    # 这里把游戏时段显式建模为**硬约束**: 不在时段内一律不跑。
    #
    # 设计约束:
    #   * **不写死任何时段** —— 全部由用户填写; 默认关闭(不限时段),
    #     因此新增字段**不改变既有行为**。
    #   * 支持**跨午夜**(如 22:00-02:00): end <= start 即视为跨夜。
    #   * 支持**限定星期**(如狭间暗域只有周五/六/日)。
    #   * 软件会通过 `ObservedWindow` **自学习**实际时段并给出提示, 见
    #     `module/config/availability.py` 与 `docs/architecture.md` §3.0。
    #
    # ★ 4-A/4-E 之后: 时段已搬进各任务 `meta.py` 的 `TaskSpec.window`
    #   （游戏机制事实）, 这里降级为**内部字段** —— 仍然是权威值
    #   （`Function._build_window` 读它）, 但不再出现在界面上。
    # ★★ 这些字段是**用户可改的**（2026-10-10 用户澄清后修正）★★
    #
    # 我一开始（4-E）把它们当成"内部字段"隐藏了 —— 那是**错的**。
    # 用户明确要求:
    #
    #   "缺 window 用 period 推导, 记得要符合前端设计意义
    #    （用户可以选择每天, 然后把时间改为 17-23 点）, 后端也要符合这个逻辑"
    #
    # 所以职责划分是:
    #   * `period`（每天/每周/每月）—— 决定**节奏**, 同时给出**默认窗口**
    #   * `window_start` / `window_end` —— **用户偏好**（"我每天只想在 17-23 跑"）
    #   * 各任务 `meta.py` 的 `TaskSpec.window` —— **游戏机制硬约束**
    #     （如狭间暗域只在周五六日）, 与用户时刻取**并集**
    #
    # 优先级见 `Function._build_window()`。
    # ★★★ S3: **多窗口列表**（替代下面全部单值字段）★★★
    #
    # 用户裁定:
    #   "不是 window slots, 而是**设置多个 window**！slots 不是已经废弃了吗"
    #   "一天跑两次 = **两个窗口**"
    #   "你直接帮我配好窗口就好"
    #
    # 设计: `docs/scheduler-architecture.md` §1.1（原子实体 + 稳定 id）
    #
    # ★ 每个窗口是**独立实体**: 用户可增 / 删 / 改**任意一条**,
    #   后端按 `id` 定位（**不按下标** —— "身份不是位置"）。
    #
    # ★ 判定: 一个任务的**可跑集合** = 所有 `enabled` 窗口的**并集**。
    #
    # ★ 被它替代并**删除**的字段:
    #   `window_enable` / `window_start` / `window_end` / `window_days` /
    #   `window_period` / `window_dom` / **`window_slots`**
    windows: List[TaskWindow] = Field(
        default_factory=list, description='window_windows_help',
        title='开放窗口')

    # ------------------------------------------------------------ 任务列表
    #
    # 任务列表就是**调度器的一种模式**, 不是新子系统(见 docs/architecture.md §5)。
    # 相关概念:
    #   * 列表顺序 -> `tasks/<Name>/meta.py` 的 `TaskSpec.list_pos`(默认顺序)
    #   * 用户编排 -> `Script.optimization.run_list`(本文件只放**每行**的东西)
    #   * 每行次数 -> 本类的 `target`

    # 本任务的目标次数。0 = 用默认值(即任务配置里的 limit_count)。
    #
    # ★ 为什么放在 scheduler 而不是任务配置里: "打几次"是**调度决策**,
    # 而任务配置里的 limit_count 是"这个任务最多打几次"的能力上限。
    # 界面上的每行次数框改的是 `target` —— 这样调整调度策略不必改任务配置。
    target: int = Field(
        default=0,
        description='target_help',
        title='目标次数',
        ge=0,
        le=999)

    # 本任务一次运行的**预期完成时间**(分钟)。
    #
    # ★ 用途: 判定"休息期间能不能穿插这个定时任务" ——
    #   若 `expected_minutes <= 休息剩余时间`, 就可以插进去跑。
    #   见 `module/config/timed_schedule.py` 的 `can_interleave()`。
    #
    # `0` = **未知** -> 不参与穿插判定（保守处理, 不能拿 0 去比）。
    expected_minutes: int = Field(
        default=0,
        description='expected_minutes_help',
        title='预期完成时间(分钟)',
        ge=0,
        le=24 * 60)

    # ------------------------------------------------------------ 开放时段: 便捷访问
    def build_window(self) -> 'AvailabilityWindow':
        """
        把本配置转成 `AvailabilityWindow`。

        解析失败(如 `window_days` 写成乱码)时**退化为不限时段**并记 warning ——
        时段配置错误不该让任务跑不起来。
        """
        from module.config.availability import ALL_DAYS, AvailabilityWindow

        if not self.window_enable:
            return AvailabilityWindow()      # enabled=False -> 不限时段

        days = []
        bad = []
        for part in str(self.window_days or '').split(','):
            part = part.strip()
            if part == '':
                continue
            try:
                d = int(part)
            except (TypeError, ValueError):
                bad.append(part)
                continue
            if 0 <= d <= 6:
                days.append(d)
            else:
                bad.append(part)

        if bad:
            # 逐项跳过而不是整体丢弃 —— 用户写了 '4,abc,6' 时, 4 和 6 仍是有效的意图。
            logger.warning(
                f'window_days 中的无效项已忽略: {bad}（应为 0-6, 周一=0）')

        if not days:
            logger.warning(f'window_days 无有效项({self.window_days!r}), 退化为每天')
            days = list(ALL_DAYS)

        try:
            return AvailabilityWindow(
                enabled=True,
                start=self.window_start,
                end=self.window_end,
                days=tuple(sorted(set(days))),
            )
        except ValueError as exc:
            logger.warning(f'开放时段配置非法({exc}), 退化为不限时段')
            return AvailabilityWindow()


if __name__ == "__main__":
    dict_s = {
        "enable": False,
        "next_run": "2026-07-19T14:15:37",
        "priority": 5,
        "retry_interval": "10 00:00:01",
        "server_update": "09:03:00",
        "float_time": "02:00:05"
    }
    s = Scheduler(**dict_s)
    print(s.model_dump())
