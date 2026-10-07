# This Python file uses the following encoding: utf-8
"""
资产审计: 死资产 / 重复定义 / 归类一致性。

为什么需要它
------------
OAS 的规则资产分散在 tasks/<Task>/[子目录]/*.json, 由 assets_extract 生成为
各 tasks/**/assets.py。任务变多后容易出现:
  1. 死资产   —— 定义了但没有任何代码引用(废弃功能或从未接线)
  2. 重复定义 —— 同一 itemName 在多个任务各写一份, 且参数不一致(维护陷阱)
  3. 归类问题 —— 文件命名混乱、同逻辑资产散落各处

引用的三种形态(必须全部覆盖, 否则死资产会被高估)
----------------------------------------------
  a) 属性访问      self.I_BATTLE_SUCCESS / GeneralBattleAssets.C_RANDOM_LEFT
  b) 字符串字面量  'C_END_1_1'  (见 module/atom/click.py:coord_in_excluded)
  c) 派生名        click.name="end_1_1" 可被引用为 'end_1_1' / 'END_1_1' / 'C_END_1_1'
                   (见 click.py:208 的 names 集合构造)

用法
----
    python -m dev_tools.assets_audit
    python -m dev_tools.assets_audit --verify      # 用 git grep 抽查, 校验口径
    python -m dev_tools.assets_audit --csv out.csv
"""
import argparse
import ast
import csv
import importlib
import inspect
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from module.atom.click import RuleClick            # noqa: E402
from module.atom.image import RuleImage            # noqa: E402
from module.atom.list import RuleList              # noqa: E402
from module.atom.long_click import RuleLongClick   # noqa: E402
from module.atom.ocr import RuleOcr                # noqa: E402
from module.atom.swipe import RuleSwipe            # noqa: E402

RULE_TYPES = (RuleImage, RuleOcr, RuleClick, RuleSwipe, RuleLongClick, RuleList)


def _py_files():
    files = []
    for base in ('tasks', 'module', 'dev_tools'):
        root = REPO_ROOT / base
        if root.exists():
            files.extend(p for p in root.rglob('*.py') if '__pycache__' not in p.parts)
    files.extend(p for p in REPO_ROOT.glob('*.py'))
    files.extend(p for p in (REPO_ROOT / 'tests').rglob('*.py') if '__pycache__' not in p.parts)
    return files


def collect_assets():
    """返回 [(模块名, 类名, 属性名, 规则对象)]。"""
    out = []
    for ap in sorted((REPO_ROOT / 'tasks').rglob('assets.py')):
        if '__pycache__' in ap.parts:
            continue
        mod_name = '.'.join(ap.relative_to(REPO_ROOT).with_suffix('').parts)
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            print(f'  [跳过] {mod_name}: {type(exc).__name__}: {exc}', file=sys.stderr)
            continue
        for cls_name, cls in list(vars(mod).items()):
            if not inspect.isclass(cls) or cls.__module__ != mod_name:
                continue
            for attr in dir(cls):
                if attr.startswith('_'):
                    continue
                obj = getattr(cls, attr, None)
                if isinstance(obj, RULE_TYPES):
                    out.append((mod_name, cls_name, attr, obj))
    return out


class ReferenceIndex:
    """
    收集所有可能的引用名。

    - attr_names  : 所有形如 X.ATTR 且 ATTR 为大写的属性名
    - str_names   : 所有 .py 中的字符串字面量(原样)
    - folded      : 上述两者的 casefold 形式, 用于大小写无关匹配
    """

    def __init__(self, files):
        self.attr_names = Counter()
        self.attr_where = defaultdict(set)
        self.str_names = set()
        self.folded = set()

        for f in files:
            if f.name == 'assets.py' or f.name.startswith('assets_'):
                continue
            try:
                tree = ast.parse(f.read_text(encoding='utf-8', errors='ignore'))
            except SyntaxError:
                continue
            rel = str(f.relative_to(REPO_ROOT))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr.isupper():
                    self.attr_names[node.attr] += 1
                    self.attr_where[node.attr].add(rel)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.str_names.add(node.value)
        self.folded = {n.casefold() for n in self.attr_names} | {s.casefold() for s in self.str_names}
        # 去掉 C_ 前缀后的集合, 以匹配 click.name 形式
        self.folded_noprefix = set()
        for n in self.folded:
            self.folded_noprefix.add(n)
            if n.startswith('c_'):
                self.folded_noprefix.add(n[2:])
        for n in self.folded:
            if n.startswith('i_'):
                self.folded_noprefix.add(n[2:])

    def used(self, attr: str, obj) -> bool:
        """判断某资产是否被引用(任意形态)。"""
        if self.attr_names.get(attr, 0) > 0:
            return True
        cands = {attr.casefold()}
        # RuleClick 等有 name 属性, 可能以 name / C_name 形式被引用
        nm = getattr(obj, 'name', None)
        if isinstance(nm, str) and nm:
            c = nm.casefold()
            cands |= {c, f'c_{c}', f'i_{c}', f'o_{c}'}
        return any(c in self.folded_noprefix for c in cands)


def _param_repr(obj):
    if isinstance(obj, RuleList):
        return f'roi_back={list(obj.roi_back)} size={list(obj.size)} array={obj.array}'
    if isinstance(obj, RuleOcr):
        return f'roi={list(obj.roi)} mode={obj.mode} keyword={obj.keyword!r}'
    if isinstance(obj, (RuleClick, RuleSwipe, RuleLongClick)):
        return f'roi_front={list(obj.roi_front)}'
    roi_f = getattr(obj, 'roi_front', None)
    roi_b = getattr(obj, 'roi_back', None)
    return (f'roi_front={list(roi_f) if roi_f else None} '
            f'roi_back={list(roi_b) if roi_b else None} th={getattr(obj, "threshold", None)}')


