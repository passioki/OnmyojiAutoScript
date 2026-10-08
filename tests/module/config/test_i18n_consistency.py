# -*- coding: utf-8 -*-
"""i18n 一致性测试 —— 防止任务名再次漂移。

## 为什么需要

任务中文名此前散落在 **4 处**手写副本, 靠人工同步, **必然漂移**。本轮实测到的:

| 任务 | `zh_CN.xml` 写的是 | 游戏/权威 |
|---|---|---|
| `AreaBoss` 地域鬼王 | **地狱**鬼王 | 地域鬼王 |
| `DemonEncounter` 逢魔之时 | **封**魔之时 | 逢魔之时 |
| `TrueOrochi` 真八岐大蛇 | 真·八岐大蛇 | 真八岐大蛇 |
| `ActivityShikigami` 当期爬塔 | 当期**式神**爬塔 | 当期爬塔 |
| `Secret` 秘闻副本 | 秘闻之**境** | 秘闻副本 |
| `FallenSun` 日轮之陨 | 日轮之**城**(本轮已修) | 日轮之陨 |

另有 17 个任务在 OAS 侧完全没有条目。合计 **39 处**不一致。

## 唯一来源

`tasks/<Name>/meta.py` 的 `TaskSpec.name_zh`。改任务名**只改这里**, 然后跑
`python dev_tools/gen_i18n.py` 分发到各副本。

## 本测试覆盖

1. `zh_CN.xml` 与权威一致
2. OASX `i18n_cn.dart` 与权威一致
3. OASX `i18n_content.dart` 的键常量齐全
4. **编译产物 `zh_CN.qm`** 与权威一致 —— 这是最容易漏的一环:
   改了 xml 忘记 `lrelease`, 界面仍显示旧译文; 而既有测试只抽查
   `Period`/`Reset At`, **不覆盖任务名**。
"""
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from module.config import task_catalog as TC

REPO = Path(__file__).resolve().parents[3]
OASX = Path(r'D:\OAS-dev\OASX-src')
XML = REPO / 'module' / 'config' / 'i18n' / 'zh_CN.xml'
QM = REPO / 'module' / 'config' / 'i18n' / 'zh_CN.qm'
DART_CN = OASX / 'lib' / 'config' / 'translation' / 'i18n_cn.dart'
DART_CONTENT = OASX / 'lib' / 'config' / 'translation' / 'i18n_content.dart'

# .qm 里任务名所在 context(QML 的任务树)
QM_CONTEXTS = ('FluTreeView', 'TaskList', 'Args', '')


def authoritative() -> dict:
    return {m.task: m.name_zh for m in TC.all_meta() if m.name_zh}


def xml_task_names() -> dict:
    if not XML.exists():
        return {}
    root = ET.parse(XML).getroot()
    out = {}
    for msg in root.iter('message'):
        src = msg.findtext('source') or ''
        trans = (msg.findtext('translation') or '').strip()
        if src in authoritative():
            out.setdefault(src, trans)
    return out


def dart_task_names() -> dict:
    """解析任意命名变体(snake/camel/Pascal)的 I18n.<key>: '值'。"""
    import re
    if not DART_CN.exists():
        return {}
    text = DART_CN.read_text(encoding='utf-8', errors='replace')
    auth = authoritative()
    out = {}
    for m in re.finditer(r"I18n\.([A-Za-z0-9_]+):\s*'([^']*)'", text):
        key, val = m.group(1), m.group(2)
        for cand in (key,
                     ''.join(p.capitalize() for p in key.split('_')),
                     key[0].upper() + key[1:] if key else key):
            if cand in auth:
                out.setdefault(cand, val)
                break
    return out


def dart_content_values() -> set:
    import re
    if not DART_CONTENT.exists():
        return set()
    text = DART_CONTENT.read_text(encoding='utf-8', errors='replace')
    return {m.group(2) for m in
            re.finditer(r"static const String (\w+) = '([^']*)';", text)}


