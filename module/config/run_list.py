# -*- coding: utf-8 -*-
"""运行列表（条目清单）—— 用户编排的调度顺序。

## 为什么需要它

此前有两个各自不完整的东西:

1. **`ConfigManual.SCHEDULER_PRIORITY`** —— 顺序**硬编码**在代码里, 用户改不了
2. `ScheduleRule.FIFO` —— 按 `next_run` 排(先到点先跑), 是"定时优先"而非"列表优先"

后来加了 `task_order`(逗号分隔任务名), 但**只能排任务**, 无法表达
"打完御魂后休息 30 分钟"这类**在序列中间发生的事**。

## 本模型(条目清单)

列表是**有序条目**的序列, 条目有两种:

    kind=task   —— 跑某个任务（**任意任务**都可以）
    kind=rest   —— **休息** N 分钟(去庭院待着, 阻塞列表)

例(JSON 里就是一个数组, 顺序天然保留):

    "run_list": [
        {"kind": "task",  "task": "Exploration"},
        {"kind": "task",  "task": "Orochi"},
        {"kind": "rest",  "minutes": 30},
        {"kind": "task",  "task": "GoldYoukai"}
    ]

## ★★ 列表里为什么**不限制**任务类型(踩过的坑) ★★

曾经为了"固定任务与定时任务分开管理", 在这里加了校验:
**只允许 `countable`(fixed/toppa) 的任务进列表**, 其余一律跳过并记 warning。

结果是一次**静默的数据破坏**:

* `countable` 的判据是"有 `count_field`", 全仓 54 个任务里只有 **14 个**满足
* `WantedQuests` 是 `fixed`(固定任务) 却**没有** `count_field` -> 被丢弃
* 用户的列表里有 `DemonEncounter` / `WantedQuests` / `MysteryShop` / `Duel` /
  `ExperienceYoukai` / `TrueOrochi` / `WeeklyTrifles` -> **全部被跳过**
* 更糟的是 `build_run_list()` 过滤后, `save_run_list()` 会把**过滤后的结果写回**
  -> 用户的编排可能被永久抹掉

**结论: 列表接受任意任务名。** 理由:

1. "固定/定时分开管理"是**调度器**的事(两个总开关 + `timed_priority`),
   不该由**列表的准入规则**来承担
2. 把定时任务放进列表只是给它一个**上下文顺序**, 与它自己的 window/周期
   **不冲突** —— 调度器仍会检查 window
3. 用户要的是"按我的顺序跑", 不是"只能放我批准的"
4. **静默丢弃用户的配置**是比"类型混用"严重得多的错误

## 语义(★ 关键设计决定)

| 条目 | 是否**阻塞**列表 | 说明 |
|---|---|---|
| `task` | ❌ **不阻塞** | 轮到时若任务未就绪(冷却/额度/不在时段), **跳过它继续看后面的** |
| `rest` | ✅ **阻塞** | 轮到时去庭院待着到时刻 T; 到点后**移除该条目**并继续 |

### ★ 为什么 `task` 不阻塞

若任务会阻塞, 则"列表里第一个任务在 6 小时冷却中"会**卡死整个列表** ——
这显然不是用户想要的。所以:

* 列表提供的是**优先顺序**(排在前面的先跑), 而不是"必须按顺序做完"
* 真正的"在此处停下"由 `rest` 条目显式表达

这与 `ScheduleRule.FILTER/FIFO/PRIORITY` 保持一致: 它们也是**排序**而非**阻塞**。

### ★ `rest` 是一次性条目

它被"轮到时"就生效, 生效期间列表**停在该条目之前**;
时间到了以后该条目**被移除**(持久化), 列表继续。

这样用户看到的是"休息这一行消失了", 而不是"每次循环都休息一次" ——
后者会让人以为软件坏了。

## 与旧 `task_order` 的关系

`task_order`(逗号分隔任务名)是**旧字段**, 已被 `run_list` 取代。
转换是一次性的、可逆的: 见 `from_task_order()`。
"""
import bisect
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class EntryKind(str, Enum):
    """
    列表条目类型。

    ## v2 只保留两种

    * `task` —— 跑一个**固定任务**
    * `rest` —— **休息**: 去庭院待着 N 分钟

    ## 为什么去掉了 `delay`

    v1 里有 `delay`（"只停列表"），那是为了表达"定时任务照常、只停列表"。
    但 v2 之后**固定任务与定时任务分开管理**（定时任务有自己的总开关），
    "只停列表" 这个概念不再有意义 —— 想只停列表就关掉定时任务开关。

    ## 为什么 `task` 只能是固定任务

    定时任务有它自己的 window / 存量 / 周期，
    "放进列表按顺序执行" 与那些机制冲突（见 `is_list_task()`）。
    """

    TASK = 'task'      # 跑一个固定任务
    REST = 'rest'      # **休息**: 去庭院待着 N 分钟


