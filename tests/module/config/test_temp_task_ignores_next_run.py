# -*- coding: utf-8 -*-
"""★★★ 守卫：**临时任务不受 `next_run` 影响**（用户裁定 S1/S2/S3）。

## ★★ 用户原话（三次追问同一件事）

> "**怎么还有 next_run？没有按照新的调度吗？**"
> "**是只是日志语义没适配，还是内层代码逻辑还是 next_run？**"
> "我总觉得**改调度逻辑这个任务我已经说过四五遍了，但是仍然没有完成**！！"

## ★ 设计依据（`DESIGN-SPEC.md` §1.2 分型规则）

| 维度 | 临时任务（`period = none`）| 周期任务 |
|---|---|---|
| `next_run` | ★★ **不参与派发判断** | ✅ 参与（时间排期）|
| 谁决定"能不能跑" | ★ **次数 + 门票** | ★ 窗口 + period |
| 谁决定"下一条是谁" | ★ **队列顺序** | ★ 队列顺序 |

## ★ 本文件守什么

| # | 守 |
|---|---|
| ① | ★ `script.py` 的**派发判定**里必须有"临时任务跳过 `next_run`"分支 |
| ② | ★ `config.py` 的 `task_delay` 里必须有"临时任务不写未来 `next_run`" |
| ③ | ★ `get_next()` 必须**跳过 `slot == 'done'`**（否则 S1 会反复跑已完成的）|
| ④ | ★ 周期任务的 `next_run` 判定**必须保留**（不能一并删掉）|
"""
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

REPO = Path(__file__).resolve().parents[3]


def _code(rel: str) -> str:
    """读源码并**剥掉注释**（本项目有"守卫匹配到自己注释"的前科）。"""
    raw = (REPO / rel).read_text(encoding='utf-8')
    return '\n'.join(l.split('#')[0] for l in raw.split('\n'))


# ───────────────────────────────────────── ① 派发判定跳过 next_run
def test_dispatch_skips_next_run_for_temp_tasks():
    """★ `script.py` 的派发判定必须有"临时任务跳过"分支。

    ★ 为什么重要：★ 用户的"跑完不轮到下一条"就是这么来的 ——
      ★ 队首任务 `next_run` 在未来 ⇒ 不派发 ⇒ 落到"等待"。
    """
    code = _code('script.py')
    i = code.find('if _is_temp_task or task.next_run <= now:')
    assert i > 0, (
        '★★ 派发判定里没有"临时任务跳过 `next_run`"的分支！\n'
        '  （★ 这是用户裁定 S1 —— 临时任务在所有时点判定里都必须被跳过）')
    # ★ 上下文必须真的算出 `_is_temp_task`
    #   ⚠ 窗口要够大：★ 我后来在防封那一段（更靠前）就算好了 `_is_temp_task`，
    #     ★ 两处相隔较远。
    window = code[max(0, i - 2500):i]
    assert 'task_period' in window, (
        '★ 必须先算出"是不是临时任务"（用 `task_period`）')


def test_dispatch_keeps_next_run_for_periodic_tasks():
    """★ 周期任务的 `next_run` 判定**必须保留**（不能一并删掉）。"""
    code = _code('script.py')
    assert 'or task.next_run <= now' in code, (
        '★ 周期任务仍要按 `next_run` 派发 —— 不能把判定整个删掉')


# ───────────────────────────────────────── ⑤ S2：防封不推临时任务
def test_antiban_does_not_push_temp_task_next_run():
    """★ S2：`antiban_wake` **只对周期任务**改 `next_run`。

    ★ 为什么重要：★ 临时任务没有排期语义 ⇒
      ★ 若防封把它的 `next_run` 推远，★ 界面/日志会显示一个"未来的时间"
      ⇒ ★★ **误导**（用户就是因此以为"还在用 `next_run` 排期"）。
    """
    import re
    code = _code('script.py')
    # ★ 必须看到"防封 + 非临时任务"的联合条件
    assert re.search(
        r'if\s+antiban_wake\s+is\s+not\s+None\s+and\s+not\s+_is_temp_task\s*:',
        code), (
        '★★ 防封那一段必须写成 '
        '`if antiban_wake is not None and not _is_temp_task:` —— '
        '否则临时任务的 `next_run` 会被防封推远')
    # ★ 且不能存在"无条件改 next_run"的老写法
    assert not re.search(
        r'if\s+antiban_wake\s+is\s+not\s+None\s*:\s*\n\s*task\.next_run\s*=',
        code), (
        '★★ 还有"无条件把 next_run 推到 antiban_wake"的写法')


