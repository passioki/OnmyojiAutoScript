# -*- coding: utf-8 -*-
"""`battle_wait` 状态机的测试（★ T6 按**当前** API **重写**）。

## 为什么整个文件是重写的

它 import 的 `_DEFAULT_PER_BATTLE` **早就不存在了** -> 收集时 `ImportError`
-> **整个文件（21 个测试）从不执行**。而 `pytest -q` 打印的是
"`N passed`" —— **收集错误被 passed 的数字完全淹没**（我也一直在用
`--ignore` 主动忽略它, 于是"全绿"是**我自己造的**）。

★ 修掉 import 后暴露真相: **15 failed, 3 passed, 3 xfailed**。
根因是**断言基于旧 API**:
```
runtime.pri_ctx['_bw_setup_probe'].per_battle['b'] = 1
-> TypeError: 'PerTaskState' object does not support item assignment
```

## 当前语义（重写的依据 —— 逐条从源码读出）

| 概念 | 当前形态 |
|---|---|
| `runtime` | **类级单例**（`pub_ctx` / `pri_ctx` / `task_owner` 都是类属性）|
| `pub_ctx` | `PublicContext(cross: dict, per_task: PerTaskState, per_battle: PerBattleState, options: dict)` |
| `pri_ctx[hook_name]` | `PrivateContext`, 四个 `dict` 槽 |
| `PerTaskState` | `@dataclass(count: int)` —— **对象, 不是 dict** |
| `PerBattleState` | `@dataclass(success: BattleResult, hook_enabled: set)` —— 同上 |
| `reset_per_battle()` | 重建 `pub_ctx.per_battle` 与**每个 hook 的** `pri_ctx[*].per_battle`, **保留** `cross` / `per_task` |
| `reset_per_task()` | 重建 `per_task`（两个 ctx 都重建）|
| `hook2event('_bw_success_soul')` | `'success'`（`_bw_` 之后、最后一个 `_` 之前）|

★ 所以"**按条目设 `per_battle['b'] = 1`**"这种断言**在新模型下不成立** ——
  新模型是**按 hook 事件**给 `per_battle` 一个**类型化对象**
  （`PerBattleSuccess` / `PerBattleGreen` …）。
"""
import logging

import pytest

from tasks.Component.GeneralBattle.battle_wait import (
    BattleResult,
    BattleWaitPlan,
    HookSignal,
    PerBattleState,
    PerTaskState,
    PrivateContext,
    PublicContext,
    battle_wait_options,
    battle_wait_strategy,
    runtime,
)


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch):
    """★ 每个测试前把 `runtime` 的**类级状态**清干净。

    ⚠ `runtime` 是**类级单例** —— 状态在测试之间**共享**。
    不清理会让测试**互相影响**（而且 `runtime.__str__` 会读到上一个测试的键）。
    """
    monkeypatch.setattr(runtime, 'task_owner', None)
    monkeypatch.setattr(runtime, 'pub_ctx', None)
    monkeypatch.setattr(runtime, 'pri_ctx', {})
    monkeypatch.setattr(battle_wait_strategy, 'battle_wait_plan', None)
    monkeypatch.setattr(battle_wait_options, 'options', None)


# ============================================================ 1. 计划（Plan）
def _seq_names(seq) -> list:
    """把顺序字符串（`'a > b > c'`）切成名字列表。

    ★ 它不是 list —— 见 `test_default_plan_has_hooks_and_sequence` 的说明。
    """
    return [s.strip() for s in str(seq).split('>') if s.strip()]


