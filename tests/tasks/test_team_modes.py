"""
验证"石距 / 经验妖怪 / 金币妖怪"改造为支持组队后的契约。

背景
----
这三个任务原先只能"开公开房等路人"(等待 50~60 秒), 无法邀请指定好友。
本次改造为支持三种身份:
    ALONE  : 保持原行为(等路人), 向后兼容
    LEADER : 开房后邀请 invite_config 指定好友, 等对方进入再挑战
    MEMBER : 等待并自动接受队长邀请

这些测试锁定: 共用枚举与配置字段、默认值向后兼容、辅助方法存在且不吞异常。
"""
import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

TEAM_TASKS = [
    ('Tako', 'tasks.Tako.config', 'Tako', 'tasks.Tako.script_task'),
    ('ExperienceYoukai', 'tasks.ExperienceYoukai.config', 'ExperienceYoukai',
     'tasks.ExperienceYoukai.script_task'),
    ('GoldYoukai', 'tasks.GoldYoukai.config', 'GoldYoukai', 'tasks.GoldYoukai.script_task'),
]


# --------------------------------------------------------------------------
# 共用枚举
# --------------------------------------------------------------------------
def test_team_user_status_is_shared_not_duplicated():
    """
    TeamUserStatus 应集中在 GeneralInvite 组件里定义, 供各任务复用,
    而不是每个任务的 config.py 再复制一份。
    """
    from tasks.Component.GeneralInvite.config_invite import TeamUserStatus

    assert [m.value for m in TeamUserStatus] == ['alone', 'leader', 'member']


def test_user_status_alias_points_to_shared_enum():
    from tasks.Component.GeneralInvite.config_invite import TeamUserStatus, UserStatus

    assert UserStatus is TeamUserStatus


@pytest.mark.parametrize('name,mod_name,cls_name,task_mod', TEAM_TASKS)
def test_task_config_reuses_shared_enum(name, mod_name, cls_name, task_mod):
    """
    三个任务的 config.py 必须复用组件里的 TeamUserStatus, 不得再自行定义
    (历史上已有 5 份复制的 UserStatus)。
    """
    from tasks.Component.GeneralInvite.config_invite import TeamUserStatus

    mod = __import__(mod_name, fromlist=[cls_name])

    # 不得再自行定义同名的 UserStatus(成为第 6 份复制)
    assert not hasattr(mod, 'UserStatus'), \
        f'{mod_name} 仍自定义了 UserStatus, 应改用 TeamUserStatus'

    # 必须是组件里那个枚举对象(而不是本地重定义)
    assert getattr(mod, 'TeamUserStatus', None) is TeamUserStatus, \
        f'{mod_name} 的 TeamUserStatus 不是组件中的那一个'

    src = (REPO_ROOT / (mod_name.replace('.', '/') + '.py')).read_text(encoding='utf-8')
    assert 'from tasks.Component.GeneralInvite.config_invite import' in src
    assert 'class TeamUserStatus' not in src, f'{mod_name} 本地重定义了 TeamUserStatus'


# --------------------------------------------------------------------------
# 配置字段与向后兼容
# --------------------------------------------------------------------------
# 每个任务里"装 user_status 的那个分组"的字段名
TASK_GROUP = {
    'Tako': 'tako_config',
    'ExperienceYoukai': 'experience_youkai',
    'GoldYoukai': 'gold_youkai',
}


@pytest.mark.parametrize('name,mod_name,cls_name,task_mod', TEAM_TASKS)
def test_config_has_team_fields(name, mod_name, cls_name, task_mod):
    """
    user_status 必须放在任务的分组内部, invite_config 作为独立分组存在。

    为什么 user_status 不能放在顶层: module/config/config_model.py 的 script_task()
    要求任务模型的顶层字段都是**嵌套模型(分组)**, 它会为每个顶层字段取
    schema["$defs"][...] 再读 ["properties"]。顶层若是标量(如枚举), 取到的是
    枚举定义(没有 properties), 于是抛 KeyError: 'properties', 导致该任务在
    GUI 中整个界面无法渲染。原 Orochi 就是把 user_status 放在 OrochiConfig 内的。
    """
    from tasks.Component.GeneralInvite.config_invite import InviteConfig, TeamUserStatus

    cls = getattr(__import__(mod_name, fromlist=[cls_name]), cls_name)
    obj = cls()
    fields = cls.model_fields

    group = TASK_GROUP[name]
    assert group in fields, f'{name} 缺少分组 {group}'
    group_obj = getattr(obj, group)
    assert 'user_status' in type(group_obj).model_fields, \
        f'{name}.{group} 缺少 user_status'

    assert 'invite_config' in fields, f'{name} 缺少 invite_config'
    assert isinstance(obj.invite_config, InviteConfig)

    # 默认必须是 ALONE —— 否则会改变既有用户的行为
    assert group_obj.user_status == TeamUserStatus.ALONE, \
        f'{name} 的 user_status 默认值应为 alone(向后兼容)'


@pytest.mark.parametrize('name,mod_name,cls_name,task_mod', TEAM_TASKS)
def test_all_top_level_fields_are_groups(name, mod_name, cls_name, task_mod):
    """
    GUI 兼容性回归护栏: 任务模型的所有顶层字段都必须是嵌套模型(分组)。

    这条测试直接覆盖曾经导致 OASX 无法显示"石距/经验妖怪/金币妖怪"界面的问题
    (把 user_status 这个标量放在了顶层 -> script_task() 抛 KeyError: 'properties')。
    """
    from pydantic import BaseModel

    cls = getattr(__import__(mod_name, fromlist=[cls_name]), cls_name)
    for fname, f in cls.model_fields.items():
        ann = f.annotation
        assert isinstance(ann, type) and issubclass(ann, BaseModel), (
            f'{name} 的顶层字段 `{fname}` 是 {ann}, 不是嵌套模型; '
            f'标量字段必须放进某个分组(如 {TASK_GROUP[name]}), 否则 GUI 无法渲染')


