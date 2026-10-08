# This Python file uses the following encoding: utf-8
# @author runhey
# github https://github.com/runhey
# --------------------------------------------------------------------------- 配置模型
#
# 这个文件**不再手写任务字段声明**。
#
# 原先是 60 个 `from tasks.X.config import X` + 56 个
# `x: X = Field(default_factory=X)` —— 共 113 行, 且**新增一个任务就要改这里**,
# 漏改就静默少一个任务。现在改为**扫描 `tasks/*/config.py` 自动发现**。
#
# 这与 `tasks/<Name>/meta.py` 的自描述配套, 一起实现:
#     **新增一个游戏活动 = 只写 `tasks/<New>/`, 零改动其它文件**
#
# 例外(真实契约里确实存在的, 显式列出比隐式猜更诚实):
#   * `Component` / `General` —— 是共享组件目录, 不是任务
#   * `Script` / `GlobalGame` —— 继承 `BaseModel` 而非 `ConfigBase`
#   * 它们没有 `scheduler` 字段(是全局设置, 不是"任务")
#
# 见 `docs/architecture.md` §7.2(消除中心化注册)。
import importlib
import inspect
import json
import re
import inflection

from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel, Field, ValidationError, create_model

from module.config.utils import *
from module.logger import logger

# 导入配置的Python文件
from tasks.Component.config_base import ConfigBase, TimeDelta


# 不是任务的目录(共享组件)
NOT_A_TASK = {'Component', 'General'}

# 需要纳入但**没有 scheduler 字段**的全局设置类
# (它们确实是特例: 没有 scheduler, 因此启发式找不到)
EXTRA_GLOBAL = ('Script', 'GlobalGame')


def _discover_config_classes() -> dict:
    """
    扫描 `tasks/*/config.py`, 返回 {字段名: 配置类}。

    字段名的派生方式与原先手写声明**完全一致**:
    `convert_to_underscore(ClassName)`(如 `GlobalGame` -> `global_game`)。
    这保证了配置文件的键不变 —— 已用 3 个真实配置逐一验证解析结果差异为 0。
    """
    # 用 `Path.cwd()` 而不是 `__file__` —— 与同文件的 `read_json()` 保持一致,
    # 且 PyInstaller 打包后 `__file__` 不可靠。
    tasks_dir = Path.cwd() / 'tasks'
    found = {}

    if not tasks_dir.is_dir():
        logger.error(f'任务目录不存在: {tasks_dir}')
        return found

    for d in sorted(tasks_dir.iterdir()):
        if not d.is_dir() or d.name in NOT_A_TASK or d.name.startswith(('_', '.')):
            continue
        if not (d / 'config.py').exists():
            continue
        try:
            mod = importlib.import_module(f'tasks.{d.name}.config')
        except Exception as exc:
            logger.warning(f'{d.name}/config.py 导入失败'
                           f'({type(exc).__name__}: {exc}), 已跳过')
            continue

        cls = _pick_config_class(mod, d.name)
        if cls is None:
            logger.warning(f'{d.name}/config.py 未找到配置类, 已跳过')
            continue
        found[convert_to_underscore(cls.__name__)] = cls

    # 补上无 scheduler 的全局设置类
    for name in EXTRA_GLOBAL:
        try:
            mod = importlib.import_module(f'tasks.{name}.config')
            cls = getattr(mod, name, None)
            if cls is not None:
                found.setdefault(convert_to_underscore(name), cls)
        except Exception as exc:
            logger.warning(f'{name}/config.py 导入失败'
                           f'({type(exc).__name__}: {exc})')

    return found


