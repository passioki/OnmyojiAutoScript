# -*- coding: utf-8 -*-
"""`Config.sort_run_list(by)` —— **一次性快捷排序**（取代已删的「调度优先级三模式」）。

## ★★★ 用户裁定（唯一依据）★★★

> "我觉得……这个**固定任务优先和定时任务优先以及不能跨类别拖动太蠢了**。
>  我只需要保持**可以自由拖动/改变执行顺序**就行, 固定任务优先和
>  定时任务优先**直接作为一个快捷排序**就好, 而不是定义一些没有意义的
>  不能跨类别拖动以及**单独的调度优先级**。"

## 它为什么**不是模式**（本文件最重要的一条）

| | 旧（已删）| 新（本文件测的）|
|---|---|---|
| 形态 | `priority_mode` **状态**（持久）| `sort_run_list(by)` **动作**（一次性）|
| 排几次 | **每次** `build_queue()` 都按它排 | **点一次, 排一次** |
| 拖动 | 受限（不能跨类别）| **永远自由** |
| 副作用 | 无 | **写盘**（用户看得见顺序变了）|

★ 所以这里有一条**必测**的守卫: 排完之后再 `build_run_list()` / `build_queue()`,
  顺序**就是新的**, 而且**再也不会被任何东西重排** —— 这正是与旧
  `priority_mode` 的本质区别。

## ★ 不碰真实配置

用**临时配置名** `__sort_probe__` + `config/template.json` 造数据,
测完在 `finally` 里删掉（`tests/conftest.py` 的快照只覆盖会话开始时
**已存在**的文件, 临时文件不在里面 -> 必须自己删干净）。
"""
import json
import logging
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

CFG = '__sort_probe__'
P = REPO / 'config' / f'{CFG}.json'

#: ★ 段归属 —— **按 `period` 派生**（用户裁定改了判据, 见下）
#
# 用户原话:
# > "按照**有没有设置周期记忆**, `period` 不限时是**固定**（固定任务改名为
# >  **临时任务**）, 其他是**定时**（定时任务名字改为**周期任务**）"
#
# ★ 所以样本任务必须按 **`period`** 挑, 不能再按 `category`:
#   * T 组 = `period != none`（周期任务）
#   * F 组 = `period == none`（临时任务）
#
# ⚠ 原来写的是 `T1,T2 = MetaDemon,Nian` / `F1,F2,F3 = Orochi,Exploration,
#   SixRealms` —— 而 **`Orochi`/`SixRealms` 的 `period=DAILY`**, 新判据下
#   它们是**周期任务**, 于是"F 组"里混进了 timed -> 断言全部失效。
#
# ★ 全部选**全天窗口**的, 免得"不在窗口"那一档干扰排 序断言。
T1, T2 = 'MetaDemon', 'KekkaiActivation'      # period != none -> 周期
F1, F2, F3 = 'Exploration', 'Hyakkiyakou', 'HeroTest'   # period == none -> 临时
REST = {'kind': 'rest', 'minutes': 10}


def _mk(**opt_overrides):
    """按模板造一份临时配置; 返回 `Config`。

    ★ 额外把 `run_list` 里出现的任务**逐个启用** —— `build_queue()` 会
      剔除**未启用**的条目（见它的 docstring）, 而模板里这些任务默认关。
      不启用的话"`build_queue()` 不重排"这条守卫就**什么都没测到**。
    """
    import server  # noqa: F401
    from module.config.config import Config
    from module.config.config_model import convert_to_underscore

    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization'].update(opt_overrides)
    for e in (opt_overrides.get('run_list') or []):
        task = e.get('task')
        if not task:
            continue
        node = tmpl.get(convert_to_underscore(task))
        if isinstance(node, dict) and isinstance(node.get('scheduler'),
                                                 dict):
            node['scheduler']['enable'] = True
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    return Config(CFG)