@pytest.mark.parametrize('name,mod_name,cls_name,task_mod', TEAM_TASKS)
def test_gui_args_generation_works(name, mod_name, cls_name, task_mod):
    """
    端到端护栏: 真正调用 GUI 用到的 script_task(), 确保能生成参数而不抛异常。
    """
    from module.config.config_model import ConfigModel

    try:
        model = ConfigModel()
        result = model.script_task(name)
    except Exception as exc:
        pytest.fail(f'script_task({name}) 抛异常, GUI 将无法显示该任务: '
                    f'{type(exc).__name__}: {exc}')

    assert result, f'script_task({name}) 返回空, GUI 无字段可显示'
    # user_status 应出现在正确的分组里
    group = TASK_GROUP[name]
    assert group in result, f'script_task({name}) 结果里缺少分组 {group}'
    names = [f['name'] for f in result[group]]
    assert 'user_status' in names, f'{group} 分组里没有 user_status: {names}'


@pytest.mark.parametrize('name,mod_name,cls_name,task_mod', TEAM_TASKS)
def test_config_defaults_unchanged_for_existing_fields(name, mod_name, cls_name, task_mod):
    """确认改造没有动到既有字段的默认值。"""
    cls = getattr(__import__(mod_name, fromlist=[cls_name]), cls_name)
    obj = cls()
    # 三个任务都必有 scheduler 与 switch_soul
    assert hasattr(obj, 'scheduler')
    assert hasattr(obj, 'switch_soul')
    assert obj.switch_soul.enable is False


def test_i18n_has_text_for_the_new_fields():
    """新字段需要在 i18n 里有中文文案, 否则 UI 显示为英文键名。"""
    import io
    import json

    d = json.load(io.open(REPO_ROOT / 'module' / 'config' / 'i18n' / 'zh-CN.json',
                          encoding='utf-8'))
    for key in ('user_status_help', 'invite_number_help', 'friend_name_help',
                'wait_time_help', 'find_mode_help'):
        assert key in d, f'i18n 缺少 {key}'
        assert d[key], f'i18n 中 {key} 为空'


# --------------------------------------------------------------------------
# 辅助方法契约
# --------------------------------------------------------------------------
def test_general_invite_provides_team_helpers():
    from tasks.Component.GeneralInvite.general_invite import GeneralInvite

    for meth in ('enter_room_and_fire', 'run_battle_by_accept'):
        assert hasattr(GeneralInvite, meth), f'GeneralInvite 缺少 {meth}'


def test_enter_room_and_fire_signature():
    """确认关键参数存在且默认值合理。"""
    from tasks.Component.GeneralInvite.general_invite import GeneralInvite

    sig = inspect.signature(GeneralInvite.enter_room_and_fire)
    params = sig.parameters
    assert 'user_status' in params
    assert 'invite_config' in params
    assert 'random_wait' in params
    assert 'joiner_image' in params
    # ALONE 默认等待时间应与改造前一致(50~60 秒量级)
    assert params['random_wait'].default == 60


def test_run_battle_by_accept_signature():
    from tasks.Component.GeneralInvite.general_invite import GeneralInvite

    sig = inspect.signature(GeneralInvite.run_battle_by_accept)
    assert 'battle_config' in sig.parameters


@pytest.mark.parametrize('name,mod_name,cls_name,task_mod', TEAM_TASKS)
def test_task_run_branches_on_user_status(name, mod_name, cls_name, task_mod):
    """
    三个任务的 run() 都必须按 user_status 分支:
    出现 MEMBER 判断, 并在 LEADER 时使用 invite_config。
    """
    script = REPO_ROOT / (task_mod.replace('.', '/') + '.py')
    src = script.read_text(encoding='utf-8')

    assert 'TeamUserStatus.MEMBER' in src, f'{name} run() 未处理 MEMBER'
    assert 'TeamUserStatus.LEADER' in src, f'{name} run() 未处理 LEADER'
    assert 'invite_config' in src, f'{name} run() 未使用 invite_config'
    assert 'enter_room_and_fire' in src, f'{name} 未调用 enter_room_and_fire'
    assert 'run_battle_by_accept' in src, f'{name} 未调用 run_battle_by_accept'


@pytest.mark.parametrize('name,mod_name,cls_name,task_mod', TEAM_TASKS)
def test_task_keeps_alone_fallback(name, mod_name, cls_name, task_mod):
    """
    ALONE 分支必须保留"等路人"路径(向后兼容), 不能只剩组队。
    """
    script = REPO_ROOT / (task_mod.replace('.', '/') + '.py')
    src = script.read_text(encoding='utf-8')

    # ensure_public 是"公开房等路人"的必要一步
    assert 'ensure_public' in src, f'{name} 丢失了公开房等路人的路径'


def test_tako_keeps_weekend_zone_switch():
    """石距在周末要用"愤怒的石距", 改造时不得丢掉该判断。"""
    src = (REPO_ROOT / 'tasks' / 'Tako' / 'script_task.py').read_text(encoding='utf-8')
    assert 'weekday()' in src
    assert '石距' in src