# 效果命名(用户要求): 按**行为**命名, 不叫"停止/延后"那种容易误解的词
KIND_LABEL = {
    EntryKind.TASK: '任务',
    EntryKind.REST: '休息',
}

# 条目类型的可读说明(界面直接显示, 不必前端维护)
KIND_HELP = {
    EntryKind.TASK: '执行这个固定任务',
    EntryKind.REST: '去庭院待着 N 分钟（游戏不会断线，组队回来时人在）',
}

# 时长的默认可选项(分钟)
DURATION_CHOICES = (10, 30, 60, 120, 240)


def is_list_task(task: str) -> bool:
    """
    **查询辅助**: 该任务是不是"可计数"的固定任务（`fixed` / `toppa`）。

    ## ⚠️ 它**不是**列表的准入规则

    曾经用它在 `from_list()` 里过滤列表条目, 结果是**静默丢弃用户配置**
    （见模块 docstring 的"踩过的坑"）。

    **列表接受任意任务名** —— 这个函数只用于"想筛出固定任务"的**展示/统计**
    场景。任何会写回配置的路径都不该用它排除条目。

    未知任务名 -> False（不崩）。
    """
    try:
        from module.config import task_catalog as TC
        meta = TC.get(task)
        return bool(meta and meta.countable)
    except Exception:
        return False


@dataclass(frozen=True)
class RunEntry:
    """
    列表里的**一个条目**。

    字段按 `kind` 使用:
        kind=TASK   -> `task`(任务名, 大驼峰; **必须是固定任务**)
        kind=REST   -> `minutes`
    """

    kind: EntryKind = EntryKind.TASK
    task: str = ''
    minutes: int = 0
    # ★★ C: 条目身份（用户裁定: "entry_id 用当前时间 + task 来实现"）★★
    #
    # 为什么需要它: 队列里**同一任务可以出现多次**（用户用重复条目表达
    # "重复跑整个任务"）。要按**条目**追踪"这条跑过没有",
    # 就必须有一个**稳定**的身份 —— 任务名不够（重复条目会撞）。
    #
    # 为空时由 `__post_init__` 自动补（**旧配置没有这个字段**, 读进来就是空）。
    entry_id: str = ''

    # ★★ S6: **类别分段**（用户裁定: "给 run_list 加类别分段"）★★
    #
    # 用户原话:
    #   "拖动只在同类别内生效是在选了**定时优先**或者**固定任务优先**时,
    #    如果选了**列表自定义**, 那么全都可以拖动次序。"
    #
    # 字段含义: 条目所属的**类别段** —— `'timed'`（定时任务类）或
    # `'fixed'`（固定任务类）。★ 空串 = **未分段**（旧配置）,
    # 由 `RunList.regroup()` 或 `Config.build_run_list()` 补齐。
    #
    # ★ 为什么存**段名**而不是"顺序号": 段内顺序已经由 `entries` 的**列表次序**
    #   表达（"顺序即数据"）; 这里只需要知道"它属于哪个段", 用来做
    #   **拖动约束**（同段内可拖, 跨段不可）。
    group: str = ''

    def __post_init__(self):
        if not isinstance(self.kind, EntryKind):
            try:
                object.__setattr__(self, 'kind', EntryKind(self.kind))
            except ValueError as exc:
                raise ValueError(
                    f'非法条目类型: {self.kind!r}; '
                    f'应为 {[k.value for k in EntryKind]}') from exc

        if self.kind == EntryKind.TASK:
            if not self.task:
                raise ValueError('kind=task 需要非空 task')
            object.__setattr__(self, 'minutes', 0)
            # ★ C: 没给 `entry_id` 就现生成一个（旧配置 / 手工构造都会走这里）
            if not self.entry_id:
                object.__setattr__(
                    self, 'entry_id', new_entry_id(self.task))
        else:
            try:
                m = int(self.minutes)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f'{self.kind.value} 的 minutes 必须是整数, 实际 {self.minutes!r}'
                ) from exc
            if m <= 0:
                raise ValueError(f'{self.kind.value} 的 minutes 必须 > 0, 实际 {m}')
            object.__setattr__(self, 'minutes', m)
            object.__setattr__(self, 'task', '')
            object.__setattr__(self, 'entry_id', '')

    # ------------------------------------------------------------------ 显示
    def describe(self) -> str:
        """人类可读描述, 供界面与日志使用。"""
        if self.kind == EntryKind.TASK:
            # ★ C: 同一任务有多条时, 显示"加入时间"才能区分它们
            at = added_at_of_entry_id(self.entry_id)
            if at is not None:
                return f'{at:%m-%d %H:%M} · {self.task}'
            return self.task
        mins = self.minutes
        # ★ 带单位 —— 用户要求显示 `[30 分钟]` / `[2 小时]`, 不是裸数字
        if mins % 60 == 0 and mins >= 60:
            return f'{KIND_LABEL[self.kind]} {mins // 60} 小时'
        return f'{KIND_LABEL[self.kind]} {mins} 分钟'

    # ------------------------------------------------------------------ 序列化
    def to_dict(self) -> dict:
        if self.kind == EntryKind.TASK:
            # ★ C: 带上 `entry_id`（**重复条目的身份**）
            #
            # ★★ S6 / 审计修复: `group` **不序列化** ★★
            #
            # 段名是 `Config._tag_and_place_rest()` 的**派生结果**（S7 由
            # `_segment_queue()` 改名而来 —— 它现在**只打段名 + 把 rest
            # 挪到最后**, 不再按任何"模式"排段）, **每次 `build_queue()`
            # 都会重算** —— 存盘只会:
            #   ① 破坏"单一数据源"（台账 §10.8）
            #   ② 前端判据与后端不一致时, 配置里躺着**错的段名**
            #   ③ 让配置文件多出一堆"用户没写过"的字段
            #
            # ★ 我第一版让它"非空才写" —— 但 `_assign_groups()` 会把它算成
            #   非空, 于是**照样落盘**（实测抓到）。所以改成**永不写**。
            return {'kind': self.kind.value, 'task': self.task,
                    'entry_id': self.entry_id}
        return {'kind': self.kind.value, 'minutes': self.minutes}

    @classmethod
    def from_dict(cls, data) -> 'RunEntry':
        """
        宽松解析。

        ★ v1 的 `delay` 条目会是 `ValueError` —— 由调用方（`RunList.from_list`）
          跳过并记录，**不让整份配置加载失败**（旧配置升级时很常见）。
        """
        if not isinstance(data, dict):
            raise ValueError(f'条目必须是对象, 实际 {type(data).__name__}')
        kind = data.get('kind')
        if kind == EntryKind.TASK.value or (kind is None and data.get('task')):
            # ★ C: 旧配置**没有** `entry_id` -> 空字符串 -> `__post_init__`
            #   会现生成一个（**向后兼容**）。
            # ★ S6: `group` 同理 —— 旧配置没有, 读进来是空串（未分段）。
            return cls(kind=EntryKind.TASK,
                       task=str(data.get('task') or ''),
                       entry_id=str(data.get('entry_id') or ''),
                       group=str(data.get('group') or ''))
        if kind == EntryKind.REST.value:
            return cls(kind=EntryKind.REST, minutes=data.get('minutes'))
        raise ValueError(f'未知条目类型: {kind!r}')


