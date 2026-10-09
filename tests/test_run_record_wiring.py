# -*- coding: utf-8 -*-
"""`script.py` 的运行记录接线测试。

## 为什么需要

运行记录放在**框架层**（`Script._record_task_run`）而不是各任务里 ——
54 个任务逐个改既容易漏，又会让"统计"散落各处。

但框架层接线有两个容易错的地方，本测试专门盯住:

1. **`TaskEnd` 路径** —— OAS 的任务正常结束时是 `raise TaskEnd`,
   不是 `return`。若记录写在 `except TaskEnd` **之后**，正常结束就全丢了。
   （`TaskEnd` 从 `tasks/base_task.py` 来, 每个任务都会抛。）
2. **异常路径** —— 任务中途崩了也要记（那正是"跑了多久"最有价值的场景）。

`finally` 保证两条路径都记 —— 这比在 `except` 里分别记更不容易漏。
"""
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def record_store(tmp_path, monkeypatch):
    """把运行记录指到临时目录（不要 chdir，Windows 会占用失败）。"""
    from module.config import run_record
    monkeypatch.setattr(run_record, '_record_file',
                        lambda: tmp_path / '.run_record.json', raising=True)
    return tmp_path / '.run_record.json'


class FakeTask:
    """最小任务替身 —— 只需 `current_count` 与 `get_task_name`。"""

    def __init__(self, name='Orochi', count=0):
        self._name = name
        self.current_count = count

    def get_task_name(self):
        return self._name


def make_script(config_name='acc'):
    """
    造一个"只带记录方法"的 Script 替身。

    ★ 不构造真的 `Script` —— 那会去连设备、起服务。
      这里只借 `_task_runs_snapshot` / `_record_task_run` 两个方法。
    """
    from script import Script

    class Stub:
        config_name = 'acc'

        def _task_runs_snapshot(self, task_obj):
            return Script._task_runs_snapshot(self, task_obj)

        def _record_task_run(self, task_obj, command, started, runs_before):
            return Script._record_task_run(self, task_obj, command,
                                           started, runs_before)

    s = Stub()
    s.config_name = config_name
    return s


class TestSnapshot:
    def test_uses_current_count(self, record_store):
        s = make_script()
        assert s._task_runs_snapshot(FakeTask(count=7)) == 7

    def test_falls_back_when_missing(self, record_store):
        """没有 `current_count` 时不崩, 退回持久化计数。"""
        s = make_script()

        class NoCount:
            def get_task_name(self):
                return 'Orochi'

        assert s._task_runs_snapshot(NoCount()) == 0


class TestRecordRun:
    def test_records_delta_and_duration(self, record_store):
        from module.config import run_record

        s = make_script()
        runs_before = 3
        started = datetime.now() - timedelta(seconds=125)
        s._record_task_run(FakeTask(count=8), 'Orochi', started, runs_before)

        cur = run_record.current('acc', 'Orochi')
        assert cur is not None, '应该写出记录'
        assert cur['runs'] == 5, f'应记增量 8-3=5, 实际 {cur["runs"]}'
        assert 120 <= cur['seconds'] <= 130, f'耗时约 125s: {cur["seconds"]}'

    def test_records_inside_finally_even_on_exception(self, record_store):
        """
        ★ 任务抛异常时也要记。

        这就是为什么记录放在 `finally` 里 —— 崩了的那次
        "跑了多久"恰恰是最该看到的。
        """
        from module.config import run_record

        s = make_script()
        started = datetime.now() - timedelta(seconds=60)

        class Boom(FakeTask):
            def get_task_name(self):
                return 'Orochi'

        try:
            try:
                raise RuntimeError('任务中途崩了')
            finally:
                s._record_task_run(Boom(count=2), 'Orochi', started, 0)
        except RuntimeError:
            pass

        assert run_record.current('acc', 'Orochi')['runs'] == 2, \
            '异常路径没有写记录'

    def test_zero_delta_still_records_duration(self, record_store):
        """一次都没打成, 但确实跑了很久 —— 耗时仍要记。"""
        from module.config import run_record

        s = make_script()
        started = datetime.now() - timedelta(seconds=90)
        s._record_task_run(FakeTask(count=5), 'Orochi', started, 5)
        cur = run_record.current('acc', 'Orochi')
        assert cur['runs'] == 0
        assert cur['seconds'] >= 85

    def test_count_decrease_does_not_go_negative(self, record_store):
        """计数被重置过（增量算出来是负）-> 记 0, 不倒退。"""
        from module.config import run_record

        s = make_script()
        s._record_task_run(FakeTask(count=2), 'Orochi',
                           datetime.now(), runs_before=9)
        assert run_record.current('acc', 'Orochi')['runs'] == 0

    def test_record_failure_never_raises(self, record_store, monkeypatch):
        """
        ★ 统计失败**绝不能影响任务** —— 记录只是报表, 跑任务才是正事。
        """
        from module.config import run_record
        monkeypatch.setattr(run_record, 'finish',
                            lambda *a, **kw: (_ for _ in ()).throw(
                                RuntimeError('磁盘满了')),
                            raising=True)
        s = make_script()
        # 不该抛出去
        s._record_task_run(FakeTask(count=1), 'Orochi', datetime.now(), 0)

    def test_accounts_are_isolated(self, record_store):
        from module.config import run_record
        a = make_script('accA')
        b = make_script('accB')
        a._record_task_run(FakeTask(count=2), 'Orochi', datetime.now(), 0)
        b._record_task_run(FakeTask(count=5), 'Orochi', datetime.now(), 0)
        assert run_record.current('accA', 'Orochi')['runs'] == 2
        assert run_record.current('accB', 'Orochi')['runs'] == 5
