# -*- coding: utf-8 -*-
"""★ 守卫：**不能出现"未完成却标记完成"**（用户 10-09 亲令 —— 最重要的一点）。

## ★★ 用户原话

> **[10-09 23:28:39]** ★★ "这很严重了，我要求以上内容**确保全部修正**，
>  且**确保不能出现未完成却标记完成的情况**。请将这个作为**最重要的一点记忆
>  并写进文档**。"

## ★ 为什么要有这组守卫

★ "已完成"是**唯一**让一条任务退出的判据（见 `DESIGN-SPEC.md` §1.5 / §2.6）：
```
★ 一旦误标 completed ⇒ ★ 该条任务**不再派发** ⇒ ★ 用户看到"任务被跳过"
★ 一旦漏标 completed ⇒ ★ 该条任务**被反复派发** ⇒ ★ 热循环（券没了还重复打）
```
⇒ ★ **两个方向都是真 bug**，所以两个方向都要守卫。

## ★ 守卫清单

| # | 守什么 |
|---|---|
| ① | ★ 只有"**真的完成**"才标 —— 即 `mark_entry_completed` 只在**成功路径**被调 |
| ② | ★ `mark_entry_completed` **不碰** `runs` / `total_*`（不污染计数）|
| ③ | ★ 没有 `entry_id` 时**不误标**（避免"整任务被跳过"）|
| ④ | ★ 标完**必须能被 `_skip_by_completed` 看到**（否则标了没用）|
| ⑤ | ★ 新一轮（轮次 +1）⇒ **自动过期**（否则永久跳过）|
"""
import io
import logging
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import pytest  # noqa: E402

from module.config import task_state as TS  # noqa: E402

CFG = '__guard_false_completion__'


@pytest.fixture()
def state(monkeypatch):
    tmp = Path(tempfile.mkdtemp()) / 'st.json'
    monkeypatch.setattr(TS, '_state_file', lambda: tmp)
    logging.disable(logging.CRITICAL)
    return tmp


# ─────────────────────────────────────────────────────── ② 不污染计数
def test_mark_completed_does_not_touch_counters(state):
    """★ `mark_entry_completed` **只写完成标记**，不动 `runs` / `total_*`。

    ★ 为什么重要：★ 若它顺手改了 `runs`，会把"打了几场"的判据弄脏
      ⇒ ★ 会直接导致"未完成却标完成"（或反之）。
    """
    eid = 'e1'
    TS.bump_entry_runs(CFG, eid, delta=3)          # 打了 3 场
    TS.record_entry_run(CFG, eid, runs_this_time=3)

    before = TS._read_all()[CFG]['__entries__'][eid]
    runs_before = int(before.get('runs') or 0)
    total_before = int(before.get('total_runs') or 0)
    log_before = len(before.get('total_log') or [])

    assert TS.mark_entry_completed(CFG, eid, '测试') is True

    after = TS._read_all()[CFG]['__entries__'][eid]
    assert int(after.get('runs') or 0) == runs_before, \
        '★ 标完成【不能】改 runs'
    assert int(after.get('total_runs') or 0) == total_before, \
        '★ 标完成【不能】改 total_runs'
    assert len(after.get('total_log') or []) == log_before, \
        '★ 标完成【不能】改 total_log'
    assert after.get('completed') is True, '★ 必须真的标上 completed'


# ─────────────────────────────────────────────────────── ③ 无 entry_id 不误标
def test_mark_completed_without_entry_id_is_noop(state):
    """★ 没有 `entry_id` ⇒ **不标**（★ 否则会"整任务被跳过"）。

    ★ 为什么重要：★ 条目身份是"**按条**判完成"的前提；
      没有身份时标完成 ⇒ ★ 分不清是哪一条 ⇒ ★ 可能误伤同任务的其它条目。
    """
    assert TS.mark_entry_completed(CFG, '', '空 id') is False
    data = TS._read_all().get(CFG) or {}
    entries = data.get(TS.ENTRIES_KEY) or {}
    assert not entries, '★ 空 entry_id 不该写出任何条目记录'


# ─────────────────────────────────────────────────────── ④ 标了要能被看到
def test_completed_is_visible_to_gate(state):
    """★ 标完成 ⇒ ★ **`get_entry_completed()` 必须返回 True**（否则标了没用）。

    ★ 这是"标记 → 判据"的**连通性**守卫：
      标了但判据看不到 ⇒ ★ 该条会被**反复派发**（热循环）。
    """
    eid = 'e2'
    assert TS.get_entry_completed(CFG, eid) is False, '初始应未完成'
    TS.mark_entry_completed(CFG, eid, '测试')
    assert TS.get_entry_completed(CFG, eid) is True, \
        '★ 标完成后判据必须看到'


