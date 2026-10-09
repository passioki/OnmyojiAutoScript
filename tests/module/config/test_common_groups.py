# -*- coding: utf-8 -*-
"""公共分组接口的测试: 发现重复分组 + 一次写入多个任务。

背景
----
实测 56 个任务共下发 1402 个字段, 其中 4 类公共分组占 60.9% —— 仅 scheduler
一个 10 字段分组就被逐字复制 54 份。用户想在多个任务上用同一设置时只能逐页改。
gui_common_groups() 负责发现这些分组, set_common_arg() 负责"改一处、多任务生效"。
"""
import pytest

from module.config.config_model import ConfigModel


@pytest.fixture
def model(monkeypatch):
    """
    返回一个 save() 被置为空操作的 ConfigModel。

    为什么: set_common_arg() 内部会调用 self.save(), 而 ConfigModel 的默认
    config_name 是 'oas' —— 直接用它会在用户的 config/ 目录里写文件。测试只需
    验证"内存中的赋值与校验行为", 落盘那一步由 script_router 的调用方负责。
    注意 pydantic v2 不允许给实例新增字段, 所以必须在**类**上打补丁。
    """
    monkeypatch.setattr(ConfigModel, 'save', lambda *a, **kw: None)
    m = ConfigModel()
    m.config_name = 'unittest'
    return m


class TestDiscoverCommonGroups:
    def test_finds_scheduler(self, model):
        groups = model.gui_common_groups(min_tasks=2)
        names = [g['group'] for g in groups]
        assert 'scheduler' in names, f'应发现 scheduler, 实际 {names[:10]}'

    def test_scheduler_is_most_used(self, model):
        groups = model.gui_common_groups(min_tasks=2)
        top = groups[0]
        assert top['group'] == 'scheduler'
        # 实测被 54 个任务使用(允许偏差)
        assert top['task_count'] >= 50, f"实际 {top['task_count']}"

    def test_scheduler_fields_complete(self, model):
        """scheduler 应是 10 个字段(含完成记忆的 period 与 reset_at)。"""
        g = [x for x in model.gui_common_groups(min_tasks=2)
             if x['group'] == 'scheduler'][0]
        names = {f['name'] for f in g['fields']}
        for expected in ('enable', 'next_run', 'priority', 'success_interval',
                         'retry_interval', 'server_update', 'delay_date',
                         'float_time', 'period', 'reset_at'):
            assert expected in names, f'scheduler 缺字段 {expected}'

    def test_min_tasks_filters(self, model):
        few = model.gui_common_groups(min_tasks=50)
        many = model.gui_common_groups(min_tasks=2)
        assert len(few) <= len(many)
        # min_tasks=50 时只应剩 scheduler 这类被大量复用的
        assert all(g['task_count'] >= 50 for g in few)

    def test_tasks_are_underscore_names(self, model):
        g = [x for x in model.gui_common_groups(min_tasks=2)
             if x['group'] == 'scheduler'][0]
        assert 'gold_youkai' in g['tasks']
        assert all(t == t.lower() for t in g['tasks'])

    def test_result_is_json_serializable(self, model):
        import json
        json.dumps(model.gui_common_groups(min_tasks=2), ensure_ascii=False,
                   default=str)


class TestSetCommonArg:
    def test_single_task(self, model):
        r = model.set_common_arg('scheduler', 'float_time', '00:07:00',
                                 only_tasks=['gold_youkai'])
        assert r['changed'] == ['gold_youkai']
        assert not r['failed']
        assert str(model.gold_youkai.scheduler.float_time) == '00:07:00'

    def test_multiple_tasks(self, model):
        r = model.set_common_arg('scheduler', 'float_time', '00:09:00',
                                 only_tasks=['gold_youkai',
                                             'experience_youkai', 'tako'])
        assert sorted(r['changed']) == ['experience_youkai', 'gold_youkai',
                                        'tako']
        for t in ('gold_youkai', 'experience_youkai', 'tako'):
            assert str(getattr(model, t).scheduler.float_time) == '00:09:00'

    def test_exclude_tasks(self, model):
        r = model.set_common_arg('scheduler', 'float_time', '00:11:00',
                                 only_tasks=['gold_youkai', 'tako'],
                                 exclude_tasks=['tako'])
        assert 'tako' not in r['changed']
        assert 'tako' in r['skipped']
        assert str(model.gold_youkai.scheduler.float_time) == '00:11:00'

    def test_out_of_range_rejected(self, model):
        """delay_date 的约束是 1..31, 越界必须被拒绝而不是静默写入。

        注意: pydantic 默认**不在赋值时校验**(ConfigBase 未设
        validate_assignment), 因此 set_common_arg 内部显式跑了模型校验。
        """
        before = model.gold_youkai.scheduler.delay_date
        r = model.set_common_arg('scheduler', 'delay_date', 99,
                                 only_tasks=['gold_youkai'])
        assert r['changed'] == []
        assert r['failed'], '越界值应出现在 failed 里'
        assert 'less than or equal to 31' in r['failed'][0]['error']
        assert model.gold_youkai.scheduler.delay_date == before, '不应被改动'

    def test_wrong_type_rejected(self, model):
        r = model.set_common_arg('scheduler', 'delay_date', 'abc',
                                 only_tasks=['gold_youkai'])
        assert r['changed'] == []
        assert r['failed']

    def test_valid_value_accepted(self, model):
        r = model.set_common_arg('scheduler', 'delay_date', 3,
                                 only_tasks=['gold_youkai'])
        assert r['changed'] == ['gold_youkai']
        assert model.gold_youkai.scheduler.delay_date == 3

    def test_enum_value_normalized(self, model):
        """传字符串 'daily' 应被规范化为 TaskPeriod.DAILY。"""
        from tasks.Component.config_scheduler import TaskPeriod
        r = model.set_common_arg('scheduler', 'period', 'daily',
                                 only_tasks=['gold_youkai'])
        assert r['changed'] == ['gold_youkai']
        assert model.gold_youkai.scheduler.period == TaskPeriod.DAILY

    def test_unknown_argument_skipped(self, model):
        r = model.set_common_arg('scheduler', 'no_such_arg', 1,
                                 only_tasks=['gold_youkai'])
        assert r['changed'] == []
        assert 'gold_youkai' in r['skipped']

    def test_unknown_group_returns_empty(self, model):
        r = model.set_common_arg('no_such_group', 'x', 1)
        assert r['changed'] == []
        assert r['total'] == 0

    def test_group_present_but_task_lacks_field(self, model):
        """
        only_tasks 里若某个任务没有该分组, 应被跳过而不是报错。
        script 任务没有 scheduler 分组。
        """
        r = model.set_common_arg('scheduler', 'float_time', '00:01:00',
                                 only_tasks=['script'])
        assert r['changed'] == []
        assert not r['failed']
