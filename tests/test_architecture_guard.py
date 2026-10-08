# -*- coding: utf-8 -*-
"""架构护栏测试 —— 用测试**强制**分层, 防止以后被图省事破坏。

## 为什么要写成测试

分层的意图写在文档里没人会看; 写在测试里, **破坏了就会红**。
本项目已经因"知识/职责放错层"栽过几次:

* 生成器与 `from_legacy` 各写一套分类判定 -> 丢了 6 个任务的间隔信息
* i18n 任务名散落 4 处 -> 实测 39 处漂移
* `task_state` 的 charges 与 `next_run` 两套资源状态并存

## 护栏内容

1. **`module/config`(调度器所在层)不得 import `module/device`**
   —— 调度器只读 `TaskSpec.requires` 这种**纯数据**。
   否则调度器会耦合到具体设备实现, 无法在无设备环境下测试/运行。

2. **任务层的设备调用必须经由 `self.device`**
   —— 不允许任务直接 import `module.device.method.*` 之类的底层实现,
   否则换后端时会漏改。

3. **平台判断集中在 `capabilities.py`**
   —— `module/device` 下不得再有散落的 `IS_WINDOWS` 分支判断
   (注释里提到不算)。
"""
import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# 调度器所在层: 不得依赖设备层
CONFIG_LAYER = REPO / 'module' / 'config'
DEVICE_LAYER = 'module.device'

# 允许的例外(有充分理由的)
CONFIG_LAYER_ALLOW = {
    # 无 —— 一旦需要, 必须在这里写明理由
}


def iter_py(root: Path):
    for p in sorted(root.rglob('*.py')):
        if '__pycache__' in p.parts:
            continue
        yield p


def imported_modules(path: Path) -> set:
    """解析 AST 取所有 import 的模块名(比正则可靠, 不会误匹配注释/字符串)。"""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                out.add(node.module)
    return out


def top_level_imports(path: Path) -> set:
    """
    **只取模块级** import(不含函数/类内部)。

    ⚠ 为什么不能直接用 `imported_modules`: `ast.walk` 会遍历**所有嵌套节点**,
    于是 `def f(): from x import y` 里的 import 也会被算进来。
    踩过: 护栏因此误报 `schema_router` "顶层 import 设备层", 而那个 import
    实际在函数内(那是刻意的延迟导入)。
    """
    try:
        tree = ast.parse(path.read_text(encoding='utf-8', errors='replace'))
    except SyntaxError:
        return set()
    out = set()
    for node in tree.body:                       # 只看模块级语句
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                out.add(node.module)
    return out


class TestConfigLayerDoesNotImportDevice:
    """
    ★ 核心护栏: `module/config` 不得 import `module/device`。

    理由: 调度器需要能在**没有设备**的环境里被单测与推理
    (本项目大量调度测试正是这样跑的)。一旦它 import 设备层,
    就会连带拉起 adbutils / cv2 / PySide6 等重依赖。
    """

    def test_no_device_imports(self):
        bad = []
        for f in iter_py(CONFIG_LAYER):
            rel = str(f.relative_to(REPO)).replace('\\', '/')
            if rel in CONFIG_LAYER_ALLOW:
                continue
            for mod in imported_modules(f):
                if mod == DEVICE_LAYER or mod.startswith(DEVICE_LAYER + '.'):
                    bad.append((rel, mod))
        assert bad == [], (
            'module/config 不得依赖 module/device(调度器必须能脱离设备运行):\n'
            + '\n'.join(f'  {f} -> {m}' for f, m in bad))

    def test_schema_router_has_no_top_level_device_import(self):
        """
        `schema_router` 顶层不得 import 设备层 —— 设备相关的东西必须**延迟到
        函数内**导入。

        理由: 这样"静态 schema 构造"就完全不牵连设备层, 可以脱离设备单测。
        (`/capabilities` 端点确实需要设备层, 但它在函数内 import, 见该文件。)
        """
        f = REPO / 'module' / 'server' / 'schema_router.py'
        mods = top_level_imports(f)
        bad = [m for m in mods
               if m == DEVICE_LAYER or m.startswith(DEVICE_LAYER + '.')]
        assert bad == [], (
            f'schema_router 顶层不应 import 设备层(请改为函数内导入): {bad}')

    def test_top_level_vs_nested_distinction(self, tmp_path):
        """
        ★ 自检: 两个解析函数必须**语义不同** —— 函数内的 import 不算顶层。

        用临时文件验证(而不是靠真实文件的巧合), 这样这条测试本身是可信的。
        """
        src = tmp_path / 'sample.py'
        src.write_text(
            'import os\n'
            'from module.device.env import IS_WINDOWS\n'
            '\n'
            'def f():\n'
            '    from module.device.capabilities import capabilities\n'
            '    return capabilities()\n',
            encoding='utf-8')

        top = top_level_imports(src)
        allm = imported_modules(src)

        assert 'module.device.env' in top, '模块级 import 应被 top_level_imports 看到'
        assert 'module.device.capabilities' in allm, '嵌套 import 应被 imported_modules 看到'
        assert 'module.device.capabilities' not in top, \
            '函数内的 import **不应**算作顶层(否则会误报延迟导入)'


