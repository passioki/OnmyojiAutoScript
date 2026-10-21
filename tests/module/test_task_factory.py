# -*- coding: utf-8 -*-
"""★★ 守卫：「新建任务」工厂（`module/task_factory.py` · SPEC §1.16 `NT1`~`NT4`）。

## ★ 这条守卫要证明的事（= 用户要的"新建任务 → **测试**"里的"测试"）

★ 用户 [10-14] 原话：
> "**先做最小代码验证，跑通整个流程**" ⇒ ★ "跑通**新建任务、测试、运行**这个流程"

★ 本文件证明**前两步**：
  ① ★ **新建**：4 个文件**原子**落盘（★ 失败回滚、★ 语法自检）
  ② ★ **测试**：新任务被**系统真的认出来** ——
     ★ `task_catalog.get_spec()` 找到它（`meta.py` 契约）
     ★ 它的 `config.py` 里真有 `ConfigBase` 子类（配置节点契约）
     ★ 它的 `script_task.py` 里真有 `class ScriptTask` + `run()`（执行契约）
     ★ `docs/flows/README.md` 里**自动登记**了一行（★ 否则流程图守卫会红）
★ ★ **"运行"由用户在实机点**（用户 [10-14] 裁定）⇒ ★ 本守卫**不碰设备**。

## ★ 怎么保证不空转（本项目铁律）

★ 断言分两层：★ **临时目录**里验"落盘 + 回滚"；★ **真 `tasks/`** 里验"系统认识它"
  ⇒ ★ 后者一旦坏掉（例：`ConfigBase` 忘了继承）**立刻变红**，不会只查源码文本。
★ ★ 且**两次注入验证**都做过真红（★ 见台账 §D.8）。
"""
import ast
import importlib.util
import logging
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

from module import task_factory as TF  # noqa: E402

#: ★ 真 `tasks/` 下用的探针名（★ 用完**必删** —— `finally` 里）
PROBE = 'FlowProbeDemo'
PROBE_ZH = '流程探针'


@pytest.fixture()
def tmp_root(tmp_path):
    """★ 一个假的 `tasks/` 根（★ 只测落盘与回滚，不碰真仓库）。"""
    root = tmp_path / 'tasks'
    root.mkdir()
    return root


# ────────────────────────────────────────── ① 渲染（模板自检）
def test_render_replaces_every_token():
    """★ 模板里**不许**留 `__XXX__` 占位符（★ 那会变成语法错误或错名字）。"""
    files = TF.render_files('MyNewTask', '我的新任务', 'FIXED', 'DAILY')
    assert set(files) == set(TF.FILES), f'★ 应当是 4 个文件，实际 {sorted(files)}'
    for fn, text in files.items():
        assert '__NAME' not in text and '__CATEGORY__' not in text \
            and '__PERIOD__' not in text, f'★ {fn} 里还有没替换的占位符'
        ast.parse(text)      # ★ 语法必须过
    assert "task='MyNewTask'" in files['meta.py']
    assert "name_zh='我的新任务'" in files['meta.py']
    assert 'Category.FIXED' in files['meta.py']
    assert 'Period.DAILY' in files['meta.py']
    # ★★ 两条被"库存类守卫"逼出来的合同（★ 实测踩过：新任务一建就把它们撞红）
    assert 'window=AvailabilityWindow(' in files['meta.py'], (
        '★★ 必须显式声明 window —— 否则 `test_every_task_has_window` 变红'
        '（Period.NONE 推导不出窗口）')
    assert 'list_pos=__LIST_POS__' not in files['meta.py']
    assert 'list_pos=7' in TF.render_files('MyNewTask', '我的新任务', 'FIXED',
                                           'DAILY', 7)['meta.py'], (
        '★ list_pos 必须由工厂注入（★ 守卫要求全局唯一）')
    assert 'class MyNewTask(ConfigBase)' in files['config.py']
    assert 'my_new_task_config' in files['config.py'], '★ 分组字段名要用 snake_case'
    assert 'class ScriptTask(GameUi)' in files['script_task.py']
    assert "task='MyNewTask'" in files['script_task.py']


