# This Python file uses the following encoding: utf-8
# @brief    Configurations for Ryou Dokan Toppa (阴阳竂道馆突破配置)
# @author   jackyhwei
# @note     draft version without full test
# github    https://github.com/roarhill/oas

from pydantic import BaseModel, Field
# from pygments.lexer import default
# from scripts.regsetup import description

from tasks.Component.GeneralBattle.config_general_battle import GeneralBattleConfig
from tasks.Component.SwitchSoul.switch_soul_config import SwitchSoulConfig
from tasks.Component.config_base import ConfigBase, Time
from tasks.Component.config_scheduler import Scheduler

class AbyssShadowsTime(ConfigBase):
    # ★ 片 4 (W-a/B): 本类原有的「偏好时刻」字段**已删除** ——
    #   用户裁定「放弃'希望几点'这个概念」，改用 `scheduler.windows`
    #   的 `start` 表达（迁移见 `Config.migrate_moment_fields_to_windows_once`）。
    # ⚠ 删完全部字段后类体为空 ⇒ 必须留一个语句,
    #   否则 `IndentationError: expected an indented block`
    #   （★ 本会话在 `SixRealmsGate` 上踩过一次）。
    # ★ 保留空类而不删掉它, 是因为配置树里仍有
    #   `<任务>.<本类对应字段名>` 这个节点 —— 删了会改变配置结构。
    pass
class AbyssShadowsCombatTime(BaseModel):
    # 设置战斗时间
    CombatTime_enable: bool = Field(default=False, description="开启智能伤害")
    boss_combat_time: int = Field(default=60, description="以秒为单位设置首领战斗时间，请合理设置")
    general_combat_time: int = Field(default=60, description="以秒为单位设置副将战斗时间，请合理设置")
    elite_combat_time: int = Field(default=60, description="以秒为单位设置精英战斗时间，请合理设置")

class AbyssShadows(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    abyss_shadows_time: AbyssShadowsTime = Field(default_factory=AbyssShadowsTime)
    abyss_shadows_combat_time: AbyssShadowsCombatTime = Field(default_factory=AbyssShadowsCombatTime)
    general_battle_config: GeneralBattleConfig = Field(default_factory=GeneralBattleConfig)
    switch_soul_config: SwitchSoulConfig = Field(default_factory=SwitchSoulConfig)
