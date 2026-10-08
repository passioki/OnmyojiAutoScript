# -*- coding: utf-8 -*-
"""i18n 漂移诊断 —— 量化"任务名散落在多处"的实际代价。

## 背景

任务中文名此前存在 **3 处**手写副本:
  1. `module/config/i18n/zh_CN.xml`(OAS, XML -> .qm)
  2. `dev_tools` 生成 catalog 时的参考: OASX `lib/config/translation/i18n_cn.dart`
  3. OASX 运行时通过 `/chinese_translate` 把 map **推给** OAS -> `zh-CN.json`

其中 (3) 说明一个关键事实: **OAS 侧的运行时名称其实来自 OASX**,
所以 `zh_CN.xml` 是**冗余副本**, 会漂移。

本轮已经真实发生过一次漂移: `FallenSun` 在 `zh_CN.xml` 里写的是"日轮之城",
而 OASX 与游戏实际都是"日轮之陨"。

## 本脚本做什么

**只读**对比 4 个来源, 列出:
  * 各来源有/没有哪些任务名
  * 同一个任务在不同来源里翻译不一致的
  * 与 `task_catalog`(以 meta.py 为权威) 不一致的

不修改任何文件 —— 先把问题量化清楚再决定怎么改。
"""
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(r'D:\OAS-dev\OnmyojiAutoScript')
OASX = Path(r'D:\OAS-dev\OASX-src')
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import logging                        # noqa: E402
logging.disable(logging.CRITICAL)

from module.config import task_catalog as TC   # noqa: E402

# ---------------------------------------------------------------- 权威
authoritative = {m.task: (m.name_zh or '') for m in TC.all_meta()}
print('=' * 96)
print(f'权威来源: task_catalog(源自 tasks/<Name>/meta.py) —— {len(authoritative)} 个任务')
print('=' * 96)


# ---------------------------------------------------------------- 来源 1: zh_CN.xml
def load_oas_xml() -> dict:
    """
    从 zh_CN.xml 提取 {任务名: 中文名}。

    XML 里任务名条目形如:
        <message><source>FallenSun</source><translation>日轮之陨</translation></message>
    """
    f = REPO / 'module' / 'config' / 'i18n' / 'zh_CN.xml'
    if not f.exists():
        return {}
    text = f.read_text(encoding='utf-8', errors='replace')
    out = {}
    for m in re.finditer(
            r'<source>([A-Za-z][A-Za-z0-9_]*)</source>\s*'
            r'<translation>(.*?)</translation>', text, re.S):
        src, trans = m.group(1), m.group(2).strip()
        if src in authoritative:      # 只关心任务名条目
            out.setdefault(src, trans)
    return out


# ---------------------------------------------------------------- 来源 2: OASX dart
def load_oasx_dart() -> dict:
    """
    从 OASX `i18n_cn.dart` 提取 {任务名: 中文名}。

    条目形如: `I18n.fallen_sun: '日轮之陨',`
    """
    f = OASX / 'lib' / 'config' / 'translation' / 'i18n_cn.dart'
    if not f.exists():
        return {}
    text = f.read_text(encoding='utf-8', errors='replace')
    out = {}
    for m in re.finditer(r"I18n\.([a-z0-9_]+):\s*'([^']*)'", text):
        key, val = m.group(1), m.group(2)
        # 把 snake_case 键还原成 PascalCase 任务名
        pascal = ''.join(p.capitalize() for p in key.split('_'))
        if pascal in authoritative:
            out.setdefault(pascal, val)
    return out


# ---------------------------------------------------------------- 来源 3: OAS 运行时
def load_runtime_json() -> dict:
    f = REPO / 'module' / 'config' / 'i18n' / 'zh-CN.json'
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return {k: v for k, v in data.items() if k in authoritative}


# ---------------------------------------------------------------- 来源 4: assets
def load_assets() -> dict:
    f = REPO / 'assets' / 'i18n' / 'zh-CN.json'
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return {k: v for k, v in data.items() if k in authoritative}


sources = {
    'zh_CN.xml (OAS)': load_oas_xml(),
    'i18n_cn.dart (OASX)': load_oasx_dart(),
    'zh-CN.json (运行时)': load_runtime_json(),
    'assets/i18n/zh-CN.json': load_assets(),
}

print()
print('=' * 96)
print('各来源覆盖情况')
print('=' * 96)
print(f'{"来源":<26}{"条目数":<8}{"缺失任务":<10}{"与权威不一致"}')
print('-' * 96)
for name, data in sources.items():
    missing = [t for t in authoritative if t not in data]
    wrong = [(t, data[t], authoritative[t]) for t in data
             if t in authoritative and data[t] != authoritative[t]]
    print(f'{name:<26}{len(data):<8}{len(missing):<10}{len(wrong)}')

print()
for name, data in sources.items():
    missing = sorted(t for t in authoritative if t not in data)
    wrong = sorted((t, data[t], authoritative[t]) for t in data
                   if t in authoritative and data[t] != authoritative[t])
    if not missing and not wrong:
        print(f'  ✓ {name}: 完全一致')
        continue
    print(f'  --- {name} ---')
    if missing:
        print(f'      缺失 {len(missing)} 个: {missing[:10]}'
              + (' ...' if len(missing) > 10 else ''))
    if wrong:
        print(f'      不一致 {len(wrong)} 个:')
        for t, got, want in wrong[:10]:
            print(f'        {t:<22} 实际={got!r}  权威={want!r}')
        if len(wrong) > 10:
            print(f'        ... 共 {len(wrong)} 个')

# ---------------------------------------------------------------- 交叉漂移
print()
print('=' * 96)
print('交叉比对: 同一任务在不同来源是否翻译不同')
print('=' * 96)
drift = []
for task in authoritative:
    vals = {n: d[task] for n, d in sources.items() if task in d}
    if len(set(vals.values())) > 1:
        drift.append((task, vals))
if drift:
    print(f'  发现 {len(drift)} 个任务在不同来源里翻译不一致:')
    for task, vals in drift[:15]:
        print(f'    {task}:')
        for n, v in vals.items():
            mark = '  <-权威' if v == authoritative[task] else ''
            print(f'        {n:<26} {v!r}{mark}')
else:
    print('  ✓ 无交叉漂移')

print()
print('=' * 96)
print('结论')
print('=' * 96)
print(f'  权威(task_catalog) {len(authoritative)} 个任务;')
for name, data in sources.items():
    n_bad = len([t for t in authoritative if t not in data]) + \
        len([t for t in data if t in authoritative and data[t] != authoritative[t]])
    print(f'    {name:<26} 需修正 {n_bad} 条')