def _pick_config_class(mod, dirname):
    """
    从模块里挑出**任务配置类**。

    ⚠ 并非所有配置类都继承 `ConfigBase` —— `Script` / `GlobalGame` 直接继承
    `BaseModel`。只查 `ConfigBase` 会漏掉它们。

    规则(按优先级):
      1. 与目录同名的类
      2. 带 `scheduler` 字段的类(任务配置类的标志)
      3. 类名转下划线 == 目录名
    """
    def _is_cfg(o):
        return (inspect.isclass(o) and issubclass(o, BaseModel)
                and o is not BaseModel and o is not ConfigBase
                # 只接受**本模块定义**的类, 排除 import 进来的
                and o.__module__ == mod.__name__)

    cands = [o for o in vars(mod).values() if _is_cfg(o)]

    for c in cands:
        if c.__name__ == dirname:
            return c
    for c in cands:
        try:
            keys = set(getattr(c, 'model_fields', None) or {})
        except Exception:
            keys = set()
        if 'scheduler' in keys:
            return c
    for c in cands:
        if convert_to_underscore(c.__name__) == convert_to_underscore(dirname):
            return c
    return None


# 字段默认工厂。用闭包而不是 `default_factory=cls` ——
# create_model 对可调用对象有额外校验, 闭包形式最稳妥。
def _factory(cls):
    return lambda: cls()


_CONFIG_CLASSES = _discover_config_classes()
logger.info(f'ConfigModel: 自动发现 {len(_CONFIG_CLASSES)} 个配置类')

# 发现为空说明 `tasks/` 路径不对(如工作目录错) —— 必须**大声失败**。
# 否则会静默生成一个没有任何任务字段的 ConfigModel, 所有任务的配置都读不出来,
# 而报错点会离病因很远(在某个 getattr 上)。
if not _CONFIG_CLASSES:
    raise RuntimeError(
        f'ConfigModel 自动发现到 0 个配置类 —— 请确认当前工作目录({Path.cwd()})'
        f'下存在 tasks/ 且其中含 */config.py。')
if len(_CONFIG_CLASSES) < 40:
    logger.warning(f'ConfigModel 只发现 {len(_CONFIG_CLASSES)} 个配置类, '
                   f'远少于预期的 ~56 个, 请检查 tasks/ 是否完整')

_FIELDS = {name: (cls, Field(default_factory=_factory(cls)))
           for name, cls in _CONFIG_CLASSES.items()}
_FIELDS['config_name'] = (str, 'oas')
_FIELDS['running_task'] = (str, '')


