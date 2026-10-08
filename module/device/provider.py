# -*- coding: utf-8 -*-
"""设备能力接口 —— 跨平台的**契约**(Protocol), 而不是散落的布尔判断。

## 定位(重要, 与最初设想不同)

设计文档最初设想"任务声明所需能力, 能力不足则禁用该任务"。**实测后修正**:

> **没有任务真正需要 `window_message` / `window_background` / `emulator_manage`。**

* 截图与点击都有多条路径(`ADB` / `uiautomator2` / `minitouch` / `DroidCast` /
  `scrcpy` / `nemu_ipc`), 窗口消息只是**其中一种可选方式**
* 模拟器管理只在"任务队列空 -> 关闭模拟器"这类**运行策略**里用
  (见 `script.py`), 不是任何单个任务的前提
* `Restart` 任务只是重启**游戏 app**(`app_stop` / `app_start`), 与模拟器无关

因此能力是**全局可用性**, 不是**任务前提**。`TaskSpec.requires` 保留为
**扩展点** —— 将来若真有任务强依赖某能力(如"必须用窗口消息才能操作"),
在那里声明即可, 框架会给出可读的禁用提示。**但现在不该假装已有这样的任务**,
否则就是在声明不存在的约束。

## 本模块提供

* `DeviceCapabilities` —— 当前平台能做什么(见 `capabilities.py`)
* `DeviceProvider` —— 设备应实现的**最小契约**, 供跨平台实现方参照

★ **关键约束**: `module/config`(调度器所在层)不得 import 任何 `module/device`。
   调度器只读 `TaskSpec.requires` 这个**纯数据**。写成架构护栏测试
   (见 `tests/test_architecture_guard.py`)。
"""
from typing import Protocol, runtime_checkable

import numpy as np

from module.device.capabilities import (      # noqa: F401  (对外再导出)
    ALL_CAPABILITIES, CAPABILITY_LABEL, EMULATOR_MANAGE, WINDOW_BACKGROUND,
    WINDOW_MESSAGE, DeviceCapabilities, capabilities, detect_capabilities,
    disabled_tasks, platform_name, reload_capabilities, startup_report,
    validate_requires)


@runtime_checkable
class DeviceProvider(Protocol):
    """
    设备应实现的**最小契约**。

    任何平台的实现(ADB / 将来的其它后端)只要满足这个 Protocol,
    上层任务代码就不必关心平台差异。

    注意这是 **Protocol 而非基类** —— 现有 `Device` 类**无需改动**即可满足
    (结构化类型)。这样引入契约不会带来重构风险。
    """

    image: np.ndarray

    def screenshot(self) -> np.ndarray:
        """截取当前画面。"""
        ...

    def click(self, x: int, y: int) -> None:
        """点击坐标(硬编码 1280x720 坐标系)。"""
        ...

    def capabilities(self) -> DeviceCapabilities:
        """当前平台/设备支持的能力。"""
        ...


def check_device_provider(obj) -> tuple:
    """
    校验一个对象是否满足 `DeviceProvider` 契约。

    :return: (是否满足, 缺失的方法名元组)
    """
    required = ('screenshot', 'click', 'capabilities')
    miss = tuple(n for n in required if not callable(getattr(obj, n, None)))
    return (not miss), miss