class TestBattleWaitPlan:
    def test_default_plan_has_hooks_and_sequence(self):
        """★ `HOOKS_DEFAULT` 是 **tuple**; 顺序是 **`>` 分隔的字符串**。

        ⚠ 三个我第一版搞错的地方:
          1. 以为顺序是 **list** -> 实际是字符串（遍历会得到**单个字符**）
          2. 以为**实例的**顺序在 `SEQUENCE_DEFAULT` -> 实际类常量里**没有**
             `setup` / `idle`; **实例属性**是 `p.sequence`
             （= `SEQUENCE_DEFAULT + extra + ' idle'`）
          3. 以为自定义 hook 会改 `SEQUENCE_DEFAULT` -> 它只进 **`extra_sequence`**
        """
        p = BattleWaitPlan()
        assert isinstance(p.HOOKS_DEFAULT, tuple)
        assert p.HOOKS_DEFAULT, '应有默认 hook 集合'
        # ★ 实例的顺序属性叫 `sequence`
        names = _seq_names(p.sequence)
        assert names, f'实例 sequence 应非空: {p.sequence!r}'
        for name in names:
            # 每一项都必须是**已声明的 hook**（或 `idle`）
            assert name in p.HOOKS_DEFAULT or name == 'idle', (
                f'sequence 里的 {name!r} 不是已知 hook')

    def test_instance_sequence_includes_setup_and_idle(self):
        """★ 实例顺序要含 `setup`（循环之前）与 `idle`（等待中）。

        ★ 注意 `setup` 在 **`HOOKS_DEFAULT`** 里, 而 `idle` 由 `__init__`
          **追加到末尾**。
        """
        p = BattleWaitPlan()
        assert 'setup' in p.HOOKS_DEFAULT
        assert _seq_names(p.sequence)[-1] == 'idle', (
            f'`idle` 应在实例 sequence 的**最后**: {p.sequence!r}')

    def test_custom_hook_is_inserted_before_idle(self):
        """★ 自定义 hook（不在默认集合里）必须插在 **`idle` 之前**。

        ⚠ 参数格式是 **`event_strategy`**（`'extra_probe'`）——
        我第一版传裸 `'green'` -> `ValueError: ... expected
        "event_strategy" format`。
        """
        p = BattleWaitPlan('myextra_probe')
        names = _seq_names(p.sequence)
        assert 'myextra' in names, names
        assert names.index('myextra') < names.index('idle'), (
            f'自定义事件应插在 idle 之前: {names}')
        # ★ 事件名 -> 策略名 落在**实例属性**上
        assert p.myextra == 'probe'

    def test_bad_hook_name_raises(self):
        """★ 非法 hook 名 -> **报错**（不静默忽略）。

        ★ 静默忽略会让"我配了 green 却没生效"变成**极难查**的问题。
        """
        with pytest.raises(ValueError):
            BattleWaitPlan('green')          # 缺 `_strategy` 段
        with pytest.raises((TypeError, ValueError)):
            BattleWaitPlan(123)              # 非字符串

    def test_duplicate_event_raises(self):
        """★ 同一个事件配两次 -> **报错**（而不是后者覆盖前者）。

        ⚠ 我第一版写成 `BattleWaitPlan(green='a', **{'green': 'b'})` ——
        那是 **Python 层面**的"重复关键字参数"（`TypeError`）,
        **进不到函数体**, 所以测不到源码里那个 `ValueError`。
        -> 用 **位置参数 + 关键字参数** 才走得到。
        """
        with pytest.raises(ValueError):
            BattleWaitPlan('green_a', green='b')


# ============================================================ 2. 事件 → hook 映射
class TestHookEventMapping:
    @pytest.mark.parametrize('func_name,event', [
        ('_bw_setup_probe', 'setup'),
        ('_bw_completion_default', 'completion'),
        ('_bw_success_soul', 'success'),
        ('_bw_green_default', 'green'),
        ('_bw_randomclick_default', 'randomclick'),
    ])
    def test_hook2event(self, func_name, event):
        """★ `hook2event` 决定"这个 hook 用哪个 options 类" —— 错了会**静默**用错配置。"""
        assert runtime.hook2event(func_name) == event

    def test_event2hook_roundtrip(self):
        for ev in ('setup', 'success', 'green'):
            hook = runtime.event2hook(ev, 'default')
            assert runtime.hook2event(hook) == ev


# ============================================================ 3. 上下文（Context）
class TestContexts:
    def test_public_context_defaults(self):
        pub = PublicContext()
        assert pub.cross == {}
        assert isinstance(pub.per_task, PerTaskState)
        assert isinstance(pub.per_battle, PerBattleState)
        assert pub.options == {}

    def test_private_context_defaults(self):
        pri = PrivateContext()
        for slot in ('cross', 'per_task', 'per_battle', 'options'):
            assert getattr(pri, slot) == {}, f'{slot} 默认应是空 dict'

    def test_per_battle_state_has_hook_enabled(self):
        """★ `PerBattleState.hook_enabled` 是个 **set**（默认含各 hook, 除 completion）。"""
        st = PerBattleState()
        assert isinstance(st.hook_enabled, set)
        assert isinstance(st.success, BattleResult)