# ───────────────────────────────────────── ② task_delay 不写未来
def test_task_delay_does_not_schedule_temp_tasks_in_future():
    """★ `task_delay()` 对临时任务**不写未来的 `next_run`**。

    ⚠ 断言要**够强** —— 我第一版只查字符串，★ 自检（注入破坏）**仍绿**
      ⇒ ★ 那种守卫是**恒真**的，等于没有。
    """
    code = _code('module/config/config.py')
    i = code.find('def task_delay')
    assert i > 0
    j = code.find('\n    def ', i + 10)
    body = code[i:j]

    # ★ ① 必须真的算出"是不是临时任务"
    assert 'task_period' in body, '★ `task_delay` 必须判断 `task_period`'
    # ★ ② 必须真的有一个 `if _is_temp:` 分支（★ 显式字面量，避免弱断言）
    assert 'if _is_temp:' in body, (
        '★★ `task_delay` 里没有 `if _is_temp:` 分支 —— '
        '临时任务的未来 `next_run` 不会被压成"现在"')
    m = re.search(r'if\s+_is_temp\s*:', body)
    assert m
    # ★ ③ 该分支体内必须真的把 `next_run` 改成 `_now`
    tail = body[m.end():]
    assert re.search(r'next_run\s*=\s*_now', tail[:400]), (
        '★★ `if _is_temp:` 分支里没有 `next_run = _now` —— '
        '临时任务仍会被写成"未来"')


# ───────────────────────────────────────── ③ get_next 跳过 done
def test_get_next_skips_done_entries():
    """★ `get_next()` 必须跳过 `slot == 'done'`。

    ★ 为什么重要：★ 已完成的条目**仍留在 `pending_task`**（为了按队列顺序显示）
      ⇒ ★ 若不跳过，★ S1（临时任务即刻派发）会让它**反复跑已完成的**。

    ⚠ 断言要**够强**：★ 必须看到"**跳过 `done` 的循环**"这个结构，
      ★ 而不只是源码里出现过 `done` 这个词。
    """
    import re
    code = _code('module/config/config.py')
    i = code.find('def get_next')
    assert i > 0
    j = code.find('\n    def ', i + 10)
    body = code[i:j]

    # ★ 必须是一个"遍历 pending_task 并 continue 掉 done"的循环
    assert re.search(r'for\s+_f\s+in\s+self\.pending_task\s*:', body), (
        '★★ `get_next()` 必须**遍历** `pending_task`（不能只取 `[0]`）\n'
        '  ★ 否则"队首已完成"时会反复派发它')
    assert re.search(r"getattr\(_f,\s*'slot'[^)]*?\)[^=]*==\s*'done'", body), (
        '★★ `get_next()` 里必须判断 `slot == \'done\'` 并 `continue`')
    assert 'continue' in body, '★ 必须有 `continue`（跳过已完成的）'
    # ★ 且必须**不再**直接返回 `pending_task[0]`
    assert 'self.pending_task[0]' not in body, (
        '★★ `get_next()` 不能再用 `pending_task[0]`（会返回已完成的条目）')


# ───────────────────────────────────────── ④ 端到端：临时任务真能派发
def test_temp_task_with_future_next_run_is_still_dispatchable(monkeypatch,
                                                              tmp_path):
    """★★ 功能验证：临时任务 `next_run = +3 天` ⇒ ★ **仍是 pending（可派发）**；
    周期任务同条件 ⇒ ★ **进 waiting（不可派发）**。"""
    import json
    import logging

    logging.disable(logging.CRITICAL)
    from module.config import task_state as TS
    monkeypatch.setattr(TS, '_state_file', lambda: tmp_path / 'st.json')

    cfgname = '__T_TEMP_NR__'
    p = REPO / 'config' / f'{cfgname}.json'
    try:
        import server  # noqa: F401
        from module.server.main_manager import mm
        from datetime import datetime, timedelta

        fut = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d %H:%M:%S')
        from module.server import schema_router as SR  # noqa: F401

        def build(period):
            d = json.loads((REPO / 'config' / 'template.json')
                           .read_text(encoding='utf-8'))
            d['script']['optimization']['run_list'] = [
                {'kind': 'task', 'task': 'RealmRaid', 'entry_id': 'r1',
                 'target': 99}]
            s = d.setdefault('realm_raid', {}).setdefault('scheduler', {})
            s.update({'enable': True, 'period': period, 'windows': [],
                      'next_run': fut})
            return d

        # ★ 临时任务
        p.write_text(json.dumps(build('none'), ensure_ascii=False),
                     encoding='utf-8')
        c1 = mm.config_cache(cfgname)
        c1.update_scheduler()
        pend1 = [getattr(f, 'command', '') for f in c1.pending_task]
        assert 'RealmRaid' in pend1, (
            f'★★ 临时任务 `next_run=+3天` 却不进 pending ⇒ {pend1}')

        # ★ 周期任务（换个配置名，避免缓存）
        cfgname2 = '__T_PERIOD_NR__'
        p2 = REPO / 'config' / f'{cfgname2}.json'
        p2.write_text(json.dumps(build('daily'), ensure_ascii=False),
                      encoding='utf-8')
        c2 = mm.config_cache(cfgname2)
        c2.update_scheduler()
        pend2 = [getattr(f, 'command', '') for f in c2.pending_task]
        assert 'RealmRaid' not in pend2, (
            f'★ 周期任务 `next_run=+3天` 不该进 pending ⇒ {pend2}')
        p2.unlink()
    finally:
        try:
            p.unlink()
        except OSError:
            pass
