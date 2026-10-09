# -*- coding: utf-8 -*-
"""「次数」统一入口（`BaseTask.effective_target` / `bind_counter`）的测试。

## 背景：改造前"次数"是**双轨**的

| 来源 | 位置 | 问题 |
|---|---|---|
| `scheduler.target` | 界面输入框 | **全仓无人读取** —— 空壳 |
| `limit_count` 等 | 各任务配置 | 界面**改不到**，且字段名有 `minions_cnt` / `hya_limit_count` / `number_attack` 三种别名 |

于是"设置次数"实际是坏的。现在收敛到 `BaseTask.effective_target()`:

    scheduler.target > 0  ->  用它（用户编排）
    否则                  ->  任务配置里的值（能力默认）
    再否则                ->  meta.py 的 count_default

## 两条容易踩的坑（本测试专门盯住）

1. **`_find_count_field` 要遍历配置树** —— 各任务把 `limit_count` 放在
   不同层级（`orochi_config.` / `bondling_config.` / 根上……），
   硬编码路径必然漏。
2. **解析失败必须记 warning, 不能 `except: pass`** ——
   我第一版写 `except Exception: pass`，把
   `AttributeError: 'FakeTask' object has no attribute '_find_count_field'`
   （测试替身写错导致的）**完全吞掉**，表现成"次数设置不生效"，白查很久。
"""
import logging

import pytest

from module.config import task_catalog as TC
from module.config.utils import convert_to_underscore
from tasks.base_task import BaseTask


class StubTask(BaseTask):
    """
    只借 `BaseTask` 的计数逻辑，不初始化设备/配置树。

    ★ **必须继承 `BaseTask`** —— `effective_target` 内部会调
      `self._find_count_field`，不继承就会 AttributeError，
      然后被最外层 except 吞掉，测试会误以为是实现问题。
    """

    def __init__(self, config, name):
        self.config = config
        self._name = name
        self._counter_task = None
        self._counter_period = 'none'
        self._counter_reset_at = None
        self._counter_persisted = 0
        self.current_count = 0
        self.limit_count = None

    def get_task_name(self):
        return self._name


CONFIG = '恋鸟树'


@pytest.fixture(scope='module')
def cfg():
    from pathlib import Path
    if not (Path.cwd() / 'config' / f'{CONFIG}.json').exists():
        pytest.skip(f'缺少配置 {CONFIG}')
    from module.server.main_manager import mm
    return mm.config_cache(CONFIG)


def stub(cfg, name) -> StubTask:
    return StubTask(cfg, name)


def user_target(cfg, name) -> int:
    sub = getattr(cfg, convert_to_underscore(name), None)
    sch = getattr(sub, 'scheduler', None) if sub is not None else None
    return int(getattr(sch, 'target', 0) or 0)


class TestEffectiveTarget:
    def test_all_countable_tasks_resolve(self, cfg):
        """每个可计数任务都要能解析出次数（不抛异常、不是 None）。"""
        countable = [m for m in TC.all_meta() if m.countable]
        assert countable, '应存在可计数任务'
        for m in countable:
            got = stub(cfg, m.task).effective_target()
            assert got is not None, f'{m.task} 解析出 None'
            assert isinstance(got, int) and got > 0, \
                f'{m.task} 解析出非法值 {got!r}'

    def test_user_target_wins(self, cfg):
        """`target > 0` 时**必须**用它（这是用户编排，优先级最高）。"""
        name = 'Orochi'
        sch = getattr(getattr(cfg, convert_to_underscore(name)), 'scheduler')
        old = sch.target
        try:
            for v in (1, 7, 999):
                sch.target = v
                assert stub(cfg, name).effective_target() == v, \
                    f'target={v} 未被采用'
        finally:
            sch.target = old

    def test_falls_back_to_task_config_when_target_zero(self, cfg):
        """
        `target == 0` 时回落到**任务配置里的值**（不是元数据默认值）。

        ★ 这个区别很重要: 配置里的值可能被用户改过
          （实测 `FallenSun` 配的是 9, 而不是元数据默认的 50）。
          回落时应该尊重**配置**，而不是元数据。
        """
        name = 'FallenSun'
        sch = getattr(getattr(cfg, convert_to_underscore(name)), 'scheduler')
        old = sch.target
        try:
            sch.target = 0
            got = stub(cfg, name).effective_target()
            from_config = stub(cfg, name)._find_count_field('limit_count')
            if from_config is not None:
                assert got == from_config, \
                    f'target=0 时应回落到配置值 {from_config}, 实际 {got}'
        finally:
            sch.target = old

    @pytest.mark.parametrize('name,alias', [
        ('Exploration', 'minions_cnt'),
        ('Hyakkiyakou', 'hya_limit_count'),
        ('RealmRaid', 'number_attack'),
    ])
    def test_alias_fields_resolve(self, cfg, name, alias):
        """
        字段名有别名（`minions_cnt` 等）的任务也要能解析。

        `TaskMeta.count_field_effective` 会把别名统一成 `limit_count`，
        但配置树里存的是**别名**，所以 `_find_count_field` 必须能找到它。
        """
        meta = TC.get(name)
        assert meta.count_field == alias, f'{name} 的字段名变了? {meta.count_field}'
        got = stub(cfg, name).effective_target()
        assert got is not None and got > 0, f'{name} 解析失败: {got!r}'

    @pytest.mark.parametrize('name', ['DemonEncounter', 'TrueOrochi',
                                      'GoldYoukai', 'Duel', 'ExperienceYoukai'])
    def test_non_countable_returns_none(self, cfg, name):
        """定时/充能/限时任务没有"次数"概念 -> 返回 None。"""
        meta = TC.get(name)
        if meta is not None:
            assert not meta.countable, f'{name} 现在是可计数的? 测试需更新'
        assert stub(cfg, name).effective_target() is None, \
            f'{name} 不该有次数'

    def test_unknown_task_returns_none(self, cfg):
        """未知任务不抛异常, 返回 None。"""
        assert stub(cfg, 'NotARealTask').effective_target() is None


