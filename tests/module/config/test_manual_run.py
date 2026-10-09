# -*- coding: utf-8 -*-
"""「运行一次」—— 手动请求"立刻跑一次"，按**点击顺序**插队。

## 用户确认的语义

> 可以直接加在任务总览里，可以考虑全部任务都添加上这个按钮。
> 点击后按照点击先后顺序，直接排在最高优先级
> （就是跑完当前任务/战斗后插队运行）

后来调整为：

> 可以把这个和重置一样，放在**停用选中**旁边，**运行一次**选用。

要点：

1. **所有任务**都能点（固定任务与定时任务都可以）
2. **按点击先后顺序**排队
3. **跑完当前任务/战斗后**才插队（不是立即打断 —— 与"暂停调度"同一个安全点）
4. 只跑**一次** —— 跑完就从队列里消失

## 为什么用"时间戳队列"而不是布尔标记

用户要"按点击顺序"。若只记一个 `set`，多个任务同时被点就丢了顺序。
用一个 `[(time, task)]` 的列表，天然有序。

## 为什么不做"立即打断"

打断会卡在半途（战斗中 / 组队房间里）—— 与「暂停调度」同样的理由。
所以插队点是**任务边界**：当前任务跑完，队列里的下一个就是它。
"""
import json
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    """把队列指到临时文件（不要 chdir —— Windows 会占用失败）。"""
    from module.config import manual_run
    monkeypatch.setattr(manual_run, '_queue_file',
                        lambda: tmp_path / '.manual_run.json', raising=True)
    return tmp_path / '.manual_run.json'


class TestQueue:
    def test_request_adds_to_queue(self, store):
        from module.config import manual_run
        manual_run.request('acc', 'Orochi')
        assert manual_run.pending('acc') == ['Orochi']

    def test_click_order_preserved(self, store):
        """★ 按**点击先后**排队 —— 这是用户明确要求的。"""
        from module.config import manual_run
        for name in ('Orochi', 'FallenSun', 'GoryouRealm'):
            manual_run.request('acc', name)
        assert manual_run.pending('acc') == ['Orochi', 'FallenSun', 'GoryouRealm']

    def test_duplicate_request_does_not_double_queue(self, store):
        """同一个任务点两次 -> 仍只排一个（避免重复跑）。"""
        from module.config import manual_run
        manual_run.request('acc', 'Orochi')
        manual_run.request('acc', 'Orochi')
        assert manual_run.pending('acc') == ['Orochi']

    def test_re_request_after_take_moves_to_end(self, store):
        """取走之后再点 -> 排到**队尾**（新的点击是新的顺序）。"""
        from module.config import manual_run
        manual_run.request('acc', 'Orochi')
        manual_run.request('acc', 'FallenSun')
        assert manual_run.take('acc') == 'Orochi'
        manual_run.request('acc', 'Orochi')
        assert manual_run.pending('acc') == ['FallenSun', 'Orochi']

    def test_take_pops_in_order(self, store):
        from module.config import manual_run
        manual_run.request('acc', 'A')
        manual_run.request('acc', 'B')
        assert manual_run.take('acc') == 'A'
        assert manual_run.take('acc') == 'B'
        assert manual_run.take('acc') is None

    def test_take_removes_from_queue(self, store):
        """★ 只跑**一次** —— 取走后就没了。"""
        from module.config import manual_run
        manual_run.request('acc', 'Orochi')
        manual_run.take('acc')
        assert manual_run.pending('acc') == []

    def test_cancel(self, store):
        from module.config import manual_run
        manual_run.request('acc', 'A')
        manual_run.request('acc', 'B')
        assert manual_run.cancel('acc', 'A') is True
        assert manual_run.pending('acc') == ['B']

    def test_cancel_absent_returns_false(self, store):
        from module.config import manual_run
        assert manual_run.cancel('acc', 'NotQueued') is False

    def test_clear(self, store):
        from module.config import manual_run
        manual_run.request('acc', 'A')
        manual_run.clear('acc')
        assert manual_run.pending('acc') == []

    def test_is_pending(self, store):
        from module.config import manual_run
        manual_run.request('acc', 'A')
        assert manual_run.is_pending('acc', 'A') is True
        assert manual_run.is_pending('acc', 'B') is False