def test_skeleton_has_example_recognition_but_no_clicking():
    """★★ `NT3`：★ 骨架**必须带示例识别**，★ 且**绝不含乱点屏幕的动作**。

    ★ 依据：★ 用户裁定"**2需要示例识别**" + ★ 骨架若"会乱点"，
      ★ 用户在没标好素材时就会**误操作账号**。
    """
    text = TF.render_files('MyNewTask', '我的新任务')['script_task.py']
    assert 'self.appear(' in text, '★★ 骨架必须带示例识别（用户要求）'
    for banned in ('self.click(', 'appear_then_click(', 'self.swipe(',
                   'ui_click(', 'device.click('):
        assert banned not in text, f'★★ 骨架不许出现会动屏幕的调用：{banned}'


# ────────────────────────────────────────── ② 命名校验（NT2）
@pytest.mark.parametrize('bad', [
    '', 'lower', 'myTask', '1Task', 'has space', '中文任务', 'A/B', '../Evil',
    'Task-1', 'Task_1', '_Private', 'Component', 'General', 'ScriptTask',
])
def test_validate_name_rejects_bad_names(bad, tmp_root):
    """★ `NT2`：一批**必须要拒**的名字（★ 含路径穿越与保留名）。"""
    assert TF.validate_name(bad, tmp_root), f'★ `{bad}` 应当被拒'


@pytest.mark.parametrize('good', ['MyNewTask', 'A1', 'FlowProbeDemo', 'Xy9Z'])
def test_validate_name_accepts_good_names(good, tmp_root):
    """★ 正常的大驼峰名字必须放过。"""
    assert TF.validate_name(good, tmp_root) == ''


def test_validate_name_is_case_insensitive_on_windows(tmp_root):
    """★ `Rest` 与 `ReSt` 在 Windows 上是**同一个目录** ⇒ ★ 必须拒。

    ⚠ 注意：★ 用**大小写混合**的 `ReSt` 来测（★ 全小写的 `rest` 会被
      "必须大驼峰"那条先拦下 ⇒ ★ 就测不到"大小写不敏感"这件事了）。
    """
    (tmp_root / 'Rest').mkdir()
    assert TF.validate_name('ReSt', tmp_root), '★ 大小写不敏感（Windows 同目录）'
    assert TF.validate_name('REST', tmp_root)


def test_path_traversal_is_impossible(tmp_root):
    """★★ `NT4`：★ 名字里的路径分隔符必须被拒（★ 否则能写到 `tasks/` 之外）。"""
    before = set(tmp_root.iterdir())
    res = TF.create_task('../../evil', '坏', tasks_root=tmp_root)
    assert res.ok is False
    assert set(tmp_root.iterdir()) == before, '★ `tasks/` 下不该出现任何东西'


# ────────────────────────────────────────── ③ 原子落盘 + 回滚（NT1）
def test_create_writes_four_files(tmp_root):
    """★ `NT1`：4 个文件都要在，且都是合法 Python。"""
    res = TF.create_task('MyNewTask', '我的新任务', 'FIXED', 'DAILY',
                         tasks_root=tmp_root, register_flow=False)
    assert res.ok is True, res.error
    d = tmp_root / 'MyNewTask'
    assert d.is_dir()
    for fn in TF.FILES:
        assert (d / fn).is_file(), f'★ 缺文件 {fn}'
        ast.parse((d / fn).read_text(encoding='utf-8'))
    assert not (tmp_root / '.MyNewTask.creating').exists(), '★ 临时目录必须已被移走'


def test_failed_create_leaves_nothing_behind(tmp_root, monkeypatch):
    """★★★ `NT1` 核心：★ 中途失败 ⇒ ★ **不留半成品目录**。

    ★ 为什么要紧：★ 半成品目录会让 `config_model._discover_config_classes()`
      ★ 发现一个**坏配置类** ⇒ ★★ **整个后端起不来**（SPEC §1.16 NT1）。
    """
    real_replace = TF.os.replace

    def boom(src, dst):
        raise OSError('注入的失败：模拟"落地那一刻"炸掉')

    monkeypatch.setattr(TF.os, 'replace', boom)
    res = TF.create_task('MyNewTask', '我的新任务', tasks_root=tmp_root,
                         register_flow=False)
    assert res.ok is False
    assert not (tmp_root / 'MyNewTask').exists(), '★★ 不许留 `MyNewTask/`'
    assert not (tmp_root / '.MyNewTask.creating').exists(), '★★ 不许留临时目录'
    monkeypatch.setattr(TF.os, 'replace', real_replace)
    assert list(tmp_root.iterdir()) == [], '★ 失败后 `tasks/` 应当是空的'


