# -*- coding: utf-8 -*-
"""★★★ 分类判据 = 配置里的 `scheduler.period`（用户裁定, 本轮核心）★★★

## 用户原话

> "**窗口必须在选了周期后才能设置。这样子判断依据就可以按有没有周期来判断**"
> "周期是 period 啊！你联系下上下文行不, 是**每天、每周每月、不限**那个"

## 这条判据回答什么

| `scheduler.period` | 分类 | 界面名 |
|---|---|---|
| `daily` / `weekly` / `monthly` | `'timed'` | ★ **周期任务** |
| `none`（不限）| `'fixed'` | ★ **临时任务** |

## ★★ 为什么必须钉住"读配置"而不是读 `meta.py` ★★

**实机验收反馈**: 用户"在前端改了 `period`, 队列标签不动"。

**根因**: 标签原来读 `TaskSpec.priority_group` → `meta.py` 的 `TaskSpec.period`
（**写死源码、前端改不了**）。而用户改的是**配置**里的 `scheduler.period`
（`/args` 的 scheduler 组那个 enum 下拉）。
★ **同名、不同字段、不同来源** -> 永不联动。

★ 修法: 判据改读 `Config.task_period()`（**配置优先**, `meta.py` 降级为
  "出厂默认值"）。本文件**专门钉住这个联动**。
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

CFG = '__period_cfg__'
P = REPO / 'config' / f'{CFG}.json'


def _mk(run_list=None, period_overrides=None):
    """造临时配置; `period_overrides` = {任务名: 'daily'|'weekly'|'none'}。"""
    import server  # noqa: F401
    from module.config.config import Config
    from module.config.config_model import convert_to_underscore

    os.chdir(REPO)
    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization']['run_list'] = run_list or []
    for name, per in (period_overrides or {}).items():
        key = convert_to_underscore(name)
        node = tmpl.get(key)
        if isinstance(node, dict) and isinstance(node.get('scheduler'), dict):
            node['scheduler']['period'] = per
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    return Config(CFG)


@pytest.fixture()
def cfg():
    os.chdir(REPO)
    c = _mk()
    try:
        yield c
    finally:
        try:
            P.unlink()
        except OSError:
            pass


class TestJudgeReadsConfig:
    """★★ 核心: 判据读**配置**, 所以"改配置 = 立刻联动"。"""

    @staticmethod
    def _after_backfill(period_overrides):
        """造配置, 并**先把一次性回填标记置上** —— 模拟"已经跑过迁移"。

        ⚠ 为什么需要这一步: 回填只在**首次**跑（见 `period_backfilled`
          标记）。若在测试里让回填生效, 那么"把 period 设成 `none`"会被
          回填成出厂值 —— 那是**设计行为**, 不是 bug。
          本类测的是"**回填之后**判据是否读配置", 所以先置标记。

        ★ 另有 `TestBackfillMigration` 专门测回填本身。
        """
        import server  # noqa: F401
        from module.config.config import Config
        from module.config.config_model import convert_to_underscore

        os.chdir(REPO)
        tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
            encoding='utf-8'))
        tmpl['script']['optimization']['run_list'] = []
        # ★ 预置一次性标记 -> 回填不再干预
        tmpl['script']['optimization']['period_backfilled'] = True
        for name, per in period_overrides.items():
            key = convert_to_underscore(name)
            node = tmpl.get(key)
            if isinstance(node, dict) and isinstance(node.get('scheduler'),
                                                     dict):
                node['scheduler']['period'] = per
        P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
        return Config(CFG)

    def test_period_none_is_temporary(self, cfg):
        """`period=none` -> 临时任务（`fixed`）。"""
        c = self._after_backfill({'Orochi': 'none'})
        assert c.task_period('Orochi') == 'none'
        assert c.priority_group_of('Orochi') == 'fixed'

    def test_period_daily_is_cycle(self, cfg):
        """`period=daily` -> 周期任务（`timed`）。"""
        c = self._after_backfill({'AreaBoss': 'daily'})
        assert c.task_period('AreaBoss') == 'daily'
        assert c.priority_group_of('AreaBoss') == 'timed'

    def test_period_weekly_is_cycle(self, cfg):
        c = self._after_backfill({'Exploration': 'weekly'})
        assert c.priority_group_of('Exploration') == 'timed'

    def test_period_monthly_is_cycle(self, cfg):
        c = self._after_backfill({'Exploration': 'monthly'})
        assert c.priority_group_of('Exploration') == 'timed'

    def test_change_period_flips_classification(self, cfg):
        """★★ 这条就是用户报的现象: **改 period, 分类必须跟着变**。"""
        c1 = self._after_backfill({'Orochi': 'none'})
        assert c1.priority_group_of('Orochi') == 'fixed', 'none 应是临时'
        c2 = self._after_backfill({'Orochi': 'daily'})
        assert c2.priority_group_of('Orochi') == 'timed', (
            '★ 把 period 改成 daily 后**必须**变成周期任务 —— '
            '若仍是 fixed, 说明判据又回去读 meta.py 了（用户报的 bug）')

    def test_normalization_variants(self, cfg):
        """任务名的三种写法都要认（大驼峰 / 下划线）。"""
        c = self._after_backfill({'BondlingFairyland': 'daily'})
        for name in ('BondlingFairyland', 'bondling_fairyland'):
            assert c.priority_group_of(name) == 'timed', name

    def test_judge_does_not_read_meta_priority_group(self):
        """★ 反向守卫: 源码里不许再拿 `meta.priority_group` 当判据。"""
        from _srcutil import code_only
        for rel in ('module/config/config.py',
                    'module/server/schema_router.py'):
            src = code_only(REPO / rel)
            assert 'meta.priority_group' not in src, (
                f'★ {rel} 又在读 `meta.priority_group` —— 那是 meta.py 的'
                f'写死值, 前端改不了 -> 用户"改了周期标签不动"的根因')


class TestOverviewExposesPeriod:
    """★ `/overview` 必须同时给出 `period` 与**同源**的 `priority_group`。"""

    @pytest.fixture(scope='module')
    def live(self):
        os.chdir(REPO)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_fields_present(self, live):
        from module.server import schema_router as SR
        rows = SR.build_overview('恋鸟树').get('tasks') or []
        assert rows
        for r in rows:
            assert 'period' in r, f'{r["command"]} 缺 period'
            assert 'priority_group' in r
            assert 'priority_group_label' in r

    def test_group_matches_period(self, live):
        """★★ `priority_group` 必须与 `period` **同源**（一条判据）。"""
        from module.server import schema_router as SR
        rows = SR.build_overview('恋鸟树').get('tasks') or []
        for r in rows:
            want = 'fixed' if r['period'] == 'none' else 'timed'
            assert r['priority_group'] == want, (
                f'★ {r["command"]}: period={r["period"]!r} 但 '
                f'priority_group={r["priority_group"]!r} —— 必须由 period 推出')

    def test_label_matches_group(self, live):
        from module.config import task_catalog as TC
        from module.server import schema_router as SR
        rows = SR.build_overview('恋鸟树').get('tasks') or []
        for r in rows:
            assert r['priority_group_label'] == \
                TC.PRIORITY_GROUP_LABEL[r['priority_group']], r['command']


class TestBackfillMigration:
    """★ 一次性回填（用户确认要做）: `scheduler.period` 按出厂默认值补上。"""

    def test_backfill_then_idempotent(self):
        """★ 第一次回填改了东西; 第二次**幂等**返回 False。

        ## ⚠ 为什么必须自己构造前提（我踩过）

        `config/template.json` 已经被**修正过**（38 个任务的 `period` 已按
        出厂值写好、`period_backfilled` 已是 `True`）—— 那是**正确**的仓库状态。

        ★ 所以本测试**不能**假设模板是"回填前"的旧状态, 否则它断言的是
          "仓库模板还是旧的" —— 一旦模板被修正, 测试就**假失败**
          （实测: 报 `Orochi` 得到 `none` 而非 `daily`）。

        ★ 修法: 显式**清掉标记** + 把 `period` 打回 `none`, 自己造出
          "老配置"的样子, 再验证回填。
        """
        import server  # noqa: F401
        from module.config.config import Config, task_period_default
        from module.config.config_model import convert_to_underscore

        os.chdir(REPO)
        tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
            encoding='utf-8'))
        before = {n: task_period_default(n) for n in
                  ('Orochi', 'DemonRetreat')}

        # ① ★ 显式造出"回填前"的状态:
        #    标记清掉 + 目标任务的 period 打回 none（不依赖仓库模板现状）
        tmpl['script']['optimization']['period_backfilled'] = False
        for name in ('Orochi', 'DemonRetreat'):
            key = convert_to_underscore(name)
            node = tmpl.get(key)
            assert isinstance(node, dict), f'{key} 不在模板里'
            node['scheduler']['period'] = 'none'
        P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')

        try:
            # ② ★ 核心断言: **构造 `Config` 就会回填**（这就是生产路径 ——
            #    `migrate_task_period_once()` 在 `__init__` 里被调用）
            #
            #    ⚠ 不要"构造后再把状态按回去再手动调" —— `Config` 构造时会
            #      `save()`, 内存与磁盘会不一致, 那样测出来的是**测试脚手架**
            #      的行为, 不是生产行为（我踩过两次）。
            c1 = Config(CFG)
            got = {n: c1.task_period(n) for n in before}
            assert got['Orochi'] == before['Orochi'], (
                f'★ 构造后 Orochi 应被回填成 {before["Orochi"]!r}, '
                f'实际 {got["Orochi"]!r}')
            assert got['DemonRetreat'] == before['DemonRetreat']

            # ③ 幂等: 标记已置上 -> 再调**无改动**
            assert c1.migrate_task_period_once() is False, (
                '★ 第二次回填应**无改动**（幂等）')
            # ④ 且磁盘上确实是回填后的值
            disk = json.loads(P.read_text(encoding='utf-8'))
            assert disk[convert_to_underscore('Orochi')]['scheduler'][
                'period'] == before['Orochi'], '★ 回填没落盘'
        finally:
            try:
                P.unlink()
            except OSError:
                pass

    def test_user_choice_is_respected(self):
        """★ 用户明确选的 `daily`/`weekly`/`monthly` **不许**被回填覆盖。"""
        import server  # noqa: F401
        from module.config.config import Config
        from module.config.config_model import convert_to_underscore

        os.chdir(REPO)
        tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
            encoding='utf-8'))
        # 故意把 AreaBoss（出厂 none）设成 weekly -> 是"用户的选择"
        key = convert_to_underscore('AreaBoss')
        tmpl[key]['scheduler']['period'] = 'weekly'
        P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
        try:
            c = Config(CFG)
            c.migrate_task_period_once()
            assert Config(CFG).task_period('AreaBoss') == 'weekly', (
                '★ 用户设的 weekly 被回填覆盖了 —— 那会静默改掉用户的选择')
        finally:
            try:
                P.unlink()
            except OSError:
                pass

    def test_none_survives_after_backfill(self):
        """★★★ 关键回归守卫: 回填**跑过之后**, 用户设的「不限」必须保住 ★★★

        ## 这条钉的是一个**真实踩到的坑**

        `Config()` **每个 HTTP 请求都新建**, 而回填在 `__init__` 里调用。
        若只看"当前值是 `none` 就回填", 那么用户把某任务改成「不限」后,
        **下一次请求就被改回出厂值** —— ★ **用户完全改不动「不限」**。

        实测复现（修之前）:
        ```
        写入 period='none' -> Config(cfg) -> task_period() 返回 'daily'
                                          -> 磁盘也被改回 'daily'
        ```

        ★ 修法: `Optimization.period_backfilled` **一次性标记** ——
          回填只做第一次, 之后永不再碰。
        """
        import server  # noqa: F401
        from module.config.config import Config

        os.chdir(REPO)
        tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
            encoding='utf-8'))
        P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
        try:
            # ① 首次加载 -> 回填 + 置标记
            Config(CFG).migrate_task_period_once()
            # ② 模拟"用户在前端设成不限"
            d = json.loads(P.read_text(encoding='utf-8'))
            d['orochi']['scheduler']['period'] = 'none'
            P.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
            # ③ ★ 下一个请求（重新构造 Config）—— 值必须保住
            c = Config(CFG)
            assert c.task_period('Orochi') == 'none', (
                '★ 用户设的「不限」被迁移改回出厂值了 —— '
                '那样用户永远改不动"不限"')
            assert json.loads(P.read_text(encoding='utf-8'))['orochi'][
                'scheduler']['period'] == 'none', (
                '★ 磁盘上的值也被改回去了')
            assert bool(getattr(c.model.script.optimization,
                                'period_backfilled', False)) is True, (
                '★ 一次性标记没置上 -> 每次启动都会重跑回填')
        finally:
            try:
                P.unlink()
            except OSError:
                pass

    def test_marker_makes_second_run_noop(self):
        """★ 标记置上后, 再改任何东西都不许被回填干预。"""
        import server  # noqa: F401
        from module.config.config import Config

        os.chdir(REPO)
        tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
            encoding='utf-8'))
        tmpl['script']['optimization']['period_backfilled'] = True
        tmpl['orochi']['scheduler']['period'] = 'none'
        tmpl['area_boss']['scheduler']['period'] = 'none'
        P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
        try:
            c = Config(CFG)
            assert c.migrate_task_period_once() is False, '有标记时不该回填'
            assert c.task_period('Orochi') == 'none'
            assert c.task_period('AreaBoss') == 'none'
        finally:
            try:
                P.unlink()
            except OSError:
                pass

    def test_writes_enum_not_str(self):
        """★ 回填必须写**枚举对象**（写裸字符串会触发 pydantic 警告）。"""
        from _srcutil import code_of
        body = code_of(REPO / 'module/config/config.py',
                       'def migrate_task_period_once')
        assert 'TaskPeriod(' in body, (
            '★ 必须用 `TaskPeriod(want)` 包一层 —— 本项目已踩过'
            '“传字符串给枚举字段”的坑（pydantic 会报 '
            'Expected enum but got str）')