class _ConfigModelBase(ConfigBase):
    """只放方法, 字段由文件末尾的 `ConfigModel = create_model(...)` 动态注入。"""

    def __init__(self, config_name: str=None) -> None:
        """

        :param config_name:
        """
        if not config_name:
            super().__init__()
            return
        data = self.read_json(config_name)
        data["config_name"] = config_name
        super().__init__(**data)

    def __setattr__(self, key, value):
        """
        只要修改属性就会触发这个函数 自动保存
        :param key:
        :param value:
        :return:
        """
        super().__setattr__(key, value)
        logger.info("auto save config")
        self.save()

    @staticmethod
    def read_json(config_name: str) -> dict:
        """
        读文件 没有额外操作
        :param config_name:  不带后缀
        :return:
        """
        filepath = Path.cwd() / "config" / f"{config_name}.json"
        return read_file(filepath)

    @staticmethod
    def write_json(config_name: str, data) -> None:
        """

        :param config_name: 不带后缀
        :param data:  字典而不是字符串
        :return:
        """
        filepath = Path.cwd() / "config" / f"{config_name}.json"
        write_file(filepath, data)

    def gui_args(self, task: str) -> str:
        """
        返回提供给gui显示的参数
        :param task: 输入的是任务的名称英文 如'Script' 或者是'script'都是可以的
        :return: 返回的是pydantic给我们结构化的输出的信息, 如果不能获取就返回空的str
        """
        task = convert_to_underscore(task)
        task_gui = getattr(self, task, None)
        if task_gui is None:
            logger.warning(f'{task} is no inexistence')
            return ''

        schema2 = task_gui.schema()
        # https://github.com/pydantic/pydantic/discussions/5687
        if 'definitions' in schema2:
            if 'Scheduler' in schema2['definitions']:
                if 'properties' in schema2['definitions']['Scheduler']:
                    properties = schema2['definitions']['Scheduler']['properties']
                    if 'success_interval' in properties:
                        properties['success_interval']['type'] = 'string'
                    if 'failure_interval' in properties:
                        properties['failure_interval']['type'] = 'string'
        return json.dumps(schema2)

    def gui_task(self, task: str) -> str:
        """
        返回提供给gui显示的参数
        :param task:
        :return:
        """
        task_name = convert_to_underscore(task)
        task = getattr(self, task_name, None)
        if task is None:
            logger.warning(f'{task_name} is no inexistence')
            return ''
        return task.json()

    def save(self) -> None:
        """

        :return:
        """
        self.write_json(self.config_name, self.model_dump())

    @staticmethod
    def type(key: str) -> str:
        """
        输入模型的键值，获取这个字段对象的类型 比如输入是orochi输出是Orochi
        :param key:
        :return:
        """
        field_type: str = str(ConfigModel.__annotations__[key])
        # return field_type
        if '.' in field_type:
            classname = field_type.split('.')[-1][:-2]
            return classname
        else:
            classname = re.findall(r"'([^']*)'", field_type)[0]
            return classname

    @staticmethod
    def deep_get(obj, keys: str, default=None):
        """
        递归获取模型的值
        :param obj:
        :param keys:
        :param default:
        :return:
        """
        if not isinstance(keys, list):
            keys = keys.split('.')
        value = obj
        try:
            for key in keys:
                value = getattr(value, key)
        except AttributeError:
            return default
        return value

    @staticmethod
    def deep_set(obj, keys: str, value) -> bool:
        if not isinstance(keys, list):
            keys = keys.split('.')
        current_obj = obj
        try:
            for key in keys[:-1]:
                current_obj = getattr(current_obj, key)
            setattr(current_obj, keys[-1], value)
            return True
        except (AttributeError, KeyError):
            return False

    # ----------------------------------- fastapi -----------------------------------
    def script_task(self, task: str) -> dict:
        """

        :param task: 同gui_args函数
        :return:
        """
        task = convert_to_underscore(task)
        task = getattr(self, task, None)
        if task is None:
            logger.warning(f'{task} is no inexistence')
            return {}

        def extract_groups(sch):
            # 从schema 中提取未解析的group的数据
            # properties = properties_groups(sch)
            results = {}
            properties = {}
            for key, value in sch["properties"].items():
                if 'items' in value:
                    properties[key] = re.search(r"/([^/]+)$", value['items']['$ref']).group(1)
                else:
                    properties[key] = re.search(r"/([^/]+)$", value['$ref']).group(1)

            for key, value in properties.items():
                results[key] = sch["$defs"][value]
            return results

        def merge_value(groups, jsons, definitions) -> list[dict]:
            # 将 groups的参数，同导出的json一起合并, 用于前端显示
            result = []
            for key, value in groups["properties"].items():
                # deal with exclude 
                if key in jsons and jsons[key] == 0xABCDEF:
                    continue

                item = {}
                item["name"] = key
                item["title"] = value["title"] if "title" in value else inflection.underscore(key)
                if "description" in value:
                    item["description"] = value["description"]
                # ★ 不能直接 value["default"] —— pydantic 的 model_json_schema()
                #   里**带 `$ref` 的属性没有 `default` 键**(默认值在 `$defs` 里),
                #   直接取会 `KeyError: 'default'` -> 接口 500。
                #
                #   触发条件: 顶层组的属性是 `$ref`(如 `Script` 的
                #   device/error/optimization/anti_ban 全是指向 $defs 的引用)。
                #   于是点「脚本」菜单 -> `/{script}/Script/args` -> 500。
                #
                #   ★ 这是**原有 bug**(生产版同样代码), 不是本次改造引入的。
                default_value = value.get("default", jsons.get(key, None))
                item["default"] = default_value
                item["value"] = jsons[key] if key in jsons else default_value
                item["type"] = value["type"] if "type" in value else "enum"
                if '$ref' in value:  # list
                    enum_key = re.search(r"/([^/]+)$", value['$ref']).group(1)
                    # 只有枚举型 $defs 才有 'enum'; 结构体没有 -> 别硬取
                    item["enumEnum"] = definitions.get(enum_key, {}).get("enum", [])
                # if 'allOf' in value:
                #     enum_key = re.search(r"/([^/]+)$", value['allOf'][0]['$ref']).group(1)
                #     item["enumEnum"] = definitions[enum_key]["enum"]
                result.append(item)
            return result

        schema = task.model_json_schema()
        groups = extract_groups(schema)
        groups_value = groups.copy()

        result: dict[str, list] = {}
        for key, value in task.model_dump(context={'hide': True}).items():
            if key not in groups:
                for group_name in groups.keys():
                    if group_name in key:
                        groups_value[key] = groups[group_name]
            # ★ 同上: 找不到对应 group 时**跳过**该键, 而不是 KeyError。
            #   (现有回退逻辑只做"子串匹配", 匹配不到就留着 key 不在
            #    groups_value 里 —— 直接下标取就崩。)
            group = groups_value.get(key)
            if group is None:
                logger.warning(
                    f'script_task({task.__class__.__name__}): '
                    f'字段 {key!r} 找不到对应的 schema 组, 已跳过')
                continue
            result[key] = merge_value(group, value, schema["$defs"])

        return result

    def script_set_arg(self, task: str, group: str, argument: str, value) -> bool:
        # 验证参数
        task = convert_to_underscore(task)
        group = convert_to_underscore(group)
        argument = convert_to_underscore(argument)

        # pandtic验证
        if isinstance(value, str) and len(value) == 8:
            try:
                value = datetime.strptime(value, '%H:%M:%S').time()
            except ValueError:
                pass
        if isinstance(value, str) and len(value) == 11:
            try:
                date_time = datetime.strptime(value, '%d %H:%M:%S')
                value = TimeDelta(days=date_time.day, hours=date_time.hour, minutes=date_time.minute, seconds=date_time.second)
            except ValueError:
                pass
        if isinstance(value, str) and len(value) == 19:
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                pass
        if isinstance(value, str) and value == 'true':
            value = True
        if isinstance(value, str) and value == 'false':
            value = False

        task_object = getattr(self, task, None)
        group_object = getattr(task_object, group, None)
        if group_object is None:  # deal list
            matchs = re.findall(r'\d+', group)
            index = int(matchs[-1]) - 1 if matchs else None
            task_object_list = list(dict(task_object))
            for k, v in dict(task_object).items():
                if k not in group:
                    continue
                group_object = v[index] if group_object is None else None
        argument_object = getattr(group_object, argument, None)

        if argument_object is None:
            logger.error(f'Set arg {task}.{group}.{argument}.{value} failed')
            return False

        # XXX temp implementation to enable oasx control the datetime configuration globally rather than a single task
        if task == "restart" and group == "task_config" and argument == "reset_task_datetime_enable" and value == True:
            date_time = self.restart.task_config.reset_task_datetime
            logger.info(f"reset_task_datetime={date_time}")
            self.reset_datetime_for_all_enabled_tasks(date_time)

        # 设置参数
        try:
            setattr(group_object, argument, value)
            logger.info(f'Set arg {self.config_name}.{task}.{group}.{argument}.{value}')
            self.save()  # 我是没有想到什么方法可以使得属性改变自动保存的
            return True
        except ValidationError as e:
            logger.error(e)
            return False

    def gui_common_groups(self, min_tasks: int = 2) -> list:
        """
        找出被多个任务重复使用的字段分组("公共分组")。

        动机: 实测 56 个任务共下发 1402 个字段, 其中 4 类公共分组占了 60.9% ——
        scheduler 一个 10 字段分组就被逐字复制了 54 份。用户想在多个任务上用
        同一设置时, 只能逐个页面改。此方法为"改一处、多任务生效"提供依据。

        :param min_tasks: 至少被多少个任务使用才算公共分组
        :return: [{group, task_count, tasks, fields:[{name,title,description,type}]}]
                 按 task_count 降序
        """
        info: Dict[str, Any] = {}
        for task_name, value in self.model_dump().items():
            if not isinstance(value, dict):
                continue
            task_object = getattr(self, task_name, None)
            if task_object is None:
                continue
            for group_name, group_value in value.items():
                if not isinstance(group_value, dict):
                    continue
                group_object = getattr(task_object, group_name, None)
                if group_object is None or not isinstance(group_object, BaseModel):
                    continue
                item = info.setdefault(group_name, {'tasks': set(), 'fields': {}})
                item['tasks'].add(task_name)
                for field_name in group_value.keys():
                    if field_name in item['fields']:
                        continue
                    f_info = type(group_object).model_fields.get(field_name)
                    desc = getattr(f_info, 'description', '') if f_info else ''
                    item['fields'][field_name] = {
                        'name': field_name,
                        'title': inflection.underscore(field_name),
                        'description': desc,
                    }
        out = []
        for group_name, item in info.items():
            if len(item['tasks']) < min_tasks:
                continue
            out.append({
                'group': group_name,
                'task_count': len(item['tasks']),
                'tasks': sorted(item['tasks']),
                'fields': list(item['fields'].values()),
            })
        out.sort(key=lambda x: -x['task_count'])
        return out

    def set_common_arg(self, group: str, argument: str, value,
                       only_tasks: list = None,
                       exclude_tasks: list = None) -> dict:
        """
        把某个公共分组下的某个参数**一次写入所有引用该分组的任务**。

        只在该任务确实含有这个分组时才写(避免把同名字段误写到别的语义上);
        每个任务单独 try, 某个任务失败不影响其他任务。

        :param group: 分组名(下划线形式, 如 'scheduler')
        :param argument: 字段名(下划线形式, 如 'float_time')
        :param value: 新值
        :param only_tasks: 只写这些任务(下划线形式)
        :param exclude_tasks: 排除这些任务
        :return: {'changed': [任务...], 'failed': [{'task','error'}...],
                  'skipped': [任务...], 'total': int}
        """
        only = {convert_to_underscore(t) for t in only_tasks} if only_tasks else None
        skip = {convert_to_underscore(t) for t in exclude_tasks} if exclude_tasks else set()

        changed, failed, skipped = [], [], []
        for task_name, task_value in self.model_dump().items():
            if not isinstance(task_value, dict) or group not in task_value:
                continue
            if not isinstance(task_value.get(group), dict):
                continue
            if only is not None and task_name not in only:
                continue
            if task_name in skip:
                skipped.append(task_name)
                continue

            group_object = getattr(getattr(self, task_name, None), group, None)
            if group_object is None or not isinstance(group_object, BaseModel):
                skipped.append(task_name)
                continue
            field_info = type(group_object).model_fields.get(argument)
            if field_info is None:
                skipped.append(task_name)
                continue

            try:
                # 先做一次显式校验: pydantic 默认**不在赋值时校验**
                # (ConfigBase 未设 validate_assignment), 若直接 setattr,
                # 越界的值会被静默写进配置。用 model_validate 走一遍类型与
                # 约束(如 priority 的 ge/le、枚举取值)。
                validated = self._validate_arg_value(field_info, value)
                setattr(group_object, argument, validated)
                changed.append(task_name)
            except (ValidationError, ValueError, TypeError) as exc:
                failed.append({'task': task_name, 'error': str(exc)[:200]})
            except Exception as exc:
                failed.append({'task': task_name,
                               'error': f'{type(exc).__name__}: {exc}'[:200]})

        if changed:
            self.save()
            logger.info(f'Set common arg {group}.{argument}={value!r} '
                        f'for {len(changed)} tasks: {changed[:8]}'
                        f'{"..." if len(changed) > 8 else ""}')
        return {'changed': changed, 'failed': failed,
                'skipped': skipped, 'total': len(changed)}

    @staticmethod
    def _validate_arg_value(field_info, value):
        """
        按字段的注解与约束校验并转换一个值。

        为什么需要: pydantic 默认只在**构造**时校验, 赋值(setattr)不校验 ——
        ConfigBase 未设 validate_assignment, 因此直接赋值会把越界值(如 priority
        取 999)静默写进配置。这里显式跑一遍模型校验, 让调用方能拿到 ValidationError。

        :return: 规范化后的值
        :raises pydantic.ValidationError: 值不合法时
        """
        from pydantic import create_model
        probe = create_model('_ArgProbe', __config__=None,
                             v=(field_info.annotation, field_info))
        return probe(v=value).v

    def copy_script_task(self, task_name: str, source_task: BaseModel) -> bool:
        model_task_name = convert_to_underscore(task_name)
        try:
            setattr(self, model_task_name, source_task)
            self.save()
            logger.info(f'Copy task {model_task_name} success')
            return True
        except ValidationError as e:
            logger.error(e)
            return False

    def copy_task_group(self, task_name: str, group_name: str, source_task: BaseModel) -> bool:
        model_task_name = convert_to_underscore(task_name)
        model_group_name = convert_to_underscore(group_name)
        task_object = getattr(self, model_task_name, None)
        if not task_object:
            return False
        source_group_obj = getattr(source_task, model_group_name, None)
        if not source_group_obj:
            return False
        try:
            setattr(task_object, model_group_name, source_group_obj)
            self.save()
            logger.info(f'Copy task group {model_task_name}.{model_group_name} success')
            return True
        except ValidationError as e:
            logger.error(e)
            return False

    def replace_next_run(self, d, dt: datetime):
        for k, v in d.items():
            if isinstance(v, dict):
                self.replace_next_run(v, dt=dt)
            elif k == "next_run":
                d[k] = dt
                # convert value to datetime if it's a str
                if isinstance(v, str):
                    current_time = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
                    if current_time != dt:
                        d[k] = dt.strftime("%Y-%m-%d %H:%M:%S")
                # already a datetime value
                elif isinstance(v, datetime) and v != dt:
                    d[k] = dt.strftime("%Y-%m-%d %H:%M:%S")

    def reset_datetime_for_all_enabled_tasks(self, task_datetime: datetime):
        logger.warn(f"trying to reset datetime of all tasks to: {task_datetime}")
        # logger.info(f"current config: {self.dict()}")
        data = self.dict()
        self.replace_next_run(data, task_datetime)
        # logger.info(f"new config: {data}")

        # write to json config  file
        self.write_json(self.config_name, data)

        # reload from the newly modified json config file
        data = self.read_json(self.config_name)
        super().__init__(**data)


if __name__ == "__main__":
    try:
        c = ConfigModel("oas1")
    except ValidationError as e:
        print(e)
        c = ConfigModel()

    print(c.script_task('GuildBanquet'))



# ---------------------------------------------------------------------------
# 动态构造 ConfigModel
#
# `_ConfigModelBase` 提供 `__init__` / `gui_args` / `save` 等方法, 字段则由
# `create_model` 注入。这样既保留全部方法, 又不必手写字段声明。
# ---------------------------------------------------------------------------
ConfigModel = create_model(
    'ConfigModel',
    __base__=_ConfigModelBase,
    **_FIELDS,
)
