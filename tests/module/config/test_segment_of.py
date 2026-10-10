# -*- coding: utf-8 -*-
"""`Config._segment_of()` —— 任务属于哪个**优先级段**(`'timed'` / `'fixed'`)。

## 为什么单独留这个文件

原来这些断言住在 `test_priority_mode.py`, 而那个文件**整篇**测的是
「调度优先级三模式」（`PriorityMode` 枚举 / `Optimization.priority_mode` /
`_order_by_priority_mode()`）—— 用户裁定把那一整簇删掉了, 所以文件已删除。

★ 但 `_segment_of()` **还在生产里活着**, 且删掉三模式之后**只剩两个用途**:

| 用途 | 在哪 |
|---|---|
| `/overview` 的 `priority_group`（界面渲染类别色条/标签）| `module/server/schema_router.py` |
| `Config.sort_run_list(by=...)` 的**一次性排序**依据 | `module/config/config.py` |

⚠ 它**不再**用于"限制拖动范围" —— 拖动永远自由。

★ 所以这几条断言**仍然有效**, 必须保留（连带删掉它们才是真的删多了）。
"""
import logging
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)


@pytest.fixture()
def cfg():
    """★ 用**临时配置名** —— 不碰用户的实时配置。

    `_segment_of()` 只读 `task_catalog`, 与配置内容无关, 所以一份
    空 `run_list` 的模板配置就够; 但**仍然不碰真实配置文件**
    （这是本项目踩过多次的事故形态, 见 `tests/conftest.py`）。
    """
    import json
    import server  # noqa: F401
    from module.config.config import Config

    os.chdir(REPO)
    name = '__segment_of__'
    p = REPO / 'config' / f'{name}.json'
    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization']['run_list'] = []
    p.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    try:
        yield Config(name)
    finally:
        try:
            p.unlink()
        except OSError:
            pass


class TestSegmentOf:
    def test_segment_of_known_tasks(self, cfg):
        assert cfg._segment_of('MetaDemon') == 'timed', '限时活动算 timed'
        assert cfg._segment_of('Nian') == 'timed', '年兽算 timed'
        assert cfg._segment_of('TrueOrochi') == 'timed', '真蛇算 timed'
        assert cfg._segment_of('Orochi') == 'fixed'
        assert cfg._segment_of('RealmRaid') == 'fixed', '结界突破算 fixed'
        assert cfg._segment_of('Exploration') == 'fixed'

    def test_unknown_task_falls_back_to_fixed(self, cfg):
        """★ 未知任务名不崩, 落到 `'fixed'`（保守默认）。

        同一条判据被 `sort_run_list()` 用来决定"排前面/排后面"——
        它**不能抛异常**, 否则一次排序会把整个 `run_list` 搞丢。
        """
        assert cfg._segment_of('NotARealTask') == 'fixed'

    def test_only_two_segments_exist(self, cfg):
        """★★ 用户裁定后**只有两个段** ★★

        旧的第三种东西是「模式」（`PriorityMode`）—— 那个概念**已删除**:
        执行顺序 = `run_list` 的顺序本身, 段名只是**显示用**的派生值。
        """
        segs = {cfg._segment_of(t) for t in
                ('MetaDemon', 'Nian', 'Orochi', 'RealmRaid', 'Exploration')}
        assert segs == {'timed', 'fixed'}, segs