class TestPersistence:
    def test_survives_reopen(self, store):
        """落盘 —— 进程重启后请求还在（用户说过要能恢复）。"""
        from module.config import manual_run
        manual_run.request('acc', 'Orochi')
        raw = json.loads(store.read_text(encoding='utf-8'))
        assert 'acc' in raw

    def test_accounts_isolated(self, store):
        from module.config import manual_run
        manual_run.request('accA', 'Orochi')
        manual_run.request('accB', 'FallenSun')
        assert manual_run.pending('accA') == ['Orochi']
        assert manual_run.pending('accB') == ['FallenSun']

    def test_corrupt_file_does_not_crash(self, store):
        from module.config import manual_run
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text('{ broken', encoding='utf-8')
        assert manual_run.pending('acc') == []
        manual_run.request('acc', 'A')      # 应能自愈
        assert manual_run.pending('acc') == ['A']

    def test_task_name_normalised(self, store):
        """`Orochi` 与 `orochi` 是同一个任务。"""
        from module.config import manual_run
        manual_run.request('acc', 'Orochi')
        assert manual_run.is_pending('acc', 'orochi') is True

    def test_empty_when_missing(self, store):
        from module.config import manual_run
        assert manual_run.pending('acc') == []
        assert manual_run.take('acc') is None


class TestOrderingHelper:
    """
    调度器要用它把"手动请求的任务"提到最前。

    这是**纯函数**, 所以语义能被测试固定下来。
    """

    class F:
        def __init__(self, cmd):
            self.command = cmd

        def __repr__(self):
            return self.command

    def test_manual_first_in_click_order(self):
        from module.config.manual_run import order_first
        pend = [self.F('A'), self.F('B'), self.F('C'), self.F('D')]
        got = order_first(pend, ['D', 'B'])
        assert [x.command for x in got] == ['D', 'B', 'A', 'C']

    def test_empty_queue_keeps_order(self):
        from module.config.manual_run import order_first
        pend = [self.F('A'), self.F('B')]
        got = order_first(pend, [])
        assert [x.command for x in got] == ['A', 'B']

    def test_requested_task_not_in_pending_is_ignored(self):
        """请求了但不在 pending（还没到点/被禁用）-> 不动它, 也不报错。"""
        from module.config.manual_run import order_first
        pend = [self.F('A'), self.F('B')]
        got = order_first(pend, ['NotThere'])
        assert [x.command for x in got] == ['A', 'B']

    def test_none_and_empty(self):
        from module.config.manual_run import order_first
        assert order_first([], ['A']) == []
        assert order_first(None, ['A']) == []
        assert order_first([self.F('A')], None)


class TestRequestMany:
    """界面上的按钮可能是"对选中的任务运行一次"。"""

    def test_request_many_in_given_order(self, store):
        from module.config import manual_run
        manual_run.request_many('acc', ['A', 'B', 'C'])
        assert manual_run.pending('acc') == ['A', 'B', 'C']

    def test_request_many_appends_to_existing(self, store):
        from module.config import manual_run
        manual_run.request('acc', 'X')
        manual_run.request_many('acc', ['A', 'B'])
        assert manual_run.pending('acc') == ['X', 'A', 'B']

    def test_request_many_tolerates_garbage(self, store):
        from module.config import manual_run
        manual_run.request_many('acc', ['A', '', None, 'B'])
        assert manual_run.pending('acc') == ['A', 'B']

    def test_request_many_empty(self, store):
        from module.config import manual_run
        manual_run.request_many('acc', [])
        assert manual_run.pending('acc') == []
