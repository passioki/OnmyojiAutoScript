# -*- coding: utf-8 -*-
"""
扫描"模块级未定义名字"(undefined name)缺陷。

动机: tasks/DemonEncounter/script_task.py 曾在代码里 raise GameStuckError, 但该模块
只 import 了 TaskEnd, 命中时抛 NameError 并一路落到 script.py:616 的通用 except ->
exit(1), 使整个脚本进程退出。这类缺陷静态可查, 且后果严重(进程自杀), 因此值得全仓扫描。

判定方式:
  1. ast 解析每个 .py, 收集模块级导入名、模块级赋值名、函数/类定义名 —— 这些是"可解析的名字"
  2. 收集模块内所有 Name 节点(Load 上下文)的标识符 —— 这些是"被引用的名字"
  3. 引用了但既非内置、也非本模块定义/导入、且不是局部变量/参数/推导式目标的 => 可疑

为避免误报, 显式排除:
  - Python 内置名 (builtins)
  - 函数参数、局部赋值、with/except/for/推导式绑定、global/nonlocal 声明
  - 类主体的属性式访问不是 Name 节点, 天然不会误报
  - 通过 `from x import *` 导入的模块整体跳过(无法静态判定)

用法:
    toolkit\\python.exe dev_tools\\undefined_name_audit.py
    toolkit\\python.exe dev_tools\\undefined_name_audit.py --path tasks
"""
import argparse
import ast
import builtins
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BUILTINS = set(dir(builtins)) | {'__file__', '__name__', '__doc__', '__spec__',
                                 '__package__', '__loader__', '__builtins__',
                                 '__debug__', 'WindowsError', 'unicode', 'basestring'}


class _NameCollector(ast.NodeVisitor):
    """收集一个作用域内被绑定的名字与引用的名字。"""

    def __init__(self):
        self.bound: set[str] = set()
        self.loaded: set[str] = set()

    # ---- 绑定 ----
    def visit_arg(self, node):
        self.bound.add(node.arg)
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound.add(node.id)
        else:
            self.loaded.add(node.id)

    def visit_alias(self, node):
        # import a.b as c  -> 绑定 c;  import a.b -> 绑定 a
        name = node.asname or node.name.split('.')[0]
        self.bound.add(name)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.bound.add(node.name)
        self.generic_visit(node)

    def visit_Global(self, node):
        self.bound.update(node.names)

    def visit_Nonlocal(self, node):
        self.bound.update(node.names)

    def visit_FunctionDef(self, node):
        self.bound.add(node.name)

    def visit_AsyncFunctionDef(self, node):
        self.bound.add(node.name)

    def visit_ClassDef(self, node):
        self.bound.add(node.name)

    def visit_Lambda(self, node):
        # lambda 的参数属于它自己的作用域, 这里只关心它引用的外部名
        for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
            self.bound.add(a.arg)
        if node.args.vararg:
            self.bound.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.bound.add(node.args.kwarg.arg)
        self.generic_visit(node)


class _ModuleScan(ast.NodeVisitor):
    """逐文件扫描: 收集模块级可解析名, 以及所有被引用名。"""

    def __init__(self):
        self.module_level: set[str] = set()
        self.all_loaded: set[str] = set()
        self.bound_anywhere: set[str] = set()
        self.star_import = False
        self.suspicious: list[tuple[int, str]] = []

    # 模块级导入/定义/赋值都算作"整个模块可解析的名字"
    def visit_Import(self, node):
        for a in node.names:
            name = a.asname or a.name.split('.')[0]
            self.module_level.add(name)
            self.bound_anywhere.add(name)

    def visit_ImportFrom(self, node):
        for a in node.names:
            if a.name == '*':
                self.star_import = True
                continue
            name = a.asname or a.name
            self.module_level.add(name)
            self.bound_anywhere.add(name)

    def _visit_def(self, node):
        self.module_level.add(node.name)
        self.bound_anywhere.add(node.name)
        self.generic_visit(node)

    visit_FunctionDef = _visit_def
    visit_AsyncFunctionDef = _visit_def
    visit_ClassDef = _visit_def

    def visit_Name(self, node):
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bound_anywhere.add(node.id)
        else:
            self.all_loaded.add(node.id)
        self.generic_visit(node)

    def visit_arg(self, node):
        self.bound_anywhere.add(node.arg)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        if node.name:
            self.bound_anywhere.add(node.name)
        self.generic_visit(node)

    def visit_Global(self, node):
        self.bound_anywhere.update(node.names)
        self.generic_visit(node)

    def visit_Nonlocal(self, node):
        self.bound_anywhere.update(node.names)
        self.generic_visit(node)


def scan_file(path: Path) -> list[tuple[int, str]]:
    """返回 [(行号, 未定义名字)]。"""
    try:
        src = path.read_text(encoding='utf-8')
    except Exception:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    scan = _ModuleScan()
    scan.visit(tree)
    if scan.star_import:
        return []

    # 收集全部 Store 上下文(函数内局部变量等), 简化处理: 只要在文件任何位置被绑定过
    # 就不算未定义。这会产生漏报, 但能保证零误报, 而漏报是可接受的。
    resolved = set(scan.module_level) | set(scan.bound_anywhere) | BUILTINS

    out = []
    for name in sorted(scan.all_loaded - resolved):
        # 找到首次引用行号, 便于定位
        line = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == name and \
                    isinstance(node.ctx, ast.Load):
                line = node.lineno
                break
        out.append((line, name))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description='未定义名字审计')
    parser.add_argument('--path', default='.', help='相对仓库根的扫描子目录')
    args = parser.parse_args()

    root = (REPO_ROOT / args.path).resolve()
    targets = []
    for base in ('tasks', 'module', 'dev_tools'):
        base_dir = root if root.is_dir() and root.name == base else REPO_ROOT / base
        if not base_dir.exists():
            continue
        for py in base_dir.rglob('*.py'):
            if '__pycache__' in py.parts:
                continue
            targets.append(py)

    print('=' * 78)
    print('未定义名字审计 (undefined name)')
    print('=' * 78)
    print(f'扫描文件数: {len(targets)}')

    total = 0
    for py in sorted(targets):
        findings = scan_file(py)
        if not findings:
            continue
        rel = py.relative_to(REPO_ROOT).as_posix()
        for line, name in findings:
            total += 1
            print(f'  {rel}:{line}  未定义: {name}')

    print()
    if total:
        print(f'发现 {total} 处可疑的未定义名字引用。')
        print('注意: 该扫描为保守实现, 只报告"整个文件中从未被绑定"的名字, 因此误报率极低,')
        print('      但会漏掉"仅在某个执行路径上才未定义"的情况(如条件导入)。')
    else:
        print('未发现未定义名字引用。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
