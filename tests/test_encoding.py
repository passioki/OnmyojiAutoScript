"""
验证标准输出的 UTF-8 编码设置(module/base/encoding.py)。

背景:
    Windows 中文版的系统 ANSI 代码页是 936(GBK), 而现代终端与 OASX 按 UTF-8 读取。
    Python 的标准输出被重定向(非终端)时按 locale 首选编码即 GBK 写出, 造成
    "写 GBK / 读 UTF-8" 的中文乱码(实测: 由 OASX 启动后端时日志中文乱码)。
    日志文件本身无此问题 —— module/logger.py 写文件时显式用了 encoding='utf-8'。

这些测试锁定修复不会被回退。
"""
import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENCODING_MODULE = REPO_ROOT / 'module' / 'base' / 'encoding.py'

# 应当在自己的最顶部、早于任何可能间接导入 module.logger 的语句完成设置
# 注: 旧的内置 PySide6 GUI 入口 gui.py 已移除(见 docs 里的架构说明), 因此不再列入。
ENTRY_POINTS = ('server.py', 'script.py')


# --------------------------------------------------------------------------
# 模块本身的行为
# --------------------------------------------------------------------------
def test_setup_utf8_stdio_is_idempotent():
    from module.base.encoding import setup_utf8_stdio

    assert setup_utf8_stdio() is True
    assert setup_utf8_stdio() is True


def test_setup_utf8_stdio_configures_both_streams():
    from module.base.encoding import setup_utf8_stdio

    setup_utf8_stdio()
    assert sys.stdout.encoding.lower().replace('-', '') == 'utf8'
    assert sys.stderr.encoding.lower().replace('-', '') == 'utf8'


def test_setup_utf8_stdio_exports_environment_for_children():
    """multiprocessing 子进程需要靠环境变量继承同样的编码设置。"""
    from module.base.encoding import setup_utf8_stdio

    setup_utf8_stdio()
    assert os.environ.get('PYTHONIOENCODING') == 'utf-8'


def test_setup_utf8_stdio_does_not_override_explicit_environment(monkeypatch):
    """
    若调用方已显式指定 PYTHONIOENCODING, 不应被覆盖。

    通过重新加载模块来绕过其内部的幂等标记。
    """
    import importlib

    import module.base.encoding as enc

    monkeypatch.setenv('PYTHONIOENCODING', 'gbk')
    reloaded = importlib.reload(enc)
    try:
        reloaded.setup_utf8_stdio()
        assert os.environ['PYTHONIOENCODING'] == 'gbk'
    finally:
        # 复原模块状态, 避免影响后续测试
        monkeypatch.undo()
        importlib.reload(enc)


def test_setup_utf8_stdio_reports_true():
    from module.base.encoding import setup_utf8_stdio

    assert setup_utf8_stdio() is True


# --------------------------------------------------------------------------
# 入口点的接入方式
# --------------------------------------------------------------------------
@pytest.mark.parametrize('entry', ENTRY_POINTS)
def test_entry_point_calls_setup_utf8_stdio(entry):
    source = (REPO_ROOT / entry).read_text(encoding='utf-8')
    assert 'setup_utf8_stdio()' in source, f'{entry} 未调用 setup_utf8_stdio()'


@pytest.mark.parametrize('entry', ('server.py', 'script.py'))
def test_logger_import_comes_after_encoding_setup(entry):
    """
    module.logger 会在导入期创建 ConsoleHandler 并绑定当时的 sys.stdout,
    因此它必须在 setup_utf8_stdio() 之后才被导入, 否则导入期的输出仍会乱码。
    """
    source = (REPO_ROOT / entry).read_text(encoding='utf-8')
    setup_at = source.find('setup_utf8_stdio()')
    assert setup_at != -1, f'{entry} 未调用 setup_utf8_stdio()'

    logger_at = source.find('from module.logger import logger')
    if logger_at != -1:
        assert setup_at < logger_at, \
            f'{entry} 中 module.logger 在编码设置之前被导入'


def test_logger_file_handler_keeps_explicit_utf8():
    """
    日志文件侧本来是正确的(显式 encoding='utf-8'), 修复不应触碰它。
    """
    source = (REPO_ROOT / 'module' / 'logger.py').read_text(encoding='utf-8')
    assert "encoding='utf-8'" in source


# --------------------------------------------------------------------------
# 启动脚本
# --------------------------------------------------------------------------
@pytest.mark.parametrize('script_name', ('oas-server.bat', 'oas-backend.bat'))
def test_launcher_sets_utf8_environment(script_name):
    """
    批处理应在调用 python 之前设置编码环境变量, 使直起的进程也正确。

    注意: oas-server.bat 与 oas-backend.bat 被 .gitignore 忽略(上游如此),
    因此这两个文件在代码仓库中可能不存在。此测试仅在其存在时校验,
    真正兜底的是 module/base/encoding.py 的 setup_utf8_stdio()。

    (原先还包含 oas-gui.bat —— 它随旧的内置 PySide6 GUI 一起移除了。)
    """
    path = REPO_ROOT / 'deploy' / 'launcher' / script_name
    if not path.exists():
        pytest.skip(f'{script_name} 不存在(可能被 gitignore)')

    source = path.read_text(encoding='utf-8', errors='ignore')

    assert 'PYTHONIOENCODING=utf-8' in source, f'{script_name} 未设置 PYTHONIOENCODING'

    # 设置必须出现在启动 python 之前
    set_at = source.find('PYTHONIOENCODING=utf-8')
    py_at = None
    for m in re.finditer(r'^\s*(start\s+)?pythonw?\s+\S+', source, re.MULTILINE):
        py_at = m.start()
        break
    if py_at is not None:
        assert set_at < py_at, f'{script_name} 中编码设置晚于 python 启动'


def test_encoding_fix_does_not_depend_on_launcher_scripts():
    """
    核心保证: 即使批处理未设置环境变量(例如被 gitignore 而未随仓库分发),
    Python 侧的 setup_utf8_stdio() 也必须能独立完成修复。
    """
    import importlib

    import module.base.encoding as enc

    previous = os.environ.pop('PYTHONIOENCODING', None)
    previous_utf8 = os.environ.pop('PYTHONUTF8', None)
    try:
        reloaded = importlib.reload(enc)
        assert reloaded.setup_utf8_stdio() is True
        assert sys.stdout.encoding.lower().replace('-', '') == 'utf8'
        assert os.environ.get('PYTHONIOENCODING') == 'utf-8'
    finally:
        if previous is not None:
            os.environ['PYTHONIOENCODING'] = previous
        else:
            os.environ.pop('PYTHONIOENCODING', None)
        if previous_utf8 is not None:
            os.environ['PYTHONUTF8'] = previous_utf8
        importlib.reload(enc)