# ============================================================ 4. runtime 重置语义
class TestRuntimeReset:
    def test_reset_per_battle_keeps_cross_and_per_task(self):
        """★★ 核心语义: `reset_per_battle()` **只重建 per_battle**,
        必须**保留** `cross` 与 `per_task`。

        ★ 这是"跨战斗状态不该在下一场丢掉, 而单场判断该重置"的落地。
        """
        runtime._ensure_pub_default()
        runtime.pub_ctx.cross['c'] = 1
        runtime.pub_ctx.per_task.count = 7
        runtime.pub_ctx.per_battle.success = BattleResult.SUCCESS

        runtime.reset_per_battle()

        assert runtime.pub_ctx.cross == {'c': 1}, 'cross 不该被 per_battle 重置清掉'
        assert runtime.pub_ctx.per_task.count == 7, 'per_task 不该被清掉'
        assert runtime.pub_ctx.per_battle.success == BattleResult.FAILURE, (
            'per_battle 必须被重置成默认')

    def test_reset_per_battle_replaces_the_object(self):
        """★ 断言"**是新对象**"而不是"字段相等"。

        ⚠ 我原来写 `assert pub_ctx.per_battle == PerBattleState()` ——
        `PerBattleState` 是 `@dataclass`, **有 `__eq__`**（按字段比）,
        所以那条**其实能过**; 但要表达"重建"的语义,
        **`is not` 更准**（否则"只改了字段"也会通过）。
        """
        runtime._ensure_pub_default()
        before = runtime.pub_ctx.per_battle
        runtime.reset_per_battle()
        assert runtime.pub_ctx.per_battle is not before

    def test_reset_per_task_replaces_both_contexts(self):
        runtime._ensure_pub_default()
        runtime._ensure_pri_default('_bw_setup_probe')
        runtime.pub_ctx.cross['keep'] = 1
        runtime.pub_ctx.per_task.count = 3
        runtime.pri_ctx['_bw_setup_probe'].cross['keep'] = 1

        runtime.reset_per_task()

        # ★ cross 保留; per_task 重建
        assert runtime.pub_ctx.cross == {'keep': 1}
        assert runtime.pub_ctx.per_task.count == 0
        assert runtime.pri_ctx['_bw_setup_probe'].cross == {'keep': 1}

    def test_reset_per_battle_also_resets_private_per_battle(self):
        """★ **每个 hook 的** `pri_ctx[*].per_battle` 也要重置。

        ⚠ 这正是我第一版写错的地方 —— 我以为 `per_battle` 是 `dict`
        （`per_battle['b'] = 1`）, 实际是**按 hook 事件的类型化对象**。
        """
        runtime._ensure_pub_default()
        runtime._ensure_pri_default('_bw_setup_probe')
        ctx = runtime.pri_ctx['_bw_setup_probe']
        before = ctx.per_battle
        runtime.reset_per_battle()
        assert ctx.per_battle is not before, (
            '私有 ctx 的 per_battle 没被重置')


# ============================================================ 5. task_owner 切换
class TestTaskOwnerSwitch:
    def test_owner_switch_resets_per_task(self):
        """★ 换任务 -> `reset_per_task()`（`cross` 保留, `per_task` 重建）。"""
        class _Owner:
            pass

        runtime._ensure_pub_default()
        runtime.pub_ctx.cross['keep'] = 1
        runtime.pub_ctx.per_task.count = 5
        runtime.task_owner = _Owner()          # 上一个任务

        # 模拟 `__call__` 的第一段逻辑（不真的跑 hook）
        new_owner = _Owner()
        if runtime.task_owner is None or new_owner is not runtime.task_owner:
            runtime.task_owner = new_owner
            runtime.reset_per_task()

        assert runtime.task_owner is new_owner
        assert runtime.pub_ctx.per_task.count == 0, '换任务后 per_task 应重置'
        assert runtime.pub_ctx.cross == {'keep': 1}, 'cross 应保留'