class TestTaskLayerUsesDeviceAbstraction:
    """任务不得直接 import 设备底层方法实现。"""

    # 任务构造 Device 本身是允许的(它是门面)
    ALLOW_SUB = ('module.device.device',)

    def test_tasks_do_not_import_device_internals(self):
        bad = []
        for f in iter_py(REPO / 'tasks'):
            rel = str(f.relative_to(REPO)).replace('\\', '/')
            for mod in imported_modules(f):
                if not mod.startswith(DEVICE_LAYER):
                    continue
                if mod in self.ALLOW_SUB:
                    continue
                bad.append((rel, mod))
        assert bad == [], (
            '任务不应直接 import 设备层内部模块(应经 self.device 门面):\n'
            + '\n'.join(f'  {f} -> {m}' for f, m in bad))


class TestPlatformChecksAreCentralised:
    """
    "某个功能**是否存在**"的判断应集中到 `capabilities.py`, 而不是散落的
    `if IS_WINDOWS`。

    **例外(合法)**: "选哪份**平台实现**"必然要按平台分支 —— 那是在挑
    实现文件, 不是在决定功能是否存在。这类文件列在 `ALLOWED` 里并注明理由。
    """

    ALLOWED = {
        # 常量定义处
        'module/device/env.py',
        # 能力声明处(本护栏的目的地)
        'module/device/capabilities.py',
        # 平台实现**选择**: 该模块本身就是"Windows 版实现",
        # import 时按平台决定要不要加载(不是功能开关)
        'module/device/method/windows.py',
        'module/device/platform2/__init__.py',
    }

    def test_no_scattered_is_windows_branches(self):
        bad = []
        for f in iter_py(REPO / 'module' / 'device'):
            rel = str(f.relative_to(REPO)).replace('\\', '/')
            if rel in self.ALLOWED:
                continue
            for i, line in enumerate(
                    f.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
                stripped = line.strip()
                # 跳过注释
                if stripped.startswith('#'):
                    continue
                # 找**作为条件/导入**使用的 IS_WINDOWS / IS_MACINTOSH / IS_LINUX
                if re.search(r'\b(IS_WINDOWS|IS_MACINTOSH|IS_LINUX)\b', stripped):
                    bad.append((rel, i, stripped[:80]))
        assert bad == [], (
            '平台判断应集中到 module/device/capabilities.py(改为读能力):\n'
            + '\n'.join(f'  {f}:{i} {s}' for f, i, s in bad)
            + '\n(若确实是"选平台实现"而非"功能开关", 请加入 ALLOWED 并注明理由)')


class TestCapabilitiesModule:
    """能力模块自身的基本契约。"""

    def test_importable_without_device(self):
        """能力模块必须能被单独 import(不牵连 adbutils / cv2)。"""
        from module.device.capabilities import capabilities
        assert capabilities() is not None

    def test_all_capabilities_are_attributes(self):
        from module.device.capabilities import (ALL_CAPABILITIES,
                                                DeviceCapabilities)
        caps = DeviceCapabilities()
        for name in ALL_CAPABILITIES:
            assert hasattr(caps, name), f'DeviceCapabilities 缺字段 {name}'

    def test_missing_reports_correctly(self):
        from module.device.capabilities import DeviceCapabilities
        none_caps = DeviceCapabilities()
        assert set(none_caps.missing(('emulator_manage',))) == {'emulator_manage'}
        all_caps = DeviceCapabilities(True, True, True)
        assert all_caps.missing(('emulator_manage',)) == ()

    def test_unknown_capability_is_false(self):
        """未知名不应抛异常, 而是 False(拼错能力名不会崩)。"""
        from module.device.capabilities import DeviceCapabilities
        assert DeviceCapabilities().has('no_such_capability') is False

    def test_platform_name_nonempty(self):
        from module.device.capabilities import platform_name
        assert platform_name()


class TestTaskSpecRequires:
    """
    `requires` 是**扩展点**。

    实测结论: **当前没有任务真正需要这些能力**(截图/点击都有多条路径,
    模拟器管理属于运行策略而非任务前提)。因此这里不假装存在这样的任务,
    只验证机制本身可用。
    """

    def test_default_empty(self):
        from module.config.task_catalog import TaskSpec
        assert TaskSpec(task='Demo', name_zh='演示').requires == ()

    def test_no_task_declares_requires(self):
        """
        若将来真有任务声明了 `requires`, 这条测试会失败 ——
        那是**有意的提醒**: 请确认该任务是**强依赖**(而非"优先使用"),
        并在 `docs/architecture.md` 里说明理由。
        """
        from module.config import task_catalog as TC
        declaring = {t: s.requires for t, s in TC.all_specs().items() if s.requires}
        assert declaring == {}, (
            f'这些任务声明了 requires: {declaring}\n'
            f'请确认是**强依赖**(能力缺失就必须禁用该任务), '
            f'而不是"有则更好"。若确认强依赖, 请更新本测试与文档。')
