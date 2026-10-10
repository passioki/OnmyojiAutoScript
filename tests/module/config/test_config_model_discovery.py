# -*- coding: utf-8 -*-
"""`ConfigModel` 自动发现的测试。

## 背景

`config_model.py` 原先手写 60 个 `from tasks.X.config import X` +
56 个 `x: X = Field(default_factory=X)`。**新增一个游戏活动要改这里**,
漏改的后果是**静默的** —— 任务不报错, 只是配置里读不到它。

现在改为扫描 `tasks/*/config.py` 自动发现, 与 `tasks/<Name>/meta.py` 的
自描述配套, 一起实现:

    **新增一个游戏活动 = 只写 `tasks/<New>/`, 零改动其它文件**

## 两个易错点(已在本轮踩过)

1. **并非所有配置类都继承 `ConfigBase`** —— `Script` 与 `GlobalGame` 直接
   继承 `BaseModel`。只查 `ConfigBase` 会静默漏掉它们(少 2 个字段)。
2. **字段名须用类名派生** —— `convert_to_underscore(ClassName)`, 而不是目录名。
   因为手写声明的 key 就是这么来的; 用目录名有可能得到不同的键。
"""
import pytest

from module.config.config_model import (
    EXTRA_GLOBAL, NOT_A_TASK, ConfigModel, _discover_config_classes)
from module.config.utils import convert_to_underscore


class TestDiscoveryCompleteness:
    def test_field_count_matches_handwritten(self):
        """
        自动发现的字段数 == 原手写声明的 58 个。

        (56 个任务/设置 + `config_name` + `running_task`)
        这是替换安全性的核心断言: 少一个字段就意味着某个任务的配置读不出来。
        """
        assert len(ConfigModel.__annotations__) == 59

    def test_contains_expected_globals(self):
        keys = set(ConfigModel.__annotations__)
        for k in ('config_name', 'running_task', 'script', 'restart',
                  'global_game'):
            assert k in keys, f'缺少全局字段 {k}'

    @pytest.mark.parametrize('task', [
        'FallenSun', 'GoldYoukai', 'TrueOrochi', 'MetaDemon',
        'AbyssShadows', 'RealmRaid', 'Exploration', 'HeroTest',
        'GlobalGame', 'Script', 'Restart',
    ])
    def test_task_present(self, task):
        key = convert_to_underscore(task)
        assert key in ConfigModel.__annotations__, f'缺少 {key}'

    def test_no_duplicate_keys(self):
        keys = list(ConfigModel.__annotations__)
        assert len(keys) == len(set(keys)), '字段名有重复'

    def test_not_a_task_dirs_excluded(self):
        """共享组件目录不是任务, 不应产生配置字段。"""
        keys = set(ConfigModel.__annotations__)
        assert 'component' not in keys
        assert 'general' not in keys
        assert 'Component' in NOT_A_TASK


class TestDiscoveryRobustness:
    def test_discover_returns_dict_of_classes(self):
        found = _discover_config_classes()
        assert isinstance(found, dict)
        assert len(found) >= 56
        for key, cls in found.items():
            assert isinstance(key, str) and key
            assert isinstance(cls, type)

    def test_keys_are_snake_case(self):
        for key in _discover_config_classes():
            assert key == key.lower(), f'{key} 不是小写下划线形式'
            assert ' ' not in key

    def test_basemodel_subclasses_included(self):
        """
        `Script` / `GlobalGame` 继承 `BaseModel` 而非 `ConfigBase` ——
        用 `issubclass(cls, ConfigBase)` 过滤会漏掉它们(踩过)。
        """
        from pydantic import BaseModel
        from tasks.Component.config_base import ConfigBase

        found = _discover_config_classes()
        script = found.get('script')
        assert script is not None, 'script 未被发现'
        assert issubclass(script, BaseModel)
        assert not issubclass(script, ConfigBase), \
            'Script 应当是 BaseModel 子类而非 ConfigBase 子类'

    def test_extra_global_list_is_accurate(self):
        """`EXTRA_GLOBAL` 里列的类必须真的存在于发现结果中。"""
        found = _discover_config_classes()
        for name in EXTRA_GLOBAL:
            assert convert_to_underscore(name) in found, \
                f'EXTRA_GLOBAL 里的 {name} 未被发现'


class TestModelBehavior:
    def test_instantiation(self):
        c = ConfigModel()
        assert isinstance(c, ConfigModel)

    def test_nested_models_are_real(self):
        c = ConfigModel()
        assert type(c.script).__name__ == 'Script'
        assert type(c.global_game).__name__ == 'GlobalGame'
        assert type(c.fallen_sun).__name__ == 'FallenSun'

    def test_type_static_method(self):
        assert ConfigModel.type('script') == 'Script'
        assert ConfigModel.type('fallen_sun') == 'FallenSun'
        assert ConfigModel.type('gold_youkai') == 'GoldYoukai'

    def test_model_dump_covers_all_fields(self):
        """
        `model_dump()` 的键 == 全部字段。

        注意**不要**用 `ConfigModel(**dumped)` 回灌 —— 真实契约是
        `ConfigModel(config_name=...)`, 由 `__init__` 自己读 JSON。
        直接传 kwargs 会落到 `_ConfigModelBase.__init__` 上而报 TypeError
        (这是既有设计, 不是本步引入的)。
        """
        c = ConfigModel()
        dumped = c.model_dump()
        assert set(dumped) == set(ConfigModel.__annotations__)

    def test_load_real_config(self):
        """真实配置能加载, 且字段数完整。"""
        from pathlib import Path
        p = Path.cwd() / 'config' / '恋鸟树.json'
        if not p.exists():
            pytest.skip('缺少真实配置, 跳过')
        c = ConfigModel(config_name='恋鸟树')
        assert set(c.model_dump()) == set(ConfigModel.__annotations__)
        assert type(c.fallen_sun).__name__ == 'FallenSun'

    def test_scheduler_defaults_disabled(self):
        """新任务的 scheduler 默认关闭 —— 自动发现不应意外启用任何任务。"""
        c = ConfigModel()
        assert c.fallen_sun.scheduler.enable is False

    def test_window_fields_present(self):
        """★ S3: 窗口字段是 **`windows` 列表**（单值 `window_*` 已删除）。

        默认**空列表** = 用户没配 -> 回退 `meta.py` 的游戏机制窗口。
        """
        c = ConfigModel()
        sch = c.fallen_sun.scheduler
        assert sch.windows == [], '默认应是空列表（用户没配窗口）'
        # 被替代的字段必须**不存在**
        for dead in ('window_enable', 'window_start', 'window_end',
                     'window_slots'):
            assert not hasattr(sch, dead), f'{dead} 已废弃, 不该还在'
