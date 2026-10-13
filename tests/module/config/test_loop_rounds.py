# -*- coding: utf-8 -*-
"""★ 队列循环「轮数」守卫测试（2026-10-13 补）

## ★★★ 为什么需要这个文件 ★★★

> ★★ 用户原话（[10-12]）：
> > "**循环计数的那个问题，昨天凌晨修复的，循环只计数到 1 的问题**"

### ★ 那个 bug 长什么样

★ `script.py` 里判断队列跑空后要不要循环时，**拿枚举和字符串直接比**：

```python
method = self.config.script.optimization.when_task_queue_empty
if method == 'loop':          # ❌ str(WhenTaskQueueEmpty.LOOP) == 'WhenTaskQueueEmpty.LOOP'
```

★ `when_task_queue_empty` 是**枚举**，`str(枚举)` = `'WhenTaskQueueEmpty.LOOP'`
  ⇒ ★ **永远不等于 `'loop'`** ⇒ 分支进不去
  ⇒ ★ `bump_loop_rounds()` **从不被调用**
  ⇒ ★★ 界面上的"已跑轮数"**永远停在旧值（看起来像"只计数到 1"）**，
     且停止判据 `_done >= _times` **永不成立**（跑满 N 轮也不停）。

★ 修法：★ 取 `.value`（`str(getattr(raw, 'value', raw) or '').lower()`）。

### ★ 为什么必须加守卫

★ 2026-10-13 的审计结论：
  `tests/` 里对 `get_loop_rounds` / `bump_loop_rounds` / `reset_loop_rounds`
  **零覆盖**（只有 `test_schema_router.py` 测了 `loop_times` **字段存在性**）。
★ ⇒ 这条"历史上刚坏过"的判据**没有任何回归防线** ⇒ 再坏一次无人发现。

## ★ 覆盖的内容（四组）

| # | 断言 |
|---|---|
| **①** | `bump_loop_rounds()` **真的会递增**（0→1→2→3）—— ★ 直接对应"只计数到 1" |
| **②** | `get_loop_rounds()` **读回**当前轮数（且跨调用一致） |
| **③** | ★ **停止判据**：`_done >= _times` 在跑满后成立 |
| **④** | `reset_loop_rounds()` 清 0，且**清完能再跑** |
| **⑤** | ★★ **枚举取值**：`WhenTaskQueueEmpty.LOOP.value == 'loop'`
        —— ★ 这是那个 bug 的**根因**，必须钉死 |
| **⑥** | `delta` 参数生效（一次加多轮） |

⚠ 本文件**不碰真实状态文件**（用 `monkeypatch` 指到 `tmp_path`）。
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from module.config import task_state as TS  # noqa: E402

CFG = 'looptest'


@pytest.fixture()
def state(monkeypatch, tmp_path):
    """★ 把状态文件隔离到 tmp_path（**绝不碰真实 `log/.task_state.json`**）。"""
    tmp = tmp_path / '.task_state.json'
    monkeypatch.setattr(TS, '_state_file', lambda: tmp)
    return tmp


# ---------------------------------------------------------------- ① 递增
def test_bump_loop_rounds_really_increments(state):
    """★★★ 核心：`bump_loop_rounds()` 必须**真的递增**。

    ★ 这是"循环只计数到 1"那个 bug 的**直接回归守卫**。
    """
    assert TS.get_loop_rounds(CFG) == 0, '初始应为 0 轮'

    assert TS.bump_loop_rounds(CFG) == 1, '第 1 次 bump 应得 1'
    assert TS.bump_loop_rounds(CFG) == 2, \
        '★ 第 2 次 bump 必须得 2（旧 bug 会卡在 1 不再涨）'
    assert TS.bump_loop_rounds(CFG) == 3, '第 3 次 bump 应得 3'

    assert TS.get_loop_rounds(CFG) == 3, '读回也应是 3'


# ---------------------------------------------------------------- ② 读回
def test_get_loop_rounds_reads_back(state):
    """★ 写进去的轮数必须能**读回来**（否则界面显示不动）。"""
    TS.bump_loop_rounds(CFG, delta=7)
    assert TS.get_loop_rounds(CFG) == 7
    # ★ 再读一次仍一致（不是"一次性"的）
    assert TS.get_loop_rounds(CFG) == 7


# ---------------------------------------------------------------- ③ 停止判据
def test_stop_when_reached_loop_times(state):
    """★ 停止判据 `_done >= _times` 必须**在跑满后成立**。

    ★ 对应 `script.py`：
        if _times > 0 and _done >= _times:  -> 停止循环
    ★ 旧 bug 下 `_done` 恒为旧值 ⇒ 这个条件**永不成立** ⇒ 跑满也不停。
    """
    times = 2
    assert TS.get_loop_rounds(CFG) < times, '还没跑满'

    TS.bump_loop_rounds(CFG)
    assert TS.get_loop_rounds(CFG) < times, '跑 1 轮时还不该停'

    TS.bump_loop_rounds(CFG)
    done = TS.get_loop_rounds(CFG)
    assert done >= times, \
        f'★ 跑满 {times} 轮后 _done({done}) 必须 >= _times({times})，否则永不停止'


# ---------------------------------------------------------------- ④ 重置
def test_reset_loop_rounds_clears_to_zero(state):
    """★ 重置后必须回到 0，且**能再跑**（用户点「重置循环计数」的语义）。"""
    TS.bump_loop_rounds(CFG, delta=5)
    assert TS.get_loop_rounds(CFG) == 5

    assert TS.reset_loop_rounds(CFG) == 0
    assert TS.get_loop_rounds(CFG) == 0, '重置后应回到 0'

    # ★ "能再跑"：再加又是 1
    assert TS.bump_loop_rounds(CFG) == 1, '重置后应能重新从 1 开始计数'


# ---------------------------------------------------------------- ⑤ 枚举根因
def test_when_task_queue_empty_enum_values_are_strings():
    """★★★ **根因守卫**：取 `.value` 后必须等于 `'loop'` / `'shuffle'` 等小写词。

    ★ `script.py` 的判据是：
        _wte = str(getattr(_wte_raw, 'value', _wte_raw) or '').lower()
        if _wte == 'loop': ...
    ★ 若 `when_task_queue_empty` 的枚举值**不是**小写 `'loop'`（例如改名、
      或变成 `'WhenTaskQueueEmpty.LOOP'`），循环逻辑会**静默失效**。
    """
    # ★ 枚举真身：`tasks/Script/config_optimization.py`
    #   （★ 不在 `module/config/config_model.py` —— 踩过这个坑）
    from tasks.Script.config_optimization import WhenTaskQueueEmpty

    assert WhenTaskQueueEmpty.LOOP.value == 'loop', \
        "★ LOOP 的 .value 必须是 'loop'（script.py 靠它判等）"
    assert WhenTaskQueueEmpty.SHUFFLE.value == 'shuffle', \
        "★ SHUFFLE 的 .value 必须是 'shuffle'（script.py 靠它判等）"
    assert WhenTaskQueueEmpty.GOTO_MAIN.value == 'goto_main', \
        "★ GOTO_MAIN 的 .value 必须是 'goto_main'"

    # ★ 反例钉死：直接 str() 枚举**不会**得到小写词（这正是旧 bug 的成因）
    assert str(WhenTaskQueueEmpty.LOOP) != 'loop', \
        '★ 若这条不成立，说明 str(枚举) 变了 —— 那 script.py 的取 .value 手法要复查'


def test_script_py_uses_dot_value_not_raw_enum():
    """★ 源码级守卫：`script.py` 必须**取 `.value`** 才能和 `'loop'` 比。

    ★ 这条守的是"**别把修复改回去**"—— 这正是 2026-10-12 那个 bug。
    ⚠ 判据只看**可执行代码**（剥掉注释与 docstring）—— ★ 注释里提到旧写法是
      合法的（那是"记录 bug 成因"），不能误判成 bug 复现。
    """
    import io
    import tokenize

    raw = (ROOT / 'script.py').read_text(encoding='utf-8')

    # ★ 剥掉注释（`tokenize` 是"认代码"的正规做法，比正则可靠）
    code_only = []
    for tok in tokenize.generate_tokens(io.StringIO(raw).readline):
        if tok.type == tokenize.COMMENT:
            continue
        code_only.append(tok.string)
    code = ' '.join(code_only)

    assert "getattr ( _wte_raw , 'value' , _wte_raw )" in code or \
        "getattr(_wte_raw, 'value', _wte_raw)" in raw, \
        "★ script.py 必须用 getattr(raw, 'value', raw) 取枚举值"

    # ★ 可执行代码里必须出现取 `.value` 的写法
    assert "'value'" in code, "★ 必须取 .value（旧 bug：直接 str(枚举)）"

    # ★ 反例：**可执行代码**里不能有"裸枚举与字符串比"
    assert "when_task_queue_empty == 'loop'" not in code, \
        "★ 不允许在可执行代码里出现裸枚举与字符串比较（那正是旧 bug 的写法；注释里允许）"


# ---------------------------------------------------------------- ⑥ delta
def test_bump_loop_rounds_delta(state):
    """★ `delta` 参数必须生效（供一次性补多轮）。"""
    assert TS.bump_loop_rounds(CFG, delta=4) == 4
    assert TS.bump_loop_rounds(CFG, delta=3) == 7
    assert TS.get_loop_rounds(CFG) == 7


# ---------------------------------------------------------------- ⑦ 健壮性
def test_loop_rounds_never_raises_on_bad_state(state):
    """★ 状态文件坏了也不能抛（排障期尤其重要 —— 不能挡住调度）。"""
    state.write_text('{ 这不是合法 JSON', encoding='utf-8')
    # ★ 都不应抛异常（内部 try/except ⇒ 退化为 0 / 忽略）
    assert TS.get_loop_rounds(CFG) == 0
    TS.bump_loop_rounds(CFG)
    TS.reset_loop_rounds(CFG)
