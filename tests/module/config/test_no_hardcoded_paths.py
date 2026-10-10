# -*- coding: utf-8 -*-
"""★★ 守卫: 代码里不得出现硬编码绝对路径 ★★

## 依据（用户裁定）

> "**杜绝硬编码，写进文档里。**"

见 `docs/architecture.md` §13。

## 为什么要有这条测试

实测踩到的真 bug: `dev_tools/gen_i18n.py` 硬编码了
`D:\OAS-dev\OASX-src`（历史仓库），而**实际编译的是** `D:\OASX-clean`
-> 新增任务的 i18n 写进了**没人在编译的目录**, 界面显示英文 key。
★ 排查时看到的是"i18n 加了但界面没变"——根因却是**路径**。

## 豁免（**不是**放水, 是划清边界）

| 豁免 | 理由 |
|---|---|
| `dev_tools/paths.py` | 它的**候选列表**按设计就要写绝对路径（但逐个验证是不是真仓库）|
| ★ `if __name__ == '__main__':` **块内** | 那是开发者手动跑的单文件调试代码, **不参与运行** |
| ★ 带 `# 调试示例` 标记的行 | 极少数模块级调试常量 —— ★ **必须显式标**, 不许默默留着 |
| 字符串字面量里的**示例** | 本测试只查"像路径赋值"的形态 |

★ 判据只在**代码行**上（先去掉 `#` 之后的部分）。
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# 形如 Path(r'D:\...') / = r'C:/...'
_PAT = re.compile(r"""(Path\(\s*r?['"][A-Za-z]:[\\/])|(=\s*r?['"][A-Za-z]:[\\/])""")

ALLOW_FILES = {
    'dev_tools/paths.py',          # ★ 候选列表（按设计）
}
# ★ 显式豁免标记（必须出现在**同一行**）
ALLOW_MARK = '# 调试示例'


def _py_files():
    for sub in ('dev_tools', 'module', 'tasks'):
        d = REPO / sub
        if not d.is_dir():
            continue
        for p in d.rglob('*.py'):
            if '__pycache__' in p.parts:
                continue
            yield p


def _main_block_lines(lines):
    """找出 `if __name__ == '__main__':` 块覆盖的行号（1-based）。

    ★ 用**缩进**判定块的范围: 从 `if __name__` 那行起, 直到出现
      缩进 <= 该 `if` 的非空行（或文件结束）。
    """
    covered = set()
    i = 0
    while i < len(lines):
        s = lines[i]
        if re.match(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]\s*:", s):
            base = len(s) - len(s.lstrip())
            covered.add(i + 1)
            j = i + 1
            while j < len(lines):
                t = lines[j]
                if not t.strip():
                    covered.add(j + 1)
                    j += 1
                    continue
                ind = len(t) - len(t.lstrip())
                if ind <= base:
                    break
                covered.add(j + 1)
                j += 1
            i = j
            continue
        i += 1
    return covered


def test_no_hardcoded_absolute_paths():
    bad = []
    for p in _py_files():
        rel = p.relative_to(REPO).as_posix()
        if rel in ALLOW_FILES:
            continue
        lines = p.read_text(encoding='utf-8', errors='replace').split('\n')
        exempt = _main_block_lines(lines)
        for i, line in enumerate(lines, 1):
            if i in exempt or ALLOW_MARK in line:
                continue
            code = line.split('#')[0]
            if _PAT.search(code):
                bad.append(f'{rel}:{i}: {line.strip()[:78]}')
    assert not bad, (
        '★ 出现硬编码绝对路径（见 docs/architecture.md §13）—— '
        '请改用 `dev_tools/paths.py` 的 oas_root() / require_oasx()；\n'
        '  若确实是调试残留, 加 `' + ALLOW_MARK + '` 标记或放进 `__main__` 块:\n  '
        + '\n  '.join(bad[:20]))


def test_paths_module_resolves():
    """`paths.py` 必须能解析出 OAS 仓库（相对推导, 永不出错）。"""
    from dev_tools.paths import oas_root
    root = oas_root()
    assert (root / 'module' / 'config').is_dir(), root
    assert (root / 'tasks').is_dir(), root


def test_paths_refuses_to_guess(monkeypatch):
    """★ 找不到 OASX 时**不许猜** —— `require_oasx()` 必须抛。"""
    import dev_tools.paths as P

    monkeypatch.setattr(P, '_OASX_CANDIDATES', ())
    monkeypatch.setattr(P, '_read_local', lambda: {})
    monkeypatch.delenv('OASX_REPO', raising=False)
    P._resolved_cache.clear()
    assert P.oasx_root(verbose=False) is None
    with pytest.raises(SystemExit):
        P.require_oasx()
