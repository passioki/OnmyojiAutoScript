# -*- coding: utf-8 -*-
"""运行列表（条目清单）—— 用户编排的调度顺序。

## 为什么需要它

此前有两个各自不完整的东西:

1. **`ConfigManual.SCHEDULER_PRIORITY`** —— 顺序**硬编码**在代码里, 用户改不了
2. `ScheduleRule.FIFO` —— 按 `next_run` 排(先到点先跑), 是"定时优先"而非"列表优先"

后来加了 `task_order`(逗号分隔任务名), 但**只能排任务**, 无法表达
"打完御魂后休息 30 分钟"这类**在序列中间发生的事**。

## 本模型(条目清单)

列表是**有序条目**的序列, 条目有三种:

    kind=task   —— 跑某个任务
    kind=rest   —— **全部停止** N 分钟(连定时任务一起停)
    kind=delay  —— **只停列表** N 分钟(定时任务照常)

例(JSON 里就是一个数组, 顺序天然保留):

    "run_list": [
        {"kind": "task",  "task": "Exploration"},
        {"kind": "task",  "task": "Orochi"},
        {"kind": "rest",  "minutes": 30},
        {"kind": "task",  "task": "GoldYoukai"}
    ]

## 语义(★ 关键设计决定)

| 条目 | 是否**阻塞**列表 | 说明 |
|---|---|---|
| `task` | ❌ **不阻塞** | 轮到时若任务未就绪(冷却/额度/不在时段), **跳过它继续看后面的** |
| `rest` | ✅ **阻塞** | 轮到时暂停一切(含定时任务)到时刻 T; 到点后**移除该条目**并继续 |
| `delay` | ✅ **阻塞** | 轮到时只推迟**列表**; 定时任务照常。到点后移除该条目并继续 |

### ★ 为什么 `task` 不阻塞

若任务会阻塞, 则"列表里第一个任务在 6 小时冷却中"会**卡死整个列表** ——
这显然不是用户想要的。所以:

* 列表提供的是**优先顺序**(排在前面的先跑), 而不是"必须按顺序做完"
* 真正的"在此处停下"由 `rest` / `delay` 条目显式表达

这与 `ScheduleRule.FILTER/FIFO/PRIORITY` 保持一致: 它们也是**排序**而非**阻塞**。

### ★ `rest` / `delay` 是一次性条目

它们被"轮到时"就生效, 生效期间列表**停在该条目之前**;
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
    """列表条目类型。"""

    TASK = 'task'      # 跑某个任务
    REST = 'rest'      # **全部停止** N 分钟(连定时任务一起停)
    DELAY = 'delay'    # **只停列表** N 分钟(定时任务照常)


# 效果命名(用户要求): 不叫"休息/延后", 而按**效果**命名, 一目了然
KIND_LABEL = {
    EntryKind.TASK: '任务',
    EntryKind.REST: '全部停止',
    EntryKind.DELAY: '只停列表',
}

# 条目类型的可读说明(界面直接显示, 不必前端维护)
KIND_HELP = {
    EntryKind.TASK: '执行这个任务',
    EntryKind.REST: '暂停调度 N 分钟 —— 连定时任务一起停',
    EntryKind.DELAY: '只推迟列表 N 分钟 —— 定时任务照常',
}

# 时长的默认可选项(分钟)
DURATION_CHOICES = (10, 30, 60, 120, 240)


@dataclass(frozen=True)
class RunEntry:
    """
    列表里的**一个条目**。

    字段按 `kind` 使用:
        kind=TASK   -> `task`(任务名, 大驼峰)
        kind=REST   -> `minutes`
        kind=DELAY  -> `minutes`
    """

    kind: EntryKind = EntryKind.TASK
    task: str = ''
    minutes: int = 0

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

    # ------------------------------------------------------------------ 显示
    def describe(self) -> str:
        """人类可读描述, 供界面与日志使用。"""
        if self.kind == EntryKind.TASK:
            return self.task
        mins = self.minutes
        if mins % 60 == 0 and mins >= 60:
            return f'{KIND_LABEL[self.kind]} {mins // 60} 小时'
        return f'{KIND_LABEL[self.kind]} {mins} 分钟'

    # ------------------------------------------------------------------ 序列化
    def to_dict(self) -> dict:
        if self.kind == EntryKind.TASK:
            return {'kind': self.kind.value, 'task': self.task}
        return {'kind': self.kind.value, 'minutes': self.minutes}

    @classmethod
    def from_dict(cls, data) -> 'RunEntry':
        """宽松解析: 认不出来就抛 ValueError, 由调用方决定跳过还是报错。"""
        if not isinstance(data, dict):
            raise ValueError(f'条目必须是对象, 实际 {type(data).__name__}')
        kind = data.get('kind')
        if kind == EntryKind.TASK.value or kind is None and data.get('task'):
            return cls(kind=EntryKind.TASK, task=str(data.get('task') or ''))
        if kind == EntryKind.REST.value:
            return cls(kind=EntryKind.REST, minutes=data.get('minutes'))
        if kind == EntryKind.DELAY.value:
            return cls(kind=EntryKind.DELAY, minutes=data.get('minutes'))
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

        只有 `rest` / `delay` 会阻塞(`task` 不阻塞, 见模块文档)。
        """
        for e in self.entries:
            if e.kind in (EntryKind.REST, EntryKind.DELAY):
                return e
        return None

    def index_of_blocker(self):
        """阻塞条目的下标; 没有则 -1。"""
        for i, e in enumerate(self.entries):
            if e.kind in (EntryKind.REST, EntryKind.DELAY):
                return i
        return -1

    # ------------------------------------------------------------------ 写
    def add(self, entry: RunEntry, index: int = None) -> None:
        """插入条目。`index=None` 或越界时追加到末尾。"""
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
    def from_list(cls, data, on_bad=None) -> 'RunList':
        """
        宽松解析: 坏条目**跳过**并记 warning, 而不是整份配置加载失败。

        理由: 列表是用户编辑的内容, 一条写坏不该让整个配置不可用。
        """
        out = cls()
        for item in (data or []):
            try:
                out.entries.append(RunEntry.from_dict(item))
            except ValueError as exc:
                if on_bad is not None:
                    on_bad(item, exc)
        return out

    # ------------------------------------------------------------------ 兼容旧字段
    @classmethod
    def from_task_order(cls, task_order: str, on_bad=None) -> 'RunList':
        """
        从旧的 `task_order`(逗号分隔任务名)迁移。

        旧字段只能表达"任务顺序", 所以迁移结果里**没有** rest/delay 条目。
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
