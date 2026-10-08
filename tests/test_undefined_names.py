# -*- coding: utf-8 -*-
"""用标准库 symtable 检查"引用了但从未定义/导入"的全局名。

为什么需要这个测试
------------------
线上实测 2026-10-08: `tasks/Component/GeneralInvite/general_invite.py` 的
`enter_room_and_fire()` 里用了 `TeamUserStatus`, 但该文件**忘了导入它**。
后果:

    tasks/GoldYoukai/script_task.py:130  self.enter_room_and_fire(conf_team, ...)
    general_invite.py:236                if str(user_status) == TeamUserStatus.LEADER.value:
    NameError: name 'TeamUserStatus' is not defined

房间已经建好、`GR_CREATE_ENSURE_2` 也点了, 随后崩溃 —— 表现为"建了房但没点开始挑战",
并且因为那个分支在 NameError 之后, ALONE 的"等路人再点挑战"逻辑从未执行。

这类错误**语法正确、导入模块也成功**, 只有真正执行到那一行才会暴露。而现有的
`test_team_modes.py` 只检查签名与源码文本, 从不执行, 因此完全没抓到。

本测试用 `symtable` 做真实的符号分析: 找出每个函数里判定为全局自由变量、
但在整个模块中既没有 import、也没有在模块级定义的名字。这正是 NameError 的成因。
"""
import builtins
import symtable
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# 只检查我们自己写的代码
SCAN_DIRS = ('module', 'tasks', 'deploy', 'dev_tools')
SKIP_PARTS = ('__pycache__', '.git', 'toolkit')


def _iter_py_files():
    for d in SCAN_DIRS:
        base = REPO_ROOT / d
        if not base.exists():
            continue
        for p in base.rglob('*.py'):
            if any(s in p.parts for s in SKIP_PARTS):
                continue
            yield p


def _collect_module_level_names(table: symtable.SymbolTable) -> set:
    """
    模块级可用的名字: 模块内定义(含 import/def/class/赋值) + 内建名 + 模块属性。

    注意 `symtable` 把 `from x import y` 也记成符号, 因此"模块级符号表里出现过的
    名字"就是模块作用域内可见的名字。
    """
    names = set(dir(builtins))
    # 解释器自动注入的模块级属性, 静态分析里不会作为符号出现
    names |= {'__file__', '__name__', '__doc__', '__package__',
              '__loader__', '__spec__', '__builtins__', '__debug__'}
    for sym in table.get_symbols():
        names.add(sym.get_name())
    return names


def _has_star_import(src: str) -> bool:
    """
    是否存在 `from x import *`。

    有通配导入时无法静态判定模块级有哪些名字, 会产生大量误报
    (实测: `deploy/utils.py`、`module/config/utils.py` 都被通配导入,
    导致其中的 `os`、`read_file`、`convert_to_underscore` 等被误判)。
    这类文件直接跳过 —— 本测试的目标是抓"忘了写 import"这种确定性错误,
    而不是做完整的名字解析。
    """
    for line in src.splitlines():
        s = line.strip()
        if s.startswith('from ') and s.endswith('import *'):
            return True
    return False


def _find_undefined_globals(path: Path) -> list:
    """返回 [(函数名, 未定义名)]。"""
    src = path.read_text(encoding='utf-8')
    if _has_star_import(src):
        return []
    try:
        top = symtable.symtable(src, str(path), 'exec')
    except SyntaxError:
        return []          # 语法错误由 py_compile/其它测试负责

    module_names = _collect_module_level_names(top)
    problems = []

    def walk(table, func_stack):
        for child in table.get_children():
            name = child.get_name()
            if child.get_type() == 'function':
                for sym in child.get_symbols():
                    # "全局自由变量": 在本作用域被引用, 但不在本作用域绑定
                    if sym.is_referenced() and sym.is_global() and \
                            not sym.is_assigned() and not sym.is_parameter():
                        n = sym.get_name()
                        if n not in module_names:
                            problems.append(('::'.join(func_stack + [name]), n))
            walk(child, func_stack + [name])

    walk(top, [])
    return problems


@pytest.mark.parametrize('path', sorted(_iter_py_files()),
                         ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_undefined_global_references(path):
    """
    模块里不得出现"引用了但从未定义/导入"的全局名。

    这条测试的价值: 它能抓住 `NameError` 这类只在运行时才暴露、且可能藏在
    从未被测试覆盖的分支里的错误 —— 就像 GeneralInvite 里漏导入
    TeamUserStatus 那次。
    """
    problems = _find_undefined_globals(path)
    # 过滤掉一些已知的合法动态情况: 由 exec/globals() 注入的名字很难静态判定,
    # 这里若真有则会在下面以失败信息呈现, 便于人工确认。
    if problems:
        detail = ', '.join(f'{fn} -> {n}' for fn, n in problems[:10])
        pytest.fail(
            f'{path.relative_to(REPO_ROOT)} 存在可能未定义的全局引用: {detail}'
        )