@dataclass
class RunList:
    """
    有序的条目清单(可变, 因为 `rest`/`delay` 生效后要**移除**)。

    为什么不用 `task_order` 那种逗号字符串:
      条目需要**多个字段**(task / minutes), 而且要能**插入到任意位置**。
    """

    entries: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self):
        return iter(self.entries)

    def is_empty(self) -> bool:
        return not self.entries

    # ------------------------------------------------------------------ 读
    def task_order(self) -> list:
        """列表里的任务名(按出现顺序, 去重保首)。"""
        seen, out = set(), []
        for e in self.entries:
            if e.kind == EntryKind.TASK and e.task not in seen:
                seen.add(e.task)
                out.append(e.task)
        return out

    def blocking_entry(self):
        """
        返回**阻塞列表**的那个条目, 若没有则 None。

        v2 里只有 `rest` 会阻塞 —— `task` 不阻塞（未就绪就跳过, 见模块文档）。
        """
        for e in self.entries:
            if e.kind == EntryKind.REST:
                return e
        return None

    def index_of_blocker(self):
        """阻塞条目的下标; 没有则 -1。"""
        for i, e in enumerate(self.entries):
            if e.kind == EntryKind.REST:
                return i
        return -1

    def total_rest_minutes(self) -> int:
        """
        整份列表的**休息总时长**（分钟）。

        供「预期执行流程」与"休息时可穿插"的判定使用。
        """
        return sum(e.minutes for e in self.entries
                   if e.kind == EntryKind.REST)

    # ------------------------------------------------------------------ 写
    def unique_entry_id(self, entry: RunEntry) -> str:
        """给条目一个**在本列表内唯一**的 `entry_id`。

        ## 为什么需要

        `entry_id = 时间 + task`（用户裁定）精确到**秒**。同一秒内加入**两次
        同一任务**时, 两条的 id **完全相同** —— 按条目追踪会失效
        （实测踩过: 两条 `RealmRaid` 都是 `20261010T091229-RealmRaid`）。

        ## 做法

        重复时**追加序号**（不改变前缀格式, 仍然可拆可合并）:

            20261010T091229-RealmRaid
            20261010T091229-RealmRaid-2
            20261010T091229-RealmRaid-3
        """
        base = entry.entry_id or new_entry_id(entry.task)
        used = {e.entry_id for e in self.entries if e.entry_id}
        if base not in used:
            return base
        n = 2
        while f'{base}-{n}' in used:
            n += 1
        return f'{base}-{n}'

    def add(self, entry: RunEntry, index: int = None) -> None:
        """插入条目。`index=None` 或越界时追加到末尾。

        ★ C: 插入前**唯一化** `entry_id`
          （同一秒加两次同一任务时, `时间+task` 会撞 -> 追加序号区分）。
        """
        if entry.kind == EntryKind.TASK:
            eid = self.unique_entry_id(entry)
            if eid != entry.entry_id:
                object.__setattr__(entry, 'entry_id', eid)
        if index is None or index < 0 or index > len(self.entries):
            self.entries.append(entry)
        else:
            self.entries.insert(index, entry)

    def remove_at(self, index: int) -> RunEntry or None:
        if 0 <= index < len(self.entries):
            return self.entries.pop(index)
        return None

    def remove_blocker(self) -> RunEntry or None:
        """移除第一个阻塞条目(时间到之后调用)。"""
        i = self.index_of_blocker()
        return self.remove_at(i) if i >= 0 else None

    def clear(self) -> None:
        self.entries.clear()

    def set_from_task_order(self, tasks) -> None:
        """
        只重排**任务条目**, 让 `rest`/`delay` 条目的**下标保持不变**。

        参数是**任务名列表**(不含控制条目)。实现: 把所有任务条目按新顺序
        依次填进"任务槽位", 控制条目原地不动。

        例:
            原: [A, rest, B, C]
            调用 set_from_task_order(['C', 'A', 'B'])
            结果: [C, rest, A, B]        <- rest 仍在第 2 位

        ★ 与 `replace_all()` 的区别:
          * 本方法**不知道**控制条目该怎么摆(任务名列表里没有它们),
            所以保持原位
          * 界面拖拽时用户拖的就是**完整清单**, 应该用 `replace_all()`
        """
        wanted = [t for t in (tasks or []) if t]
        # 逐个填"任务槽位"; 任务变少时**多余的槽位要删掉**
        # (踩过: 只覆盖不删除 -> 传 ['A'] 却留下 A,B,C 三行)
        out = []
        wi = 0
        for e in self.entries:
            if e.kind != EntryKind.TASK:
                out.append(e)
                continue
            if wi < len(wanted):
                out.append(RunEntry(kind=EntryKind.TASK, task=wanted[wi]))
                wi += 1
            # else: 丢弃多余的任务条目
        for name in wanted[wi:]:
            out.append(RunEntry(kind=EntryKind.TASK, task=name))
        self.entries = out

    def replace_all(self, entries) -> None:
        """
        **整体替换**条目清单。

        界面拖拽排序后走这里 —— 因为用户拖的就是完整清单(含控制条目),
        位置信息完整, 不需要"保持原位"的猜测。

        :param entries: `RunEntry` 列表; 也接受 `to_list()` 那样的 dict 列表
        """
        out = []
        for item in (entries or []):
            if isinstance(item, RunEntry):
                out.append(item)
            else:
                out.append(RunEntry.from_dict(item))
        self.entries = out

    # ------------------------------------------------------------------ 序列化
    def to_list(self) -> list:
        return [e.to_dict() for e in self.entries]

    @classmethod
    def from_list(cls, data, on_bad=None, only_list_tasks=False) -> 'RunList':
        """
        宽松解析: **只跳过真正坏的条目**（结构错误 / 未知类型 / 数字非法）,
        并记 warning —— 而不是整份配置加载失败。

        ## ★★ `only_list_tasks` 默认必须是 `False`（踩过的坑）★★

        曾经默认 `True`(只允许 `countable` 的任务进列表), 结果是一次
        **静默的数据破坏**: 用户的 7 个条目被跳过, 而
        `build_run_list()` 过滤后 `save_run_list()` 会把**过滤后的结果写回**
        —— 编排可能被永久抹掉。

        **列表接受任意任务名**（理由见模块 docstring）。

        该参数**保留**只是为了将来可能出现的"只想看固定任务"的**查询**场景;
        **任何会把结果写回配置的路径都不该传 `True`**。

        :param on_bad: 坏条目的回调 `(item, exc)`; 传了才记录（避免静默丢弃）
        """
        out = cls()
        for item in (data or []):
            try:
                entry = RunEntry.from_dict(item)
                if (only_list_tasks and entry.kind == EntryKind.TASK
                        and not is_list_task(entry.task)):
                    raise ValueError(
                        f'{entry.task} 不是固定任务'
                        f'（仅在 only_list_tasks=True 的查询场景下才排除）')
                out.entries.append(entry)
            except ValueError as exc:
                if on_bad is not None:
                    on_bad(item, exc)
        return out

    # ------------------------------------------------------------------ 兼容旧字段
    @classmethod
    def from_task_order(cls, task_order: str, on_bad=None) -> 'RunList':
        """
        从旧的 `task_order`(逗号分隔任务名)迁移。

        旧字段只能表达"任务顺序", 所以迁移结果里**没有** rest 条目。

        ★ 这里**不做**"只收固定任务"的校验 —— 旧配置里可能混着定时任务,
          迁移时宁可先留着（用户自己会看到并清理）, 也不要静默丢掉。
        """
        out = cls()
        for part in str(task_order or '').split(','):
            name = part.strip()
            if not name:
                continue
            try:
                out.entries.append(RunEntry(kind=EntryKind.TASK, task=name))
            except ValueError as exc:
                if on_bad is not None:
                    on_bad(name, exc)
        return out

    def to_task_order(self) -> str:
        """导出成旧格式(便于回退)。"""
        return ','.join(self.task_order())

    # ------------------------------------------------------------------ 预演
    def preview(self, now: datetime, running_lookup=None) -> list:
        """
        预演执行流程(供界面「预期执行流程」面板)。

        :param now: 起点
        :param running_lookup: `task -> bool`, 该任务现在是否正在跑
        :return: [{'at': datetime, 'kind': str, 'text': str, 'note': str}]

        ## 语义

        * `task` 条目 —— 排在**同一时刻**(列表只定先后, 不定间隔)
        * `rest` / `delay` —— 时间**往后推 N 分钟**, 之后的条目都在新时刻

        ★ 这是**推算, 不是保证** —— 实际还受体力 / 网络 / 开放时段影响。
          界面必须标注"推算", 不能让用户以为精确。
        """
        out = []
        t = now
        for e in self.entries:
            if e.kind == EntryKind.TASK:
                running = bool(running_lookup(e.task)) if running_lookup else False
                out.append({
                    'at': t,
                    'kind': e.kind.value,
                    'text': e.task,
                    'note': '进行中' if running else '',
                })
            else:
                t = t + timedelta(minutes=e.minutes)
                out.append({
                    'at': t,
                    'kind': e.kind.value,
                    'text': e.describe(),
                    'note': KIND_HELP[e.kind],
                })
        return out


