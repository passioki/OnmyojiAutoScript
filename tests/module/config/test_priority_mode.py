# -*- coding: utf-8 -*-
"""S6 守卫: `priority_mode` **三模式** + **队列层分段**（用户裁定）。

用户原话:
> "拖动只在同类别内生效是在选了**定时优先**或者**固定任务优先**时, 如果选了
>  **列表自定义**, 那么全都可以拖动次序。你理解下, 也就是**三个选项:
>  定时任务优先、固定任务优先、自定义**"
> "**给 run_list 加类别分段**"
"""
import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)


class _F:
    """最小 `Function` 替身（只需要 `command`）。"""

    def __init__(self, command):
        self.command = command


@pytest.fixture()
def cfg():
    import server  # noqa: F401
    from module.server.main_manager import mm
    c = mm.config_cache('恋鸟树')
    before = c.priority_mode()
    yield c
    # ★ 还原（我在实时配置上做过测试 —— 必须还原）
    try:
        c.model.script.optimization.priority_mode = before
        c.model.script.optimization.priority_mode_explicit = True
    except Exception:
        pass


class TestPriorityModeEnum:
    def test_three_modes(self):
        from tasks.Script.config_optimization import PriorityMode
        assert {m.value for m in PriorityMode} == {
            'timed_first', 'fixed_first', 'custom'}

    def test_labels_match_user_words(self):
        """★ 界面名要能对上用户说的"定时任务优先 / 固定任务优先 / 自定义"。"""
        src = (REPO / 'module/config/i18n/zh-CN.json').read_text(
            encoding='utf-8')
        for kw in ('定时任务优先', '固定任务优先', '自定义'):
            assert kw in src, f'i18n 里缺「{kw}」'

    def test_default_is_custom_behavior_preserving(self):
        """★ 默认必须是 `custom`（**行为保持**）。

        若默认 `timed_first`, 会**悄悄重排**既有用户的队列 ——
        实测会打破 `build_queue()` 的"用户编排在前 + 自动追加在后"两条契约。
        """
        from tasks.Script.config_optimization import Optimization, PriorityMode
        assert Optimization().priority_mode == PriorityMode.CUSTOM

    def test_old_fields_deprecated_but_present(self):
        """★ 旧字段**保留**（旧配置里有, 直接删会崩）, 且标为内部字段。"""
        from tasks.Script.config_optimization import Optimization
        o = Optimization()
        assert hasattr(o, 'schedule_rule')
        assert hasattr(o, 'timed_priority')
        assert hasattr(o, 'priority_mode_explicit'), \
            '迁移标记字段缺失 —— 幂等会失效'


