# -*- coding: utf-8 -*-
"""`running_task` 命名契约与配置污染修复的回归测试。

覆盖两个真实故障:

1. `BaseTask.get_task_name()` 曾把 config 里的 running_task 当校验依据, 不一致就抛
   ScriptError, 经 script.py 的 exit(1) 使整个脚本进程退出。触发场景是
   `_wait_close_game()` 内 `self.run('Restart')` —— 此时 model 残留上一个任务名。
   现在应以任务类所在目录名为准, 只在日志里告警。

2. `Config.task_delay()` 开头会 reload(), 把内存里的 running_task 换成磁盘旧值,
   随后 save() 把脏值写回文件。现在 reload 前后需要保护该运行时字段。

注意: `ConfigModel.__setattr__` 有"改属性即自动落盘"的行为, 因此不能用"改内存再看
reload 结果"的方式构造断言 —— 磁盘会被同步写成新值。要制造内存/磁盘不一致, 必须
先加载配置, 再直接改写磁盘文件。
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEMPLATE = REPO_ROOT / 'config' / 'template.json'


@pytest.fixture()
def temp_config(cfg_name='unit_cfg'):
    """把仓库的 template.json 复制到临时目录, 切 cwd, 返回 (tmpdir, cfg_name)。"""
    if not TEMPLATE.exists():
        pytest.skip('缺少 config/template.json, 无法构造测试配置')
    tmp = Path(tempfile.mkdtemp(prefix='oas_cfg_'))
    old_cwd = os.getcwd()
    (tmp / 'config').mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE, tmp / 'config' / f'{cfg_name}.json')
    os.chdir(tmp)
    try:
        yield tmp, cfg_name
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)


def _set_disk_running_task(tmp: Path, cfg_name: str, value: str) -> None:
    """直接改写磁盘 json 里的 running_task, 不经过 pydantic, 制造内存/磁盘不一致。"""
    path = tmp / 'config' / f'{cfg_name}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['running_task'] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


# ---------------------------------------------------------------------------
# 1. get_task_name 语义
# ---------------------------------------------------------------------------
def test_get_task_name_prefers_path_and_warns_on_mismatch(monkeypatch):
    """model 与目录名不一致时, 返回目录名而不是抛异常, 并记录告警。"""
    from tasks.base_task import BaseTask
    from module.logger import logger

    class FakeModel:
        def __init__(self):
            self.running_task = 'FrogBoss'   # 实例属性, 与 pydantic 行为一致

    class FakeConfig:
        def __init__(self):
            self.model = FakeModel()

    task = BaseTask.__new__(BaseTask)
    task.config = FakeConfig()

    monkeypatch.setattr(
        'inspect.getfile',
        lambda _cls: str(REPO_ROOT / 'tasks' / 'DemonEncounter' / 'script_task.py'),
    )
    warnings = []
    monkeypatch.setattr(logger, 'warning', lambda msg, *a, **k: warnings.append(str(msg)))

    name = task.get_task_name()

    assert name == 'DemonEncounter', f'应以目录名为准, 实际得到 {name}'
    assert any('Task name mismatch' in w for w in warnings), '应记录一次告警'
    assert task.config.model.running_task == 'DemonEncounter', '应顺手修正被污染的值'


def test_get_task_name_returns_path_when_model_empty(monkeypatch):
    """model 为空时返回目录名且不告警。"""
    from tasks.base_task import BaseTask
    from module.logger import logger

    class FakeModel:
        def __init__(self):
            self.running_task = ''

    class FakeConfig:
        def __init__(self):
            self.model = FakeModel()

    task = BaseTask.__new__(BaseTask)
    task.config = FakeConfig()
    monkeypatch.setattr(
        'inspect.getfile',
        lambda _cls: str(REPO_ROOT / 'tasks' / 'Dokan' / 'script_task.py'),
    )
    warnings = []
    monkeypatch.setattr(logger, 'warning', lambda msg, *a, **k: warnings.append(str(msg)))

    assert task.get_task_name() == 'Dokan'
    assert not warnings, f'不应告警, 实际: {warnings}'


def test_get_task_name_does_not_raise_on_mismatch(monkeypatch):
    """这是本次修复的核心: 不一致必须是告警而不是 ScriptError。"""
    from tasks.base_task import BaseTask
    from module.exception import ScriptError
    from module.logger import logger

    class FakeModel:
        def __init__(self):
            self.running_task = 'Restart'

    class FakeConfig:
        def __init__(self):
            self.model = FakeModel()

    task = BaseTask.__new__(BaseTask)
    task.config = FakeConfig()
    monkeypatch.setattr(
        'inspect.getfile',
        lambda _cls: str(REPO_ROOT / 'tasks' / 'FrogBoss' / 'script_task.py'),
    )
    monkeypatch.setattr(logger, 'warning', lambda *a, **k: None)

    try:
        name = task.get_task_name()
    except ScriptError as exc:
        pytest.fail(f'不应再抛 ScriptError: {exc}')
    assert name == 'FrogBoss'


# ---------------------------------------------------------------------------
# 2. task_delay 不再污染 running_task
# ---------------------------------------------------------------------------
def test_task_delay_preserves_running_task(temp_config):
    """task_delay 内部的 reload 不应把内存里的 running_task 换成磁盘旧值。"""
    tmp, cfg_name = temp_config
    from module.config.config import Config

    config = Config(cfg_name)
    # 内存里代表"当前正在跑的任务", 此时若被 reload 覆盖就会变成磁盘值
    config.model.running_task = 'Restart'
    # 直接改磁盘, 制造内存/磁盘不一致
    _set_disk_running_task(tmp, cfg_name, 'FrogBoss')

    # 走真实 task_delay (DemonEncounter 在 template 中必然存在 scheduler)
    config.task_delay(task='DemonEncounter', success=True)

    assert config.model.running_task == 'Restart', (
        f'task_delay 后 running_task 应保持内存值 Restart, 实际 {config.model.running_task}'
    )


def test_reload_alone_does_read_disk_value(temp_config):
    """对照实验: 裸 reload 确实会读回磁盘值, 说明上面的保护是必要的。"""
    tmp, cfg_name = temp_config
    from module.config.config import Config

    config = Config(cfg_name)
    config.model.running_task = 'Restart'
    _set_disk_running_task(tmp, cfg_name, 'FrogBoss')

    config.reload()
    assert config.model.running_task == 'FrogBoss', '裸 reload 应读回磁盘值'
