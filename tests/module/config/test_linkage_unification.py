# -*- coding: utf-8 -*-
"""★★★ 「联动统一」守卫：周期/临时 与 入队/移出 必须**同源** ★★★

## 用户裁定（本轮）

> "**显示周期的不应该移除队列后回退到添加任务的池子里而是直接停用**,
>  这说明目前的**[联动]还不完善**。"
> "当前正在运行的**任务无法被取消**"
> 取消语义 = **(a)**「暂停 + 移出队列」

## 实测到的真漂移（本文件钉住它）

`TaskSpec.auto_queue` 在 54 个 `meta.py` 里显式声明，而
`auto_queue_effective` 的推导依据是 **`category`** —— ★ 那是**被废弃的判据**
（分类已改为按 `scheduler.period`）。于是两者**必然漂移**，实测 4 个:

| 任务 | `period` | 界面分类 | 旧 `auto_queue` | 后果 |
|---|---|---|---|---|
| `OtherWorldTwilight` | daily | **周期** | `False` | 界面说周期, 却不自动入队 |
| `RyouToppa` | daily | **周期** | `False` | 同上 |
| `SixRealms` | daily | **周期** | `False` | 同上 |
| `TalismanPass` | none | **临时** | `True` | 界面说临时, 却自动入队 |

★ 这就是"**添加任务里还显示着固定任务标签**"+"**联动不完善**"的根因。
"""
import asyncio
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

from _srcutil import code_of  # noqa: E402

CFG = '__linkage_unify__'
P = REPO / 'config' / f'{CFG}.json'


def _mk(periods):
    """造临时配置; `periods` = {任务名: 'daily'|'weekly'|'none'}。"""
    os.chdir(REPO)
    import server  # noqa: F401
    from module.config.config import Config
    from module.config.config_model import convert_to_underscore

    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization']['period_backfilled'] = True
    tmpl['script']['optimization']['run_list'] = []
    for name, per in periods.items():
        key = convert_to_underscore(name)
        node = tmpl.get(key)
        assert isinstance(node, dict), f'{key} 不在模板里'
        node['scheduler']['period'] = per
        node['scheduler']['enable'] = True
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    return Config(CFG)


def _call(fn, *a, **kw):
    return asyncio.new_event_loop().run_until_complete(fn(*a, **kw))


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    try:
        P.unlink()
    except OSError:
        pass


class TestAutoQueueIsSameSourceAsPeriod:
    """★★ 核心: `auto_queue` 必须由 `period` 推出（与界面分类同源）。"""

    def test_cycle_task_is_auto_queue(self):
        c = _mk({'SixRealms': 'daily'})
        assert c.priority_group_of('SixRealms') == 'timed'
        assert c.auto_queue_of('SixRealms') is True, (
            '★ 周期任务必须自动进队列 —— 否则界面上它躺在【添加任务】池子里')

    def test_temp_task_is_not_auto_queue(self):
        c = _mk({'TalismanPass': 'none'})
        assert c.priority_group_of('TalismanPass') == 'fixed'
        assert c.auto_queue_of('TalismanPass') is False, (
            '★ 临时任务**不该**自动进队列 —— 否则界面说临时、行为像周期')

    def test_auto_queue_tasks_matches_cycle_tasks(self):
        """★ 集合级同源: `auto_queue_tasks()` 必须**恰好**等于周期任务集。"""
        import server  # noqa: F401
        from module.config import task_catalog as TC

        c = _mk({})
        aq = set(c.auto_queue_tasks())
        cyc = {t for t in TC.all_specs() if c.priority_group_of(t) == 'timed'}
        assert aq == cyc, (
            f'★ 两个判据漂移了！\n  只在 auto_queue: {sorted(aq - cyc)}\n'
            f'  只在周期任务:   {sorted(cyc - aq)}')

    def test_flip_period_flips_auto_queue(self):
        """★★ 改 `period` 后,**入队行为必须跟着变**（这才是"联动"）。"""
        c1 = _mk({'Sougenbi': 'none'})
        assert c1.auto_queue_of('Sougenbi') is False
        c2 = _mk({'Sougenbi': 'daily'})
        assert c2.auto_queue_of('Sougenbi') is True, (
            '★ 把 period 改成 daily 后必须变成自动入队（否则联动是假的）')

    def test_overview_fields_are_same_source(self):
        """★ `/overview` 的 `auto_queue` 必须与 `period` 同源（实测 0 个不同源）。"""
        import server  # noqa: F401
        from module.server import schema_router as SR
        from module.server.main_manager import mm

        live = mm.config_cache('恋鸟树')
        rows = SR.build_overview('恋鸟树').get('tasks') or []
        assert rows
        bad = [(r['command'], r.get('period'), r.get('auto_queue'))
               for r in rows
               if bool(r.get('auto_queue')) != (r.get('period') != 'none')]
        assert not bad, (
            '★ /overview 里 auto_queue 与 period 不同源: ' + str(bad[:6]))


