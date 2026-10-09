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


# 模块级 fixture —— 多个测试类都要用
# (类内 fixture 只有该类能看见, 第二个类用会出现 "fixture not found")
@pytest.fixture(scope='module')
def schema():
    return build_schema(CONFIG)


@pytest.fixture(scope='module')
def overview():
    return build_overview(CONFIG)


class TestSchema:
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

    def test_has_ui_rendering_fields(self, overview):
        """
        界面渲染所需的补充字段。

        ★ 这些字段存在是为了让前端**不必内置任务知识** ——
          类别中文标签、列表位置、存量、资源描述全部由后端给出。
        """
        for r in overview['tasks']:
            for k in ('category_label', 'charges', 'list_pos', 'in_list',
                      'resource_describe'):
                assert k in r, f'{r.get("name")} 缺界面字段 {k}'

    def test_category_label_is_chinese(self, overview):
        """
        类别标签应是中文, 前端直接显示。

        ★ 元数据缺失的任务(还没写 `meta.py` 的)也要有标签 ——
          否则界面会出现"类型"列为空的行。
        """
        for r in overview['tasks']:
            lb = r['category_label']
            assert lb, f'{r["name"]} 的 category_label 为空'
            assert any('\u4e00' <= ch <= '\u9fff' for ch in lb), \
                f'类别标签应是中文: {lb!r}'

    def test_list_pos_comes_from_spec(self, overview):
        """
        `list_pos` 应来自 `TaskSpec`(带默认顺序), 而不是全为 None。

        ⚠ 踩过的坑: 写成 `getattr(meta, 'list_pos', None)` 会**静默返回 None**
          (`list_pos` 在 `TaskSpec` 上, 不在 `TaskMeta` 上), 表现是
          "所有任务的 list_pos 都是 None", 很难发现。
        """
        have = [r for r in overview['tasks'] if r['list_pos'] is not None]
        assert len(have) > 40, \
            f'应有 40+ 个任务带 list_pos, 实际 {len(have)} —— 疑似又取错对象'

    def test_in_list_matches_list_pos(self, overview):
        for r in overview['tasks']:
            assert r['in_list'] == (r['list_pos'] is not None), \
                f'{r["name"]}: in_list 与 list_pos 不一致'

    def test_charges_shape_when_present(self, overview):
        """
        `charges` 的键名必须能对上 —— 归一化过的。

        ⚠ 踩过的坑: `task_state.summarize()` 的键是**压缩小写**
          (`experienceyoukai`), 而 `model_dump` 是**下划线**
          (`experience_youkai`)。直接查**不报错、只是为空**。
        """
        for r in overview['tasks']:
            c = r['charges']
            if c is None:
                continue
            assert isinstance(c, dict)
            assert 'count' in c and 'max' in c, f'{r["name"]} 的 charges 结构不对'

    def test_charge_tasks_can_find_charges(self, overview):
        """至少有一个充能任务能拿到存量(证明键名归一化生效)。"""
        got = [r for r in overview['tasks']
               if r['category'] == 'charge' and r['charges']]
        assert got, ('所有充能任务的 charges 都是空的 —— '
                     '疑似键名归一化失效(压缩小写 vs 下划线)')

    def test_in_window_defaults_true(self, overview):
        """未配置开放时段时, 所有任务都应 in_window=True。"""
        assert all(r['in_window'] for r in overview['tasks'])

    def test_teams_present(self, overview):
        assert isinstance(overview['teams'], list)

    def test_at_is_timestamp(self, overview):
        datetime.strptime(overview['at'], '%Y-%m-%d %H:%M:%S')


