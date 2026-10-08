# -*- coding: utf-8 -*-
"""`/schema` 与 `/overview` 接口的测试。

## 为什么需要这两个接口

设计原则: **前端不内置任务知识, 全部从接口拉**(见 `docs/architecture.md` §7.2)。
否则每加一个任务、每改一个类别, 都要同步改前端 —— 又变成"同一知识多处"。

* `/schema`   —— 静态元数据(中文名 / 类别 / 资源规则 / 可配字段), 与账号无关
* `/overview` —— 动态运行态(现在能不能跑 / 为什么不能 / 下次什么时候)

## 本测试关注

1. schema 覆盖全部任务, 且元数据来自 `meta.py`(不重复定义)
2. 资源规则能被前端理解(补充方式 / 周期 / 槽位 / 描述)
3. overview 的 `can_run` 与 `slot` 自洽(可跑 <=> 在 pending 桶)
4. 未启用任务必须 `can_run=False` 且给出原因
5. 两个接口都**不抛异常**(界面依赖它们, 挂了整个总览页空白)
"""
from datetime import datetime

import pytest

from module.config import task_catalog as TC
from module.server.schema_router import build_overview, build_schema

CONFIG = '恋鸟树'


@pytest.fixture(scope='module')
def have_config():
    from pathlib import Path
    if not (Path.cwd() / 'config' / f'{CONFIG}.json').exists():
        pytest.skip(f'缺少配置 {CONFIG}')
    return CONFIG


class TestSchema:
    @pytest.fixture(scope='class')
    def schema(self):
        return build_schema(CONFIG)

    def test_covers_all_tasks(self, schema):
        assert schema['count'] == len(TC.all_tasks())
        assert set(schema['tasks']) == set(TC.all_tasks())

    def test_name_zh_comes_from_meta(self, schema):
        """名称必须与 `meta.py` 一致 —— 接口不重新定义知识。"""
        for task, spec in TC.all_specs().items():
            assert schema['tasks'][task]['name_zh'] == spec.name_zh

    def test_category_comes_from_meta(self, schema):
        for task, spec in TC.all_specs().items():
            assert schema['tasks'][task]['category'] == spec.category.value

    @pytest.mark.parametrize('task,expect', [
        ('FallenSun', {'capacity': 50, 'refill': 'none', 'period': 'daily'}),
        ('GoldYoukai', {'capacity': 2, 'refill': 'slots', 'period': 'none'}),
        ('TrueOrochi', {'capacity': 2, 'refill': 'none', 'period': 'weekly'}),
        ('MetaDemon', {'capacity': 1, 'refill': 'window', 'period': 'daily'}),
        ('DemonEncounter', {'capacity': 1, 'refill': 'interval',
                            'period': 'none'}),
    ])
    def test_resource_rules(self, schema, task, expect):
        res = schema['tasks'][task]['resource']
        for k, v in expect.items():
            assert res[k] == v, f'{task}.{k} 期望 {v}, 实际 {res[k]}'

    def test_slots_are_readable_strings(self, schema):
        """槽位要转成 'HH:MM' 字符串, 前端才好显示。"""
        slots = schema['tasks']['GoldYoukai']['resource']['slots']
        assert slots == ['00:00', '12:00']

    def test_interval_is_list(self, schema):
        iv = schema['tasks']['DemonEncounter']['resource']['interval']
        assert isinstance(iv, list) and len(iv) == 3
        assert iv == [0, 1, 0]

    def test_every_resource_has_describe(self, schema):
        for task, item in schema['tasks'].items():
            assert item['resource']['describe'], f'{task} 缺 describe'

    def test_categories_list(self, schema):
        cats = {c['value'] for c in schema['categories']}
        assert cats == {c.value for c in TC.Category}
        # 只有固定任务与结界突破可以设次数
        countable = {c['value'] for c in schema['categories'] if c['countable']}
        assert countable == {c.value for c in TC.COUNTABLE_CATEGORIES}

    def test_countable_flag_consistent(self, schema):
        for task, item in schema['tasks'].items():
            if item['countable']:
                assert item['count_field'] == TC.UNIFIED_COUNT_FIELD, \
                    f'{task} 可设次数但字段名不是统一名'
            else:
                assert item['count_field'] is None

    def test_window_fields_exposed(self, schema):
        """开放时段字段由接口给出, 前端不必硬编码字段名。"""
        names = {f['name'] for f in schema['window_fields']}
        assert names == {'window_enable', 'window_start',
                         'window_end', 'window_days'}

    def test_source_is_declared(self, schema):
        assert 'meta.py' in schema['source']


class TestOverview:
    @pytest.fixture(scope='class')
    def overview(self, have_config):
        return build_overview(CONFIG)

    def test_no_error(self, overview):
        assert 'error' not in overview, overview.get('error')

    def test_shape(self, overview):
        assert overview['config'] == CONFIG
        assert isinstance(overview['tasks'], list)
        assert overview['total'] == len(overview['tasks'])
        assert 0 <= overview['runnable'] <= overview['total']

    def test_runnable_count_matches_rows(self, overview):
        n = sum(1 for r in overview['tasks'] if r['can_run'])
        assert n == overview['runnable']

    def test_can_run_implies_pending_slot(self, overview):
        """可跑 <=> 在 pending 桶 —— 两者必须自洽, 否则界面会自相矛盾。"""
        for r in overview['tasks']:
            if r['can_run']:
                assert r['slot'] == 'pending', \
                    f'{r["name"]} can_run=True 但 slot={r["slot"]!r}'
                assert r['enable'], f'{r["name"]} 未启用却 can_run=True'

    def test_disabled_tasks_have_reason(self, overview):
        for r in overview['tasks']:
            if not r['enable']:
                assert r['can_run'] is False
                assert r['reason'] == '未启用', \
                    f'{r["name"]} 未启用但 reason={r["reason"]!r}'

    def test_not_run_without_reason(self, overview):
        """不可跑的任务必须给出原因 —— 否则界面显示空白, 用户不知道为什么。"""
        for r in overview['tasks']:
            if not r['can_run']:
                assert r['reason'], f'{r["name"]} 不可跑却没有原因'

    def test_rows_sorted_runnable_first(self, overview):
        flags = [r['can_run'] for r in overview['tasks']]
        # 一旦出现 False, 后面不应再有 True
        assert flags == sorted(flags, reverse=True), '可跑的任务应排在最前'

    def test_has_expected_fields(self, overview):
        for r in overview['tasks']:
            for k in ('name', 'command', 'name_zh', 'category', 'enable',
                      'priority', 'next_run', 'period', 'slot', 'can_run',
                      'reason', 'in_window'):
                assert k in r, f'{r.get("name")} 缺字段 {k}'

    def test_in_window_defaults_true(self, overview):
        """未配置开放时段时, 所有任务都应 in_window=True。"""
        assert all(r['in_window'] for r in overview['tasks'])

    def test_teams_present(self, overview):
        assert isinstance(overview['teams'], list)

    def test_at_is_timestamp(self, overview):
        datetime.strptime(overview['at'], '%Y-%m-%d %H:%M:%S')


class TestRobustness:
    """接口挂了整个总览页会空白, 因此必须不抛异常。"""

    def test_schema_unknown_config(self):
        s = build_schema('不存在的配置')
        assert isinstance(s, dict)
        # schema 与账号无关, 应该照样返回全部任务
        assert s['count'] == len(TC.all_tasks())

    def test_overview_unknown_config(self):
        o = build_overview('不存在的配置')
        assert isinstance(o, dict)
        # 可能返回 error, 但不应抛异常
        assert 'tasks' in o or 'error' in o