def test_bad_template_is_caught_before_writing(tmp_root, monkeypatch):
    """★ 模板自己坏掉 ⇒ ★ **落盘之前**就报错（★ 不留坏文件）。"""
    monkeypatch.setitem(TF._TEMPLATES, 'config.py', 'def broken(:\n')
    res = TF.create_task('MyNewTask', '我的新任务', tasks_root=tmp_root,
                         register_flow=False)
    assert res.ok is False
    assert '语法错误' in res.error
    assert list(tmp_root.iterdir()) == []


def test_dry_run_does_not_touch_disk(tmp_root):
    """★ `dry_run` 只渲染 + 自检，★ 不落盘。"""
    res = TF.create_task('MyNewTask', '我的新任务', tasks_root=tmp_root,
                         register_flow=False, dry_run=True)
    assert res.ok is True
    assert list(tmp_root.iterdir()) == []


# ────────────────────────────────────────── ④ ★★ 真·系统发现（"测试"的实质）
@pytest.fixture()
def probe():
    """★ 在**真 `tasks/`** 下建一个探针任务，跑完**必删**（含台账那行）。

    ★★★ [10-15] T0-1（坑 **P18 的真正根因**）：备份/还原必须**按字节** ★★★

    ★ 旧代码：`before = index.read_text(encoding='utf-8')` ＋ 收尾
      `write(before)` —— ★ `read_text` 默认 **universal newlines** ⇒ 备份里
      **CRLF 已经变成 LF**；收尾再 `newline=''` 写回
      ⇒ ★ **整份 `docs/flows/README.md` 被还原成 LF**。
    ★ 在 `core.autocrlf=true` 下 ⇒ ★ **每跑一次这个文件，`git status` 就多一个
      ` M docs/flows/README.md`**（而 `git diff --numstat` **为空**）——
      ★ 也就是说：**幻影脏的真正来源是这个 fixture 的还原**，不只是
      `task_factory._register_in_flow_index` 的写入。
    ⇒ ★ 现在改 `read_bytes()` / `write_bytes()` ⇒ **逐字节**还原。
    """
    from module.config import task_catalog as TC

    d = TF.TASKS_ROOT / PROBE
    index = TF.FLOW_INDEX
    before = index.read_bytes() if index.is_file() else b''
    try:
        res = TF.create_task(PROBE, PROBE_ZH, 'TIMED', 'NONE', register_flow=True)
        assert res.ok is True, f'★ 创建探针失败：{res.error}'
        yield res
    finally:
        shutil.rmtree(d, ignore_errors=True)
        if index.is_file():
            # ★ 按字节还原（★ 不许经过任何换行翻译）
            index.write_bytes(before)
        try:
            TC.reload_specs()
        except Exception:
            pass


def test_probe_is_discovered_by_task_catalog(probe):
    """★★★ 核心：★ 新任务必须被 **`task_catalog`** 认出来（`meta.py` 契约生效）。

    ★ 这就是"**新建**"与"**测试**"之间的那道门：★ `meta.py` 写错一个字段，
      ★ 任务就"存在但不存在"（界面里没有、调度器不认）。
    """
    from module.config import task_catalog as TC

    TC.reload_specs()
    spec = TC.get_spec(PROBE)
    assert spec is not None, f'★★ `{PROBE}` 没被 task_catalog 发现（meta.py 契约没生效）'
    assert spec.name_zh == PROBE_ZH, f'★ 中文名不对：{spec.name_zh!r}'
    assert spec.task == PROBE
    # ★★ 这一条守的是**第二个视图**：`all_tasks()` 读的是 `task_catalog_data.json`
    #   再**合并** meta.py 发现（`task_catalog.py:760`），缓存由 `reload()` 清。
    #   ⚠ ★ 只清 `reload_specs()` 的话，这里会红（★ 我第一版工厂就是这么错的，
    #     而且**单跑测试是绿的** —— 因为在同一个进程里前序用例已经先调过 `all_tasks()`）。
    assert PROBE in [t for t in TC.all_tasks()], (
        '★★ `all_tasks()` 看不到新任务 —— ★ 说明 `task_catalog.reload()` 没调 '
        '（只调 `reload_specs()` 不够：那是另一个缓存）')


def test_probe_config_class_is_real(probe):
    """★★ 新任务的 `config.py` 里必须真有 `ConfigBase` 子类（且带 `scheduler`）。"""
    path = TF.TASKS_ROOT / PROBE / 'config.py'
    spec = importlib.util.spec_from_file_location(f'_probe_{PROBE}_config', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)      # ★ 真 import（★ 不是查文本）
    from tasks.Component.config_base import ConfigBase
    cls = getattr(mod, PROBE, None)
    assert cls is not None, f'★ `config.py` 里没有与目录同名的类 `{PROBE}`'
    assert issubclass(cls, ConfigBase), '★ 必须继承 ConfigBase（否则没有配置节点）'
    assert 'scheduler' in cls.model_fields, '★ 必须有 `scheduler`（调度契约）'