class TestRemovalRuleFollowsGroupNotAutoQueue:
    """★ 移出队列的停用规则必须按**周期/临时**, 不再按 `auto_queue`。"""

    def test_source_uses_priority_group(self):
        body = code_of(REPO / 'module/server/schema_router.py',
                       'async def post_queue_remove')
        assert 'priority_group_of' in body, (
            '★ `post_queue_remove` 必须用 `priority_group_of` 判类别 —— '
            '用 `auto_queue` 会与界面分类漂移（用户报的"联动不完善"）')
        # 反向: 不该再从 meta 读 auto_queue_effective 当判据
        assert 'auto_queue_effective' not in body, (
            '★ 不该再用 `auto_queue_effective`（依据已废弃的 category）')

    def test_cycle_task_removal_disables(self):
        """★ 周期任务移除 -> **直接停用**（用户明确要求）。"""
        import server  # noqa: F401
        from module.server import schema_router as SR

        c = _mk({'SixRealms': 'daily'})
        c.model.deep_set(c.model, keys='sixrealms.scheduler.enable', value=True)
        c.save()
        r = _call(SR.post_queue_remove, CFG, {'task': 'SixRealms'})
        assert r.get('ok') is True, r
        assert r.get('priority_group') == 'timed', r
        assert r.get('enable') is False, (
            '★ 周期任务移出后必须 enable=False（否则会被自动补齐回来）')

    def test_temp_task_removal_keeps_enabled(self):
        """★ 临时任务移除 -> **只出队列**, 仍在【添加任务】里。"""
        import server  # noqa: F401
        from module.server import schema_router as SR

        c = _mk({'TalismanPass': 'none'})
        c.model.deep_set(c.model, keys='talismanpass.scheduler.enable', value=True)
        c.save()
        r = _call(SR.post_queue_remove, CFG, {'task': 'TalismanPass'})
        assert r.get('ok') is True, r
        assert r.get('priority_group') == 'fixed', r
        assert r.get('enable') is True, (
            '★ 临时任务移出后 enable 必须保持（它要留在【添加任务】池子里）')


