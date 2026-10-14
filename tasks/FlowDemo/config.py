# This Python file uses the following encoding: utf-8
"""`FlowDemo`（流程示例）的任务配置。★ 由「新建任务」生成（SPEC §1.16 NT1~NT4）。"""
from pydantic import BaseModel, Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class FlowDemoTaskConfig(BaseModel):
    """★ 任务的**设置分组**。

    ⚠ **顶层字段必须是嵌套模型（= 分组）**，标量字段（bool/int/str/枚举）
      **必须**落在分组内部 —— 见 `tasks/Tako/config.py:15-24` 的说明：
      ★ 放到任务类顶层会让 GUI 渲染整个任务时抛 `KeyError`，**整个界面白掉**。
    """

    enable: bool = Field(default=False, description='enable_help')
    # ★ 在这里加你任务的字段，例：
    #   max_times: int = Field(default=1, ge=0, le=99, description='...')


class FlowDemo(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    flow_demo_config: FlowDemoTaskConfig = Field(default_factory=FlowDemoTaskConfig)