def _disk_tasks():
    """★ 从**磁盘**读回顺序 —— 证明它真的写盘了（不是只改内存）。"""
    d = json.loads(P.read_text(encoding='utf-8'))
    return [e.get('task') for e in d['script']['optimization']['run_list']
            if e.get('kind') == 'task']


def _disk_kinds():
    d = json.loads(P.read_text(encoding='utf-8'))
    return [e.get('kind') for e in d['script']['optimization']['run_list']]


def _mixed():
    """一段固定、一段定时、中间夹一个 rest 的典型编排。"""
    return [
        {'kind': 'task', 'task': F1},      # fixed, 段内第 1
        {'kind': 'task', 'task': F2},      # fixed, 段内第 2
        {'kind': 'task', 'task': T1},      # timed, 段内第 1
        REST,
        {'kind': 'task', 'task': T2},      # timed, 段内第 2
        {'kind': 'task', 'task': F3},      # fixed, 段内第 3
    ]


@pytest.fixture()
def cfg():
    os.chdir(REPO)          # ★ `write_json` 用 `Path.cwd()`
    try:
        yield _mk(run_list=_mixed())
    finally:
        try:
            P.unlink()
        except OSError:
            pass


class TestSortRunList:
    def test_timed_first(self, cfg):
        """`by='timed'` -> 定时段在前, 固定段在后, **段内相对顺序不变**。"""
        assert cfg.sort_run_list('timed') is True
        assert _disk_tasks() == [T1, T2, F1, F2, F3], _disk_tasks()
        # ★ 段内: 定时 = T1 -> T2（用户原顺序）; 固定 = F1 -> F2 -> F3
        assert _disk_kinds()[-1] == 'rest', 'rest 必须最后'

    def test_fixed_first(self, cfg):
        """`by='fixed'` -> 反之; 段内顺序同样不变。"""
        assert cfg.sort_run_list('fixed') is True
        assert _disk_tasks() == [F1, F2, F3, T1, T2], _disk_tasks()
        assert _disk_kinds()[-1] == 'rest', 'rest 必须最后'

    def test_rest_always_last(self, cfg):
        """★ rest 恒最后（**归一化**, 不是拒绝）。"""
        cfg.sort_run_list('timed')
        kinds = _disk_kinds()
        assert kinds == ['task'] * 5 + ['rest'], kinds

    def test_written_to_disk_and_visible_in_build_run_list(self, cfg):
        """★ 它**写盘** —— 重新 `build_run_list()` 拿到的就是新顺序。"""
        cfg.sort_run_list('timed')
        tasks = [e.task for e in cfg.build_run_list() if e.task]
        assert tasks == [T1, T2, F1, F2, F3], tasks

    def test_idempotent(self, cfg):
        """★ 幂等: 连排两次结果相同（再点一次不会翻回去）。"""
        cfg.sort_run_list('timed')
        once = _disk_tasks()
        cfg.sort_run_list('timed')
        assert _disk_tasks() == once, (once, _disk_tasks())

    def test_sort_is_one_shot_not_a_state(self, cfg):
        """★★★ 核心守卫: **它只做一次, 不留状态** ★★★

        与旧 `priority_mode` 的**本质区别**。旧实现是"设一个模式,
        然后**每次** `build_queue()` 都按它排" -> 用户手工拖的顺序会被
        **反复覆盖**（他抱怨的"拖了没用"）。

        ★ 这里钉住两件事:
          1. 排完后再 `build_queue()` **不会**把它排回去
          2. 用户随后**手工改回来**的顺序, 也**不会**被任何东西重排
        """
        cfg.sort_run_list('fixed')
        assert _disk_tasks() == [F1, F2, F3, T1, T2]

        # ① build_run_list / build_queue 都不该再动它
        assert [e.task for e in cfg.build_run_list() if e.task] == \
            [F1, F2, F3, T1, T2]
        # ⚠ `build_queue()` 会**追加**自动补齐的任务, 所以只看**前缀**
        assert [e.task for e in cfg.build_queue() if e.task][:5] == \
            [F1, F2, F3, T1, T2], 'build_queue() 把顺序排回去了'

        # ② 用户"手工"把它改成 timed 在前（模拟拖动保存）
        from module.config.run_list import RunList
        rl = cfg.build_run_list()
        rl.entries = sorted(
            rl.entries,
            key=lambda e: (2 if not getattr(e, 'task', '')
                           else (0 if e.task in (T1, T2) else 1)))
        assert cfg.save_run_list(rl) is True
        assert _disk_tasks() == [T1, T2, F1, F2, F3]

        # ★ 再走一遍调度路径 —— 顺序**必须原样**
        assert [e.task for e in cfg.build_queue() if e.task][:5] == \
            [T1, T2, F1, F2, F3], (
                '★ 有东西在按"模式"重排 —— 用户拖的顺序又被覆盖了')

    def test_does_not_touch_other_entries(self, cfg):
        """★ 只重排, **不增不删**（条数与内容都不变）。"""
        before = _disk_kinds()
        cfg.sort_run_list('timed')
        assert sorted(_disk_kinds()) == sorted(before)
        assert _disk_kinds().count('rest') == 1


