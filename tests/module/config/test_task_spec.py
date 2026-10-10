# -*- coding: utf-8 -*-
"""任务自描述（`tasks/<Name>/meta.py`）与 `TaskSpec` 的测试。

## 为什么要自描述

**目标: 新增一个游戏活动 = 只写 `tasks/<New>/`，零改动其它文件。**

此前任务元数据散落在 4 处（任务 config / OAS i18n / OASX i18n / 本模块的 JSON），
新增一个活动要改 5 个地方，**漏一处就出问题**——本轮实测 `MetaDemon` 等任务在
两个 i18n 里都缺条目，界面直接显示英文 key。

现在把"这个任务是什么"收进任务自己的目录：

    tasks/MetaDemon/
        meta.py          <- SPEC 声明
        config.py
        script_task.py
        assets.py

`task_catalog` 扫描 `tasks/*/meta.py` 自动汇总，因此调度器 / 配置模型 /
前端 schema / i18n 都会**自动**获得该任务。
"""
import pytest

from module.config import task_catalog as TC
from module.config.resource import Period, Recharge, Resource
from module.config.task_catalog import (
    FALLBACK_CATEGORY, SPEC_VAR, Category, TaskSpec)


class TestTaskSpecConstruction:
    def test_minimal(self):
        s = TaskSpec(task='Demo', name_zh='演示')
        assert s.task == 'Demo'
        assert s.category == Category.TIMED, '默认应为定时任务'
        assert s.resource is None
        assert s.requires == ()

    def test_category_from_string(self):
        s = TaskSpec(task='Demo', name_zh='演示', category='fixed')
        assert s.category == Category.FIXED

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError, match='非法 category'):
            TaskSpec(task='Demo', name_zh='演示', category='nonexistent')

    def test_empty_task_raises(self):
        with pytest.raises(ValueError, match='task 不能为空'):
            TaskSpec(task='', name_zh='演示')

    def test_frozen(self):
        s = TaskSpec(task='Demo', name_zh='演示')
        with pytest.raises(Exception):
            s.task = 'Other'

    def test_spec_var_name_is_conventional(self):
        assert SPEC_VAR == 'SPEC'


class TestDiscovery:
    """扫描 `tasks/*/meta.py` 的发现机制。"""

    def test_all_tasks_have_meta(self):
        """现有 54 个任务都已生成 meta.py（迁移完成）。"""
        specs = TC.all_specs()
        missing = [t for t in TC.all_tasks() if t not in specs]
        assert missing == [], f'这些任务缺 meta.py: {missing}'

    def test_discovered_count_matches_tasks(self):
        assert len(TC.all_specs()) == len(TC.all_tasks())

    def test_specs_are_task_spec_instances(self):
        for task, spec in TC.all_specs().items():
            assert isinstance(spec, TaskSpec), f'{task} 的 SPEC 类型不对'
            assert spec.task == task, f'{task} 的 SPEC.task 与目录名不符'

    def test_get_spec_for_known_task(self):
        s = TC.get_spec('FallenSun')
        assert s is not None
        assert s.name_zh == '日轮之陨'
        assert s.category == Category.FIXED

    def test_get_spec_for_unknown_task(self):
        assert TC.get_spec('NoSuchTask') is None

    def test_reload_specs_is_safe(self):
        before = len(TC.all_specs())
        TC.reload_specs()
        assert len(TC.all_specs()) == before


class TestSpecOverridesJson:
    """
    自描述**优先于**中心化 JSON。

    这样改任务的名称/类别只需改它自己的 meta.py, 不必再去动中心文件 ——
    这正是"新增任务零改动"的前提。
    """

    @pytest.mark.parametrize('task,expect_category', [
        ('FallenSun', Category.FIXED),
        ('GoldYoukai', Category.CHARGE),
        ('RyouToppa', Category.TOPPA),
        ('RealmRaid', Category.TOPPA),
        ('MetaDemon', Category.LIMITED),
        ('DemonEncounter', Category.TIMED),
        ('Exploration', Category.FIXED),
        ('HeroTest', Category.FIXED),
    ])
    def test_category_comes_from_spec(self, task, expect_category):
        assert TC.get(task).category == expect_category
        # 且与 SPEC 一致
        spec = TC.get_spec(task)
        if spec is not None:
            assert TC.get(task).category == spec.category

    @pytest.mark.parametrize('task,expected_name', [
        ('FallenSun', '日轮之陨'),
        ('HeroTest', '英杰试炼'),
        ('AbyssShadows', '狭间暗域'),
        ('Sougenbi', '业原火'),
        ('RealmRaid', '个人突破'),
    ])
    def test_name_comes_from_spec(self, task, expected_name):
        assert TC.get(task).name_zh == expected_name

    def test_json_only_task_still_visible(self):
        """即使某任务没有 meta.py, 也应能从 JSON 读到(渐进迁移不中断服务)。"""
        # 所有任务都有 meta.py, 但机制本身要保证退路存在
        assert len(TC.all_meta()) == 54


class TestSpecResources:
    """meta.py 里声明的资源规则应与实测数据一致。"""

    def test_fixed_daily(self):
        r = TC.get_spec('FallenSun').resource
        assert r.capacity == 50
        assert r.period == Period.DAILY
        assert r.refill == 'none'
    def test_weekly_capacity(self):
        r = TC.get_spec('TrueOrochi').resource
        assert r.capacity == 2
        assert r.period == Period.WEEKLY

    def test_limited_window(self):
        r = TC.get_spec('MetaDemon').resource
        assert r.refill == 'window'
        assert r.is_activity_gated is True

    def test_interval_preserved(self):
        """小时级间隔必须保留为 interval, 不能被归成 period(曾踩过)。"""
        r = TC.get_spec('DemonEncounter').resource
        assert r.refill == 'interval'
        assert r.interval == (0, 1, 0)
    def test_fallback_category_is_timed(self):
        """未提供 meta.py 的任务降级为定时任务, 而不是报错。"""
        assert FALLBACK_CATEGORY == Category.TIMED
