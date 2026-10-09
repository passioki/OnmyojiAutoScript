# -*- coding: utf-8 -*-
"""运行记录与归档（`module/config/run_record.py`）的测试。

## 为什么需要

用户确认的设计:

1. **任务记录必须落盘** —— "即使进程停止也能继续恢复"
   * `task_state` 已经落了"计数 / 周期完成记忆 / 存量"
   * 但**运行历史**（跑了多少次、花了多久）还没有
2. **「重置」不是清除, 而是归档后重开** ——
   "这样后续可以分析运行记录和展示运行结果,
    如御魂战斗多少次, 消耗多少体力, 花了多少时间"

★ 用户明确说**先只要"次数 + 耗时"**（体力以后再考虑）。

## 数据模型

    current   —— 当前这一"轮"的累计（重置时结算并归档）
    archive   —— 已归档的若干"轮"

每一轮记:

    started_at   本轮第一次运行的时间
    updated_at   最后一次更新
    runs         跑了几次（战斗次数）
    seconds      累计耗时（秒）

## 为什么归档而不是删除

用户的原话是"后续可以分析运行记录和展示运行结果" ——
删掉就没有"历史"可分析了。归档保留完整轨迹，且**不改动**已有数据。
"""
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    """
    把记录文件指到临时目录。

    ★ 不要 `os.chdir` —— Windows 上会因文件占用导致
      `PermissionError: WinError 32`（在 `test_effective_target` 里踩过）。
      直接 monkeypatch 路径函数更干净。
    """
    from module.config import run_record
    path = tmp_path / '.run_record.json'
    monkeypatch.setattr(run_record, '_record_file', lambda: path,
                        raising=True)
    return path


class TestBeginAndFinish:
    def test_begin_creates_current(self, store):
        from module.config import run_record
        run_record.begin('acc', 'Orochi')
        cur = run_record.current('acc', 'Orochi')
        assert cur is not None
        assert cur['runs'] == 0
        assert cur['seconds'] == 0
        assert cur['started_at']

    def test_finish_accumulates(self, store):
        from module.config import run_record
        run_record.begin('acc', 'Orochi')
        run_record.finish('acc', 'Orochi', runs=5, seconds=120)
        cur = run_record.current('acc', 'Orochi')
        assert cur['runs'] == 5
        assert cur['seconds'] == 120

    def test_finish_without_begin_still_records(self, store):
        """直接从 `finish` 开始也要能记（容错: 进程重启后 begin 可能丢了）。"""
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=3, seconds=60)
        cur = run_record.current('acc', 'Orochi')
        assert cur['runs'] == 3

    def test_runs_accumulate_across_calls(self, store):
        from module.config import run_record
        run_record.begin('acc', 'Orochi')
        run_record.finish('acc', 'Orochi', runs=2, seconds=30)
        run_record.finish('acc', 'Orochi', runs=3, seconds=45)
        cur = run_record.current('acc', 'Orochi')
        assert cur['runs'] == 5
        assert cur['seconds'] == 75

    def test_started_at_kept_from_first_begin(self, store):
        from module.config import run_record
        run_record.begin('acc', 'Orochi')
        first = run_record.current('acc', 'Orochi')['started_at']
        time.sleep(0.01)
        run_record.begin('acc', 'Orochi')     # 再次 begin 不该改 started_at
        assert run_record.current('acc', 'Orochi')['started_at'] == first

    def test_negative_values_ignored(self, store):
        """负数不该把累计值弄坏。"""
        from module.config import run_record
        run_record.begin('acc', 'Orochi')
        run_record.finish('acc', 'Orochi', runs=5, seconds=100)
        run_record.finish('acc', 'Orochi', runs=-2, seconds=-10)
        cur = run_record.current('acc', 'Orochi')
        assert cur['runs'] == 5, f'负数不该扣减: {cur}'
        assert cur['seconds'] == 100


class TestPersistence:
    def test_survives_reopen(self, store):
        """★ 核心: 进程停止后记录还在（落盘, 不是内存）。"""
        from module.config import run_record
        run_record.begin('acc', 'Orochi')
        run_record.finish('acc', 'Orochi', runs=7, seconds=90)

        # 模拟"进程重启": 重新读文件（不依赖任何内存缓存）
        raw = json.loads(store.read_text(encoding='utf-8'))
        assert 'acc' in raw
        # ★ 键是**归一化后的小写** —— 这样 `Orochi` / `orochi` / `OROCHI`
        #   都会落到同一条记录上（否则同一个任务会因为大小写不同被拆开）。
        assert raw['acc']['orochi']['current']['runs'] == 7

    def test_isolated_between_accounts(self, store):
        from module.config import run_record
        run_record.finish('accA', 'Orochi', runs=3, seconds=10)
        run_record.finish('accB', 'Orochi', runs=9, seconds=20)
        assert run_record.current('accA', 'Orochi')['runs'] == 3
        assert run_record.current('accB', 'Orochi')['runs'] == 9

    def test_isolated_between_tasks(self, store):
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=3, seconds=10)
        run_record.finish('acc', 'FallenSun', runs=5, seconds=20)
        assert run_record.current('acc', 'Orochi')['runs'] == 3
        assert run_record.current('acc', 'FallenSun')['runs'] == 5

    def test_task_name_normalised(self, store):
        """`Orochi` 与 `orochi` 是同一个任务。"""
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=3, seconds=10)
        assert run_record.current('acc', 'orochi')['runs'] == 3

    def test_corrupt_file_does_not_crash(self, store):
        """文件坏了不该让任务跑不起来（读失败 -> 当作空）。"""
        from module.config import run_record
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text('{ this is not json', encoding='utf-8')
        assert run_record.current('acc', 'Orochi') is None
        # 写入应当能自愈
        run_record.finish('acc', 'Orochi', runs=1, seconds=5)
        assert run_record.current('acc', 'Orochi')['runs'] == 1

    def test_missing_file_returns_none(self, store):
        from module.config import run_record
        assert run_record.current('acc', 'Orochi') is None