def new_entry_id(task: str, when: datetime = None) -> str:
    """生成条目 id: `时间 + task`（用户裁定 —— 可拆可合并）。

    格式: `20261010T143005-RealmRaid`
    """
    when = when or datetime.now()
    return f'{when:%Y%m%dT%H%M%S}-{task}'


def task_of_entry_id(entry_id: str) -> str:
    """从 `entry_id` **拆出** task（可拆 —— 用户要求）。

    `20261010T143005-RealmRaid`   -> `RealmRaid`
    `20261010T143005-RealmRaid-2` -> `RealmRaid`（去掉**唯一化序号**）

    认不出格式时**原样返回**（不静默丢东西）。
    """
    s = str(entry_id or '')
    if '-' not in s:
        return s
    head, _, tail = s.partition('-')
    # 形如 20261010T143005 才当前缀剥掉
    if not (len(head) == 15 and head[8] == 'T'
            and head.replace('T', '').isdigit()):
        return s
    # `tail` 可能是 `RealmRaid` 或 `RealmRaid-2` -> 去掉末尾的纯数字序号
    parts = tail.rsplit('-', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return tail


def added_at_of_entry_id(entry_id: str):
    """从 `entry_id` 拆出加入时间; 认不出返回 `None`。"""
    s = str(entry_id or '')
    head = s.split('-', 1)[0]
    if len(head) == 15 and head[8] == 'T':
        try:
            return datetime.strptime(head, '%Y%m%dT%H%M%S')
        except ValueError:
            return None
    return None