class TestRunListSection:
    """
    `/schema` 的 `list` 段 —— 运行列表(条目清单 / 模型 B)的界面契约。

    列表是**有序条目**的序列, 条目三种(按**效果**命名):

        task   执行某个任务
        rest   **全部停止** N 分钟(连定时任务一起停)
        delay  **只停列表** N 分钟(定时任务照常)
    """

    @pytest.fixture
    def lst(self, schema):
        return schema['list']

    def test_has_expected_keys(self, lst):
        for k in ('mode_value', 'modes', 'order_field', 'order_group',
                  'entry_kinds', 'duration_choices', 'note'):
            assert k in lst, f'list 段缺 {k}'

    def test_order_field_is_run_list(self, lst):
        """用户编排写进 `run_list`, 不再是旧的 `task_order`。"""
        assert lst['order_field'] == 'run_list'
        assert lst['order_group'] == 'script.optimization'

    def test_mode_value_is_list(self, lst):
        assert lst['mode_value'] == 'List'

    def test_modes_have_value_and_label(self, lst):
        assert len(lst['modes']) >= 4
        for m in lst['modes']:
            assert 'value' in m and 'label' in m

    def test_entry_kinds_cover_two(self, lst):
        """v2 只有两种条目: `task`（固定任务）与 `rest`（休息）。"""
        kinds = {k['value'] for k in lst['entry_kinds']}
        assert kinds == {'task', 'rest'}, kinds

    def test_entry_kind_flags_are_consistent(self, lst):
        """`needs_task` / `needs_minutes` / `blocks_list` 必须自洽。"""
        for k in lst['entry_kinds']:
            if k['value'] == 'task':
                assert k['needs_task'] and not k['needs_minutes']
                assert not k['blocks_list'], 'task 条目**不该**阻塞列表'
            else:
                assert k['needs_minutes'] and not k['needs_task']
                assert k['blocks_list'], f'{k["value"]} 应阻塞列表'

    def test_effect_based_naming(self, lst):
        """按**行为**命名: `task` -> 任务, `rest` -> 休息。"""
        label = {k['value']: k['label'] for k in lst['entry_kinds']}
        assert label['task'] == '任务'
        assert label['rest'] == '休息'

    def test_rest_help_mentions_town(self, lst):
        """休息的说明必须写明**去庭院**（不是"什么都不做"）。"""
        help_ = {k['value']: k['help'] for k in lst['entry_kinds']}
        assert '庭院' in help_['rest'], help_['rest']

    def test_exposes_two_master_switches(self, lst):
        """暴露"启用固定/启用定时"与相关开关的定义, 前端不必硬编码字段名。"""
        gf = lst.get('global_fields') or {}
        for key in ('enable_fixed', 'enable_timed',
                    'timed_priority', 'rest_interleave'):
            assert key in gf, f'list.global_fields 缺 {key}'
            assert gf[key].get('label'), f'{key} 缺 label'

    def test_duration_choices_positive_sorted(self, lst):
        d = lst['duration_choices']
        assert d and all(m > 0 for m in d) and d == sorted(d)

    def test_note_mentions_blocking(self, lst):
        assert '阻塞' in lst['note']


class TestRunRecordEndpoints:
    """
    运行记录与归档的接口。

    ★ 「重置」= **归档后重开**（不是删除）—— 用户明确要求。
    """

    def test_get_all_returns_shape(self, have_config):
        from module.server.schema_router import get_run_record
        import asyncio

        r = asyncio.run(get_run_record(CONFIG))
        assert 'error' not in r, r.get('error')
        assert isinstance(r['tasks'], dict)
        assert r['count'] == len(r['tasks'])

    def test_get_all_has_readable_duration(self, have_config):
        """接口直接给可读耗时文本, 免得每个前端各写一份格式化。"""
        from module.server.schema_router import get_run_record
        import asyncio

        r = asyncio.run(get_run_record(CONFIG))
        for task, row in r['tasks'].items():
            assert 'seconds_text' in row, f'{task} 缺 seconds_text'
            assert '分钟' in row['seconds_text'] or '小时' in row['seconds_text']

    def test_get_one_returns_current_archive_total(self, have_config):
        from module.server.schema_router import get_run_record
        import asyncio

        r = asyncio.run(get_run_record(CONFIG, task='Orochi'))
        assert 'error' not in r
        for key in ('current', 'archive', 'total'):
            assert key in r, f'缺 {key}'
        assert isinstance(r['archive'], list)

    def test_reset_archives_not_deletes(self, have_config, tmp_path,
                                        monkeypatch):
        """★ 核心语义: 重置后 `archive` 里**有**东西, 而 `current` 清零。"""
        from module.config import run_record
        from module.server.schema_router import (get_run_record,
                                                 put_run_record_reset)
        import asyncio

        monkeypatch.setattr(
            run_record, '_record_file',
            lambda: tmp_path / '.run_record.json', raising=True)

        run_record.begin(CONFIG, 'Orochi')
        run_record.finish(CONFIG, 'Orochi', runs=11, seconds=330)

        res = asyncio.run(put_run_record_reset(CONFIG, tasks=['Orochi']))
        assert 'error' not in res, res.get('error')
        assert res['archived_rounds'] == 1, res

        after = asyncio.run(get_run_record(CONFIG, task='Orochi'))
        assert after['current']['runs'] == 0, '重置后当前应为 0（重开）'
        assert len(after['archive']) == 1, '归档必须保留'
        assert after['archive'][0]['runs'] == 11
        assert after['total']['runs'] == 11, '总计仍能看到历史'

    def test_reset_tolerates_bad_names(self, have_config, tmp_path,
                                       monkeypatch):
        from module.config import run_record
        from module.server.schema_router import put_run_record_reset
        import asyncio

        monkeypatch.setattr(
            run_record, '_record_file',
            lambda: tmp_path / '.run_record.json', raising=True)
        run_record.finish(CONFIG, 'Orochi', runs=3, seconds=30)

        res = asyncio.run(put_run_record_reset(
            CONFIG, tasks=['Orochi', 'NotARealTask']))
        assert 'error' not in res
        assert res['archived_rounds'] == 1, '坏名字不该让整批失败'

    def test_reset_empty_list(self, have_config):
        from module.server.schema_router import put_run_record_reset
        import asyncio

        res = asyncio.run(put_run_record_reset(CONFIG, tasks=[]))
        assert 'error' not in res
        assert res['archived_rounds'] == 0

    def test_archive_endpoint(self, have_config, tmp_path, monkeypatch):
        from module.config import run_record
        from module.server.schema_router import get_task_archive
        import asyncio

        monkeypatch.setattr(
            run_record, '_record_file',
            lambda: tmp_path / '.run_record.json', raising=True)
        run_record.finish(CONFIG, 'Orochi', runs=4, seconds=120)
        run_record.reset(CONFIG, 'Orochi')

        r = asyncio.run(get_task_archive(CONFIG, 'Orochi'))
        assert 'error' not in r
        assert len(r['archive']) == 1
        assert '分钟' in r['archive'][0]['seconds_text']


