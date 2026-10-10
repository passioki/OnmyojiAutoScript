# -*- coding: utf-8 -*-
"""T8: `migrate_priority_mode_once()` 的迁移 / 幂等 / `explicit` 阻断测试。

## 为什么必须有（审计 T8）

它是**唯一会改写用户配置**的 S6 路径, 却 **零测试**。而且审计发现:
`config/恋鸟树.json` 的 `priority_mode_explicit` 已被置真 -> 该账号的迁移路径
**被永久关闭** -> **以后再也无法用真实配置发现迁移 bug**。

## ★ 怎么做到"不碰真实配置"

用一个**临时配置名**（`__t8_priority_mode__`）, 在 `config/` 下建文件 ->
测完**删除**。`tests/conftest.py` 的快照只覆盖"会话开始时已存在的文件",
新文件不在快照里 -> 不会被它还原, 所以**必须自己删干净**
（用 `finally`）。
"""
import json
import logging
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

CFG = '__t8_priority_mode__'
P = REPO / 'config' / f'{CFG}.json'


@pytest.fixture()
def tmp_cfg():
    """建一个最小可加载的临时配置, 测完删除。"""
    os.chdir(REPO)                    # ★ `write_json` 用 `Path.cwd()`
    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization']['run_list'] = []
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    try:
        yield P
    finally:
        try:
            P.unlink()
        except OSError:
            pass


def _opt():
    d = json.loads(P.read_text(encoding='utf-8'))
    return d['script']['optimization']


def _write(**kw):
    d = json.loads(P.read_text(encoding='utf-8'))
    d['script']['optimization'].update(kw)
    P.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')


def _load():
    """重新构造 `Config` —— **会触发** `migrate_priority_mode_once()`。"""
    import server  # noqa: F401
    from module.config.config import Config
    return Config(CFG)


class TestMigrationMapping:
    """映射表 4 条分支（`schedule_rule` + `timed_priority` -> `priority_mode`）。"""

    def test_list_rule_becomes_custom(self, tmp_cfg):
        """`schedule_rule=List`（用户**显式**选了"列表自定义"）-> `custom`。"""
        _write(schedule_rule='List', timed_priority='timed',
               priority_mode='custom', priority_mode_explicit=False)
        _load()
        assert _opt()['priority_mode'] == 'custom'
        assert _opt()['priority_mode_explicit'] is True

    def test_timed_priority_list_becomes_fixed_first(self, tmp_cfg):
        """`timed_priority=list`（定时等固定跑完）-> **`fixed_first`**。"""
        _write(schedule_rule='FIFO', timed_priority='list',
               priority_mode='custom', priority_mode_explicit=False)
        _load()
        assert _opt()['priority_mode'] == 'fixed_first', _opt()

    def test_factory_default_becomes_custom(self, tmp_cfg):
        """★★ 出厂默认组合（`Filter` + `timed`）-> **`custom`**（**行为保持**）。

        迁成 `timed_first` 会**悄悄重排**几乎所有既有用户的队列
        （他们抱怨过"拖动次序失效"）。所以保持 `custom`。
        """
        _write(schedule_rule='Filter', timed_priority='timed',
               priority_mode='custom', priority_mode_explicit=False)
        _load()
        assert _opt()['priority_mode'] == 'custom', _opt()

    # ★ T8: "未知规则"这条**不可能发生** —— `schedule_rule` / `timed_priority`
    #   都是 pydantic **枚举字段**, 写非法值在**加载配置时**就 `ValidationError`
    #   （实测: `Input should be 'Filter', 'FIFO', 'Priority' or 'List'`）。
    #   所以迁移代码里那个 `else: new = CUSTOM` 分支**只能**被出厂默认组合
    #   走到 —— 已由 `test_factory_default_becomes_custom` 覆盖。
    #   ★ 我第一版写了这条测试 -> **必然失败**（枚举校验在迁移之前）。


class TestExplicitBlocks:
    """★★ `priority_mode_explicit=True` 必须**永久阻止**迁移 ★★"""

    def test_explicit_true_is_never_overwritten(self, tmp_cfg):
        """用户在新界面选了 `timed_first`, 旧字段却是 `Filter`+`list`
        （按映射表会改成 `fixed_first`）—— **不得**被改。"""
        _write(schedule_rule='Filter', timed_priority='list',
               priority_mode='timed_first', priority_mode_explicit=True)
        _load()
        assert _opt()['priority_mode'] == 'timed_first', (
            f'explicit=True 时迁移仍改写了用户选择: {_opt()}')

    def test_explicit_true_keeps_fixed_first(self, tmp_cfg):
        _write(schedule_rule='Filter', timed_priority='timed',
               priority_mode='fixed_first', priority_mode_explicit=True)
        _load()
        assert _opt()['priority_mode'] == 'fixed_first'


class TestIdempotency:
    def test_second_load_changes_nothing(self, tmp_cfg):
        """★ 幂等: 连加载两次, 结果必须一样。"""
        _write(schedule_rule='FIFO', timed_priority='list',
               priority_mode='custom', priority_mode_explicit=False)
        _load()
        first = dict(_opt())
        _load()
        second = dict(_opt())
        assert first.get('priority_mode') == second.get('priority_mode')
        assert (first.get('priority_mode_explicit')
                == second.get('priority_mode_explicit'))

    def test_migration_sets_explicit_so_it_runs_once(self, tmp_cfg):
        """★ 迁移后 `explicit` 必须为 True —— 这是"只跑一次"的**唯一**保证。

        ⚠ 不能用 `priority_mode` 的**默认值**当哨兵: 它**有默认值**
        （`custom`）, "用户没设过"与"用户就选了默认值"**分辨不出来**。
        """
        _write(schedule_rule='List', timed_priority='timed',
               priority_mode='custom', priority_mode_explicit=False)
        _load()
        assert _opt()['priority_mode_explicit'] is True

    def test_already_explicit_untouched_by_idempotency(self, tmp_cfg):
        """已经 explicit=True 的, 再加载也不动。"""
        _write(schedule_rule='List', timed_priority='timed',
               priority_mode='fixed_first', priority_mode_explicit=True)
        _load(); _load()
        assert _opt()['priority_mode'] == 'fixed_first'
        assert _opt()['priority_mode_explicit'] is True
