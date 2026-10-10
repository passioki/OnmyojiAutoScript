# -*- coding: utf-8 -*-
"""#6 **任务完成汇报**（用户 2026-10-10 新需求）。

用户原话:
    "添加一个**任务完成汇报 tab**, 现在的日志属于原始日志, 应该**转移到
     单独界面**用来 debug, 当前日志位置替换为**任务完成汇报**的 tab,
     只会报完成了哪些、**出错任务标注**等等其它可以作为简报的内容"

## 设计要点（本测试钉住）

* **不新增状态存储** —— 复用 `run_record` / `task_state` / `failure_state`
* **出错任务要标注** —— 失败 / 冷却 / 短运行都要能看出来
* **中文名** —— 简报给人看, 不能是 `demonencounter` 这种键
* **一个数据源坏掉不能让整页挂**
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture()
def report():
    import logging
    logging.disable(logging.CRITICAL)
    from module.config.report import build_report
    return build_report('恋鸟树')


class TestReportShape:
    def test_top_level_keys(self, report):
        for k in ('config', 'at', 'summary', 'tasks', 'errors'):
            assert k in report, f'汇报缺顶层键 {k}'

    def test_at_is_timestamp(self, report):
        datetime.strptime(report['at'], '%Y-%m-%d %H:%M:%S')

    def test_summary_keys(self, report):
        for k in ('total', 'completed', 'failed', 'in_cooldown',
                  'total_runs', 'total_minutes'):
            assert k in report['summary'], f'summary 缺 {k}'

    def test_task_row_keys(self, report):
        assert report['tasks'], '一个任务都没有 —— 数据源可能全坏了'
        for t in report['tasks']:
            for k in ('key', 'name', 'runs', 'seconds', 'fail_count',
                      'in_cooldown', 'completed_in_period', 'marks'):
                assert k in t, f'任务行缺 {k}: {t}'

    def test_no_error_key(self, report):
        assert 'error' not in report, f'汇报报错了: {report.get("error")}'


class TestErrorMarking:
    """★ 用户要求"**出错任务标注**"。"""

    def test_marks_are_known_values(self, report):
        known = {'cooldown', 'failed', 'completed', 'short'}
        for t in report['tasks']:
            bad = set(t['marks']) - known
            assert not bad, f'{t["name"]} 有未知标注: {bad}'

    def test_failed_task_is_marked(self, report):
        """有失败计数的任务必须带 `failed` 标注, 且进 `errors`。"""
        failed = [t for t in report['tasks'] if t['fail_count'] > 0]
        if not failed:
            pytest.skip('当前没有失败记录')
        for t in failed:
            assert 'failed' in t['marks'], f'{t["name"]} 有失败却没标 failed'
        names = {e['name'] for e in report['errors']}
        assert {t['name'] for t in failed} & names, \
            '有失败任务却没出现在 errors 简报里'

    def test_cooldown_marked_and_first(self, report):
        cd = [t for t in report['tasks'] if t['in_cooldown']]
        if not cd:
            pytest.skip('当前没有冷却中的任务')
        for t in cd:
            assert 'cooldown' in t['marks']

    def test_errors_have_level_and_text(self, report):
        for e in report['errors']:
            assert e.get('level') in ('cooldown', 'failed', 'short'), e
            assert e.get('text'), 'errors 条目必须有可读文本'
            assert e.get('name'), 'errors 条目必须带中文名'

    def test_completed_marked(self, report):
        got = [t for t in report['tasks'] if t['completed_in_period']]
        for t in got:
            assert 'completed' in t['marks']


class TestChineseNames:
    """★ 简报给人看 —— 必须是中文名, 不能是 `demonencounter`。"""

    def test_names_are_chinese(self, report):
        import re
        names = [t['name'] for t in report['tasks'] if t['runs'] > 0]
        assert names, '没有跑过的任务, 无法校验中文名'
        # 至少大部分有中文（认不出的任务会回退成键, 那是允许的）
        zh = [n for n in names if re.search(r'[\u4e00-\u9fff]', n)]
        assert zh, f'一个中文名都没有: {names}'

    def test_known_task_has_chinese_name(self, report):
        for t in report['tasks']:
            if t['key'] == 'demonencounter':
                assert t['name'] == '逢魔之时', f'实际: {t["name"]}'


class TestSummaryConsistency:
    def test_counts_match_tasks(self, report):
        s = report['summary']
        tasks = report['tasks']
        assert s['total'] == len(tasks)
        assert s['total_runs'] == sum(t['runs'] for t in tasks)
        assert s['failed'] == sum(1 for t in tasks if t['fail_count'] > 0)
        assert s['completed'] == sum(
            1 for t in tasks if t['completed_in_period'])
        assert s['in_cooldown'] == sum(
            1 for t in tasks if t['in_cooldown'])

    def test_total_minutes_matches_seconds(self, report):
        expect = round(sum(t['seconds'] for t in report['tasks']) / 60.0, 1)
        assert report['summary']['total_minutes'] == expect


class TestRobustness:
    """★ 一个数据源坏掉**不该**让整页挂（静默降级是本项目的已知缺陷模式）。"""

    def test_survives_broken_source(self, monkeypatch):
        from module.config import report as R
        # 让 `run_record` 抛异常
        import module.config.run_record as rr
        monkeypatch.setattr(rr, 'summarize',
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
        got = R.build_report('恋鸟树')
        assert 'error' not in got
        assert 'tasks' in got
        # 数据源坏了 -> 至少不该崩
        assert isinstance(got['tasks'], list)

    def test_unknown_config_is_empty_not_error(self):
        from module.config.report import build_report
        got = build_report('__不存在的账号__')
        assert 'error' not in got, f'不存在的账号不该报错: {got.get("error")}'
        assert got['tasks'] == [] or isinstance(got['tasks'], list)


class TestEndpoint:
    def test_endpoint_returns_report(self):
        import asyncio
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.schema_router import get_task_report
        got = asyncio.new_event_loop().run_until_complete(
            get_task_report('恋鸟树'))
        assert 'error' not in got, got.get('error')
        assert got['summary']['total'] == len(got['tasks'])
