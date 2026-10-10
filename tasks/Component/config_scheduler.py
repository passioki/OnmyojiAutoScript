# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
from enum import Enum

from pydantic import AliasChoices, Field

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
RECOMMENDED_WINDOWS = {
    'restart': '12:00,20:00',
    'ryou_toppa': '07:00',
}


def apply_recommended_windows(node_map: dict) -> list:
    """给 `node_map`（`{任务键: 节点dict}`）里**未迁移过**的任务配好窗口。

    :param node_map: 配置的**原始 dict**（可写回）
    :return: 实际改动的任务键列表（空 = 无需迁移）
    """
    changed = []
    for key, slots in RECOMMENDED_WINDOWS.items():
        node = node_map.get(key)
        if not isinstance(node, dict):
            continue
        sch = node.get('scheduler')
        if not isinstance(sch, dict):
            continue
        # ★ 已是"用户自己配过"的 -> 不动（window_period 被显式设过 或
        #   已经有 slots 且非空）
        if str(sch.get('window_slots') or '').strip():
            continue
        sch['window_enable'] = True
        sch['window_slots'] = slots
        # 起止时刻留一个合理的默认（slots 生效时会被忽略, 但界面要显示）。
        #
        # ★ 必须是 `datetime.time`, **不是字符串** —— `Settings.Time` 的
        #   序列化器直接调 `.strftime`, 给字符串会在**保存**时崩:
        #     AttributeError: 'str' object has no attribute 'strftime'（踩过）
        from datetime import time as _time
        if not isinstance(sch.get('window_start'), _time):
            sch['window_start'] = _time(hour=12, minute=0)
        if not isinstance(sch.get('window_end'), _time):
            sch['window_end'] = _time(hour=22, minute=0)
        sch['window_period'] = 'daily'
        changed.append(key)
    return changed


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
    window_enable: bool = Field(
        default=False,
        description='window_enable_help',
        title='启用开放时段')
    window_start: Time = Field(
        default=Time(hour=17, minute=0, second=0),
        description='window_start_help',
        title='开放开始')
    window_end: Time = Field(
        default=Time(hour=23, minute=0, second=0),
        description='window_end_help',
        title='开放结束')
    # 限定星期: 逗号分隔的 0-6(周一=0), 空或 "0,1,2,3,4,5,6" 表示每天。
    # 用字符串而非列表, 与既有 charge_slots='0,12' 的风格一致, 也便于 GUI 输入。
    window_days: str = Field(
        default='0,1,2,3,4,5,6',
        description='window_days_help',
        title='开放星期')
    # ★★ #1: 窗口周期 + 月内日（用户裁定的结构, 两端**共用**周期）★★
    #
    # 用户原话:
    #   "窗口开始: 下拉选择：每天、每周、每月 / 下拉选择：时:分、周几：时：分、几号：时：分"
    #   "窗口语义：(B) 两端必须同周期"
    #
    # 所以:
    #   * `window_period` 决定"时:分"是**哪一天**的时:分
    #   * `window_days`   在 `weekly` 时有意义（周几）
    #   * `window_dom`    在 `monthly` 时有意义（几号）
    window_period: WindowPeriod = Field(
        default=WindowPeriod.DAILY,
        description='window_period_help',
        title='窗口周期')
    # 月内日: 逗号分隔 1-31; 空 = 整月
    window_dom: str = Field(
        default='',
        description='window_dom_help',
        title='开放几号')
    # ★★ ⑥(b): **一天几个固定时刻**（用户裁定推导出的第 4 种语义）★★
    #
    # 例: `'12:00,20:00'` -> 每天 12:00 与 20:00 各跑一次
    #     （由**窗口开放次数**表达, 不引入新的"次数"概念）
    #
    # ★ 与 `window_start` / `window_end` **互斥**:
    #   填了 slots 就用 slots, 否则用 start/end。
    #
    # ⚠ 为什么不能用"重复条目"表达: 重复条目会跑**完整的任务**,
    #   而 `Restart` 只在体力补充时刻（12/20 点）才有意义。
    window_slots: str = Field(
        default='',
        description='window_slots_help',
        title='每日固定时刻')

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