# ─────────────────────────────────────────────────────── ⑤ 新一轮必须过期
def test_completed_expires_next_round(state):
    """★ 新一轮（轮次 +1）⇒ ★ **自动过期**（否则该条**永久跳过**）。

    ★ 为什么重要：★ 用户报的"**循环第二次时结界突破没有触发**"
      就是"永久跳过"的一种表现。
    """
    eid = 'e3'
    TS.mark_entry_completed(CFG, eid, '测试')
    assert TS.get_entry_completed(CFG, eid) is True

    TS.bump_loop_rounds(CFG)                        # 进入新一轮
    assert TS.get_entry_completed(CFG, eid) is False, \
        '★ 进入新一轮后必须能再跑（自动过期）'

    after = TS._read_all()[CFG]['__entries__'][eid]
    assert 'completed' not in after, '★ 过期时要顺手清掉 completed 字段'


# ─────────────────────────────────────────────────────── ① 只在成功路径标
def test_mark_completed_only_called_on_success_path():
    """★ 静态守卫：★ `script.py` 里的"自动标完成"必须在**成功**分支内。

    ★ 为什么重要：★ 若在失败/异常路径也会标 ⇒ ★ **未完成却标完成**
      （★ 正是用户 10-09 亲令要杜绝的）。
    ★ 做法：在 `script.py` 里找 `mark_entry_completed` 的调用，
      要求它**被 `if _eid and success:` 包住**。
    """
    src = (Path(__file__).resolve().parents[3] / 'script.py') \
        .read_text(encoding='utf-8')
    # 剥掉注释（本项目有"守卫匹配到自己注释"的前科）
    raw = [l.split('#')[0] for l in src.split('\n')]

    # ★★★ 用【行级缩进】判"是否被成功门包住" ★★★
    #
    #   ⚠ 不要用"往前数 N 个字符"—— 我在两者之间插了新代码（补记非战斗任务
    #     场次），那种脆弱判据就**假红**了（★ 实测发生过）。
    #   ★ 行级判据：`mark_entry_completed` 所在行的**缩进**必须**大于**
    #     前面那个 `if ... success ...:` 行 —— 那样才是"在它里面"。
    call_line = None
    guard_line = None
    for i, l in enumerate(raw):
        if call_line is None and 'mark_entry_completed(' in l:
            call_line = i
            break
    assert call_line is not None, '★ script.py 里应有"自动标完成"的调用'

    # 从调用行往上找最近的"含 success 的 if 行"
    for j in range(call_line - 1, -1, -1):
        s = raw[j].rstrip()
        if not s.strip():
            continue
        if s.lstrip().startswith('if ') and 'success' in s:
            guard_line = j
            break
    assert guard_line is not None, (
        '★ "自动标完成"必须在显式的 `if ... success ...:` 分支内 —— '
        '否则会出现"未完成却标记完成"（用户 10-09 亲令：最重要的一点）')

    def _indent(s):
        return len(s) - len(s.lstrip())

    assert _indent(raw[call_line]) > _indent(raw[guard_line]), (
        '★ "自动标完成"必须在"成功"分支的**内部**（缩进更深），'
        '★ 不能与 `if` 同级 —— 否则失败路径也会标完成')


def test_battle_tasks_report_completion_only_when_done():
    """★ 静态守卫：★ 任务"自报完成"必须紧跟在**判定为真**的分支里。

    ★ 以 RealmRaid 为例（它的"没票 ⇒ 本轮结束"是最典型的自报）：
      `self.mark_entry_completed(...)` 必须在
      `if not self.check_ticket(...):` **之内**。
    """
    p = (Path(__file__).resolve().parents[3]
         / 'tasks' / 'RealmRaid' / 'script_task.py')
    if not p.exists():
        pytest.skip('RealmRaid 不在')
    code = '\n'.join(l.split('#')[0] for l in
                     p.read_text(encoding='utf-8').split('\n'))

    idx = code.find('mark_entry_completed(')
    assert idx > 0, '★ RealmRaid 应在"没券"时自报本轮完成'

    window = code[max(0, idx - 500):idx]
    assert 'check_ticket' in window or 'not self.check_ticket' in window, (
        '★ 自报完成必须【只在】"没券（= 本轮做完了）"的分支里 —— '
        '不能在其它路径误标')