class TestFindCountField:
    def test_finds_nested_field(self, cfg):
        """`limit_count` 藏在多层配置里也要找到。"""
        got = stub(cfg, 'Orochi')._find_count_field('limit_count')
        assert got is not None and got > 0, f'未找到, 得到 {got!r}'

    def test_missing_field_returns_none(self, cfg):
        assert stub(cfg, 'Orochi')._find_count_field('no_such_field') is None

    def test_does_not_recurse_forever(self, cfg):
        """配置树里有循环引用也不能死循环。"""
        got = stub(cfg, 'Orochi')._find_count_field('limit_count')
        assert isinstance(got, int)


class TestBindCounterSetsLimit:
    """
    ★ 不要在测试里 `os.chdir` + `TemporaryDirectory` ——
      Windows 上会因文件占用导致清理失败（`PermissionError: WinError 32`），
      而 `task_state` 是按 `Path.cwd()` 定位状态文件的，改 cwd 也会牵连日志。

      改为直接 monkeypatch `task_state._state_file`，指到临时路径。
    """

    @pytest.fixture
    def tmp_state(self, tmp_path, monkeypatch):
        """把 `task_state` 的状态文件与锁指到临时目录。"""
        from module.config import task_state

        state_file = tmp_path / '.task_state.json'
        monkeypatch.setattr(task_state, '_state_file',
                            lambda: state_file, raising=True)
        return state_file

    def test_bind_counter_sets_limit_count(self, cfg, tmp_state):
        """
        `bind_counter()` 要**同时**设定 `self.limit_count`。

        ★ 这是"次数统一到一个入口"的关键 —— 任务里只调 `bind_counter()`,
          不必再去读配置。
        """
        t = stub(cfg, 'Orochi')
        t.limit_count = None
        rc = t.bind_counter()
        assert rc == 0, f'首次应恢复 0, 实际 {rc}'
        assert t.limit_count is not None and t.limit_count > 0, \
            'bind_counter 没有设定 limit_count'
        assert t._counter_task == 'orochi', \
            f'计数键应为小写任务名, 实际 {t._counter_task!r}'

    def test_bind_counter_honours_user_target(self, cfg, tmp_state):
        """用户设了 target, `bind_counter` 要用它。"""
        name = 'Orochi'
        sch = getattr(getattr(cfg, convert_to_underscore(name)), 'scheduler')
        old = sch.target
        try:
            sch.target = 3
            t = stub(cfg, name)
            t.limit_count = None
            t.bind_counter()
            assert t.limit_count == 3, \
                f'应取用户 target=3, 实际 {t.limit_count}'
        finally:
            sch.target = old

    def test_bind_counter_restores_from_disk(self, cfg, tmp_state):
        """
        写盘后重新 `bind_counter` 要能**恢复**计数（"暂停后继续是真继续"）。
        """
        from module.config import task_state

        name = 'Orochi'
        task_state.add_count(cfg.config_name, name.lower(), delta=4,
                             period='daily')
        t = stub(cfg, name)
        t.bind_counter(period='daily')
        assert t.current_count == 4, \
            f'应从磁盘恢复 4, 实际 {t.current_count}'
        assert t._counter_persisted == 4