# ============================================================ 6. options 分发
class TestRuntimeStr:
    def test_str_shows_hook_name_and_scope_keys(self):
        """★ `__str__` 是**排障入口** —— 它必须能打印出 hook 名与四个作用域的键。"""
        def _bw_setup_probe(self):
            raise AssertionError('不该真的执行')

        r = runtime(_bw_setup_probe)
        s = str(r)
        assert '_bw_setup_probe' in s
        for token in ('pub[c:', 't:', 'b:', 'o:', 'pri[c:'):
            assert token in s, f'__str__ 少了 {token!r}: {s}'

    def test_str_is_safe_without_any_state(self):
        """★ 没有任何上下文时 `__str__` **不能崩**（排障时最需要它）。"""
        def _bw_idle_probe(self):
            raise AssertionError('不该真的执行')

        assert str(runtime(_bw_idle_probe))


# ============================================================ 7. 装饰器 / 描述符
class TestRuntimeDescriptor:
    def test_runtime_wraps_and_keeps_name(self):
        """★ `update_wrapper` 必须保住 `__name__` —— **完成检测**依赖它。"""
        def _bw_completion_probe(self):
            return 'ok'

        r = runtime(_bw_completion_probe)
        assert r.__name__ == '_bw_completion_probe'
        assert r.hook_name == '_bw_completion_probe'

    def test_call_injects_pub_and_pri(self):
        """★ `__call__` 给被包裹函数注入 `pub=` / `pri=`（这是 hook 的契约）。"""
        seen = {}

        def _bw_setup_probe(self, pub=None, pri=None):
            seen['pub'] = pub
            seen['pri'] = pri
            return 'done'

        r = runtime(_bw_setup_probe)
        owner = object()
        out = r(owner)
        assert out == 'done'
        assert isinstance(seen['pub'], PublicContext)
        assert isinstance(seen['pri'], PrivateContext)
        assert runtime.task_owner is owner

    def test_ensure_pri_default_creates_typed_slots(self):
        """★ 首次用某 hook -> `per_task` / `per_battle` 按**事件**给**类型化对象**。"""
        runtime._ensure_pri_default('_bw_green_probe')
        ctx = runtime.pri_ctx['_bw_green_probe']
        # 不是裸 dict（那是旧模型）
        assert not isinstance(ctx.per_task, type({})), (
            'per_task 应是按事件类型化的对象, 不是裸 dict')
        assert not isinstance(ctx.per_battle, type({})), (
            'per_battle 应是按事件类型化的对象, 不是裸 dict')


# ============================================================ 8. 信号
class TestHookSignal:
    def test_signal_is_enum_with_int_values(self):
        """★ `HookSignal` 是 **int 枚举**（`CONTINUE=1 / BUSY=2 / DONE=3`）。

        ⚠ 我第一版断言"取值都是 `str`" —— 实际是 **int**。
        ★ 这三个值是**状态机**的返回约定: hook 返回哪个决定"继续等 / 忙 /
          结束"。
        """
        vals = {s.value for s in HookSignal}
        assert vals == {1, 2, 3}, vals
        assert {s.name for s in HookSignal} == {'CONTINUE', 'BUSY', 'DONE'}


# ============================================================ 9. 模块级钩子（防回归）
class TestNoStaleApi:
    """★ 反向守卫: 旧 API 不得回来（它们曾让整个文件**静默不执行**）。"""

    def test_default_per_battle_factory_gone(self):
        from tasks.Component.GeneralBattle import battle_wait as BW
        assert not hasattr(BW, '_DEFAULT_PER_BATTLE'), (
            '`_DEFAULT_PER_BATTLE` 已不存在 —— 它曾让本文件因 ImportError '
            '而**一个测试都不跑**。若它回来了, 请同步改这里的 import。')

    def test_per_battle_is_object_not_dict(self):
        """★ 反向守卫: `per_battle` **不是** `dict`（旧模型的写法）。"""
        pub = PublicContext()
        assert not isinstance(pub.per_battle, dict), (
            'per_battle 现在是 PerBattleState 对象 —— '
            '`per_battle["k"] = v` 会 TypeError')
