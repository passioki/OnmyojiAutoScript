# -*- coding: utf-8 -*-
"""i18n 数据的**唯一来源**与读取工具。

## 为什么需要这个模块

任务中文名此前散落在 **4 处**手写副本, 真实发生了漂移。实测(OAS 侧):

| 任务 | `zh_CN.xml` 写的是 | 游戏/权威来源 |
|---|---|---|
| `AreaBoss` 地域鬼王 | **地狱**鬼王 ❌ | 地域鬼王 |
| `DemonEncounter` 逢魔之时 | **封**魔之时 ❌ | 逢魔之时 |
| `TrueOrochi` 真八岐大蛇 | 真·八岐大蛇 ❌ | 真八岐大蛇 |
| `ActivityShikigami` 当期爬塔 | 当期**式神**爬塔 ❌ | 当期爬塔 |
| `Secret` 秘闻副本 | 秘闻之**境** ❌ | 秘闻副本 |
| `FallenSun` 日轮之陨 | 日轮之**城** ❌(本轮已修) | 日轮之陨 |

根因不是"没人校对", 而是**同一份知识存在 4 处** —— 靠人工同步必然漂移。

## 唯一来源

    tasks/<Name>/meta.py  的 TaskSpec.name_zh
        ↓  由 task_catalog 汇总
    本模块把它分发到各消费方(生成器负责写)

任何一处要改任务名, **只改 `meta.py`**。
"""
import json
import re
from pathlib import Path


# --------------------------------------------------------------------------- 读取各副本
def load_oas_xml(repo: Path, task_names) -> dict:
    """
    从 OAS `module/config/i18n/zh_CN.xml` 提取 {任务名: 中文名}。

    条目形如:
        <message><source>FallenSun</source><translation>日轮之陨</translation></message>
    """
    f = repo / 'module' / 'config' / 'i18n' / 'zh_CN.xml'
    if not f.exists():
        return {}
    text = f.read_text(encoding='utf-8', errors='replace')
    out = {}
    for m in re.finditer(
            r'<source>([A-Za-z][A-Za-z0-9_]*)</source>\s*'
            r'<translation>(.*?)</translation>', text, re.S):
        src, trans = m.group(1), m.group(2).strip()
        if src in task_names:
            out.setdefault(src, trans)
    return out


def load_oasx_dart(oasx: Path, task_names) -> dict:
    """
    从 OASX `lib/config/translation/i18n_cn.dart` 提取 {任务名: 中文名}。

    ⚠ **键有 3 种命名变体**(实测):
        I18n.fallen_sun: '日轮之陨',       # snake_case(多数)
        I18n.sixRealms: '六道之门',        # camelCase
        I18n.GotoMain: '回到庭院',         # PascalCase
    只认 snake_case 会误判为"缺翻译", 并生成重复条目。

    本函数把任意变体都归一化到任务名, 因此同一任务的多条记录会合并
    (`setdefault` 保留第一个)。
    """
    f = oasx / 'lib' / 'config' / 'translation' / 'i18n_cn.dart'
    if not f.exists():
        return {}
    text = f.read_text(encoding='utf-8', errors='replace')
    out = {}
    for m in re.finditer(r"I18n\.([A-Za-z0-9_]+):\s*'([^']*)'", text):
        key, val = m.group(1), m.group(2)
        task = _key_to_task_any(key, task_names)
        if task:
            out.setdefault(task, val)
    return out


def _key_to_task_any(key: str, task_names) -> str or None:
    """
    把任意命名变体的键还原成任务名。

    依次尝试:
      1. 本身就是任务名(PascalCase)
      2. snake_case -> PascalCase
      3. camelCase -> PascalCase
    """
    if key in task_names:
        return key
    candidates = {key_to_task(key)}       # snake_case
    if key and key[0].islower():
        candidates.add(key[0].upper() + key[1:])   # camelCase
    for c in candidates:
        if c in task_names:
            return c
    return None


def load_oasx_content_keys(oasx: Path) -> dict:
    """
    从 OASX `lib/config/translation/i18n_content.dart` 提取 {常量名: 英文值}。

    这里定义的是**键常量**, 如 `static const String fallen_sun = 'FallenSun';`。
    没有常量 = 代码里无法引用该任务名 = 界面显示英文 key。
    """
    f = oasx / 'lib' / 'config' / 'translation' / 'i18n_content.dart'
    if not f.exists():
        return {}
    text = f.read_text(encoding='utf-8', errors='replace')
    return {m.group(1): m.group(2)
            for m in re.finditer(r"static const String (\w+) = '([^']*)';", text)}


def load_runtime_json(repo: Path, task_names) -> dict:
    """OASX 运行时推给 OAS 的 `module/config/i18n/zh-CN.json`。"""
    f = repo / 'module' / 'config' / 'i18n' / 'zh-CN.json'
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return {k: v for k, v in data.items() if k in task_names}


def load_assets_json(repo: Path, task_names) -> dict:
    """`assets/i18n/zh-CN.json` —— 附加(help)文案, 也可能是任务名。"""
    f = repo / 'assets' / 'i18n' / 'zh-CN.json'
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return {k: v for k, v in data.items() if k in task_names}


# --------------------------------------------------------------------------- 键名转换
def task_to_key(task: str) -> str:
    """`FallenSun` -> `fallen_sun`(Dart 的 I18n 键形式)。"""
    return re.sub(r'(?<!^)(?=[A-Z])', '_', task).lower()


def key_to_task(key: str) -> str:
    """`fallen_sun` -> `FallenSun`。"""
    return ''.join(p.capitalize() for p in str(key).split('_'))


# --------------------------------------------------------------------------- 差异计算
def diff(source: dict, authoritative: dict):
    """
    返回 (缺失, 不一致)。

    缺失: 权威里有、来源里没有的
    不一致: 两边都有但值不同 -> [(任务, 来源值, 权威值)]
    """
    missing = sorted(t for t in authoritative if t not in source)
    wrong = sorted((t, source[t], authoritative[t]) for t in source
                   if t in authoritative and source[t] != authoritative[t])
    return missing, wrong
