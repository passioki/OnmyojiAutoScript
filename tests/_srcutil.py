# -*- coding: utf-8 -*-
"""★ 源码守卫的公共工具: **剥注释 / 剥 docstring**。

## 为什么必须集中成一处（第二轮复审的"模式 2"）

本项目**反复**踩同一个坑: 源码守卫写成

```python
src = (REPO / 'module/config/config.py').read_text(encoding='utf-8')
i = src.find('if self._is_list_rule(_rule):')
seg = src[i:j]
assert '_order_by_queue' in seg          # ★ 命中的是**注释**！
```

`str.find` / `in` **都会匹配注释**。台账里已记录过**至少 3 次**
"守卫匹配到自己的说明文字", 而第二轮复审又找到 **5 处**同款:

| 位置 | 症状 |
|---|---|
| `test_queue_no_leak_all_rules.py:101-105` | `find()` 命中 T1 **自己写的注释** -> **永远通过**（假绿）|
| `test_queue_membership_and_category.py`（**已删的** `TestPriorityModeHint`）| `'drag_within_group_only' in src` 命中 `schema_router.py` 的 **docstring**；`'def _segment_queue' in src` 只证明文本出现过 |
| `test_entry_scoped_state.py:115` | `body` **没剥注释**（同文件 `:126` 剥了, 反差明显）|
| `test_duplicate_queue_entries.py:47-60` | 未剥注释, 可被注释满足 / 会被注释**假失败** |

★ 根本原因: **剥注释逻辑在 4+ 个文件里各写一份**（"同一知识多处定义"
在测试里也在犯）。这个模块把它收敛成**一处**。

## 用法

```python
from _srcutil import code_of, code_only, module_source

body = code_of(repo / 'module/config/config.py', 'def update_scheduler')
assert '_order_by_queue' in body        # ★ 现在不会命中注释
```
"""
from __future__ import annotations

import re
from pathlib import Path

__all__ = ['strip_comments', 'code_only', 'code_of', 'module_source']

#: 三引号字符串（docstring）—— 非贪婪, 跨行
_TRIPLE_RE = re.compile(r'"""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'')


def strip_comments(src: str) -> str:
    """剥掉**注释与 docstring**, 只留可执行代码。

    ⚠ 顺序很重要: **先剥三引号, 再剥 `#`** —— 否则字符串里的 `#`
    （如 `'#fff'`）会被误当成注释开头。
    """
    src = _TRIPLE_RE.sub('', src)
    return '\n'.join(line.split('#', 1)[0] for line in src.split('\n'))


def code_only(path) -> str:
    """读文件 -> 剥注释。"""
    return strip_comments(Path(path).read_text(encoding='utf-8'))


def code_of(path, def_line: str) -> str:
    """取**某个函数/方法**的函数体（剥注释）。

    :param def_line: 用于定位的**定义行片段**（如 `'def update_scheduler'`）。
                     取它之后的第一个**同级或更浅缩进**的 `def` / `class`
                     之前的全部内容。
    :raises AssertionError: 找不到定义行（**不静默返回空**——
        静默返回空会让守卫变成"空转通过", 正是要防的）。
    """
    lines = Path(path).read_text(encoding='utf-8').split('\n')
    idx = next((n for n, l in enumerate(lines)
                if def_line in l.split('#', 1)[0]), None)
    if idx is None:
        raise AssertionError(
            f'{Path(path).name}: 找不到定义行 {def_line!r} —— '
            f'★ 不要静默跳过（那会让守卫空转通过）')

    indent = len(lines[idx]) - len(lines[idx].lstrip())
    end = len(lines)
    for n in range(idx + 1, len(lines)):
        s = lines[n]
        if not s.strip():
            continue
        cur = len(s) - len(s.lstrip())
        # 同级或更浅的 def/class -> 函数结束
        if cur <= indent and re.match(r'\s*(def|class|@)\s', s):
            end = n
            break
    body = '\n'.join(lines[idx:end])
    return strip_comments(body)


def module_source(path) -> str:
    """别名 —— 语义更清楚的写法（"这个模块的代码"）。"""
    return code_only(path)