class TestManualRunEndpoints:
    """
    「运行一次」—— 按**点击顺序**插队，跑一次就出队。

    ★ 用户确认: "点击后按照点击先后顺序，直接排在最高优先级
      （就是跑完当前任务/战斗后插队运行）"。
    """

    @pytest.fixture(autouse=True)
    def clean_queue(self, tmp_path, monkeypatch):
        from module.config import manual_run
        monkeypatch.setattr(manual_run, '_queue_file',
                            lambda: tmp_path / '.manual_run.json',
                            raising=True)
        yield
        manual_run.clear(CONFIG)

    def test_put_preserves_click_order(self, have_config):
        import asyncio

        from module.server.schema_router import get_manual_run, put_manual_run
        r = asyncio.run(put_manual_run(CONFIG, tasks=['Orochi', 'FallenSun',
                                                      'GoryouRealm']))
        assert 'error' not in r, r.get('error')
        assert r['tasks'] == ['Orochi', 'FallenSun', 'GoryouRealm'], \
            '必须保留点击顺序'
        assert r['count'] == 3
        assert r['head'] == 'Orochi'

        again = asyncio.run(get_manual_run(CONFIG))
        assert again['tasks'] == ['Orochi', 'FallenSun', 'GoryouRealm']

    def test_duplicate_not_double_queued(self, have_config):
        import asyncio

        from module.server.schema_router import put_manual_run
        asyncio.run(put_manual_run(CONFIG, tasks=['Orochi']))
        r = asyncio.run(put_manual_run(CONFIG, tasks=['Orochi']))
        assert r['count'] == 1, '重复点不该排两次'

    def test_delete_cancels_one(self, have_config):
        import asyncio

        from module.server.schema_router import (delete_manual_run,
                                                 put_manual_run)
        asyncio.run(put_manual_run(CONFIG, tasks=['Orochi', 'FallenSun']))
        r = asyncio.run(delete_manual_run(CONFIG, task='Orochi'))
        assert r['cancelled'] is True
        assert r['tasks'] == ['FallenSun']

    def test_delete_empty_task_clears_all(self, have_config):
        import asyncio

        from module.server.schema_router import (delete_manual_run,
                                                 put_manual_run)
        asyncio.run(put_manual_run(CONFIG, tasks=['Orochi', 'FallenSun']))
        r = asyncio.run(delete_manual_run(CONFIG, task=''))
        assert r['cleared'] is True
        assert r['tasks'] == []

    def test_schema_exposes_queue(self, schema):
        """`/schema` 里带一份队列摘要 —— 进页面只发一次请求。"""
        assert 'manual_run' in schema['list']
        assert 'tasks' in schema['list']['manual_run']


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
