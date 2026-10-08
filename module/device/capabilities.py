# -*- coding: utf-8 -*-
"""平台能力声明 —— 让"不支持"变成**可读的降级**, 而不是崩溃。

## 为什么需要

此前平台差异靠 `if IS_WINDOWS` **散点判断**, 且有一处是**硬阻塞**:

    # module/device/emulator.py 顶层
    import winreg        # ← Linux/macOS 上直接 ModuleNotFoundError

也就是说: 在非 Windows 上, 只要 import 到 emulator 模块就**崩**,
而不是"优雅地告诉用户这个功能不可用"。

## 设计

把"当前平台能做什么"集中成一组**能力(capability)**, 而不是散落的布尔判断:

    DeviceCapabilities(window_message=..., window_background=..., emulator_manage=...)

任务侧在 `meta.py` 里**声明所需能力**:

    SPEC = TaskSpec(..., requires=('emulator_manage',))

框架启动时校验 -> 能力不足的任务**自动禁用并给出可读提示**:

    [Task] Restart 需要 emulator_manage 能力, 当前平台(linux)不支持, 已自动禁用

★ 关键约束: `module/config`(**调度器所在层**)不得 import 任何 `module/device`。
   调度器只读 `TaskSpec.requires` 这个**纯数据**, 由设备层或服务层去校验。
   这条约束写成架构护栏测试(见 tests/test_architecture_guard.py), 防止以后
   有人图省事在调度器里直接读设备。
"""
import sys
from typing import NamedTuple

from module.logger import logger


# 能力名常量(供 `TaskSpec.requires` 引用, 避免拼写错误)
WINDOW_MESSAGE = 'window_message'          # 窗口消息点击/长按(仅 Windows)
WINDOW_BACKGROUND = 'window_background'    # 窗口后台截图(仅 Windows)
EMULATOR_MANAGE = 'emulator_manage'        # 启动/关闭模拟器实例(仅 Windows)

ALL_CAPABILITIES = (WINDOW_MESSAGE, WINDOW_BACKGROUND, EMULATOR_MANAGE)

# 能力的中文说明(界面/日志用)
CAPABILITY_LABEL = {
    WINDOW_MESSAGE: '窗口消息点击',
    WINDOW_BACKGROUND: '后台截图',
    EMULATOR_MANAGE: '模拟器管理',
}


class DeviceCapabilities(NamedTuple):
    """当前平台/设备支持的能力。"""

    window_message: bool = False
    window_background: bool = False
    emulator_manage: bool = False

    def has(self, name: str) -> bool:
        """查询某个能力名(未知名 -> False)。"""
        return bool(getattr(self, name, False))

    def missing(self, requires) -> tuple:
        """返回 `requires` 里当前不具备的能力名。"""
        return tuple(n for n in (requires or ()) if not self.has(n))

    def describe(self) -> str:
        have = [CAPABILITY_LABEL.get(n, n) for n in ALL_CAPABILITIES if self.has(n)]
        return '、'.join(have) if have else '无(仅基础 ADB 能力)'


def platform_name() -> str:
    """当前平台名(日志用)。"""
    if sys.platform == 'win32':
        return 'windows'
    if sys.platform == 'darwin':
        return 'macos'
    if sys.platform.startswith('linux'):
        return 'linux'
    return sys.platform


def detect_capabilities() -> DeviceCapabilities:
    """
    探测当前平台的能力。

    * `window_message` / `window_background`: 依赖 Windows 的窗口消息与
      `win32gui` 系列 API。
    * `emulator_manage`: 依赖 Windows 注册表(找模拟器安装路径)与
      `taskkill` 等命令。

    三个都是"锦上添花"而非"必需" —— 没有它们, 靠 ADB 仍能正常截图与点击,
    只是无法后台操作、也无法由脚本启动/关闭模拟器。
    """
    is_win = sys.platform == 'win32'
    caps = DeviceCapabilities(
        window_message=is_win,
        window_background=is_win,
        emulator_manage=is_win,
    )
    logger.info(f'平台能力探测({platform_name()}): {caps.describe()}')
    return caps


# 进程内缓存(探测很便宜, 但没必要每次都打日志)
_CACHE = None


def capabilities() -> DeviceCapabilities:
    """取当前平台能力(带缓存)。"""
    global _CACHE
    if _CACHE is None:
        _CACHE = detect_capabilities()
    return _CACHE


def reload_capabilities() -> DeviceCapabilities:
    """强制重新探测(测试用)。"""
    global _CACHE
    _CACHE = None
    return capabilities()


def validate_requires(requires, task: str = '') -> tuple:
    """
    校验某任务声明的能力是否满足。

    :return: 缺少的能力名元组; 为空表示满足。
    """
    miss = capabilities().missing(requires)
    if miss:
        names = '、'.join(CAPABILITY_LABEL.get(n, n) for n in miss)
        logger.warning(
            f'{task or "任务"} 需要 {names} 能力, '
            f'当前平台({platform_name()})不支持, 已自动禁用')
    return miss


def disabled_tasks(specs: dict = None) -> dict:
    """
    找出**因平台能力不足而应禁用**的任务。

    :param specs: {任务名: TaskSpec}; 留空则从 task_catalog 取
    :return: {任务名: (缺少的能力名...)}
    """
    if specs is None:
        try:
            from module.config import task_catalog as TC
            specs = TC.all_specs()
        except Exception as exc:
            logger.warning(f'读取任务自描述失败({type(exc).__name__}: {exc}), '
                           f'跳过能力校验')
            return {}

    out = {}
    for task, spec in (specs or {}).items():
        requires = getattr(spec, 'requires', ()) or ()
        if not requires:
            continue
        miss = capabilities().missing(requires)
        if miss:
            out[task] = miss
    return out


def startup_report() -> str:
    """启动时的可读报告(写进日志, 让用户知道哪些功能被降级了)。"""
    caps = capabilities()
    lines = [f'平台: {platform_name()}   可用能力: {caps.describe()}']
    disabled = disabled_tasks()
    if disabled:
        for task, miss in sorted(disabled.items()):
            names = '、'.join(CAPABILITY_LABEL.get(n, n) for n in miss)
            lines.append(f'  [禁用] {task}: 需要 {names}, 当前平台不支持')
    else:
        lines.append('  所有任务的能力需求均满足')
    return '\n'.join(lines)
