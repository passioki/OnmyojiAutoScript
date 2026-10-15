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

from module.config import task_catalog as TC
from module.config.config_model import (
    EXTRA_GLOBAL, NOT_A_TASK, ConfigModel, _discover_config_classes)
from module.config.utils import convert_to_underscore

# ★★★ [10-15] B 方案（用户裁定"好的"）用的两个**结构性**集合 ★★★
#
# ★ 这两个集合**不随任务增减**（所以钉住它们是合理的，不产生返工）：
#   ① `KNOWN_GLOBAL_SCALARS` = `ConfigModel` 里**手写的全局字段**
#      （★ [10-15] 探针实测：`keys - task_keys` 的 7 个里，除
#       `EXTRA_GLOBAL`（Script/GlobalGame）之外的 5 个）
#   ② ★ `KNOWN_TASKS_WITHOUT_FIELD` = **有 `meta.py` 但没有配置类**的已知例外
#      （★ [10-15] 探针实测：`goto_main` —— `GotoMain` 是**纯控制节点**，
#        没有 `tasks/GotoMain/config.py`）★ 这正是"不许猜、必须探针取证"的收获：
#        若照直觉写 `task_keys ⊆ keys`，这条断言**当场就会红**。
KNOWN_GLOBAL_SCALARS = {
    'config_name', 'running_task', 'running_entry_id',
    'force_next_entry_id', 'orochi_moans',
}
KNOWN_TASKS_WITHOUT_FIELD = {'goto_main'}


class TestDiscoveryCompleteness:
    def test_fields_match_task_nodes(self):
        """★★★ 每个任务节点都必须有字段（已知例外除外）；任务之外只许有已知全局 ★★★

        ## ★ [10-15] B 方案（用户裁定"好的"）

        原名 `test_field_count_matches_handwritten`，里面写死
        `len(ConfigModel.__annotations__) == 62` —— ★ 而它的 docstring 自己
        就是一部"返工史"：`58 → 59 → 60 → 61 → 62`，★ 每新增一个任务/字段
        都要回来改（`PENDING-LEDGER.md` §D.9）。

        ★★ 数字没有信息量。真正要守的是**两条方向相反的完备性**：

        | 方向 | 若违反 | 后果 |
        |---|---|---|
        | ① 任务 → 字段（除已知例外）| 少了字段 | ★ **静默**：该任务的配置读不出来 |
        | ② 字段 → 任务 ∪ 已知全局 | 多出字段 | ★ 手写脏字段 / 命名漂移 |

        ★ 收益 = 新增任务 **零改动**；两条完备性仍然照抓。
        """
        keys = set(ConfigModel.__annotations__)
        task_keys = {convert_to_underscore(t) for t in TC.all_tasks()}
        known_globals = ({convert_to_underscore(n) for n in EXTRA_GLOBAL}
                         | KNOWN_GLOBAL_SCALARS)

        # ① 任务 → 字段（★ 除已知"纯控制节点"例外）
        missing = sorted(task_keys - keys - KNOWN_TASKS_WITHOUT_FIELD)
        assert not missing, (
            f'★ 这些任务节点在 ConfigModel 里没有字段（新增任务漏注册）: {missing}')
        # ② 字段 → 任务 ∪ 已知全局（★ 反向：防手写脏字段）
        extra = keys - task_keys
        assert extra == known_globals, (
            f'★ ConfigModel 的非任务字段与已知集合不符: '
            f'多 {sorted(extra - known_globals)} · '
            f'少 {sorted(known_globals - extra)}')
        # ③ 已知例外自身不许腐烂（那些任务必须真的存在）
        stale = sorted(KNOWN_TASKS_WITHOUT_FIELD - task_keys)
        assert not stale, (
            f'★ 这个"无字段例外"清单已腐烂（任务不存在了）: {stale}')

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
        # ★ [10-15] B 方案：**不再写死 `>= 56`** ⇒ 改为"发现到的类必须覆盖
        #   每个有配置类的任务"（★ 已知的"无配置类"例外除外）
        task_keys = {convert_to_underscore(t) for t in TC.all_tasks()}
        missing = sorted(task_keys - set(found) - KNOWN_TASKS_WITHOUT_FIELD)
        assert not missing, f'自动发现漏了这些任务的配置类: {missing}'
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