def test_probe_script_task_contract(probe):
    """★★ 新任务的 `script_task.py` 必须满足执行契约：`class ScriptTask` + `run()`。"""
    path = TF.TASKS_ROOT / PROBE / 'script_task.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    names = [c.name for c in classes]
    assert 'ScriptTask' in names, f'★ 类名必须是 `ScriptTask`（script.py:848-852 写死），实际 {names}'
    st = next(c for c in classes if c.name == 'ScriptTask')
    funcs = [n.name for n in st.body if isinstance(n, ast.FunctionDef)]
    assert 'run' in funcs, f'★ 必须实现 `run()`，实际 {funcs}'


def test_probe_is_registered_in_flow_index(probe):
    """★★ 新任务必须**自动登记**在流程图台账里（★ 否则 `test_task_flow_docs` 变红）。"""
    text = TF.FLOW_INDEX.read_text(encoding='utf-8')
    assert f'`{PROBE}`' in text, '★ 新建任务没有登记到 `docs/flows/README.md`'
    assert '新建任务待补' in text


def test_probe_registration_keeps_flow_guard_green(probe):
    """★★★ 端到端：★ 新建完，**流程图守卫必须还是绿的**（★ 这是"不返工"的关键）。"""
    import subprocess
    r = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/test_task_flow_docs.py', '-q',
         '--no-header', '-p', 'no:cacheprovider'],
        cwd=str(REPO), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, (
        '★★★ 新建任务之后流程图守卫变红了 —— '
        '★ 说明"登记"这一步没做对：\n' + (r.stdout or '')[-1500:] + (r.stderr or '')[-500:])


# ---------------------------------------------------------------- 行尾保留（坑 P18）
def test_flow_index_registration_keeps_line_endings(tmp_path):
    """★★★ [10-15] T0-1 / 坑 **P18 根治**：登记新任务时**必须保留原行尾**。

    ## 缺陷（[10-15] 实测，可复现）

    ★ 旧实现 `path.read_text(encoding='utf-8')` 走的是 **universal newlines**
    （`CRLF → LF`），而写回用的是 `newline=''`（不翻译）
    ⇒ ★ **整份 `docs/flows/README.md` 的每一个换行都被改成了 LF**。
    ★ 在 `core.autocrlf=true` 的仓库里 ⇒ ★ **每跑一次**
    `tests/test_task_flow_docs.py` ＋ `tests/module/test_task_factory.py`，
    `git status` 就多一个 ` M docs/flows/README.md`，而 `git diff --numstat`
    **为空**（★ 纯行尾幻影）⇒ ★ 每轮都要手动 `git checkout --`。

    ## 这条守卫

    ★ 造一个 **CRLF** 的临时台账 ⇒ 登记一行 ⇒ ★ **文件必须仍然是纯 CRLF**
    （★ 既不许变 LF，也不许变成"混行尾"）。
    ★ 注入验证：把读/写改回"`read_text` + `\\n` 拼接" ⇒ 本条**必须变红**。
    """
    index = tmp_path / 'README.md'
    # ★ 与真台账同形：表头必须同时含「状态」「待补理由」（`__register_in_flow_index` 靠它定位）
    index.write_bytes(
        ('# 流程图台账\r\n'
         '\r\n'
         '| 任务 | 状态 | 待补理由 |\r\n'
         '|---|---|---|\r\n'
         '| `RealmRaid`（个人突破）| ✅ 已完成 | — |\r\n').encode('utf-8'))

    ok = TF._register_in_flow_index('ProbeTask', '探针', index_path=index)
    assert ok, '★ 没找到台账表 ⇒ 登记失败（表头形状变了？）'

    raw = index.read_bytes()
    assert b'\r\n' in raw, '★★ P18 复发：登记后 CRLF 全没了（整份文件被改成 LF）'
    assert b'\n' not in raw.replace(b'\r\n', b''), (
        '★★ 登记后出现**裸 LF**（混合行尾）—— 行尾保住了，但"一致性"没保住')
    assert '`ProbeTask`' in raw.decode('utf-8'), '★ 没登记进去'
