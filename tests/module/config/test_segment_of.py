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
        """★ 已知任务的段归属。

        ## ★★★ 期望值按 **`period` 派生**，不写死 ★★★

        用户裁定（口径重定）:
        > "按照**有没有设置周期记忆**, `period` 不限时是**固定**（固定任务
        >  改名为**临时任务**）, 其他是**定时**（定时任务名字改为**周期任务**）"

        ★ 所以 `Orochi`（`period=DAILY`）**是周期任务**，不再是 fixed ——
          这正是用户核对 54 个任务后指出的"分类不对"。
        ★ 断言**从 `task_catalog` 读 `period` 来算期望值**，而不是写死
          `'timed'`/`'fixed'`：这样"分类规则"与"断言"不会各说各话
          （写死的话，任务一改 period 测试就假失败，而实现其实是对的）。
        """
        from module.config import task_catalog as TC
        from module.config.resource import Period

        def want(task: str) -> str:
            spec = TC.get_spec(task)
            assert spec is not None, f'{task} 不在 catalog'
            # 与 TaskSpec.priority_group 同一判据: 有周期记忆 = timed
            return 'fixed' if spec.period_effective == Period.NONE else 'timed'

        for task in ('MetaDemon', 'Nian', 'TrueOrochi', 'Orochi',
                     'RealmRaid', 'Exploration', 'AbyssShadows',
                     'BondlingFairyland', 'DemonEncounter'):
            assert cfg._segment_of(task) == want(task), (
                f'★ {task} 的段归属与 `period` 不符 '
                f'(period={TC.get_spec(task).period_effective})')

    def test_judge_is_period_not_category(self, cfg):
        """★★ 判据必须是 **`period`**，不是 `category` ★★

        ★ 这是本轮改动的**核心**：旧实现读 `category_effective`，
          于是"有硬性开放时段却叫固定"（逢魔/道馆/狩猎战）与
          "随时能跑却叫定时"两类矛盾同时存在。
        """
        from module.config import task_catalog as TC
        from module.config.resource import Period

        for name in TC.all_specs():
            spec = TC.get_spec(name)
            expect = ('fixed' if spec.period_effective == Period.NONE
                      else 'timed')
            assert spec.priority_group == expect, (
                f'★ {name}: period={spec.period_effective} 但段='
                f'{spec.priority_group!r} —— 判据必须只看 period')

    def test_orenchi_is_period_task_now(self, cfg):
        """★ 回归守卫: `Orochi`（period=DAILY）必须是**周期任务**。

        ★ 它原来被算成 `fixed`（因为 `category=FIXED`）—— 用户核对 54 个
          任务时指出"分类不对"。这条**专门钉住那个修正**。
        """
        from module.config import task_catalog as TC
        from module.config.resource import Period
        assert TC.get_spec('Orochi').period_effective == Period.DAILY
        assert cfg._segment_of('Orochi') == 'timed', (
            '★ Orochi 有 daily 周期 -> 应是周期任务; '
            '若回到 fixed 说明判据又去看 category 了')

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

        ★ 界面名: `'timed'` = **周期任务**, `'fixed'` = **临时任务**。
        """
        segs = {cfg._segment_of(t) for t in
                ('MetaDemon', 'Nian', 'Orochi', 'RealmRaid', 'Exploration')}
        assert segs == {'timed', 'fixed'}, segs

    def test_labels_are_renamed(self):
        """★★ 界面名的改名必须生效（用户裁定）★★

        > "固定任务改名为**临时任务**"、"定时任务名字改为**周期任务**"

        ★ 旧名"定时/固定"确实容易混（"定时"会被读成"必须在某个点跑",
          而判据其实是"**有没有周期记忆**"）。
        """
        from module.config import task_catalog as TC
        assert TC.PRIORITY_GROUP_LABEL['timed'] == '周期'
        assert TC.PRIORITY_GROUP_LABEL['fixed'] == '临时'