class TestSortRunListRejectsBadInput:
    """★ 非法 `by` -> `False`, **且不改动配置**（不猜、不静默）。"""

    @pytest.mark.parametrize('bad', ['nope', '', None, 'TIMED ', 'custom',
                                     'priority', 0, [], 'fast'])
    def test_returns_false(self, cfg, bad):
        assert cfg.sort_run_list(bad) is False, f'{bad!r} 应被拒绝'

    def test_config_untouched(self, cfg):
        before = _disk_tasks()
        for bad in ('nope', '', None):
            cfg.sort_run_list(bad)
        assert _disk_tasks() == before, '非法 by 竟然改了配置'
        assert [e.task for e in cfg.build_run_list() if e.task] == before


class TestSortEndpointContract:
    """★ `PUT /{script}/queue/sort` 的**契约**与它调用的方法一致。

    ⚠ 这里**不**起 HTTP 服务, 只核对"端点接受什么"与"`Config` 接受什么"
      一致 —— 它们**必须是同一套判据**（两处定义就会漂移）。
    """

    def test_endpoint_accepts_exactly_two_values(self):
        """端点把 body 归一化后只放行 `timed` / `fixed`。"""
        from _srcutil import code_only
        src = code_only(REPO / 'module' / 'server' / 'schema_router.py')
        assert 'async def put_queue_sort' in src, '端点应存在'
        assert "if by not in ('timed', 'fixed')" in src or \
            'if by not in ("timed", "fixed")' in src, (
                '端点应只放行 timed / fixed')

    def test_endpoint_calls_config_sort_run_list(self):
        from _srcutil import code_of
        body = code_of(REPO / 'module' / 'server' / 'schema_router.py',
                       'async def put_queue_sort')
        assert 'config.sort_run_list(by)' in body, (
            '端点必须委托给 `Config.sort_run_list()` —— '
            '排序规则不能在两处定义')

    def test_old_priority_mode_endpoint_is_gone(self):
        """★ 反向守卫: 旧的 `PUT /{script}/priority_mode` **不该**还在。"""
        from _srcutil import code_only
        src = code_only(REPO / 'module' / 'server' / 'schema_router.py')
        assert 'def put_priority_mode' not in src
        assert 'def get_priority_mode' not in src

    def test_no_state_field_left_on_model(self):
        """★ 反向守卫: `Optimization` 上**不该**再有 `priority_mode` 字段。"""
        from tasks.Script.config_optimization import Optimization
        o = Optimization()
        assert not hasattr(o, 'priority_mode'), \
            '「模式」这个状态字段应已删除（现在是一次性动作）'
        assert not hasattr(o, 'priority_mode_explicit')