def _param_key(obj):
    parts = [type(obj).__name__]
    for name in ('roi_front', 'roi_back', 'roi', 'threshold', 'method', 'mode',
                 'keyword', 'array', 'size', 'direction', 'file'):
        v = getattr(obj, name, None)
        if v is not None:
            parts.append(f'{name}={tuple(v) if isinstance(v, (list, tuple)) else v}')
    return '|'.join(map(str, parts))


def verify_with_git_grep(names, sample=12):
    """用 git grep 抽查若干"死资产", 校验审计口径。"""
    print()
    print('=' * 88)
    print('抽查校验(用 git grep 独立核对审计结论)')
    print('=' * 88)
    bad = 0
    for name in list(names)[:sample]:
        r = subprocess.run(['git', 'grep', '-n', '-w', name], cwd=str(REPO_ROOT),
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        lines = [l for l in (r.stdout or '').splitlines()
                 if 'assets.py' not in l and '\\res\\' not in l and '/res/' not in l]
        flag = 'OK ' if not lines else 'MISMATCH'
        if lines:
            bad += 1
        print(f'  [{flag}] {name}: git grep 命中 {len(lines)} 行(排除定义处)')
        for l in lines[:2]:
            print(f'          {l[:120]}')
    print()
    print(f'  抽查 {min(sample, len(names))} 个, 其中被 git grep 推翻 {bad} 个')
    return bad


def main():
    parser = argparse.ArgumentParser(description='OAS 资产审计')
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--csv', type=str, default=None)
    parser.add_argument('--verify', action='store_true', help='用 git grep 抽查校验')
    args = parser.parse_args()

    print('=' * 88)
    print('收集定义与引用...')
    print('=' * 88)
    assets = collect_assets()
    idx = ReferenceIndex(_py_files())
    print(f'  资产定义: {len(assets)} 条')
    print(f'  引用索引: 属性名 {len(idx.attr_names)} 个, 字符串字面量 {len(idx.str_names)} 个')

    by_attr = defaultdict(list)
    for mod_name, cls_name, attr, obj in assets:
        by_attr[attr].append((mod_name, cls_name, obj))

    dead = [(a, d) for a, d in by_attr.items() if not any(idx.used(a, o) for _, _, o in d)]
    dedup_dead = sum(len(d) for _, d in dead)

    print()
    print('=' * 88)
    print('1. 死资产(无任何形态的引用)')
    print('=' * 88)
    print(f'  唯一属性名 {len(by_attr)}: 有引用 {len(by_attr) - len(dead)}, 无引用 {len(dead)}')
    print(f'  涉及定义 {dedup_dead} / {len(assets)} 处 ({dedup_dead / max(1, len(assets)) * 100:.1f}%)')
    print()
    for attr, defs in sorted(dead)[:args.limit]:
        print(f'    {attr:<34} {", ".join(m for m, _, _ in defs)}')
    if len(dead) > args.limit:
        print(f'    ... 另有 {len(dead) - args.limit} 个')

    print()
    print('=' * 88)
    print('2. 跨任务重复定义')
    print('=' * 88)
    dups = [(a, d) for a, d in by_attr.items() if len(d) > 1]
    inconsistent = []
    for attr, defs in dups:
        if len({_param_key(o) for _, _, o in defs}) > 1:
            inconsistent.append((attr, defs))
    print(f'  同名属性 {len(dups)} 组, 其中参数不一致 {len(inconsistent)} 组')
    print('  (参数不一致 = 改一处不改另一处会导致行为分裂)')
    print()
    for attr, defs in sorted(inconsistent)[:args.limit]:
        print(f'    {attr}')
        for m, _, o in defs:
            print(f'        {m:<50} {_param_repr(o)}')
    if len(inconsistent) > args.limit:
        print(f'    ... 另有 {len(inconsistent) - args.limit} 组')

    print()
    print('=' * 88)
    print('3. 归类与命名一致性')
    print('=' * 88)
    json_files = [p for p in (REPO_ROOT / 'tasks').rglob('*.json') if '__pycache__' not in p.parts]
    stem_cnt = Counter(p.stem for p in json_files)
    print(f'  规则文件 {len(json_files)} 个, 文件名去重后 {len(stem_cnt)} 种')
    print('  最常见文件名:')
    for s, c in stem_cnt.most_common(8):
        print(f'      {s + ".json":<26} {c} 个')
    weird = sorted({p.name for p in json_files if re.search(r'\d', p.stem)})
    print(f'  含数字的文件名 {len(weird)} 种(编号式, 语义不明):')
    for n in weird[:12]:
        print(f'      {n}')
    if len(weird) > 12:
        print(f'      ... 另有 {len(weird) - 12} 种')

    print()
    print('=' * 88)
    print('4. 规则类型分布')
    print('=' * 88)
    tc = Counter(type(o).__name__ for _, _, _, o in assets)
    for t, c in tc.most_common():
        print(f'    {t:<16} {c}')

    if args.verify and dead:
        verify_with_git_grep([a for a, _ in sorted(dead)])

    if args.csv:
        out = Path(args.csv)
        with out.open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['属性名', '定义处数', '模块', '状态'])
            for attr, defs in sorted(by_attr.items()):
                used = any(idx.used(attr, o) for _, _, o in defs)
                for m, _, o in defs:
                    st = 'OK' if used else ('DEAD' if len(defs) == 1 else 'DEAD-DUP')
                    w.writerow([attr, len(defs), m, st])
        print()
        print(f'  已写入 CSV: {out}')


if __name__ == '__main__':
    main()
