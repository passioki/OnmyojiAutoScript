# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey

import inspect
import inflection
import random
from contextlib import contextmanager
from typing import Union
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from time import sleep, time

from module.atom.animate import RuleAnimate
from module.atom.click import RuleClick
from module.atom.gif import RuleGif
from module.atom.image import RuleImage
from module.atom.list import RuleList
from module.atom.long_click import RuleLongClick
from module.atom.ocr import RuleOcr
from module.atom.swipe import RuleSwipe
from module.base.timer import Timer
from module.config.config import Config
from module.config.utils import convert_to_underscore
from module.device.device import Device
from module.exception import ScriptError, TaskEnd
from module.logger import logger
from module.ocr.base_ocr import OcrMode

from tasks.Component.Costume.costume_base import CostumeBase
from tasks.Component.config_base import Time
from tasks.GlobalGame.assets import GlobalGameAssets
from tasks.GlobalGame.config_emergency import FriendInvitation



class BaseTask(GlobalGameAssets, CostumeBase):
    config: Config = None
    device: Device = None

    folder: str
    name: str
    stage: str

    # ⚠ `limit_time` 曾是"运行时间上限"的配置来源（各任务从 `config` 里的
    #   `Time` 字段转换后赋给这里）。★ 片 2 已把那个配置字段**删除**，
    #   上限统一到 `scheduler.expected_minutes` ⇒ 新代码应使用下面的
    #   `time_limit` 属性（从 `scheduler.expected_minutes` 派生）。
    limit_time: timedelta = None  # 【已废弃】请用 `time_limit`
    limit_count: int = None  # 限制运行的次数
    current_count: int = None  # 当前运行的次数

    @property
    def time_limit(self) -> timedelta:
        """★ **统一的「运行时间上限」**（用户裁定：`limit_time` -> `expected_minutes`）。

        ## ★★ 用户裁定（原话）★★

        > "② 真正的'两个字段'问题，`limit_count` 和 `limit_time`
        >  **都需要分别统一为 `target` 和 `expected_minutes`**，
        >  `limit_time` 和 `expected_minutes` **语义很接近，基本服务于
        >  定时任务完成时间和休息时间的长短判断**，对于**临时类任务也很贴合**。"

        ## 为什么放在基类

        ★ 片 2 调研发现：**15 个任务**各自把配置里的 `Time` 字段转成 `timedelta`
          再赋给 `self.limit_time`（共 31 处赋值）—— 这是**同一段逻辑复制了 15 遍**。
        ★ 统一到 `scheduler.expected_minutes` 后，**一个属性**就够了；
          各任务只需 `self.time_limit`，不必再关心配置字段叫什么、住在哪。

        ## 单位与默认

        * `scheduler.expected_minutes` 是 **int 分钟**（`0` = 未知）
        * ★ 本会话实测：老 `limit_time` 的值**全部是整分钟**
          （`00:30:00` / `02:30:00` / `00:20:00`）⇒ 迁移**无精度损失**
        * `0`（未设）⇒ ★ 返回一个**足够大的**上限（24 小时），
          语义 = "**不因时间而中止**"（与老默认 30 分钟**不同** ——
          老默认是"软时间 30 分钟后停"，现在"没设就不按时间停"）。
          ⚠ 但迁移会把老的 30 分钟**搬进来**，所以**行为不变**；
            只有"用户显式设成 0"才是"不按时间停"。
        """
        try:
            from module.config.config_model import convert_to_underscore
            sub = getattr(self.config, convert_to_underscore(self.get_task_name()),
                          None)
            sch = getattr(sub, 'scheduler', None) if sub is not None else None
            minutes = int(getattr(sch, 'expected_minutes', 0) or 0)
        except Exception as exc:
            logger.debug(f'读取 expected_minutes 失败'
                         f'({type(exc).__name__}: {exc}) —— 用 24 小时')
            minutes = 0
        if minutes <= 0:
            # ★ 未设 -> 不按时间中止（见 docstring 的说明）
            return timedelta(hours=24)
        return timedelta(minutes=minutes)

    def __init__(self, config: Config, device: Device) -> None:
        """

        :rtype: object
        """
        self.config = config
        self.device = device

        self.interval_timer = {}  # 这个是用来记录每个匹配的运行间隔的，用于控制运行频率
        self.animates = {}  # 保存缓存
        self.start_time = datetime.now()  # 启动的时间
        self.check_costume(self.config.global_game.costume_config)
        # self.friend_timer = None  # 这个是用来记录勾协的时间的
        # if self.config.global_game.emergency.invitation_detect_interval:
        #     self.interval_time = self.config.global_game.emergency.invitation_detect_interval
        #     self.friend_timer = Timer(self.interval_time)
        #     self.friend_timer.start()

        # 战斗次数相关
        self.current_count = 0  # 战斗次数
        self._boss_mark_flag = False
        # 战斗计数的持久化绑定(见 bind_counter/commit_count 的说明)
        self._counter_task = None
        self._counter_period = 'none'
        self._counter_reset_at = None
        self._counter_persisted = 0
        # ★ 「甲」统一：计数落盘到**条目级 `runs`**（见 commit_count 的说明）
        self._counter_entry_id = ''
        # 运行控制: 战斗循环收到暂停请求后置位, 让任务循环自然收敛
        # (见 docs/architecture.md §6.1 与 should_stop_battle_loop)
        self._pause_requested = False

    # ---------------------------------------------------------------- 战斗计数持久化

    #: 统一后的次数字段名（见 `module/config/task_catalog.py` 的
    #: `UNIFIED_COUNT_FIELD`）。历史上有 `minions_cnt` / `hya_limit_count` /
    #: `number_attack` 等别名，`TaskMeta.count_field_effective` 会把它们
    #: 统一成这个名字，所以上层与任务侧都只认它。
    LIMIT_COUNT = 'limit_count'

    def effective_target(self, task: str = None) -> int or None:
        """
        本任务这一次要打几次 —— **统一的次数入口**。

        ## 两个来源

        | 来源 | 字段 | 语义 |
        |---|---|---|
        | 用户编排 | `scheduler.target` | "这次跑几次"（调度决策）|
        | 任务默认 | 任务配置里的 `count_field` | "最多能跑几次"（能力上限）|

        优先级: `target > 0` 时用 `target`；否则回落到任务配置的默认值；
        再没有就用 `meta.py` 的 `count_default`。

        ## 为什么要有这个方法

        改造前"次数"是**双轨**的:

        * 界面有个 `scheduler.target` 输入框 —— 但**全仓无人读取它**（空壳）
        * 真正生效的是各任务配置里的 `limit_count`，而**界面上改不到它**

        于是"设置次数"这个功能实际上是坏的。

        本方法把它收敛成**一个**入口: 任务只调它, 不必关心
        用户设了什么、字段叫什么名字。

        :param task: 任务名; 留空用目录名推断
        :return: 目标次数; `None` 表示该任务没有次数概念
        """
        try:
            from module.config import task_catalog as TC

            name = str(task or self.get_task_name())
            meta = TC.get(name)
            if meta is None or not meta.countable:
                # 不可计数(定时/充能/限时) -> 没有"次数"这回事
                return None

            # 1) 用户编排的 target
            #
            # ★★★ 优先用【条目级】target（用户裁定 —— 修 bug）★★★
            #
            # ## 用户报的 bug
            #
            # > "当前临时任务**重复添加**后，修改**次数/时间会同步到所有的
            # >  同种任务**，而不是分开"
            #
            # ## 根因与修法
            #
            # 次数原来只存在**任务级** `scheduler.target` -> 改一条 =
            # 所有同任务条目一起变。
            # ★ 现在: **条目级**（`Function.target`, 由 `_order_by_queue()`
            #   按条目写入）优先; 为 0/None 才回落任务级
            #   （任务级**保留为默认值** —— 用户裁定 **甲**）。
            #
            # ★ 这里**不能**写 `except Exception: pass` —— 那会把真正的 bug
            #   (比如漏 import 导致的 NameError)吞掉, 表现成"次数设置没生效",
            #   极难排查。改为一律记日志。
            try:
                # ★ 条目级: 正在跑**那一条**自己的次数
                t = int(getattr(self.config.task, 'target', 0) or 0)
                if t > 0:
                    return t
            except Exception as exc:
                logger.debug(f'{name}: 读取条目级 target 失败'
                             f'({type(exc).__name__}: {exc}), 回落任务级')
            try:
                sub = getattr(self.config, convert_to_underscore(name), None)
                sch = getattr(sub, 'scheduler', None) if sub is not None else None
                target = int(getattr(sch, 'target', 0) or 0)
                if target > 0:
                    return target
            except Exception as exc:
                logger.warning(f'{name}: 读取 scheduler.target 失败'
                               f'({type(exc).__name__}: {exc}), 回落到任务默认值')

            # 2) 任务配置里的默认值(按统一后的字段名取)
            #
            # ★★ 片 1 收尾: 这一级【现在总是落空】—— 这是**预期的** ★★
            #
            # 用户裁定"次数全部统一为 `target`" ⇒ 片 1 **删掉了 14 个任务
            # 配置里的次数字段**（`limit_count` / `minions_cnt` /
            # `hya_limit_count` / `number_attack`）⇒ 配置树里**不再有**
            # 任务级次数字段 ⇒ `meta.count_field_effective`（= `limit_count`）
            # **永远找不到** ⇒ 直接落到第 ③ 级 `meta.count_default`。
            #
            # ★ 这正是统一后的预期路径:
            #   ① 条目级 `target` -> ② 任务级 `scheduler.target` -> ③ 出厂默认值
            #   （`task_catalog_data.json` 的 `count_default`，由
            #    `dev_tools/gen_task_catalog.py` 的 `FACTORY_COUNT_DEFAULT` 提供）
            #
            # ★ 为什么**保留**这一级: 万一将来某个任务又需要一个
            #   **任务自带的**次数字段（不在 `scheduler` 里），这条路还通；
            #   留着比删掉更安全（删掉要同时改 catalog 的语义）。
            field = meta.count_field_effective or self.LIMIT_COUNT
            found = self._find_count_field(field)
            if found is not None:
                return found

            # 3) 元数据里的默认值
            return meta.count_default
        except Exception as exc:
            logger.warning(f'解析目标次数失败({type(exc).__name__}: {exc}), 忽略')
            return None

    def _find_count_field(self, field: str) -> int or None:
        """
        在本任务的**配置对象树**里找 `field` 并返回整数值。

        为什么要遍历: 各任务把 `limit_count` 放在不同层级 ——
        `orochi_config.limit_count` / `bondling_config.limit_count` /
        `fallen_sun_config.limit_count` … 有的一层有的两层。
        遍历比在每个任务里硬编码路径更不容易漏。
        """
        from pydantic import BaseModel

        name = convert_to_underscore(str(self.get_task_name()))
        root = getattr(self.config, name, None)
        if root is None:
            return None

        seen = set()
        queue = [root]
        while queue:
            obj = queue.pop(0)
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            try:
                value = getattr(obj, field, None)
            except Exception:
                value = None
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
            if isinstance(obj, BaseModel):
                for fname in type(obj).model_fields:
                    try:
                        child = getattr(obj, fname, None)
                    except Exception:
                        continue
                    if isinstance(child, BaseModel):
                        queue.append(child)
            elif isinstance(obj, (list, tuple)):
                queue.extend([x for x in obj if isinstance(x, BaseModel)])
        return None

    def bind_counter(self, task: str = None, period='none', reset_at=None) -> int:
        """
        把 `current_count` 绑定到状态文件, 并返回恢复到内存的计数。

        为什么需要: `current_count` 原本只存在内存里(每个任务还在 run() 开头重置为 0),
        进程一旦重启(手动重启 / 崩溃后 restart / 任务被中断)计数就归零, 于是
        "我今天要打 N 次"这类固定任务会从头再打, 永远打不满 N。

        用法(在 run() 里, 取代 `self.current_count = 0` 和读 `limit_count`):

            self.bind_counter()          # 恢复计数 + 设定本次目标
            # 之后 self.current_count / self.limit_count 都已就绪

        ★ 本方法**同时设定 `self.limit_count`**（来自 `effective_target()`）,
          所以任务里不必再自己读配置 —— 这是"次数统一到一个入口"的关键。

        :param task: 任务名; 留空则用目录名推断(见 get_task_name)
        :param period: 周期类型('daily'/'weekly'/'none'), 决定何时自动清零
        :param reset_at: 游戏重置时刻(datetime.time); 留空用 task_state 的默认(0 点)
        :return: 恢复后的计数
        """
        from module.config import task_state
        name = str(task or self.get_task_name())
        self._counter_task = name.lower()
        self._counter_period = str(getattr(period, 'value', period) or 'none').lower()
        self._counter_reset_at = reset_at if isinstance(reset_at, dt_time) \
            else task_state.DEFAULT_RESET_AT

        # 恢复磁盘计数
        #
        # ★★★ 2026-10-11 用户裁定：**统一到一份计数** ★★★
        #
        # > "**1 统一**"
        # > "既然你用 `runs`，那就把他**取代 `current_count`**，
        # >  这两个**不是一个东西吗**。"
        #
        # ## ★★ 历史坑（我在这里改错过两次，记下来防再犯）★★
        #
        # * 我第一版让临时任务"每次运行从 0 开始 + 清盘上值"
        #   ⇒ ★ 与调度层的 `runs` 判据**互相干扰**（两边都不对）。
        # * 用户实测：`target=2` 却显示"已打 36 次"、且**跳过战斗** ——
        #   ★ 根因是 `period='none'` 时 `add_count()` 的 `count_key` 是空串，
        #     "上次那 36 次"被一直恢复 ⇒ `36 >= 2` ⇒ 一进任务就 break。
        #
        # ## ★ 现在的做法（保持原语义，把"清零"的责任交给正确的一层）
        #
        # ★ `current_count` 仍然是**任务内部**的"这次打了几场"，
        #   由任务自己 `bind_counter()` 恢复 / `commit_count()` 落盘。
        # ★ 而"新一轮该清零"由**调度层**做（`reset_entry_runs` 清 `runs`），
        #   任务内部计数**不在这里**做特殊处理 —— 免得两套逻辑打架。
        # ★ 界面上显示的"已运行 N 次"读的是**总记录**
        #   （`task_state.get_entry_total_runs`），与这里的计数无关。
        # ★★★ 2026-10-12 用户裁定「甲」：**`runs` 取代 `current_count`** ★★★
        #
        # > "既然你用 `runs`，那就把他**取代 `current_count`**，
        # >  这两个**不是一个东西吗**。" -> "**1 甲**"
        #
        # ## 统一之后的三份数据（用户定的"两份记录"）
        #
        # | 键 | 含义 | 谁写 | 生命周期 |
        # |---|---|---|---|
        # | ★ `runs` | **本条已打几场**（= 原来的 `current_count`）| ★ 这里（`commit_count`）| 该行运行结束 / 本周期结束 |
        # | ★ `total_runs` / `total_log` | **累计**（展示/分析）| `bump_entry_runs` | ★ 永不清零 |
        #
        # ★ 所以：`current_count` 仍是**内存工作变量**，
        #   但它的**落盘目标**从"任务级 `add_count`"改成"★ 条目级 `runs`"。
        # ★ `bind_counter()` **恢复**的也改成 `runs`。
        eid = str(getattr(self.config.model, 'running_entry_id', '') or '')
        self._counter_entry_id = eid
        if eid:
            try:
                self.current_count = task_state.get_entry_runs(
                    self.config.config_name, eid)
            except Exception as exc:
                logger.warning(f'恢复条目计数失败({type(exc).__name__}: {exc}), 从 0 开始')
                self.current_count = 0
        else:
            # ★★★ 2026-10-12 用户裁定「2 废弃」★★★
            #
            # > "**不能存在两套机制**" -> "**2 废弃**"
            #
            # ★ 原来这里退回【任务级】`task_state.get_count()` —— 那是
            #   **第二套计数机制**（与条目级 `runs` 重复）。
            # ⇒ ★ **已删**：没有 `entry_id` 就**从 0 开始**
            #   （★ 单跑 / 排障场景；生产路径必有 `entry_id` ——
            #     `script.py` 在 `self.run()` **之前**就写好了 `running_entry_id`）。
            self.current_count = 0
        self._counter_persisted = self.current_count
        if self.current_count:
            logger.info(f'从状态恢复本条已打场次: {self.current_count}')

        # ★ 设定本次目标次数(统一入口)
        target = self.effective_target(name)
        if target is not None:
            self.limit_count = int(target)
            logger.info(f'本次目标次数: {self.limit_count} '
                        f'(已打 {self.current_count})')

        return self.current_count

    def commit_count(self) -> None:
        """
        把内存里的 `current_count` 同步到状态文件（**落盘到本条的 `runs`**）。

        幂等: 内部记录"已写盘的值", 只把增量写下去, 因此重复调用不会重复累加。
        未调用 bind_counter 时是空操作。

        ## ★★★ 用户裁定「甲 / 2 废弃」：`runs` 取代 `current_count`（2026-10-12）★★★
        *
        * 有 `entry_id`（★ **生产路径必有**）-> ★ 写 **`runs`**（条目级）
        * 没有 `entry_id`（单跑 / 排障）-> ★ **不写**（★ 任务级机制**已废弃**；
          见下方注释）
        """
        if not self._counter_task:
            return
        delta = int(self.current_count) - int(self._counter_persisted)
        if delta <= 0:
            return
        from module.config import task_state
        eid = str(getattr(self, '_counter_entry_id', '') or '')
        if not eid:
            # ★★★ 2026-10-12 用户裁定「2 废弃」★★★
            #
            # > "**不能存在两套机制**" -> "**2 废弃**"
            #
            # ★ 原来这里退回【任务级】`task_state.add_count()` —— 那是
            #   **第二套计数机制**。⇒ ★ **已删**。
            # ★ 没有 `entry_id` 时**只更新内存**（不落盘）—— 单跑 / 排障场景
            #   本来也不需要跨进程恢复。
            self._counter_persisted = int(self.current_count)
            return
        try:
            task_state.bump_entry_runs(
                self.config.config_name, eid, delta=delta)
            self._counter_persisted = int(self.current_count)
        except Exception as exc:
            logger.warning(f'写条目运行次数失败'
                           f'({type(exc).__name__}: {exc}), 忽略')

    def reset_persisted_count(self) -> None:
        """清零本任务的持久化计数(供"重新计数"或排障使用)。

        ## ★★★ 用户裁定「2 废弃」之后（2026-10-12）★★★

        > "**不能存在两套机制**" -> "**2 废弃**"

        ★ 只清 **条目级 `runs`**（唯一一套）。
        ★ ~~任务级 `task_state.reset_count()`~~ ★ **已删**（第二套机制）。
        """
        if not self._counter_task:
            return
        from module.config import task_state
        eid = str(getattr(self, '_counter_entry_id', '') or '')
        if eid:
            try:
                task_state.reset_entry_runs(self.config.config_name, eid)
            except Exception as exc:
                logger.debug(f'清条目运行次数失败'
                             f'({type(exc).__name__}: {exc})')
        self.current_count = 0
        self._counter_persisted = 0

    # ------------------------------------------- 本轮已完成（临时任务的退出条件）
    def mark_entry_completed(self, reason: str = '') -> bool:
        """★★★ 上报"**本条目本轮已完成**"（用户裁定 丙）★★★

        ## ★★ 用户原话 ★★

        > "**丙**"（= 调度层默认"跑满 `target` 才算完成"；
        >           **个别任务可提前上报完成**）
        > "个人突破……没票了应该算这轮结束啊，也算成功结束了啊"
        > "门票耗尽**不上报**，**只上报任务完成**！"

        ## 什么时候该调它

        ★ 当任务**提前把这一轮做完了**（不用再跑满 `target`）时调它：
        * ★ `RealmRaid` 券打完（`check_ticket()` 返回 False）
        * 其它"资源/条件用完 ⇒ 本轮没得做了"的任务同理

        ⚠ **不要**把它当成"资源耗尽"的标记（用户明确否决）：
          项目里**没有**监控门票资源的机制 ⇒ 标了"耗尽"就**永远没人解除**
          ⇒ 那个任务**再也跑不了**。★ 所以上报的是"**本轮完成**"，
          新一轮（队列循环）时由 `clear_entry_completed()` 自动清零。

        ## 与 `target` 的关系

        * `target` 未跑满 + 任务没提前做完 ⇒ **不标**（继续跑，由调度层判）
        * 调了本方法 ⇒ ★ 立即标（**提前完成**，不再等 `target`）

        :param reason: 说明（写日志 + 落盘，便于排障）
        :return: 是否标记成功
        """
        try:
            eid = str(getattr(self.config.model, 'running_entry_id', '') or '')
            if not eid:
                # 兜底：内存里的 `config.task`（与脚本同进程时可用）
                eid = str(getattr(getattr(self.config, 'task', None),
                                  'entry_id', '') or '')
            if not eid:
                logger.info(f'mark_entry_completed: 拿不到 entry_id，跳过'
                            f'{("（" + reason + "）") if reason else ""}')
                return False
            from module.config import task_state
            _ok = task_state.mark_entry_completed(
                self.config.config_name, eid, reason=reason)
            if _ok:
                logger.info(f'「{self.get_task_name()}」上报本轮完成'
                            f'{("（" + reason + "）") if reason else ""}'
                            f' -> 调度器下次不会再派发这一条')
            return _ok
        except Exception as exc:
            logger.warning(f'上报本轮完成失败({type(exc).__name__}: {exc}), 忽略')
            return False

    # ------------------------------------------------------------------ 运行控制
    def requested_pause(self) -> bool:
        """
        界面是否请求了暂停(**⏸ 跑完当前这场战斗**)?

        语义: 返回 True 的那一刻正是**安全点** —— 战斗 + 结算 + 领奖都已完成
        (见 `docs/architecture.md` §6.1)。调用方应当**结束当前任务的本轮循环**,
        而不是硬杀进程(硬杀会卡在半途: 战斗中 / 组队房间中, 不安全)。

        为什么放在 `BaseTask`: 与 `commit_count()` 同一手法 —— 放在共享层,
        **所有走 `GeneralBattle` 的任务自动受益**, 不必逐个任务改。
        """
        try:
            from module.config import run_control
            return run_control.is_paused()
        except Exception as exc:
            # 状态读取失败时"照常运行" —— 不能因为状态文件问题把任务卡死
            logger.warning(f'查询暂停状态失败({type(exc).__name__}: {exc}), 继续运行')
            return False

    def should_stop_battle_loop(self) -> bool:
        """
        本任务的战斗循环是否该结束了?

        ## 两种暂停模式(用户确认的语义, 见 docs/architecture.md §6.1)

        | 模式 | 含义 | 本轮未打满时 |
        |---|---|---|
        | `PAUSE_BATTLE` | ⏸ 跑完**当前这场战斗**就停 | **也停**(这就是它的定义) |
        | `PAUSE_ROUND` | ⏭ 本轮(**目标次数**)跑完再停 | 继续打满 |

        因此:
          * `PAUSE_ROUND` + 本轮已打满 -> 停
          * `PAUSE_ROUND` + 本轮未打满 -> 继续(让本轮跑完)
          * `PAUSE_BATTLE`            -> 停(本场已结束)

        ## 插入位置

        调用点应放在**战斗循环体的开头**(紧跟 `self.screenshot()`)。这样:
          * 战斗中时循环体阻塞在 `battle_wait()` 里, **不会**在这里 break
            -> 天然保证只在"两场战斗之间"退出
          * 退出时任务既有的收尾逻辑(退房间 / 回庭院 / `set_next_run`)仍会执行
            -> 不会卡在半途

        任务自身的循环形如 `while 1: ... break`, 因此 `return True` 让调用方 `break` 即可。

        **为什么不在这里 raise / sys.exit**: 那会跳过收尾逻辑, 正是要避免的"卡在半途"。
        """
        requested = getattr(self, '_pause_requested', False) or self.requested_pause()

        # ★★★ 2026-10-12 用户裁定「D7.5 甲」：**播放头指向别条 ⇒ 本场跑完就停** ★★★
        #
        # ## ★★ 用户原话
        #
        # > "我点击了**别的任务的开始按钮**，虽然弹窗提示排到了最前，
        # >  但是**并不会转而运行我点击的任务**。"
        # > 裁定：★ **甲**（★ 尽快切换）
        #
        # ## ★ 为什么放在这里（这正是"安全点"）
        #
        # ★ 本函数的调用点都在**战斗循环体的开头**（★ 27 处）——
        #   ★ 战斗中会阻塞在 `battle_wait()` 里，★ **不会**在这里 break
        #   ⇒ ★ 天然保证"**只在两场战斗之间**退出"
        #   ⇒ ★ 任务的收尾逻辑（退房间 / 回庭院 / 记录）**照常执行**
        #     ⇒ ★ 不会卡在半途。
        #
        # ## ★ 判据
        #
        # ★ `model.force_next_entry_id` 有值（用户点了某条的 `[▶]`）
        #   ★ **且**它 ≠ **本条**的 `entry_id`
        #   ⇒ ★ 用户想让**别条**跑 ⇒ ★ 本条**本场跑完就停**，
        #     ★ 调度器下一轮就会把播放头那条提到最前。
        # ⚠ 播放头 == 本条 ⇒ **不停**（用户点的是自己，别自打断）。
        try:
            from module.config import run_control as _rc  # noqa: F401
            _cfg = getattr(self, 'config', None)
            _model = getattr(_cfg, 'model', None) if _cfg is not None else None
            _force = str(getattr(_model, 'force_next_entry_id', '') or '')
            # ★★ 判据修正（★ 我第一版读错字段）★★
            # ★ 第一版读 `self._counter_entry_id` —— ★ 但它**只在
            #   `bind_counter()` 里设置**，★ 而只有**战斗任务**才调它
            #   ⇒ ★ `Rest` / `Exploration` 等读到**空** ⇒ 判据不准
            #   ⇒ ★ 验收 5/6 都没过。
            # ★ 改用 `config.model.running_entry_id` ——
            #   ★ `script.py` 在**每个任务运行前**都会写它（★ 权威）。
            # ⚠ 两个都读，取非空的（兼容单跑 / 排障）。
            _mine = str(getattr(_model, 'running_entry_id', '') or '') or \
                str(getattr(self, '_counter_entry_id', '') or '')
            if _force and _force != _mine:
                logger.info(f'★[切换诊断] 播放头={_force} ≠ 本条={_mine or "?"}'
                            f' -> 本场跑完就停，交给下一条')
                return True
            elif _force:
                logger.debug(f'★[切换诊断] 播放头 = 本条（{_force}）-> 不打断')
            else:
                logger.debug(f'★[切换诊断] 无播放头请求（本条={_mine or "?"}）')
        except Exception as exc:
            logger.debug(f'检查播放头切换失败({type(exc).__name__}: {exc}), 忽略')

        if not requested:
            return False

        from module.config import run_control
        try:
            mode = run_control.pause_mode()
        except Exception as exc:
            logger.warning(f'读取暂停模式失败({type(exc).__name__}: {exc}), '
                           f'按"跑完本场就停"处理')
            return True

        if mode == run_control.PAUSE_ROUND:
            # 本轮跑完再停
            limit = getattr(self, 'limit_count', None)
            if limit:
                try:
                    if int(self.current_count) < int(limit):
                        # 本轮还没打满 -> 继续(但保留标志, 打满后会在下一次检查时停)
                        self._pause_requested = True
                        return False
                except (TypeError, ValueError):
                    pass
        return True

    # ------------------------------------------------------------------ 是否在战斗中
    # ★★★ 片 8 / D: `_in_battle` 判据（用户裁定 **丙**）★★★
    #
    # ## ★★ 用户原话 ★★
    #
    # > "应当对当前账号作一个**未在战斗中的判断**，如果处于该状态，
    # >  那么遇到**暂停/停止调度时可以直接停止**而非**跑完当前一次完整战斗流程**
    # >  （包括**换御魂、预设队伍、战斗**等）"
    #
    # > "D 丙：`_in_battle` 判据（识别到这个就是在战斗中，
    # >  **识别到则刷新为 5s 内处于战斗状态**，
    # >  `tasks\\Component\\GeneralBattle\\gb\\gb_action_bar_queue`），
    # >  **其他任何时候都是非战斗状态**，怎么样。
    # >  不过在**别的过程加断点可以更稳定**。"
    #
    # ## 设计（心跳超时，而不是"当前帧判定"）
    #
    # ★ `gb_action_bar_queue.png`（战斗界面的"行动条队列"）出现 ⇒ 在战斗中。
    # ★ 但它**不必每帧都出现**（动画/遮罩会让它短暂消失）⇒
    #   用**心跳 + 超时**：最近 `BATTLE_HEARTBEAT_S` 秒内见到过 ⇒ 算"仍在战斗"。
    # ★ 超时未见到 ⇒ **非战斗** ⇒ 暂停可以**立刻**生效。
    #
    # ⚠ 这个判据**与 `DemonEncounter` 已有的做法同源**
    #   （`tasks/DemonEncounter/script_task.py:669-703` 用同一张图重置兜底计时器）。
    # ★ 心跳由 `battle_wait_with_strategy()` 的**主循环**每帧刷新
    #   （`tasks/Component/GeneralBattle/battle_wait.py:1726`）——
    #   ★ **一处覆盖所有任务**，不必改 54 个任务。

    #: 心跳超时（秒）—— 用户指定 **5 秒**。
    BATTLE_HEARTBEAT_S = 5

    #: ★ "最近一次见到战斗图标"的**时间戳**（`time.time()`）。
    #:   ★ `None` = 从没进入过战斗 ⇒ `_in_battle` 为 `False`（非战斗）。
    _battle_seen_at = None

    def note_battle_frame(self) -> None:
        """★ 由战斗主循环每帧调用：**刷新"在战斗中"的心跳**。

        ★ 只在**真的处于战斗**时刷新 —— 判定用 `gb_action_bar_queue`；
          拿不到该资源的任务（不跑战斗的）**不会**刷新。
        """
        try:
            img = getattr(self, 'I_ACTION_BAR_QUEUE', None)
            if img is None:
                return
            if self.appear(img):
                self._battle_seen_at = time()
        except Exception as exc:
            logger.debug(f'刷新战斗心跳失败({type(exc).__name__}: {exc})')

    @property
    def _in_battle(self) -> bool:
        """★ 现在是不是**在战斗中**（最近 `BATTLE_HEARTBEAT_S` 秒内见过战斗图标）。

        ★ **没有心跳记录** / **已超时** ⇒ `False` = **非战斗**
          ⇒ 暂停/停止可以**立刻**生效（用户要的"未在战斗中就直接停"）。
        """
        seen = getattr(self, '_battle_seen_at', None)
        if seen is None:
            return False
        try:
            return (time() - float(seen)) < float(self.BATTLE_HEARTBEAT_S)
        except Exception:
            return False

    def raise_if_paused(self) -> None:
        """★★★ 在**安全点**中断当前任务（"暂停调度"真正生效的关键）★★★

        ## 为什么不直接 `return True` 让调用方 break

        实测: `should_stop_battle_loop()` 有 **27 处**调用点，而
        **15/54 个任务**根本没调用它；`run_general_battle()` 的
        50 处调用点还**丢弃了返回值**。

        ★ 光靠"让调用方自己 break"**覆盖不全** —— 这正是用户报的
        "暂停调度并没有实现"。所以改成**抛异常**:
        安全点一命中就**必然**中断, 不依赖调用方是否读返回值。

        ⚠ 异常是 `TaskPaused(BaseException)` —— 任务里的 `except Exception`
          吞不掉它（否则又会变成"点了没用"）。
        ⚠ 异常由 `script.py` 的 `run()` 接住, 那里任务收尾的 `finally` 照常
          执行 -> **不会卡在半途**。

        ## ★★★ 片 8 / D 的放宽（用户裁定 丙）★★★

        ★ **原来**这个方法的注释说"只在**本场战斗已结束**时中断" ——
          即它**只在"一秒内不会卡"的地方停**。
        ★ **用户要求放宽**：`没在战斗中` 时**也可以立刻停**
          （不必等换御魂/预设/战斗这一整套跑完）。
        ★ 所以现在抛不抛只取决于 `should_stop_battle_loop()`；
          **"在不在战斗中"由调用方决定要不要在准备阶段也调它**
          （见 `battle_before()` 里的断点）。
        """
        if self.should_stop_battle_loop():
            from module.exception import TaskPaused
            logger.info('收到暂停请求: 已在安全点(本场战斗已结束)中断当前任务')
            raise TaskPaused()

    def raise_if_paused_outside_battle(self) -> None:
        """★ **准备阶段**的安全点：**非战斗时**收到暂停就立刻中断。

        ## 为什么单独一个方法

        ★ 用户要求"**未在战斗中就直接停**"，但**战斗中不能中途打断**
          （会卡在半途：战斗动画/结算界面没走完）。
        ⇒ 所以准备阶段（换御魂 / 换预设 / 点准备）用这个：
          `在战斗中` ⇒ **不抛**（照常跑完这一场）；`非战斗` ⇒ **抛**。

        ★ 由 `battle_before()` 等准备步骤调用（片 8 / D 的"加断点"部分）。
        """
        if self._in_battle:
            return                  # ★ 战斗中 -> 不打断（等结算）
        self.raise_if_paused()

    # ------------------------------------------------------------------ 暂停护栏
    #
    # ★★★ 框架级兜底（A 方案, 用户确认）★★★
    #
    # 背景: 只有 15/54 个任务自己调了 `raise_if_paused()`; 其余 21 个
    #（不使用 `GeneralBattle` 的）**完全没有暂停检查点** -> 点「暂停调度」
    # 它们一直跑到自己结束（用户报的 1a）。
    #
    # ★ 做法: 在 `screenshot()` 这个**公共入口**上加检查 —— 一处改, 54/54 覆盖。
    #
    # ⚠ **代价（必须知道）**: `screenshot()` 在**任何**循环里都会被调,
    #   所以它比"战斗结束"**更早**中断 —— 可能在某个界面操作的中途停下。
    #   对大多数任务是安全的（游戏状态是持久的、下次会重来）,
    #   但**组队类**任务中途停下会让**队友干等**。
    #
    # ★ 所以有两道闸:
    #   ① `PAUSE_FRAMEWORK_EXEMPT` —— 需要人工确认的**永久排除名单**
    #   ② `pause_blocked()`       —— 任务可临时把自己的**临界区**保护起来
    #      （如"已经在房间里了, 让我把这一轮打完"）

    #: ★ 框架级暂停检查的**排除名单**（需要逐个人工确认）。
    #:
    #: 判据: **会邀请真人队友 / 让第三方等待**的任务。
    #: 在这些任务里于 `screenshot()` 处中断, 会让队友卡在房间里 ——
    #: 那是**不可回滚**的社交代价（比"多跑一会儿"严重得多）。
    #:
    #: ⚠ 这份名单是**实测 + 人工确认**的, 不是关键词猜的:
    #:   `MysteryShop` / `FindJade` / `Hyakkiyakou` 有**真实的
    #:   `invite_friend(...)` 调用**（见各任务 `script_task.py`）。
    #:
    #: ★ 名单里的任务**不是**没有暂停能力 —— 它们仍可在自己的
    #:   **任务级安全点**（`raise_if_paused()`）被停; 只是不走框架级兜底。
    PAUSE_FRAMEWORK_EXEMPT = (
        'MysteryShop',    # invite_friend(...)  —— 组队邀请
        'FindJade',       # invite_type / invite_history —— 邀请配置
        'Hyakkiyakou',    # invite_friend 策略 —— 邀请
    )

    def pause_blocked(self) -> bool:
        """当前是否处于**临界区**（任务要求"暂时别打断我"）。

        任务可在"已经进了房间 / 正在结算 / 正在购买"等**不可回滚**的片段里
        临时挡一下, 例如::

            with self.pause_protected():
                self.enter_room_and_fire()

        ★ 为什么要这个: 框架级检查发生在 `screenshot()` —— 那是**任意时刻**。
          有些片段被打断的代价很高（队友在等 / 道具已消耗）。
        """
        return int(getattr(self, '_pause_block_depth', 0) or 0) > 0

    @contextmanager
    def pause_protected(self):
        """上下文管理器: 这段代码里**不响应**「暂停调度」（见 `pause_blocked`）。

        ★ 可嵌套（引用计数）。★ 退出时一定会减回去（`finally`）。
        """
        self._pause_block_depth = int(
            getattr(self, '_pause_block_depth', 0) or 0) + 1
        try:
            yield
        finally:
            self._pause_block_depth = max(
                0, int(getattr(self, '_pause_block_depth', 0) or 0) - 1)

    def _pause_check_at_screenshot(self) -> None:
        """★ 框架级暂停兜底 —— 在 `screenshot()` 时检查（A 方案）。

        ## 为什么放在这里

        `screenshot()` 是**所有任务循环**都会经过的公共入口
        （实测 21 个非战斗任务的每个 `while` 里都有它）。
        ★ 一处改动 -> **54/54** 任务都能被「暂停调度」停下
          （此前只有 33 个, 见 `raise_if_paused` 的说明）。

        ## 三道闸（缺一不可）

        1. **模式闸**: 只在 `PAUSE_BATTLE`（"跑完当前这场战斗就停"）下生效。
           ★ `PAUSE_ROUND`（"本轮打满再停"）**必须**交给任务自己判断
             （它要知道 `limit_count` / `current_count`）——
             框架层没有那个知识, 硬判会**破坏"跑完本轮"的语义**。
        2. **排除闸**: `PAUSE_FRAMEWORK_EXEMPT` 里的任务跳过
           （组队类, 中途停下会让队友干等）。
        3. **临界区闸**: `pause_blocked()` 为真时跳过。

        ## 失败安全

        ★ 任何异常都**只记日志、绝不抛出** —— 暂停检查绝不能打扰任务运行
          （这个项目里"状态读取失败把任务卡死"是明确要避免的）。
        """
        try:
            # ① 临界区 / 排除名单
            if self.pause_blocked():
                return
            if self.get_task_name() in self.PAUSE_FRAMEWORK_EXEMPT:
                return
            # ② 模式闸（只处理 battle；round 交给任务自己）
            from module.config import run_control
            if not run_control.is_paused():
                return
            if run_control.pause_mode() != run_control.PAUSE_BATTLE:
                return
            # ③ 命中 -> 中断（收尾由 `script.py` 的 finally 保证）
            from module.exception import TaskPaused
            logger.info(f'{self.get_task_name()}: 收到暂停请求'
                        f'（框架级检查点, 位置=截图后）, 中断当前任务')
            raise TaskPaused()
        except TaskPaused:
            raise
        except Exception as exc:
            logger.debug(f'暂停检查异常({type(exc).__name__}: {exc}), 忽略')

    def get_task_name(self) -> str:
        """
        取任务名, 以任务类所在目录名为准。

        目录名是唯一可靠来源: 调度器是按 `tasks/<TaskName>/script_task.py` 加载任务的,
        目录名与配置项名天然一一对应。

        这里刻意不再把 config 里的 running_task 当作校验依据。原因是那个字段是
        "运行时状态"却被持久化到了配置文件, 而 Config.task_delay() 会先 reload() 再从
        磁盘整份写回(module/config/config.py:304 与 :379), 于是内存里刚设置的
        running_task 会被磁盘旧值覆盖。触发路径: _wait_close_game() 内调用
        self.run('Restart'), 此时 model 仍是上一个任务(FrogBoss)、path 却是 Restart,
        两者不一致即抛 ScriptError -> script.py 的 exit(1) 使整个脚本进程退出。

        保留为告警而非致命错误: 不一致说明状态字段被污染了, 值得记录, 但目录名已经
        给出正确答案, 没有必要因此终止整个实例。

        :return: 任务名(大驼峰)
        """
        class_file = inspect.getfile(type(self))
        path_task_name = Path(class_file).parent.name
        path_task_name = inflection.camelize(
            path_task_name,
            uppercase_first_letter=True,
        )

        model_task_name = getattr(self.config.model, 'running_task', '')
        if model_task_name:
            model_task_name = inflection.camelize(
                model_task_name,
                uppercase_first_letter=True,
            )
            if model_task_name != path_task_name:
                # 曾经的 ScriptError 在此处会导致进程自杀, 现降级为告警
                logger.warning(
                    f'Task name mismatch: model={model_task_name}, '
                    f'path={path_task_name}; 以目录名为准, 并重置被污染的 running_task'
                )
                # 顺手修正污染源, 避免它继续扩散到下一次 save()
                try:
                    self.config.model.running_task = path_task_name
                except Exception as exc:
                    logger.warning(f'Reset running_task failed: {exc}')

        return path_task_name

    def _burst(self) -> bool:
        """
        游戏界面突发异常检测
        :return: 没有出现返回False, 其他True
        """
        image = self.device.image
        appear_invitation = self.appear(self.I_G_ACCEPT)
        if not appear_invitation:
            return False
        logger.info('Invitation appearing')
        invite_type = self.config.global_game.emergency.friend_invitation
        detect_record = self.device.detect_record
        match invite_type:
            case FriendInvitation.ACCEPT:
                logger.info(f"Accept friend invitation")
                click_button = self.I_G_ACCEPT
            case FriendInvitation.REJECT:
                logger.info(f"Reject friend invitation")
                click_button = self.I_G_REJECT
            case FriendInvitation.ONLY_JADE:
                # 勾协
                logger.info(f"Only accept jade invitation")
                if self.appear(self.I_G_JADE):
                    click_button = self.I_G_ACCEPT
                else:
                    click_button = self.I_G_IGNORE
            case FriendInvitation.JADE_AND_FOOD:
                # 如果是接受勾协和粮协
                logger.info(f"Accept jade and food invitation")
                if self.appear(self.I_G_JADE) or self.appear(self.I_G_CAT_FOOD) or self.appear(self.I_G_DOG_FOOD):
                    click_button = self.I_G_ACCEPT
                else:
                    click_button = self.I_G_IGNORE
            case FriendInvitation.IGNORE:
                # 如果是忽略
                logger.info(f"Ignore friend invitation")
                click_button = self.I_G_IGNORE
            case _:
                raise ScriptError(f'Unknown friend invitation type: {invite_type}')
        if not click_button:
            raise ScriptError(f'Unknown click button type: {invite_type}')
        while 1:
            self.device.screenshot()
            if not self.appear(target=click_button):
                logger.info('Deal with invitation done')
                break
            if self.appear_then_click(click_button, interval=0.8):
                continue
        # 有的时候长战斗 点击后会取消战斗状态
        self.device.detect_record = detect_record
        # 如果接受邀请则立即执行悬赏任务
        if click_button == self.I_G_ACCEPT:
            self.set_next_run(task='WantedQuests', target=datetime.now().replace(microsecond=0))
        return True

    def screenshot(self):
        """
        截图 引入中间函数的目的是 为了解决如协作的这类突发的事件
        :return:
        """
        self.device.screenshot()
        # 判断勾协
        self._burst()

        # ★★★ 框架级「暂停调度」兜底（A 方案, 用户确认）★★★
        #
        # ★ 为什么放这里: `screenshot()` 是**所有任务循环**都会经过的公共入口
        #   （实测那 21 个不使用 `GeneralBattle` 的任务, 每个 `while` 里都有它）。
        #   一处改动 -> **54/54** 任务都能被暂停停下（此前只有 33 个）。
        #
        # ⚠ 它比"战斗结束"更早中断（可能停在界面操作中途）—— 三道闸 + 排除名单
        #   见 `_pause_check_at_screenshot()` 的 docstring。
        # ⚠ 放在 `_burst()` **之后**: 勾协是"突然事件", 先处理完它再考虑暂停,
        #   免得暂停把协作响应打断（那是要立刻做的）。
        self._pause_check_at_screenshot()

        # # 判断网络异常
        # if self.appear(self.I_NETWORK_ABNORMAL):
        #     logger.warning(f"Network abnormal")
        #     raise GameStuckError
        #
        # # 判断网络错误
        # if self.appear(self.I_NETWORK_ERROR):
        #     logger.warning(f"Network error")
        #     raise GameStuckError

        return self.device.image

    def maybe_screenshot(self, soft_skip: bool = False):
        """
        可能截图
        :param soft_skip: True跳过截图(但保证设备一定有图才跳过,否则依然截图)
        :return:
        """
        if not soft_skip or not self.exist_image():
            return self.screenshot()
        return self.device.image

    def exist_image(self) -> bool:
        """
        判断当前设备是否有图片
        :return: 有返回True，没有返回False
        """
        return hasattr(self.device, 'image') and self.device.image is not None

    def appear(self,
               target: RuleImage | RuleGif | RuleOcr,
               interval: float = None,
               threshold: float = None):
        """

        :param target: 匹配的目标可以是RuleImage, 也可以是RuleOcr
        :param interval:
        :param threshold:
        :return: interval时间到达且匹配成功则返回True, 否则False
        """
        if interval:
            if target.name in self.interval_timer:
                if self.interval_timer[target.name].limit != interval:
                    self.interval_timer[target.name] = Timer(interval)
            else:
                self.interval_timer[target.name] = Timer(interval)
            if not self.interval_timer[target.name].reached():
                return False
        if isinstance(target, RuleOcr):
            appear = self.ocr_appear(target, interval)
        else:
            appear = target.match(self.device.image, threshold=threshold)

        if appear and interval:
            self.interval_timer[target.name].reset()

        return appear

    def appear_then_click(self,
                          target: RuleImage | RuleGif | RuleOcr,
                          action: Union[RuleClick, RuleLongClick] = None,
                          interval: float = None,
                          threshold: float = None,
                          duration: float = None):
        """
        出现了就点击，默认点击图片的位置，如果添加了click参数，就点击click的位置
        :param duration: 如果是长按，可以手动指定duration，不指定默认.单位是ms！！！！
        :param action: 可以是RuleClick, 也可以是RuleLongClick
        :param target: 可以是RuleImage后续支持RuleOcr
        :param interval:
        :param threshold:
        :return: True or False
        """
        appear = self.appear(target, interval=interval, threshold=threshold)
        if appear and not action:
            x, y = target.coord()
            self.device.click(x, y, control_name=target.name)

        elif appear and action:
            x, y = action.coord()
            if isinstance(action, RuleLongClick):
                if duration is None:
                    self.device.long_click(x, y, duration=action.duration / 1000, control_name=target.name)
                else:
                    self.device.long_click(x, y, duration=duration / 1000, control_name=target.name)
            elif isinstance(action, RuleClick):
                self.device.click(x, y, control_name=target.name)

        return appear

    def appear_multi_scale(self,
                           target: RuleImage,
                           interval: float = None,
                           threshold: float = None,
                           scales: list = None,
                           scale_range: tuple = None):
        """
        多尺度图片识别，自动尝试多个缩放比例以适应图片大小的变化
        :param target: RuleImage对象
        :param interval: 匹配间隔时间
        :param threshold: 匹配阈值
        :param scales: 缩放比例列表
        :param scale_range: 缩放范围 (start, end, step)，例如 (0.8, 1.2, 0.1)
        :return: interval时间到达且匹配成功则返回True, 否则False
        """
        if interval:
            if target.name in self.interval_timer:
                if self.interval_timer[target.name].limit != interval:
                    self.interval_timer[target.name] = Timer(interval)
            else:
                self.interval_timer[target.name] = Timer(interval)
            if not self.interval_timer[target.name].reached():
                return False

        appear = target.match_multi_scale(self.device.image, threshold=threshold, scales=scales, scale_range=scale_range)

        if appear and interval:
            self.interval_timer[target.name].reset()

        return appear

    def appear_then_click_multi_scale(self,
                                      target: RuleImage,
                                      action: Union[RuleClick, RuleLongClick] = None,
                                      interval: float = None,
                                      threshold: float = None,
                                      scales: list = None,
                                      scale_range: tuple = None,
                                      duration: float = None):
        """
        多尺度图片识别并点击，自动尝试多个缩放比例以适应图片大小的变化
        :param target: RuleImage对象
        :param action: 点击位置，可以是RuleClick或RuleLongClick
        :param interval: 匹配间隔时间
        :param threshold: 匹配阈值
        :param scales: 缩放比例列表
        :param scale_range: 缩放范围 (start, end, step)，例如 (0.8, 1.2, 0.1)
        :param duration: 长按时间（毫秒）
        :return: True or False
        """
        appear = self.appear_multi_scale(target, interval=interval, threshold=threshold, scales=scales, scale_range=scale_range)

        if appear and not action:
            x, y = target.coord()
            self.device.click(x, y, control_name=target.name)
        elif appear and action:
            x, y = action.coord()
            if isinstance(action, RuleLongClick):
                if duration is None:
                    self.device.long_click(x, y, duration=action.duration / 1000, control_name=target.name)
                else:
                    self.device.long_click(x, y, duration=duration / 1000, control_name=target.name)
            elif isinstance(action, RuleClick):
                self.device.click(x, y, control_name=target.name)

        return appear

    def wait_until_appear(self,
                          target: RuleImage | RuleGif | RuleOcr,
                          skip_first_screenshot=False,
                          wait_time: int = None) -> bool:
        """
        等待直到出现目标
        :param wait_time: 等待时间，单位秒
        :param target:
        :param skip_first_screenshot:
        :return:
        """
        wait_timer = None
        if wait_time:
            wait_timer = Timer(wait_time)
            wait_timer.start()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.screenshot()
            if wait_timer and wait_timer.reached():
                logger.warning(f"Wait until appear {target.name} timeout")
                return False
            if isinstance(target, (RuleImage, RuleGif)) and self.appear(target):
                return True
            if isinstance(target, RuleOcr) and self.ocr_appear(target):
                return True

    def wait_until_appear_then_click(self,
                                     target: RuleImage | RuleGif,
                                     action: Union[RuleClick, RuleLongClick] = None,
                                     wait_time: int = None) -> bool:
        """
        等待直到出现目标，然后点击
        :param wait_time:
        :param action:
        :param target:
        :return:
        """
        if not self.wait_until_appear(target, wait_time):
            return False
        click_x, click_y = target.coord()
        if action is None:
            self.device.click(click_x, click_y, control_name=target.name)
        elif isinstance(action, RuleLongClick):
            self.device.long_click(click_x, click_y, duration=action.duration / 1000, control_name=target.name)
        elif isinstance(action, RuleClick):
            self.device.click(click_x, click_y, control_name=target.name)
        return True

    def wait_until_disappear(self, target: RuleImage) -> None:
        while 1:
            self.screenshot()
            if not self.appear(target):
                break

    def wait_until_pos_stable(self, target: RuleImage, stable_time: float = 0.3, timeout: float = 2,
                              threshold: float = None, skip_first_screenshot: bool = True) -> bool:
        """
        等待直到在同一位置稳定出现
        :param skip_first_screenshot:
        :param threshold: target匹配阈值
        :param target: 目标图像
        :param stable_time: 判断是否稳定的时间
        :param timeout: 等待稳定的超时时间
        :return: timer时间内稳定出现则返回True, 否则False
        """
        logger.info(f'Wait until {target.name} position stable')
        timeout_timer = Timer(timeout).start()
        stable_timer = Timer(stable_time).start()
        pre_roi_front, cur_roi_front = None, None
        origin_roi_back = target.roi_back
        while not timeout_timer.reached():
            self.maybe_screenshot(skip_first_screenshot)
            skip_first_screenshot = False
            # 当前页面能够匹配到target
            if target.match(self.device.image, threshold=threshold):
                cur_roi_front = target.roi_front
                logger.info(f'Current:{cur_roi_front}, pre:{pre_roi_front}')
                target.roi_back = pre_roi_front
                # 上一次匹配到的位置还能匹配到target
                if pre_roi_front is not None and target.match(self.device.image, threshold=threshold):
                    # 到达稳定时间
                    if stable_timer.reached():
                        logger.info(f'{target.name} position has stabilized')
                        target.roi_back = origin_roi_back
                        return True
                else:
                    stable_timer.reset()  # 上一次匹配到的位置这次匹配不到了, 重置定时器
            else:
                stable_timer.reset()  # 当前页面都匹配不到, 重置定时器
            # 记录这一次的target位置
            pre_roi_front = cur_roi_front
            # 还原target的匹配区域
            target.roi_back = origin_roi_back
        logger.warning(f'Wait until pos stable({target}) timeout')
        return False

    def wait_until_stable(self,
                          target: RuleImage,
                          timer=Timer(0.3, count=1),
                          timeout=Timer(5, count=10),
                          skip_first_screenshot=True):
        """
        等待目标稳定，即连续多次匹配成功
        :param target:
        :param timer:
        :param timeout:
        :param skip_first_screenshot:
        :return:
        """
        target._match_init = False
        timeout.reset()
        while 1:
            if skip_first_screenshot:
                skip_first_screenshot = False
            else:
                self.screenshot()

            if target._match_init:
                if target.match(self.device.image):
                    if timer.reached():
                        break
                else:
                    # button.load_color(self.device.image)
                    timer.reset()
            else:
                # target.load_color(self.device.image)
                target._match_init = True

            if timeout.reached():
                logger.warning(f'Wait_until_stable({target}) timeout')
                break

    def _loop_budget(self, name: str, timeout: float, max_clicks: int = None) -> dict:
        """
        创建一个用于 `while 1` 循环的超时与点击预算记录。

        任务层大量使用 `while 1: screenshot -> 条件 break -> click(continue)` 的写法,
        它的跳出完全依赖某个识别结果。一旦该识别因模板失配、UI 改版、皮肤差异或后台截图
        丢帧而恒不成立, 循环会永远点击同一个按钮。此时 Device 的看门狗也救不了:
        `click()` -> `handle_control_check()` -> `stuck_record_clear()` (device.py:165-168)
        每次点击都会重置卡死计时器, 所以只有 click_record 累计 10 次同名点击才会抛
        GameTooManyClickError, 而该异常会导致整个脚本进程 exit(1)。

        使用方式:

            budget = self._loop_budget('Check lantern 1', timeout=40, max_clicks=8)
            while 1:
                self.screenshot()
                if 条件:
                    break
                if self.appear_then_click(target, interval=1):
                    self._loop_budget_tick(budget, clicked=True)
                    continue
                self._loop_budget_tick(budget)

        :param name: 预算的可读名称, 用于日志定位
        :param timeout: 无进展超时秒数
        :param max_clicks: 点击次数上限, None 表示只按时间限制
        :return: 预算记录 dict
        """
        return {
            'name': name,
            'timer': Timer(timeout).start(),
            'timeout': timeout,
            'max_clicks': max_clicks,
            'clicks': 0,
        }

    def _loop_budget_tick(self, budget: dict, clicked: bool = False) -> None:
        """
        在循环每一轮调用, 记录进展并检查是否超预算。

        "有进展"定义为产生了点击, 因此会在点击时重置无进展计时。这与看门狗的语义有意
        区分: 看门狗判定"无操作", 本方法判定"无进展"。两个判据互补, 本方法专门覆盖
        "一直在点但界面毫无变化"这一看门狗因被重置而漏掉的场景。

        预算耗尽时抛 TaskEnd 而不是异常: 任务正常结束, 由 Script.loop 重新调度下次运行,
        避免单点界面异常升级为进程自杀(script.py:616 -> exit(1))。

        :param budget: `_loop_budget()` 返回的记录
        :param clicked: 本轮是否产生了点击
        :return: 未超预算时正常返回, 超预算时抛 TaskEnd
        """
        if clicked:
            budget['clicks'] += 1
            budget['timer'].reset()
            max_clicks = budget['max_clicks']
            if max_clicks is not None and budget['clicks'] >= max_clicks:
                logger.warning(
                    f"{budget['name']}: 点击达到上限 {max_clicks} 次仍未推进, 结束本次任务"
                )
                raise TaskEnd(budget['name'])
            return
        if budget['timer'].reached():
            logger.warning(
                f"{budget['name']}: 连续 {budget['timeout']} 秒无进展 "
                f"(已点击 {budget['clicks']} 次), 结束本次任务"
            )
            raise TaskEnd(budget['name'])

    def wait_animate_stable(self, rule: RuleAnimate, interval: float = None, timeout: float = None):
        """
        不同与上面的wait_until_stable，这个将会匹配连续的两帧图片的特定区域
        @param rule:
        @param interval:
        @param timeout:
        @return:
        """
        if not isinstance(rule, RuleAnimate):
            rule = RuleAnimate(rule)
        timeout_timer = Timer(timeout).start() if timeout is not None else None
        while 1:
            self.screenshot()

            if interval:
                if rule.name in self.interval_timer:
                    if self.interval_timer[rule.name].limit != interval:
                        self.interval_timer[rule.name] = Timer(interval)
                else:
                    self.interval_timer[rule.name] = Timer(interval)
                if not self.interval_timer[rule.name].reached():
                    return False

            stable = rule.stable(self.device.image)
            if stable:
                if interval:
                    self.interval_timer[rule.name].reset()
                break

            if timeout_timer and timeout_timer.reached():
                logger.info(f'Wait_animate_stable({rule}) timeout')
                break

    def swipe(self, swipe: RuleSwipe, interval: float = None) -> None:
        """

        :param interval:
        :param swipe:
        :return:
        """
        if not isinstance(swipe, RuleSwipe):
            return

        if interval:
            if swipe.name in self.interval_timer:
                # 如果传入的限制时间不一样，则替换限制新的传入的时间
                if self.interval_timer[swipe.name].limit != interval:
                    self.interval_timer[swipe.name] = Timer(interval)
            else:
                # 如果没有限制时间，则创建限制时间
                self.interval_timer[swipe.name] = Timer(interval)
            # 如果时间还没到达，则不执行
            if not self.interval_timer[swipe.name].reached():
                return

        x1, y1, x2, y2 = swipe.coord()
        self.device.swipe(p1=(x1, y1), p2=(x2, y2), control_name=swipe.name)

        # 执行后，如果有限制时间，则重置限制时间
        if interval:
            # logger.info(f'Swipe {swipe.name}')
            self.interval_timer[swipe.name].reset()

    def click(self, click: Union[RuleClick, RuleLongClick, RuleImage, RuleOcr] = None, interval: float = None) -> bool:
        """
        点击或者长按
        :param interval:
        :param click:
        :return: 返回值不是click是否成功，而是interval是否设置以及是否到时间
        """
        if not click:
            return False

        if interval:
            if click.name in self.interval_timer:
                # 如果传入的限制时间不一样，则替换限制新的传入的时间
                if self.interval_timer[click.name].limit != interval:
                    self.interval_timer[click.name] = Timer(interval)
            else:
                # 如果没有限制时间，则创建限制时间
                self.interval_timer[click.name] = Timer(interval)
            # 如果时间还没到达，则不执行
            if not self.interval_timer[click.name].reached():
                return False

        x, y = click.coord()
        if isinstance(click, RuleLongClick):
            self.device.long_click(x=x, y=y, duration=click.duration / 1000, control_name=click.name)
        elif isinstance(click, RuleClick) or isinstance(click, RuleImage) or isinstance(click, RuleOcr):
            self.device.click(x=x, y=y, control_name=click.name)

        # 执行后，如果有限制时间，则重置限制时间
        if interval:
            self.interval_timer[click.name].reset()
            return True
        return False

    def ocr_appear(self, target: RuleOcr, interval: float = None, exact: bool = False) -> bool:
        """
        ocr识别目标
        :param interval:
        :param target:
        :param exact: 是否只匹配完整的单个 OCR 文本， 加上这个参数是为了 https://github.com/runhey/OnmyojiAutoScript/issues/1782
        :return: 如果target有keyword或者是keyword存在，返回是True，否则返回False
                 但是没有指定keyword，返回的是匹配到的值，具体取决于target的mode
        """
        if not isinstance(target, RuleOcr):
            return None

        if interval:
            if target.name in self.interval_timer:
                # 如果传入的限制时间不一样，则替换限制新的传入的时间
                if self.interval_timer[target.name].limit != interval:
                    self.interval_timer[target.name] = Timer(interval)
            else:
                # 如果没有限制时间，则创建限制时间
                self.interval_timer[target.name] = Timer(interval)
            # 如果时间还没到达，则不执行
            if not self.interval_timer[target.name].reached():
                return None

        result = target.ocr(self.device.image, exact=exact)
        appear = False

        if not target.keyword or target.keyword == '':
            appear = False
        match target.mode:
            case OcrMode.FULL:  # 全匹配
                appear = result != (0, 0, 0, 0)
            case OcrMode.SINGLE:
                appear = result == target.keyword
            case OcrMode.DIGIT:
                appear = result == int(target.keyword)
            case OcrMode.DIGITCOUNTER:
                appear = result == target.ocr_str_digit_counter(target.keyword)
            case OcrMode.DURATION:
                appear = result == target.parse_time(target.keyword)

        if interval and appear:
            self.interval_timer[target.name].reset()

        return appear

    def ocr_appear_click(self,
                         target: RuleOcr,
                         action: Union[RuleClick, RuleLongClick] = None,
                         interval: float = None,
                         duration: float = None,
                         exact: bool = False) -> bool:
        """
        ocr识别目标，如果目标存在，则触发动作
        :param target:
        :param action:
        :param interval:
        :param duration:
        :param exact: 是否只匹配完整的单个 OCR 文本 ， 加上这个参数是为了 https://github.com/runhey/OnmyojiAutoScript/issues/1782
        :return:
        """
        appear = self.ocr_appear(target, interval, exact=exact)

        if not appear:
            return False

        if action:
            x, y = action.coord()
            self.click(action, interval)
        else:
            x, y = target.coord()
            self.device.click(x=x, y=y, control_name=target.name)
        return True

    def list_find(self, target: RuleList, name: str | list[str], max_swipe: int = 10) -> bool | tuple:
        """
        会一致在列表寻找目标，找到了就退出。
        如果是图片列表会一直往下找
        如果是纯文字的，会自动识别自己的位置，根据位置选择向前还是向后翻
        :param max_swipe: 最大滑动次数
        :param target:
        :param name:
        :return:
        """
        swipe_down = False
        swipe_distance_ratio = None
        result = None
        if not target:
            return False
        appear = False
        for _ in range(max_swipe):
            self.screenshot()
            if target.is_image:
                result = target.image_appear(self.device.image, name=name)
                swipe_down = True
            elif target.is_ocr:
                result = target.ocr_appear(self.device.image, name=name)
                swipe_down = result is not None and isinstance(result, int) and result > 0
                swipe_distance_ratio = 1
            # 结果是坐标证明找到了, 非坐标都是没找到
            if result is not None and isinstance(result, tuple):
                appear = True
                break
            if swipe_distance_ratio:
                x1, y1, x2, y2 = target.swipe_pos(number=swipe_distance_ratio, after=swipe_down)
            else:
                x1, y1, x2, y2 = target.swipe_pos(after=swipe_down)
            self.device.swipe(p1=(x1, y1), p2=(x2, y2))
            sleep(random.uniform(0.8, 1.3))  # 等待滑动完成, 待优化
        if appear:
            return result
        return False

    def list_appear_click(self, target: RuleList, interval: float = None, max_swipe: int = 10) -> bool:
        if interval:
            if target.name in self.interval_timer:
                # 如果传入的限制时间不一样，则替换限制新的传入的时间
                if self.interval_timer[target.name].limit != interval:
                    self.interval_timer[target.name] = Timer(interval)
            else:
                # 如果没有限制时间，则创建限制时间
                self.interval_timer[target.name] = Timer(interval)
            # 如果时间还没到达，则不执行
            if not self.interval_timer[target.name].reached():
                return False
        appear = self.list_find(target, name=target.array[0], max_swipe=max_swipe)
        if isinstance(appear, tuple) and interval:
            x, y = appear
            self.device.click(x, y)
            self.interval_timer[target.name].reset()
            return True
        return False

    def set_next_run(self, task: str, finish: bool = False,
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
        if finish:
            start_time = datetime.now().replace(microsecond=0)
        else:
            start_time = self.start_time
        self.config.task_delay(task, start_time=start_time, success=success, server=server, target=target)

    def custom_next_run(self, task: str, custom_time: Time = None, time_delta: float = 1) -> None:
        """
        设置下次自定义运行时间
        :param task: 任务名称，大驼峰的
        :param custom_time: 可以自定义的下次运行时间
        :param time_delta: 下次运行日期为几天后，默认为第二天
        :return:
        """
        target_time = (datetime.now() + timedelta(days=time_delta)).replace(hour=custom_time.hour,
                                                                            minute=custom_time.minute,
                                                                            second=custom_time.second)
        self.set_next_run(task, target=target_time)

    #  ---------------------------------------------------------------------------------------------------------------
    #
    #  ---------------------------------------------------------------------------------------------------------------
    def ui_reward_appear_click(self, screenshot=False) -> bool:
        """
        如果出现 ‘获得奖励’ 就点击
        :return:
        """
        if screenshot:
            self.screenshot()
        return self.appear_then_click(self.I_UI_REWARD, action=self.C_UI_REWARD, interval=0.4, threshold=0.6)

    def ui_get_reward(self, click_image: RuleImage or RuleOcr or RuleClick, click_interval: float = 1):
        """
        传进来一个点击图片 或是 一个ocr， 会点击这个图片，然后等待‘获得奖励’，
        最后当获得奖励消失后 退出
        :param click_interval:
        :param click_image:
        :return:
        """
        _timer = Timer(10)
        _timer.start()
        while 1:
            self.screenshot()

            if self.ui_reward_appear_click():
                sleep(0.5)
                while 1:
                    self.screenshot()
                    # 等待动画结束
                    if not self.appear(self.I_UI_REWARD, threshold=0.6):
                        logger.info('Get reward success')
                        break

                    # 一直点击
                    if self.ui_reward_appear_click():
                        continue
                break
            if _timer.reached():
                logger.warning('Get reward timeout')
                break

            if isinstance(click_image, RuleImage):
                if self.appear_then_click(click_image, interval=click_interval):
                    continue
            elif isinstance(click_image, RuleOcr):
                if self.ocr_appear_click(click_image, interval=click_interval):
                    continue
            elif isinstance(click_image, RuleClick):
                if self.click(click_image, interval=click_interval):
                    continue

        return True

    def ui_click(self, click, stop, interval=1, timeout=None):
        """
        循环的一个操作，直到出现stop
        :param click:
        :param stop:
        :param interval: 点击间隔
        :param timeout: 超时时间（秒），None表示不超时
        :return:
        """
        timer = Timer(timeout).start() if timeout else None
        while 1:
            self.screenshot()
            if self.appear(stop):
                return True
            if timer and timer.reached():
                logger.warning(f'ui_click timeout after {timeout}s')
                return False
            if isinstance(click, RuleImage) and self.appear_then_click(click, interval=interval):
                continue
            if isinstance(click, RuleClick) and self.click(click, interval=interval):
                continue
            elif isinstance(click, RuleOcr) and self.ocr_appear_click(click, interval=interval):
                continue

    def ui_clicks(self, clicks: list[RuleImage | RuleOcr | RuleClick], stop: RuleImage, interval=1):
        while 1:
            self.screenshot()
            if self.appear(stop):
                break
            for click in clicks:
                if isinstance(click, RuleImage) and self.appear_then_click(click, interval=interval):
                    continue
                elif isinstance(click, RuleClick) and self.click(click, interval=interval):
                    continue
                elif isinstance(click, RuleOcr) and self.ocr_appear_click(click, interval=interval):
                    continue

    def ui_click_until_disappear(self, click, interval: float = 1):
        """
        点击一个按钮直到消失
        :param interval:
        :param click:
        :return:
        """
        while 1:
            self.screenshot()
            if not self.appear(click):
                break
            elif self.appear_then_click(click, interval=interval):
                continue

    def ui_click_until_smt_disappear(self, click, stop, interval: float = 1):
        """
        点击一个按钮/区域/文字直到stop消失

        """
        while 1:
            self.screenshot()
            if not self.appear(stop):
                break
            if isinstance(click, RuleImage) or isinstance(click, RuleGif):
                self.appear_then_click(click, interval=interval)
                continue
            if isinstance(click, RuleClick):
                self.click(click, interval)
                continue
            if isinstance(click, RuleOcr):
                self.click(click)
                continue

    def ui_click_multi_scale(self, click, stop, interval=1, scale_range=None, timeout=None):
        """
        循环的一个操作，直到出现stop（支持多尺度图片识别）
        :param click:
        :param stop:
        :param interval:
        :param scale_range: 多尺度缩放范围 (start, end, step)
        :param timeout: 超时时间（秒），None表示不超时
        :return: True-找到stop条件, False-超时
        """
        timer = Timer(timeout).start() if timeout else None
        while 1:
            self.screenshot()
            if self.appear(stop):
                return True
            if timer and timer.reached():
                logger.warning(f'ui_click_multi_scale timeout after {timeout}s')
                return False
            if isinstance(click, RuleImage) and self.appear_then_click_multi_scale(click, scale_range=scale_range, interval=interval):
                continue
            if isinstance(click, RuleClick) and self.click(click, interval=interval):
                continue
            elif isinstance(click, RuleOcr) and self.ocr_appear_click(click, interval=interval):
                continue

    def push_notify(self, content='', title=None, level=3):
        logger.info(f'Push notify: {content}')

    def save_image(self, task_name=None, content=None, wait_time=2, image_type=False, push_flag=False, level=3):
        logger.info(f'Save image: {task_name}')
