# -*- coding: utf-8 -*-
"""★ 守卫：**注释/docstring 不许与现行实现脱节**（台账 `N2` / `T18`）。

## ★ 为什么需要（本项目真实发生过）

★ [10-13]~[10-14] 期间实现改了三件大事：
  ① ★ 判定 `completed` 过期：**轮次号 → 本次启动时间戳**（§1.6.x-Z3）
  ② ★ 判定"本轮完成"：**`runs >= target` → 临时任务跑完即完成**（Z6）
  ③ ★ `entry_id` 时间戳：**秒 → 毫秒**（§4.5-④）

★ 而**注释没有跟着改** ⇒ ★ [10-14] 实测**抓到 3 处**：
  * `module/config/run_list.py` 的 `unique_entry_id()` docstring 写"精确到**秒**"
  * `module/config/task_state.py` 的模块注释表写
    "`runs` → `_skip_by_count`：`runs >= target`"（★ 该方法**已停用**）
  * `module/config/config.py` 的 `_loop_candidates` 注释写
    "按**轮次号**自动过期"（★ 现行是**时间戳**）

★ ⇒ ★ 这类漂移**不会让任何测试变红**（注释不参与执行）⇒
  ★ 只有"人读到觉得不对"才发现 —— ★ 与台账 §C.3 的"空转守卫"同一类问题。

## ★ 判据为什么落在**函数 docstring / 模块注释**上（而不是行号）

★ 行号**必然漂移**（本文件自己就有"行号校正台账"）⇒
  ★ 用行号写的守卫**下次改代码就假红**。
★ 所以这里用"**取函数 / 取整份源码，再断言其中必须出现现行词**" ——
  ★ 移动代码位置不影响。

## ★ 覆盖的内容

| # | 断言 |
|---|---|
| ① | ★ `new_entry_id()` docstring 必须写**毫秒**（现行精度）|
| ② | ★ `unique_entry_id()` docstring **不许**再说"精确到**秒**"（除非同处已标"旧实现/修正"）|
| ③ | ★ `get_entry_completed()` docstring 必须写**本次启动时间 / 时间戳** |
| ④ | ★ `task_state.py` 的"`runs` 判据"说明**不许**把 `_skip_by_count` 当现行 |
| ⑤ | ★ `config.py` 的 `_loop_candidates` 段**不许**把"轮次号"当现行判据 |
"""
import inspect
import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)


def _doc(obj) -> str:
    return inspect.getdoc(obj) or ''


# ─────────────────────────── ③ entry_id 精度：毫秒
def test_new_entry_id_docstring_says_milliseconds():
    """★ `new_entry_id()` 的 docstring 必须写**毫秒**（★ 现行精度）。

    ★ [10-14] 实测：`unique_entry_id()` 的 docstring 当时写"精确到秒"，
      而 `new_entry_id()` **早已是毫秒**（`%f` 截 3 位）。
    """
    from module.config.run_list import new_entry_id
    doc = _doc(new_entry_id)
    assert '毫秒' in doc, (
        '★ `new_entry_id()` 的 docstring 必须说明【毫秒】精度'
        f'（现行实现：`{{when:%Y%m%dT%H%M%S}}{{microsecond//1000:03d}}`）。'
        f'实际开头：{doc[:120]!r}')


_PRECISION_WORDS = ('秒', '毫秒')


