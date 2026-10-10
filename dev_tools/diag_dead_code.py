# -*- coding: utf-8 -*-
"""死代码扫描 —— 只读诊断, 不改任何文件。

扫描三类:
  1. **PyWebIO 残留** —— OAS 早就不用 PyWebIO 了(README 里对比 Alas 时提到过)
  2. **已删 QML GUI 残留** —— `module/gui` 与 `fluentui` 已在 7d980485 删除
  3. **未使用的 import** —— 用 AST 解析, 不误匹配字符串/注释

输出供人工判断, 不自动修 —— 死代码的判断需要上下文。
"""
import ast
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from paths import oas_root  # noqa: E402  ★ 消除硬编码（见 paths.py）
REPO = oas_root()
os.chdir(REPO)
sys.path.insert(0, str(REPO))

# 跳过第三方与生成物
SKIP_DIRS = {'toolkit', '.git', '__pycache__', 'node_modules', '.venv',
             'venv', 'build', 'dist'}


def iter_py(root=REPO):
    for p in sorted(root.rglob('*.py')):
        if any(s in p.parts for s in SKIP_DIRS):
            continue
        yield p


def rel(p):
    return str(p.relative_to(REPO)).replace('\\', '/')


print('=' * 100)
print('1. PyWebIO 残留')
print('=' * 100)
pat = re.compile(r'pywebio|PyWebIO', re.I)
hits = []
for f in iter_py():
    for i, line in enumerate(
            f.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if pat.search(line):
            hits.append((rel(f), i, line.strip()[:95]))
for f, i, s in hits:
    print(f'  {f}:{i}')
    print(f'      {s}')
if not hits:
    print('  无')
print(f'  合计 {len(hits)} 处')

print()
print('=' * 100)
print('2. 已删 QML GUI 残留 (module/gui, fluentui, gui.py)')
print('=' * 100)
pat2 = re.compile(r'\bmodule\.gui\b|\bmodule/gui\b|\bfluentui\b|\bgui\.py\b|'
                  r'\bFluentUI\b|\bQML\b|FluentWindow', re.I)
hits2 = []
for f in iter_py():
    for i, line in enumerate(
            f.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
        if pat2.search(line):
            hits2.append((rel(f), i, line.strip()[:95]))
for f, i, s in hits2:
    print(f'  {f}:{i}')
    print(f'      {s}')
if not hits2:
    print('  无')
print(f'  合计 {len(hits2)} 处')

# 非 py 文件里也查(shell/bat/md/yml)
print()
print('  非 Python 文件里的引用:')
hits2b = []
for ext in ('*.bat', '*.sh', '*.md', '*.yml', '*.yaml', '*.toml', '*.cfg',
            '*.txt', '*.spec'):
    for f in REPO.rglob(ext):
        if any(s in f.parts for s in SKIP_DIRS):
            continue
        if rel(f).startswith('docs/') or 'CHANGELOG' in f.name:
            continue
        try:
            txt = f.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        for i, line in enumerate(txt.splitlines(), 1):
            if pat2.search(line):
                hits2b.append((rel(f), i, line.strip()[:95]))
for f, i, s in hits2b[:25]:
    print(f'    {f}:{i}  {s}')
if not hits2b:
    print('    无')
print(f'    合计 {len(hits2b)} 处')


print()
print('=' * 100)
print('3. 未使用的 import (AST 解析, 精确到行)')
print('=' * 100)


def unused_imports(path: Path):
    """返回 [(行号, 名字, 原文)]。"""
    src = path.read_text(encoding='utf-8', errors='replace')
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    lines = src.splitlines()

    # 收集所有被引用的 Name / Attribute 根名
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            n = node
            while isinstance(n, ast.Attribute):
                n = n.value
            if isinstance(n, ast.Name):
                used.add(n.id)
    # 字符串里的名字(type hint、__all__、eval)也算用到 —— 保守起见
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for m in re.finditer(r'[A-Za-z_][A-Za-z_0-9]*', node.value):
                used.add(m.group(0))

    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                name = (a.asname or a.name).split('.')[0]
                if name not in used:
                    out.append((node.lineno, name, lines[node.lineno - 1].strip()))
        elif isinstance(node, ast.ImportFrom):
            # 跳过 `import *`
            if any(a.name == '*' for a in node.names):
                continue
            for a in node.names:
                name = a.asname or a.name
                if name not in used:
                    out.append((node.lineno, name, lines[node.lineno - 1].strip()))
    return out


all_unused = defaultdict(list)
for f in iter_py():
    for ln, name, src in unused_imports(f):
        all_unused[rel(f)].append((ln, name, src))

total_unused = sum(len(v) for v in all_unused.values())
print(f'  有未使用 import 的文件: {len(all_unused)} 个, 共 {total_unused} 处')
print()
for f in sorted(all_unused, key=lambda k: -len(all_unused[k]))[:35]:
    print(f'  {f}  ({len(all_unused[f])} 处)')
    for ln, name, src in all_unused[f][:6]:
        print(f'      L{ln}: {name}   <- {src[:70]}')
    if len(all_unused[f]) > 6:
        print(f'      ... 共 {len(all_unused[f])} 处')
