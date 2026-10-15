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


class TestPauseDoesNotTouchQueue:
    """★★★ 「暂停调度」**不动队列顺序**（用户裁定 2026-10-11）★★★

    ## ★★ 用户原话 ★★

    > "这里的**退回队首是什么意思**，感觉咱们哪里沟通错了。
    >  这个**执行顺序就是个播放列表**，
    >  **退回队首不应该是软件来操作的**。"

    ## 旧设计（**已推翻**）

    原来（P-1）点暂停会**把正在跑的条目插到 `run_list` 第 1 位**，
    点「继续」时它第一个跑 —— ★ 代价是**软件擅自改动了用户编排的顺序**。

    ## 现在（用户选 **甲**）

    > "甲：★ **原地不动**（还在第 2 条），只是'停手了'
    >   恢复时从它**接着**跑"

    ⇒ ★ 暂停 = **单纯的"停手"**：不动 `run_list`、不动 `enable`、
      不动 `next_run`、**次数也留着**。
    """

    def test_put_pause_does_not_requeue(self):
        """★ `put_pause` **不许**再动 `run_list`。"""
        body = code_of(REPO / 'module/server/schema_router.py',
                       'async def put_pause')
        assert 'request_pause' in body, '★ 必须置暂停'
        assert 'save_run_list' not in body, (
            '★ 暂停**不该**再写 `run_list` —— '
            '用户: "退回队首不应该是软件来操作的"')
        assert 'entries.insert(0' not in body, (
            '★ 不许再把条目插到队首')

    def test_does_not_disable(self):
        """★ **不许停用** —— 它不是移出队列。"""
        body = code_of(REPO / 'module/server/schema_router.py',
                       'async def put_pause')
        assert '.enable = False' not in body, (
            '★ 暂停时不该停用任务')
        assert 'post_queue_remove' not in body, (
            '★ 暂停**不该**复用移除逻辑')

    def test_says_order_untouched(self):
        """★ 文案要说清"**队列顺序没有被改动**"。"""
        src = (REPO / 'module/server/schema_router.py').read_text(
            encoding='utf-8')
        i = src.index('async def put_pause')
        j = src.index('@schema_app', i)
        body = src[i:j]
        # ⚠ 兼容键仍在（旧调用方），但**恒为空**
        assert "'requeued': ''" in body, '★ `requeued` 兼容键应恒为空'
        assert '队列顺序没有被改动' in body, (
            '★ 文案必须说明"队列顺序没有被改动"')

    def test_put_pause_live_keeps_order(self):
        """★★ 实测: 暂停后**队列顺序原样不变** + `enable` 不变 ★★"""
        import server  # noqa: F401
        from module.config import run_control
        from module.server import schema_router as SR

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
            # ★ 不再"退回队首" ⇒ `requeued` 恒为空
            assert not r.get('requeued'), (
                f'★ 不该再有 requeued: {r.get("requeued")!r}')

            d = json.loads(P.read_text(encoding='utf-8'))
            tasks = [e.get('task') for e in
                     d['script']['optimization']['run_list']
                     if isinstance(e, dict)]
            assert tasks == ['Orochi', 'Exploration', 'SixRealms', 'Pets'], (
                f'★ 暂停**动了队列顺序**（应原样不变）: {tasks}')
            en = (d.get('six_realms', {}).get('scheduler') or {}).get('enable')
            assert en is True, f'★ 暂停时把 `enable` 改成 {en!r} 了'
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
        # ★ [10-15] 去盘符：前端仓库走解析器（★ 必须存在；缺了就响亮失败，**不跳过**）
        from dev_tools.paths import require_oasx
        src = (require_oasx() / 'lib' / 'views' / 'tasks' / 'queue_panel.dart')
        assert src.is_file(), f'★ 前端仓库里缺少 {src} —— 前端仓库必须存在'
        t = src.read_text(encoding='utf-8')
        # 按钮与确认弹窗都不该在（注释里提到是允许的, 所以剥注释看）
        code = '\n'.join(l.split('//')[0] for l in t.split('\n'))
        assert '_confirmAndCancel' not in code, (
            '★ 「取消任务」按钮已删除（功能聚合到暂停调度）')
        assert 'cancelRunning' not in code, (
            '★ 不该再调 `cancelRunning`')

    def test_pause_entry_lives_on_the_queue_row(self):
        """★★★ 暂停入口**长在队列行上**（SPEC §3.6「现行口径」）★★★

        ## ★ [10-15] 本用例被**改写**（原名 `test_pause_reports_requeue`）

        它原来要求 `run_control_bar.dart` 里有 `pauseScriptDetailed`，
        且文案含"退回" / "队首" —— ★★ **两个断言都是已被推翻的旧口径**：

        | 时间 | 谁 | 说法 | 状态 |
        |---|---|---|---|
        | [10-10 23:17:09] | 用户 | "点击暂停调度，正在运行的任务**自动回退到队列首位**" | ❌ **已作废** |
        | [10-11 19:21:05] | 用户 | "`[⏸ 暂停调度]` 应该和队列中任务点击运行那个按钮**是一个东西**，**放在外边就冗余了**" | ✅ 现行 |
        | [10-11 20:53:44] | 用户 | "这个暂停调度/恢复调度**不是集成到任务运行行里的按钮上了吗**，**这应该是 bug**" | ✅ 现行 |

        * ★ "回退到队列首位" 已被**推翻**：用户选 **甲 = 原地不动**
          （见本文件 `TestPauseDoesNotTouchQueue` 的 docstring 与
          SPEC §3.6 分歧块⑨）⇒ 后端 `put_pause` 的 `requeued` **恒为空**。
        * ★ 暂停**不在** `run_control_bar.dart`（那是"共用顶部"= 状态+计数+
          启停脚本）—— ★ 前端自己的守卫（`task_list_panel_test.dart` 的
          `_runControlV2Tests` 第 3 条）**明确断言**那里**不该**有
          `label: const Text('暂停调度')`。

        ⇒ ★ 两个仓库的守卫若都保留，就是**互相矛盾**；★ 按
          `DEV-WORKFLOW.md §0.5` 的权威顺序（SPEC §1~§3 正文 > 测试）
          ⇒ ★ **改这一条**。

        ★★ 注意：这**不是** `E-6-n` 里那个"B 方案（= 承认暂停入口没了）"——
        入口**没有消失**，它在**队列行**上；★ 而且 `F9`（[10-15]）修好了
        `queue_panel.dart` 里那段"条件逐字重复的死分支"⇒ `[⏸]` **真的可达**
        （★ 运行时守卫：前端 `_f9PauseReachableTests()`）。
        """
        # ★ [10-15] 去盘符：前端仓库走解析器（★ 必须存在；缺了就响亮失败，**不跳过**）
        from dev_tools.paths import require_oasx
        src = (require_oasx() / 'lib' / 'views' / 'tasks' / 'queue_panel.dart')
        assert src.is_file(), f'★ 前端仓库里缺少 {src} —— 前端仓库必须存在'
        t = src.read_text(encoding='utf-8')
        # 注释里提到旧口径是允许的（甚至是必要的说明），所以剥注释再看
        code = '\n'.join(l.split('//')[0] for l in t.split('\n'))

        # ① 队列行的暂停必须走**能拿到 `message`** 的那个方法（暂停的唯一实现入口）
        assert 'pauseScriptDetailed' in code, (
            '★ 队列行的暂停按钮要走能拿到 `message`/`requeued` 的 '
            '`pauseScriptDetailed`（否则用户看不到"停手了"的说明）')
        # ② 文案必须是**现行口径**：明确"队列顺序没有被改动"
        assert ('队列顺序不会被改动' in t) or ('队列顺序没有被改动' in t), (
            '★ 提示里要说明"**队列顺序没有被改动**"（现行口径）')
        # ③ ★ 反向：**不许**再对用户承诺"退回队首"（那已被推翻）
        assert '自动回退到队列首位' not in code, (
            '★ [10-10 23:17] 的"自动回退到队列首位"已被推翻（甲：原地不动），'
            '★ 不许留在现行代码里')
        # ④ ★ 反向：暂停**不该**再长在"共用顶部"（那是启停脚本的地方）
        top = (require_oasx() / 'lib' / 'views' / 'tasks' / 'run_control_bar.dart')
        assert top.is_file(), f'★ 前端仓库里缺少 {top}'
        tcode = '\n'.join(
            l.split('//')[0] for l in top.read_text(encoding='utf-8').split('\n'))
        assert "label: const Text('暂停调度')" not in tcode, (
            '★ 「暂停调度」按钮不该回到共用顶部 —— 依 SPEC §3.6 L3/L5')