class TestArchive:
    def test_reset_archives_instead_of_deleting(self, store):
        """★ 用户确认: 重置 = **归档后重开**, 不是清除。"""
        from module.config import run_record
        run_record.begin('acc', 'Orochi')
        run_record.finish('acc', 'Orochi', runs=10, seconds=600)

        run_record.reset('acc', 'Orochi')

        # 1) 当前记录清空（重开）
        cur = run_record.current('acc', 'Orochi')
        assert cur is not None, '重置后应有一条新的空记录（重开）'
        assert cur['runs'] == 0
        assert cur['seconds'] == 0

        # 2) 但**归档里有完整的历史**
        arch = run_record.archive('acc', 'Orochi')
        assert len(arch) == 1, f'应有 1 条归档: {arch}'
        assert arch[0]['runs'] == 10
        assert arch[0]['seconds'] == 600
        assert arch[0]['archived_at'], '归档要记时间'

    def test_multiple_resets_append(self, store):
        from module.config import run_record
        for n in (3, 5, 7):
            run_record.finish('acc', 'Orochi', runs=n, seconds=n * 10)
            run_record.reset('acc', 'Orochi')
        arch = run_record.archive('acc', 'Orochi')
        assert [a['runs'] for a in arch] == [3, 5, 7], '应按顺序追加'

    def test_archive_is_append_only(self, store):
        """归档**只增不改** —— 已有条目不该被后续操作改动。"""
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=3, seconds=30)
        run_record.reset('acc', 'Orochi')
        before = run_record.archive('acc', 'Orochi')[0]

        run_record.finish('acc', 'Orochi', runs=9, seconds=90)
        run_record.reset('acc', 'Orochi')

        after = run_record.archive('acc', 'Orochi')[0]
        assert after == before, '旧归档条目被改动了'

    def test_reset_on_nothing_is_noop(self, store):
        """
        什么都还没记录时 `reset()` -> 不该凭空造出记录。

        （`begin()` 过的任务会有一条空 `current`，那是正常的"本轮开始"，
          见下一个测试。）
        """
        from module.config import run_record
        run_record.reset('acc', 'Orochi')
        assert run_record.archive('acc', 'Orochi') == []
        assert run_record.current('acc', 'Orochi') is None, \
            '没记录过的任务不该被 reset 造出来'

    def test_reset_on_zero_runs_not_archived(self, store):
        """跑了 0 次就重置 -> 不值得归档（避免垃圾条目）。"""
        from module.config import run_record
        run_record.begin('acc', 'Orochi')
        run_record.reset('acc', 'Orochi')
        assert run_record.archive('acc', 'Orochi') == [], \
            'runs==0 不该进归档'

    def test_total_aggregates_current_and_archive(self, store):
        """总计 = 当前 + 全部归档（供界面"累计"展示）。"""
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=3, seconds=30)
        run_record.reset('acc', 'Orochi')
        run_record.finish('acc', 'Orochi', runs=5, seconds=50)
        tot = run_record.total('acc', 'Orochi')
        assert tot['runs'] == 8, f'总计应为 3+5=8: {tot}'
        assert tot['seconds'] == 80
        assert tot['archived_rounds'] == 1

    def test_archive_isolated_between_accounts(self, store):
        from module.config import run_record
        run_record.finish('accA', 'Orochi', runs=3, seconds=10)
        run_record.reset('accA', 'Orochi')
        assert run_record.archive('accB', 'Orochi') == []
        assert run_record.archive('accA', 'Orochi')[0]['runs'] == 3


class TestResetMany:
    """界面上的「重置选中」是**批量**的。"""

    def test_reset_many(self, store):
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=3, seconds=30)
        run_record.finish('acc', 'FallenSun', runs=5, seconds=50)
        run_record.reset_many('acc', ['Orochi', 'FallenSun'])
        assert run_record.archive('acc', 'Orochi')[0]['runs'] == 3
        assert run_record.archive('acc', 'FallenSun')[0]['runs'] == 5
        assert run_record.current('acc', 'Orochi')['runs'] == 0
        assert run_record.current('acc', 'FallenSun')['runs'] == 0

    def test_reset_many_tolerates_bad_names(self, store):
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=3, seconds=30)
        # 不该因为一个不存在的任务而整体失败
        run_record.reset_many('acc', ['Orochi', 'NotARealTask'])
        assert run_record.archive('acc', 'Orochi')[0]['runs'] == 3

    def test_reset_many_empty_list(self, store):
        from module.config import run_record
        run_record.reset_many('acc', [])      # 不应抛异常


class TestDuration:
    """耗时用"秒"存, 展示时再格式化 —— 存储不该带单位。"""

    def test_stored_in_seconds(self, store):
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=1, seconds=3661)
        assert run_record.current('acc', 'Orochi')['seconds'] == 3661

    def test_format_duration(self):
        from module.config.run_record import format_duration
        assert format_duration(0) == '0 分钟'
        assert format_duration(90) == '1 分钟'
        assert format_duration(3600) == '1 小时'
        assert format_duration(3661) == '1 小时 1 分钟'
        assert format_duration(-5) == '0 分钟', '负数当 0'

    def test_add_seconds_helper(self, store):
        """按"跑了多久"累加更自然（调用方不必自己算秒）。"""
        from module.config import run_record
        run_record.finish('acc', 'Orochi', runs=1, seconds=0)
        run_record.add_duration('acc', 'Orochi', timedelta(minutes=5))
        assert run_record.current('acc', 'Orochi')['seconds'] == 300