class TestOasXml:
    def test_file_exists(self):
        assert XML.exists(), 'zh_CN.xml 应随仓库发布'

    def test_all_task_names_present(self):
        auth = authoritative()
        have = xml_task_names()
        missing = sorted(t for t in auth if t not in have)
        assert missing == [], (
            f'zh_CN.xml 缺 {len(missing)} 个任务名: {missing[:10]}\n'
            f'修复: python dev_tools/gen_i18n.py')

    def test_all_task_names_correct(self):
        auth = authoritative()
        have = xml_task_names()
        wrong = [(t, have[t], auth[t]) for t in have
                 if t in auth and have[t] != auth[t]]
        assert wrong == [], (
            f'zh_CN.xml 有 {len(wrong)} 个任务名与权威不符: {wrong[:6]}\n'
            f'修复: python dev_tools/gen_i18n.py')

    def test_no_empty_translations(self):
        auth = authoritative()
        have = xml_task_names()
        empty = sorted(t for t, v in have.items() if t in auth and not v)
        assert empty == [], f'这些任务名的译文为空: {empty}'


class TestOasxDart:
    def test_all_task_names_present(self):
        if not DART_CN.exists():
            pytest.skip('OASX 源码不在本机, 跳过')
        auth = authoritative()
        have = dart_task_names()
        missing = sorted(t for t in auth if t not in have)
        assert missing == [], (
            f'OASX i18n_cn.dart 缺 {len(missing)} 个任务名: {missing[:10]}')

    def test_all_task_names_correct(self):
        if not DART_CN.exists():
            pytest.skip('OASX 源码不在本机, 跳过')
        auth = authoritative()
        have = dart_task_names()
        wrong = [(t, have[t], auth[t]) for t in have
                 if t in auth and have[t] != auth[t]]
        assert wrong == [], f'OASX 任务名与权威不符: {wrong[:6]}'

    def test_key_constants_exist(self):
        """
        `i18n_content.dart` 必须有每个任务的键常量 ——
        否则代码无法引用该名称, 界面会显示英文 key。
        (实测曾缺 15 个: abyss_shadows / hero_test / quiz 等)
        """
        if not DART_CONTENT.exists():
            pytest.skip('OASX 源码不在本机, 跳过')
        auth = authoritative()
        have = dart_content_values()
        missing = sorted(t for t in auth if t not in have)
        assert missing == [], (
            f'i18n_content.dart 缺 {len(missing)} 个键常量: {missing[:10]}')


class TestCompiledQm:
    """
    **最容易漏的一环**: OAS 侧(Fluent/QML)读的是编译产物 `.qm`, 不是 xml。
    改了 xml 忘记 `lrelease`, 界面仍显示旧译文。
    """

    def test_qm_exists_and_loads(self):
        assert QM.exists(), 'zh_CN.qm 应随仓库发布'
        try:
            from PySide6.QtCore import QCoreApplication, QTranslator
        except ImportError:
            pytest.skip('未安装 PySide6, 跳过 .qm 校验')
        QCoreApplication.instance() or QCoreApplication([])
        tr = QTranslator()
        assert tr.load(str(QM)), f'无法加载 {QM}'

    def test_qm_task_names_match_authoritative(self):
        try:
            from PySide6.QtCore import QCoreApplication, QTranslator
        except ImportError:
            pytest.skip('未安装 PySide6, 跳过 .qm 校验')
        QCoreApplication.instance() or QCoreApplication([])
        tr = QTranslator()
        if not tr.load(str(QM)):
            pytest.skip('无法加载 .qm')

        auth = authoritative()
        bad = []
        for task, want in sorted(auth.items()):
            got = ''
            for ctx in QM_CONTEXTS:
                got = tr.translate(ctx, task)
                if got:
                    break
            if got != want:
                bad.append((task, got or '(缺失)', want))
        assert bad == [], (
            f'{len(bad)} 个任务名在 .qm 里缺失或不符: {bad[:6]}\n'
            f'修复: python dev_tools/gen_i18n.py(它会重新 lrelease)')


class TestAuthoritativeSourceIsMeta:
    """权威来源必须是 `tasks/<Name>/meta.py`, 而不是任何 i18n 文件。"""

    def test_every_task_has_name_in_spec(self):
        missing = [t for t, s in TC.all_specs().items() if not s.name_zh]
        assert missing == [], f'这些 meta.py 未声明 name_zh: {missing}'

    def test_catalog_name_comes_from_spec(self):
        for task, spec in TC.all_specs().items():
            meta = TC.get(task)
            if meta is not None:
                assert meta.name_zh == spec.name_zh, \
                    f'{task} 的 catalog 名称未取自 meta.py'