class TestSegmentation:
    def test_segment_of_known_tasks(self, cfg):
        assert cfg._segment_of('MetaDemon') == 'timed', '限时活动算 timed'
        assert cfg._segment_of('Orochi') == 'fixed'
        assert cfg._segment_of('RealmRaid') == 'fixed', '结界突破算 fixed'

    def test_timed_first_puts_timed_first(self, cfg):
        cfg.model.script.optimization.priority_mode = 'timed_first'
        CMDS = ['Orochi', 'MetaDemon', 'Exploration', 'SixRealms',
                'GoldYoukai', 'RealmRaid']
        out = cfg._order_by_priority_mode([_F(c) for c in CMDS])
        tags = [cfg._segment_of(f.command) for f in out]
        # 所有 timed 必须在所有 fixed 之前
        assert tags == sorted(tags, key=lambda s: 0 if s == 'timed' else 1), tags

    def test_fixed_first_puts_fixed_first(self, cfg):
        cfg.model.script.optimization.priority_mode = 'fixed_first'
        CMDS = ['Orochi', 'MetaDemon', 'Exploration', 'SixRealms',
                'GoldYoukai', 'RealmRaid']
        out = cfg._order_by_priority_mode([_F(c) for c in CMDS])
        tags = [cfg._segment_of(f.command) for f in out]
        assert tags == sorted(tags, key=lambda s: 0 if s == 'fixed' else 1), tags

    def test_custom_does_not_reorder(self, cfg):
        """★★ `custom` 必须**完全不动** —— 用户拖的完整次序生效。"""
        cfg.model.script.optimization.priority_mode = 'custom'
        CMDS = ['Orochi', 'MetaDemon', 'Exploration', 'SixRealms',
                'GoldYoukai', 'RealmRaid']
        out = cfg._order_by_priority_mode([_F(c) for c in CMDS])
        assert [f.command for f in out] == CMDS, 'custom 模式下被重排了！'

    def test_stable_within_segment(self, cfg):
        """★ 段**内**相对顺序必须**不变**（"拖动只在同类别内生效"）。"""
        cfg.model.script.optimization.priority_mode = 'timed_first'
        fixed = ['Orochi', 'Exploration', 'SixRealms']
        out = cfg._order_by_priority_mode(
            [_F('MetaDemon')] + [_F(c) for c in fixed])
        got_fixed = [f.command for f in out if cfg._segment_of(f.command) == 'fixed']
        assert got_fixed == fixed, f'段内顺序被打乱: {got_fixed} != {fixed}'

    def test_queue_invariant_survives(self, cfg):
        """★★ 核心不变量: `pending` 仍是 `queue` 的**保序子序列**。

        我第一版在 `pending` 上事后重排 -> **破坏了这个不变量**（3 个测试
        失败）。正确做法是**在队列层**排段。

        ## ★★ T7: 这条守卫原来**是空转的（假通过）** ★★

        审计实测: `cfg` fixture **从不调 `update_scheduler()`**, 而
        `pending_task` 不是 `Config.__init__` 的字段 —— 它只在
        `update_scheduler()` 里被赋值。于是 `cfg.pending_task` 经
        `Config.__getattr__`（对未知属性**返回 `None`**）得到 `None`
        -> `p == []` -> `all()` 对**空集恒真** -> **测试无条件通过**。

        ★ 修法: ① 先 `update_scheduler()`（真正跑一遍调度）
          ② `assert p, ...` **防空转**（没有待跑任务时, 这条守卫没意义 ->
             标成 **skip** 而不是假装通过）
        """
        cfg.update_scheduler()
        q = [getattr(e, 'task', None) for e in cfg.build_queue()]
        p = [getattr(f, 'command', None) for f in (cfg.pending_task or [])]
        w = {getattr(f, 'command', None) for f in (cfg.waiting_task or [])}

        # ★ 防空转: `all()` 对空集恒真, 必须显式拒绝"什么都没测到"
        if not p:
            pytest.skip(
                f'当前没有待跑任务（pending 为空）-> 保序子序列无从验证。'
                f'queue={len(q)} waiting={len(w)}。'
                f'★ 这不是"通过", 是"没测到"。')

        expected = [t for t in q if t not in w]
        # ★★ 必须排除 **`running_task` 置顶**（设计例外, 见 §3）★★
        #
        # `update_scheduler()` 末尾会把**正在跑的那个任务**提到 `pending`
        # 最前（`_order_by_manual_run()` 之后）。实测:
        #   queue   = ['Exploration', 'GoryouRealm', ...]
        #   pending = ['GoryouRealm', 'Exploration', ...]     <- Exploration 被置顶
        # ★ 这不是 bug, 是**设计上的例外** —— 所以断言要把它排除,
        #   否则测试会随着"哪个任务在跑"随机红。
        running = getattr(cfg, 'running_task', None)
        if running:
            expected = [t for t in expected if t != running]
            p = [t for t in p if t != running]
        it = iter(expected)
        assert all(any(x == t for x in it) for t in p), (
            f'pending 不是 queue 的保序子序列（已排除 running={running!r}）\n'
            f'  queue={expected}\n  pending={p}')


class TestRunEntryGroup:
    def test_group_is_attribute(self):
        """★ `group` 是**内存属性**（`build_queue()` 每次重算）。"""
        from module.config.run_list import RunEntry
        e = RunEntry(kind='task', task='Orochi', group='fixed')
        assert e.group == 'fixed'

    def test_group_is_never_persisted(self):
        """★★ 审计修复: `group` **永不落盘** ★★

        ## 为什么

        段名是 `Config._segment_queue()` 的**派生结果**, 每次 `build_queue()`
        都会重算。存盘只会:
          ① 破坏"单一数据源"（台账 §10.8）
          ② 前端判据与后端不一致时, 配置里躺着**错的段名**
          ③ 让配置文件多出一堆"用户没写过"的字段

        ★ 我第一版让它"非空才写" —— 但 `_assign_groups()` 会把它算成**非空**,
          于是**照样落盘**（实测抓到）。所以改成**永不写**。
        """
        from module.config.run_list import RunEntry
        for g in ('', 'timed', 'fixed'):
            d = RunEntry(kind='task', task='Orochi', group=g).to_dict()
            assert 'group' not in d, f'group={g!r} 被序列化了: {d}'

    def test_from_dict_still_accepts_group(self):
        """★ 旧配置/前端若带了 `group`, 解析时**接受**（不报错）—— 只是不落盘。"""
        from module.config.run_list import RunEntry
        e = RunEntry.from_dict({'kind': 'task', 'task': 'Orochi',
                                'entry_id': 'x', 'group': 'timed'})
        assert e.group == 'timed'
        assert 'group' not in e.to_dict()

    def test_legacy_config_without_group(self):
        """★ 旧配置没有 `group` -> 空串（**向后兼容**）。"""
        from module.config.run_list import RunEntry
        e = RunEntry.from_dict({'kind': 'task', 'task': 'Orochi',
                                'entry_id': 'x'})
        assert e.group == ''