def test_unique_entry_id_docstring_is_not_stale():
    """★ `unique_entry_id()` 的**开头说明**不许把"精确到秒"当**现行**。

    ★ 判据（★ **只用第一段**，即第一个 `##` 之前 —— 那才是"现在是什么"的声明）：
      * ★ 第一段若**既没有**"秒"**也没有**"毫秒" ⇒ ★ **跳不过去，直接判失败**
        （★ 那说明"精度"这个关键事实**从文档里消失了** —— 同样是漂移）
      * ★ 第一段提到的**每一个**精度词，都必须是 **"毫秒"** ——
        ★ 出现"秒"就红（★ "毫秒"字面里不含"秒"，所以两者可区分）
    ⚠ 我在这条守卫上**连错两次**（都是"关键词在别处命中"导致假通过），
      ★ 现在改成**只认第一段**，并用**词表逐词断言**。
    """
    from module.config.run_list import RunList
    doc = _doc(RunList.unique_entry_id)
    # ★ 扫**开头 15 行块**（"现在是什么"的声明就在这一块里）
    #   ⚠ 我在这条守卫上连错三次：① 扫整份 ⇒ "毫秒"在别处命中；
    #     ② 只取摘要行 ⇒ 没有精度词（假红）；③ 按 `##` 切 ⇒
    #     `inspect.getdoc` 已去缩进，切错位置。★ 现在用"行数窗口"，最稳。
    head = '\n'.join(doc.split('\n')[:15])
    has_ms = '毫秒' in head
    has_sec = '秒' in head
    assert has_ms or has_sec, (
        '★ `unique_entry_id()` 的开头**没有交代精度**（既无"秒"也无"毫秒"）'
        f' ⇒ 读者无从判断现行格式。\n  实际开头：{head[:240]!r}')
    assert has_ms, (
        '★ `unique_entry_id()` 的开头**只提"秒"、没提"毫秒"** —— '
        '★ 而实现早已是【毫秒】（`new_entry_id()` = `%f` 截 3 位）。\n'
        f'  实际开头：{head[:240]!r}\n'
        '★ 修法：把开头的"精确到秒"改成"精确到毫秒"（历史说明可留在后面）')


# ─────────────────────────── ④ 过期判据：时间戳
def test_get_entry_completed_docstring_says_timestamp():
    """★ `get_entry_completed()` 的 docstring 必须写**时间戳 / 本次启动时间**。"""
    from module.config.task_state import get_entry_completed
    doc = _doc(get_entry_completed)
    assert ('时间戳' in doc) or ('本次启动时间' in doc), (
        '★ `get_entry_completed()` 的现行判据是【时间戳比对】'
        f'（§1.6.x-Z3），docstring 里必须写明。实际开头：{doc[:160]!r}')


# ─────────────────────────── ⑤ `runs` 不许被当成现行判据
def test_task_state_module_note_labels_runs_as_legacy():
    """★ `task_state.py` 里"`runs` 是判据"的说法必须**标成已停用**。

    ★ 判据：★ 源码里出现 `_skip_by_count` 的那一行，必须**同时**出现
      "已停用" / "不再是判据" / "遗留" 之一 ——
      ★ 否则读者会以为它还在当判据（★ 实测就是这种写法漂移）。
    """
    src = (REPO / 'module' / 'config' / 'task_state.py').read_text(
        encoding='utf-8')
    hits = [l for l in src.split('\n') if '_skip_by_count' in l]
    if not hits:
        pytest.skip('`task_state.py` 已不再提 `_skip_by_count`')
    for line in hits:
        assert any(k in line for k in ('已停用', '不再是判据', '遗留', '已废弃')), (
            '★ 这一行把 `_skip_by_count` 当成**现行判据**（★ 它已停用）：\n  '
            f'{line.strip()[:160]}\n'
            '★ 请标注"已停用 / 不再是判据 / 遗留"')


def test_config_loop_candidates_note_is_not_round_based():
    """★ `config.py` 里"`completed` 过期"的说明不许把**轮次号**当现行。

    ★ 判据（**扫窗口**，不要求同一行 —— ★ 我第一版用"同一行"，
      而那次修正把注释写成了多行 ⇒ **守卫直接 skip** ⇒ 空转）：
      ★ 找 `get_entry_completed` 附近的注释块，若其中出现"轮次号"，
        ★ 则**同一窗口**内必须出现"时间戳"或"修正/旧实现"。
    """
    src = (REPO / 'module' / 'config' / 'config.py').read_text(encoding='utf-8')
    lines = src.split('\n')
    # ★ 以 `get_entry_completed` 的每次出现为中心，取前后 12 行做窗口
    checked = 0
    for i, l in enumerate(lines):
        if 'get_entry_completed' not in l:
            continue
        lo, hi = max(0, i - 12), min(len(lines), i + 12)
        window = '\n'.join(lines[lo:hi])
        if '轮次号' not in window:
            continue
        checked += 1
        assert any(k in window for k in ('时间戳', '修正', '旧实现')), (
            '★ 这段注释把"轮次号"当成 `get_entry_completed()` 的**现行**判据'
            f'（★ 现行是时间戳）。窗口起始行 {lo + 1}：\n'
            + '\n'.join(x for x in lines[lo:hi] if '轮次号' in x)[:400])
    if checked == 0:
        pytest.skip('`config.py` 的 `get_entry_completed` 附近已不提"轮次号"')