class TestPauseAlsoRequeuesRunning:
    """★★★ 「暂停调度」顺带把正在运行的任务**退回队列首位**（用户最终裁定）★★★

    用户原话:
    > "**就把这个功能聚合到暂停调度按钮上好了**, 点击暂停调度,
    >  正在运行的任务**自动回退到队列首位, 视作等待执行**,
    >  这样是不是更优雅。"

    ★ 我第一版做成了**独立端点** `POST /running/cancel`（暂停 + **移出队列**
      + 周期任务**停用**）。★ 用户纠正了两处:
      * 不是移出队列 -> 是**退回队首**
      * 不停用 -> `enable` 保持
      * 而且**聚合进暂停按钮**, 不再需要单独按钮
    """

    def test_put_pause_moves_running_to_front(self):
        """★ `put_pause` 必须**同时**置暂停 + 把 `running_task` 退回队首。"""
        body = code_of(REPO / 'module/server/schema_router.py',
                       'async def put_pause')
        assert 'request_pause' in body, '★ 必须先置暂停'
        assert 'running_task' in body, '★ 必须在暂停时处理正在运行的任务'
        assert 'save_run_list' in body, '★ 必须把它退回 `run_list`'
        assert 'PAUSE_BATTLE' in body or 'mode' in body

    def test_does_not_disable(self):
        """★ **不许停用** —— 它不是移出队列（用户明确纠正）。"""
        body = code_of(REPO / 'module/server/schema_router.py',
                       'async def put_pause')
        assert '.enable = False' not in body, (
            '★ 暂停时不该停用任务 —— 用户明确"并非移除队列，所以不停用"')
        assert 'post_queue_remove' not in body, (
            '★ 暂停**不该**复用移除逻辑（那是"移出队列"，语义不同）')

    def test_says_requeued_and_not_disabled(self):
        """★ 返回/文案要说明"退回队首"+"未停用"+"继续后第一个跑"。

        ⚠ 这里**不用 `code_of`** —— `put_pause` 的函数体里有**多个 `try`**,
          `code_of()` 会在第一个 `try` 处截断（实测: 拿不到后半段的文案）。
          ★ 改用"从 `async def put_pause` 到下一条 `@schema_app` 之间"整段。
        """
        src = (REPO / 'module/server/schema_router.py').read_text(
            encoding='utf-8')
        i = src.index('async def put_pause')
        j = src.index('@schema_app', i)
        body = src[i:j]
        assert 'requeued' in body, '★ 返回里要告诉前端退回了哪个任务'
        assert '未停用' in body
        assert '队首' in body

    def test_put_pause_live_moves_to_front_without_disabling(self):
        """★★ 实测: 暂停 -> 退回队首 + `enable` 不变 ★★

        ## ⚠ 必须**通过 config 对象**设置状态（我踩过一次）

        `save_run_list()` 走的是**整份 `save()`**（项目既有设计, 队列排序/
        移除都这么用）—— 它把**内存模型**写回磁盘。

        ★ 所以若测试**直接改磁盘 JSON**, 而 `mm.config_cache` 里已经有旧模型,
          那么 `put_pause` 的保存会**用旧模型覆盖**测试的改动
          -> 看起来像"`enable` 被改了", 其实是**测试脚手架**的错。
          实测踩到: 报 `six_realms.scheduler.enable = None/False`。

        ★ 正确做法: 经由 `config.model.deep_set(...)` + `config.save()`,
          让内存与磁盘一致。
        """
        import server  # noqa: F401
        from module.config import run_control
        from module.server import schema_router as SR
        from module.server.main_manager import mm

        c = _mk({})
        c.model.deep_set(c.model, keys='six_realms.scheduler.enable',
                         value=True)
        c.model.deep_set(c.model, keys='script.optimization.run_list',
                         value=[{'kind': 'task', 'task': 'Orochi'},
                                {'kind': 'task', 'task': 'Exploration'},
                                {'kind': 'task', 'task': 'SixRealms'},
                                {'kind': 'task', 'task': 'Pets'}])
        c.model.running_task = 'SixRealms'
        c.save()

        run_control.clear_all()
        try:
            r = _call(SR.put_pause, CFG, mode='battle')
            assert 'error' not in r, r
            assert run_control.is_paused() is True
            assert r.get('requeued') == 'SixRealms', r

            d = json.loads(P.read_text(encoding='utf-8'))
            tasks = [e.get('task') for e in
                     d['script']['optimization']['run_list']
                     if isinstance(e, dict)]
            assert tasks[0] == 'SixRealms', f'★ 没退回队首: {tasks}'
            assert len(tasks) == 4, f'★ 队列被改了长度: {tasks}'
            en = (d.get('six_realms', {}).get('scheduler') or {}).get('enable')
            assert en is True, (
                f'★ 暂停时把 `enable` 改成 {en!r} 了 —— '
                f'用户明确"并非移除队列，所以**不停用**"')
        finally:
            run_control.clear_all()

    def test_no_running_task_still_pauses(self):
        """★ 没在跑任何任务时也能暂停（`requeued` 为空, 不是错误）。"""
        import server  # noqa: F401
        from module.config import run_control
        from module.server import schema_router as SR

        c = _mk({})
        c.model.running_task = ''
        c.save()
        run_control.clear_all()
        try:
            r = _call(SR.put_pause, CFG, mode='battle')
            assert 'error' not in r, r
            assert run_control.is_paused() is True
            assert not r.get('requeued'), r
        finally:
            run_control.clear_all()
        """★ `running/cancel` 保留为**薄别名**（转调 `put_pause`）——

        规则只许有**一处实现**, 否则必然分叉（本轮刚修过同类漂移）。
        """
        body = code_of(REPO / 'module/server/schema_router.py',
                       'async def post_cancel_running')
        assert 'put_pause(' in body, (
            '★ `running/cancel` 必须转调 `put_pause`, 不许自己再实现一遍')
        assert 'RunEntry(' not in body and 'save_run_list' not in body, (
            '★ 别名里不该再出现"挪位置"的实现细节')


    def test_cancel_endpoint_is_thin_alias(self):
        """★ `running/cancel` 保留为**薄别名**（转调 `put_pause`）——

        规则只许有**一处实现**, 否则必然分叉（本轮刚修过同类漂移）。
        """
        body = code_of(REPO / 'module/server/schema_router.py',
                       'async def post_cancel_running')
        assert 'put_pause(' in body, (
            '★ `running/cancel` 必须转调 `put_pause`, 不许自己再实现一遍')
        assert 'RunEntry(' not in body and 'save_run_list' not in body, (
            '★ 别名里不该再出现"挪位置"的实现细节')


class TestFrontendPauseIsTheOnlyEntry:
    def test_no_separate_cancel_button(self):
        """★ 界面上**不再有**单独的「取消任务」按钮（已聚合进暂停）。"""
        src = (REPO.parent / 'OASX-src' / 'lib' / 'views' / 'tasks'
               / 'queue_panel.dart')
        if not src.exists():
            pytest.skip('OASX 源码不在预期位置')
        t = src.read_text(encoding='utf-8')
        # 按钮与确认弹窗都不该在（注释里提到是允许的, 所以剥注释看）
        code = '\n'.join(l.split('//')[0] for l in t.split('\n'))
        assert '_confirmAndCancel' not in code, (
            '★ 「取消任务」按钮已删除（功能聚合到暂停调度）')
        assert 'cancelRunning' not in code, (
            '★ 不该再调 `cancelRunning`')

    def test_pause_reports_requeue(self):
        """★ 暂停按钮必须**如实报告**退回队首（否则用户不知道任务去哪了）。"""
        src = (REPO.parent / 'OASX-src' / 'lib' / 'views' / 'tasks'
               / 'run_control_bar.dart')
        if not src.exists():
            pytest.skip('OASX 源码不在预期位置')
        t = src.read_text(encoding='utf-8')
        assert 'pauseScriptDetailed' in t, (
            '★ 要走能拿到 `message`/`requeued` 的那个方法')
        assert '退回' in t or '队首' in t, (
            '★ 提示里要说明"退回队列首位"')
