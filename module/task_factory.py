# -*- coding: utf-8 -*-
"""★★ 「新建任务」工厂（Task Factory）—— `docs/DESIGN-SPEC.md` §1.16 `NT1`~`NT4`。

> ★★ **用户原话（[10-14]）**：
> > "**结合 …annotator 这类 OAS Web 标注工具，进一步集成新建任务的功能。**
> >   **需要彻底了解目前代码的实现，然后设计增删改查复制任务的标准流程…**"
> > "**1.先增   2需要示例识别**"

## ★★ 契约：一个任务 = 4 个约定文件（`tasks/Rest/meta.py:4-9` 是权威说明）

| 文件 | 必需? | 作用 |
|---|---|---|
| `meta.py` | ★★ **必需** | `SPEC = TaskSpec(...)` —— ★ **任务与调度器之间的唯一契约** |
| `config.py` | ⚠ **实测：`GotoMain` 就没有** | 任务配置节点（★ 没有它就没有配置界面）|
| `script_task.py` | ★★ **必需** | ★ 类名必须 `ScriptTask` + 必须实现 `run()`（`script.py:848-852` 写死）|
| `assets.py` | ★ 有素材才需要 | 由 `dev_tools/assets_extract.py` **自动生成** |

## ★★ 本工厂守的四条（`NT1`~`NT4`）

| # | 规则 | 本文件怎么落 |
|---|---|---|
| **NT1** | ★★ **原子创建**：要么全成、要么**全不落盘**（★ 半成品目录会让 `config_model` 发现坏配置类 ⇒ **后端起不来**）| ★ 先写**临时目录** `.‹Name›.creating` ⇒ ★ 逐个 `ast.parse` 校验 ⇒ ★ `os.replace` **原子落地**；★ 任何一步失败就 `rmtree` **回滚**（含 `docs/flows` 登记）|
| **NT2** | ★★ **命名校验在写盘之前**：`[A-Za-z][A-Za-z0-9]*`；★ 拒保留名；★ 拒已存在（Windows 大小写不敏感）| ★ `validate_name()` |
| **NT3** | ★★ **安全空壳 + 示例识别**：★ **绝不含"乱点屏幕"的动作**；`enable=False`；`period=none`；`auto_queue=False` | ★ 模板见下方 `_SCRIPT_TASK` |
| **NT4** | ★★ **只允许在 `tasks/` 下动手**；★ `Name` 必须过 `NT2` ⇒ ★ **路径穿越不可能** | ★ `tasks_root` 固定 + `validate_name` |

★ ★ **额外做了一件"合同"上的事**：创建后**自动在 `docs/flows/README.md` 登记一行** ——
  ★ 因为 `tests/test_task_flow_docs.py` 要求**每个任务都必须在流程图台账里出现**
    （★ 不登记 ⇒ 守卫变红）⇒ ★ 让新任务"生下来就是绿的"。
"""
import ast
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TASKS_ROOT = REPO / 'tasks'
FLOW_INDEX = REPO / 'docs' / 'flows' / 'README.md'

#: ★ `NT2`：**必须大驼峰**（首字母大写 + 只含字母数字）
#: ★ 为什么不能只写 `[A-Za-z][A-Za-z0-9]*`：★ 那样 `rest` / `myTask` **也会被放过**
#:   ⇒ ★ 与现有 55 个任务不一致，★ 且在 Windows 大小写不敏感的文件系统上更容易撞名。
NAME_RE = re.compile(r'^[A-Z][A-Za-z0-9]*$')

#: ★ `NT2`：保留名 —— ★ 与 `module/config/config_model.py:40` 的 `NOT_A_TASK` **同源**，
#: 另加一批"看着像任务、其实不是"的名字。
RESERVED_NAMES = frozenset({
    'Component', 'General',            # ★ config_model.NOT_A_TASK（权威）
    'Base', 'BaseTask', 'Config', 'ConfigBase',
    'Script', 'ScriptTask', 'Template', 'Utils', 'GlobalGame', 'GameUi', 'GameUI',
})

#: ★ 一个任务要落盘的 4 个文件（★ 顺序即写入顺序）
FILES = ('meta.py', 'config.py', 'script_task.py', 'assets.py')

MAX_NAME_LEN = 40


@dataclass
class CreateResult:
    """★ 新建任务的结论（★ 全字段可核查 —— 不返回"裸 True"）。"""

    ok: bool
    name: str = ''
    name_zh: str = ''
    dir: str = ''
    files: list = field(default_factory=list)
    error: str = ''
    registered: bool = False

    def __bool__(self) -> bool:
        return bool(self.ok)


# ────────────────────────────────────────────────────────────── 命名校验（NT2）
def validate_name(name: str, tasks_root: Path = None) -> str:
    """★ `NT2`：**写盘之前**的命名校验。

    :return: ★ `''` = 通过；★ 否则是**给人看的原因**
    """
    root = Path(tasks_root) if tasks_root else TASKS_ROOT
    s = str(name or '').strip()
    if not s:
        return '任务名不能为空'
    if len(s) > MAX_NAME_LEN:
        return f'任务名过长（>{MAX_NAME_LEN} 字符）'
    if not NAME_RE.match(s):
        return ('只允许 `[A-Z][A-Za-z0-9]*`（★ 大驼峰：**首字母大写**、只含字母数字，'
                '与现有 55 个任务一致；★ 不允许小写开头/下划线/空格/中文/路径分隔符）')
    if s in RESERVED_NAMES:
        return f'`{s}` 是**保留名**（不是任务，见 config_model.NOT_A_TASK）'
    if s.lower() in {x.lower() for x in RESERVED_NAMES}:
        return f'`{s}` 与保留名**只差大小写**（Windows 上同目录）'
    try:
        for d in root.iterdir():
            if d.is_dir() and d.name.lower() == s.lower():
                extra = '' if d.name == s else f'（目录实际是 `{d.name}`）'
                return f'`{s}` 已存在{extra} —— ★ Windows 大小写不敏感'
    except OSError:
        pass
    return ''


# ────────────────────────────────────────────────────────────── 模板（NT3）
_META = '''# -*- coding: utf-8 -*-
"""任务自描述 —— `__NAME__`（__NAME_ZH__）。★ 由「新建任务」生成（SPEC §1.16 NT1~NT4）。

★ **这个文件是任务与调度器之间的唯一契约**（权威说明见 `tasks/Rest/meta.py:4-9`）。

## 新增/维护一个任务要做的事

1. ★ 建 `tasks/__NAME__/`（本工厂已建好）并写 4 个文件：
   `meta.py` + `config.py` + `script_task.py` + `assets.py`
2. ★ 标素材：`/tool/annotator` 里标好并保存 ⇒ 保存时**自动重生成** `assets.py`
   （★ 命令行等价物：`python dev_tools/assets_extract.py`）
3. ★ 自查：`python dev_tools/gen_task_catalog.py`（★ 更新 `task_catalog_data.json`）

★ 调度器 / 配置模型 / 前端 schema / i18n 会**自动**获得该任务，无需改任何中心文件。
★ 规范见 `docs/architecture.md` §7（可演进性）。
"""
from datetime import time

from module.config.availability import AvailabilityWindow  # noqa: F401
from module.config.resource import Period  # noqa: F401
from module.config.task_catalog import Category, TaskSpec  # noqa: F401

SPEC = TaskSpec(
    task='__NAME__',
    name_zh='__NAME_ZH__',
    # ★ 类别：FIXED 固定 / TOPPA 突破 / LIMITED 限时 / TIMED 定时
    category=Category.__CATEGORY__,
    # ★★ `auto_queue`：★ 本项目的不变量是 **`auto_queue == NOT countable`**
    #   （"**次数任务不自动进队列，定时任务自动进**" —— 见
    #    `tests/module/config/test_execution_queue.py:test_auto_queue_matches_countable`）
    #   ⇒ ★ 新任务（TIMED、非次数类）**必须** `auto_queue=True`，★ 否则那条守卫变红。
    #   ⚠ **[10-14] 实测订正**：本模板原来写 `auto_queue=False`（想表达"新建后不自动跑"），
    #     但那**违反项目不变量**。★ **安全性不靠它**：★ 真正拦住"新建即乱跑"的是
    #     `scheduler.enable=False`（任务开关）+ 下面 `config.py` 分组里的 `enable=False`。
    auto_queue=True,
    # ★★ `list_pos` 必须**全局唯一**（★ 守卫 `test_list_pos_metadata.py` 强制）
    #   ⇒ ★ 工厂已自动取"当前最大值 + 1"（★ 别手改成 0，那会让守卫变红）
    list_pos=__LIST_POS__,
    # ★ 周期：Period.NONE 临时 / DAILY 每天 / WEEKLY 每周 / MONTHLY 每月
    period=Period.__PERIOD__,
    # ★★ **开放时段必须显式给**（★ 守卫 `test_every_task_has_window.py` 强制：
    #   "所有的定时都有着 window 属性"）—— ★ `Period.NONE` **推导不出**窗口
    #   ⇒ ★ 新任务默认给**全天**；★ 按玩法改成你要的，例
    #   `AvailabilityWindow(True, time(17, 0), time(23, 0))`
    window=AvailabilityWindow(True, time(0, 0), time(23, 59)),
)
'''

_CONFIG = '''# This Python file uses the following encoding: utf-8
"""`__NAME__`（__NAME_ZH__）的任务配置。★ 由「新建任务」生成（SPEC §1.16 NT1~NT4）。"""
from pydantic import BaseModel, Field

from tasks.Component.config_base import ConfigBase
from tasks.Component.config_scheduler import Scheduler


class __NAME__TaskConfig(BaseModel):
    """★ 任务的**设置分组**。

    ⚠ **顶层字段必须是嵌套模型（= 分组）**，标量字段（bool/int/str/枚举）
      **必须**落在分组内部 —— 见 `tasks/Tako/config.py:15-24` 的说明：
      ★ 放到任务类顶层会让 GUI 渲染整个任务时抛 `KeyError`，**整个界面白掉**。
    """

    enable: bool = Field(default=False, description='enable_help')
    # ★ 在这里加你任务的字段，例：
    #   max_times: int = Field(default=1, ge=0, le=99, description='...')


class __NAME__(ConfigBase):
    scheduler: Scheduler = Field(default_factory=Scheduler)
    __NAME_LOWER___config: __NAME__TaskConfig = Field(default_factory=__NAME__TaskConfig)
'''

_SCRIPT_TASK = '''# This Python file uses the following encoding: utf-8
"""`__NAME__`（__NAME_ZH__）的任务实现。★ 由「新建任务」生成（SPEC §1.16 NT3）。

## ★★ 这是**安全空壳**（★ 四条保证）

* ★ **没有任何"乱点屏幕"的动作** —— 免得素材没配好就误操作账号
* ★ `enable=False`（`config.py`）⇒ ★ 开关没打开时它不做事
* ★ `period=none` + `auto_queue=False`（`meta.py`）⇒ ★ **不会自动进队列**
* ★ 结尾**一定** `set_next_run` + `TaskEnd` ⇒ ★ 不会把调度器挂住

## ★ 示例识别在哪里

★ 下面 `self.appear(self.I_UI_BACK_RED, ...)` 就是**示例识别** ——
  ★ 用的是**全局素材**（`tasks/GlobalGame/assets.py` 的 `I_UI_BACK_RED`，一定存在）
  ⇒ ★ **开箱即可跑**，不需要你先标素材。
★ 你自己的素材标好之后，把那一行换成 `self.I_YOUR_ASSET` 即可。
"""
from module.exception import TaskEnd
from module.logger import logger

from tasks.GameUi.game_ui import GameUi
from tasks.GameUi.page import page_main


class ScriptTask(GameUi):
    """★ 类名**必须**叫 `ScriptTask`、**必须**实现 `run()`（`script.py:848-852` 写死）。"""

    def run(self) -> None:
        logger.hr('__NAME__', 1)

        # ── ① 准备（SPEC §1.19-C2）：回到庭院 —— 以已知界面为起点
        self.goto_page(page_main)

        # ── ② 示例识别（★ 用户要求"骨架要带示例识别"）
        if self.appear(self.I_UI_BACK_RED, threshold=0.8, interval=1):
            logger.info('★ 示例识别命中：`I_UI_BACK_RED` 可见 —— '
                        '★ 这里就是写"识别到之后做什么"的地方')
        else:
            logger.info('★ 示例识别未命中（★ 也正常：骨架不做任何点击）')

        # ── ③ 收尾（SPEC §1.19-C7）：★ 上报本轮成功 + 交回调度器
        #   ★ `finish=True` ⇒ 以**收尾时刻**为基准排下一次（`base_task.py:1570-1571`）
        self.set_next_run(task='__NAME__', success=True, finish=True)
        raise TaskEnd('__NAME__')
'''

_ASSETS = '''# This Python file uses the following encoding: utf-8
"""`__NAME__`（__NAME_ZH__）的素材。★ **由 `dev_tools/assets_extract.py` 自动生成**。

★ 现在这里是**空壳**，这是**正常的**：
  * ★ 用标注工具标好素材并保存 ⇒ ★ 本文件会被**自动重生成**，素材成为类属性
  * ★ 骨架的示例识别用的是**全局素材** `I_UI_BACK_RED`
    （`tasks/GlobalGame/assets.py`）⇒ ★ 不需要本文件先有内容也能跑
"""


class __NAME__Assets:
    pass
'''

_TEMPLATES = {
    'meta.py': _META,
    'config.py': _CONFIG,
    'script_task.py': _SCRIPT_TASK,
    'assets.py': _ASSETS,
}


def _snake(name: str) -> str:
    """★ `FlowDemo` ⇒ `flow_demo`（配置分组字段名用）。"""
    return re.sub(r'(?<!^)(?=[A-Z])', '_', str(name)).lower()


def _next_list_pos(root: Path) -> int:
    """★ 取"当前最大 `list_pos` + 1"。

    ★ 为什么要它：★ 守卫 `tests/module/config/test_list_pos_metadata.py::test_positions_are_unique`
      ★ 要求 `list_pos` **全局唯一** ⇒ ★ 新任务若照抄 `list_pos=0`，**一建就红**
      （★ 实测：本项目现有 56 个目录里已经有重复值 —— 这条守卫是真的在管事）。
    """
    mx = 0
    try:
        for d in Path(root).iterdir():
            meta = d / 'meta.py'
            if not meta.is_file():
                continue
            m = re.search(r'list_pos\s*=\s*(\d+)',
                          meta.read_text(encoding='utf-8', errors='replace'))
            if m:
                mx = max(mx, int(m.group(1)))
    except OSError:
        pass
    return mx + 1


def render_files(name: str, name_zh: str, category: str = 'TIMED',
                 period: str = 'NONE', list_pos: int = 0) -> dict:
    """★ 生成 4 个文件的内容（★ 不落盘 —— 便于单测逐个断言）。"""
    subs = {
        '__NAME_LOWER__': _snake(name),
        '__NAME_ZH__': str(name_zh or name),
        '__NAME__': str(name),
        '__CATEGORY__': str(category or 'TIMED').upper(),
        '__PERIOD__': str(period or 'NONE').upper().replace('PERIOD.', ''),
        '__LIST_POS__': str(int(list_pos)),
    }
    out = {}
    for fn, tpl in _TEMPLATES.items():
        text = tpl
        # ★ 先替换长 token（`__NAME_LOWER__` 含 `__NAME__` 的前缀，顺序不能反）
        for token in ('__NAME_LOWER__', '__NAME_ZH__', '__CATEGORY__',
                      '__PERIOD__', '__LIST_POS__', '__NAME__'):
            text = text.replace(token, subs[token])
        out[fn] = text
    return out


# ────────────────────────────────────────────────────────────── 创建（NT1）
def create_task(name: str, name_zh: str = '', category: str = 'TIMED',
                period: str = 'NONE', *, tasks_root: Path = None,
                register_flow: bool = True, dry_run: bool = False) -> CreateResult:
    """★★ `NT1`：**原子**创建一个任务（4 个文件 + 流程图登记）。

    ★ 步骤：① 校验名 ② 渲染 ③ 写**临时目录** ④ 逐个 `ast.parse` 自检
      ⑤ `os.replace` **原子落地** ⑥ 登记流程图 ⇒ ★ 任何一步失败都**回滚**。

    :param name: ★ 大驼峰任务名（= 目录名 = `ScriptTask` 所在包）
    :param name_zh: ★ 中文名（空则用 `name`）
    :param category: ★ `FIXED` / `TOPPA` / `LIMITED` / `TIMED`
    :param period: ★ `NONE` / `DAILY` / `WEEKLY` / `MONTHLY`
    :param tasks_root: ★ 默认 `backend/tasks`（★ 单测会传临时目录）
    :param register_flow: ★ 是否往 `docs/flows/README.md` 补一行登记
    :param dry_run: ★ 只渲染 + 自检，**不落盘**
    """
    root = Path(tasks_root) if tasks_root else TASKS_ROOT
    zh = str(name_zh or name or '').strip()

    # ── ① 命名校验（★ NT2：必须在写盘之前）
    reason = validate_name(name, root)
    if reason:
        return CreateResult(ok=False, name=str(name or ''), error=reason)

    files = render_files(name, zh, category, period, _next_list_pos(root))

    # ── ④ 自检：★ 模板必须先能通过语法解析（★ 免得落下一个"坏任务"把后端起不来）
    for fn, text in files.items():
        try:
            ast.parse(text)
        except SyntaxError as exc:
            return CreateResult(ok=False, name=name, name_zh=zh,
                                error=f'★ 生成的 {fn} 语法错误（模板 bug）：{exc}')

    if dry_run:
        return CreateResult(ok=True, name=name, name_zh=zh, dir=str(root / name),
                            files=list(files), error='(dry-run 未落盘)')

    tmp = root / f'.{name}.creating'
    final = root / name
    written = False
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=False)
        for fn in FILES:
            with open(tmp / fn, 'w', encoding='utf-8', newline='') as f:
                f.write(files[fn])
        # ── ⑤ 原子落地
        os.replace(tmp, final)
        written = True
    except Exception as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        return CreateResult(ok=False, name=name, name_zh=zh,
                            error=f'写盘失败（已回滚）：{type(exc).__name__}: {exc}')

    registered = False
    if register_flow:
        try:
            registered = _register_in_flow_index(name, zh)
        except Exception:
            registered = False

    # ★★ NT1：登记失败 ⇒ ★ 也要回滚（"要么全成、要么全不落盘"）
    if register_flow and not registered:
        shutil.rmtree(final, ignore_errors=True)
        return CreateResult(ok=False, name=name, name_zh=zh,
                            error='流程图台账登记失败 ⇒ 已回滚（★ NT1：要么全成、要么全不落盘）')

    _invalidate_catalog(root)
    return CreateResult(ok=True, name=name, name_zh=zh, dir=str(final),
                        files=[str(final / fn) for fn in FILES],
                        registered=registered)


def _invalidate_catalog(root: Path) -> None:
    """★★ 刷新 `task_catalog` 的**两个**缓存（★ 只在真 `tasks/` 下创建时做）。

    ## ★★ 为什么必须是**两个**（★ 实测踩出来的）

    `module/config/task_catalog.py` 里有**两套**视图，各自独立缓存：

    | 视图 | 读什么 | 谁清缓存 |
    |---|---|---|
    | ★ `get_spec()` / `all_specs()` | ★ `tasks/*/meta.py` **发现**（`_load_specs`，`task_catalog.py:691`）| ★ `reload_specs()`（`:696`）|
    | ★ `all_tasks()` / `all_meta()` / `get()` | ★ `task_catalog_data.json`（`_load`，`:711`）★ **再合并**发现（`:760`）⇒ ★ 新任务在这一侧**也会**出现 | ★ `reload()`（`:788`）|

    ⚠ ★ 只调 `reload_specs()` ⇒ ★ `all_tasks()` **看不到新任务**（★ 它读的是已被
      `lru_cache` 缓存住的 `_load()` 结果）⇒ ★ 界面"新建了却不在列表里"
      ⇒ ★★ 这正是本工厂第一版的 bug —— ★ **单跑测试是绿的，放进完整守卫链才红**
      （★ 因为链里的前序用例已经先调过 `all_tasks()` 把缓存坐实了）。
    """
    try:
        if Path(root).resolve() != TASKS_ROOT.resolve():
            return
        from module.config import task_catalog as TC
        TC.reload_specs()      # ★ 视图①：meta.py 发现
        TC.reload()            # ★ 视图②：JSON + 合并（all_tasks/all_meta/get）
    except Exception:
        pass


def _register_in_flow_index(name: str, name_zh: str,
                            index_path: Path = None) -> bool:
    """★ 在 `docs/flows/README.md` 的**待补台账**里补一行（★ 让守卫保持绿）。

    ★ 为什么是"合同"的一部分：`tests/test_task_flow_docs.py` 要求
      **每个 `tasks/<Name>/` 都在台账里出现**（★ 漏登记 ⇒ 守卫变红）。
    """
    path = Path(index_path) if index_path else FLOW_INDEX
    if not path.is_file():
        return False
    lines = path.read_text(encoding='utf-8').split('\n')
    row = (f'| `{name}`（{name_zh}）| ⬜ **新建任务待补** | '
           f'★ [10-14] 由「新建任务」创建 ⇒ ★ 流程图待补'
           f'（★ 先看 `RealmRaid.md` 样板：五段结构 + 每个判断带 `文件:行号`）|')

    start = None
    for i, line in enumerate(lines):
        if line.startswith('|') and '待补台账' in '\n'.join(lines[max(0, i - 30):i]):
            start = i
    if start is None:
        for i, line in enumerate(lines):
            if line.startswith('|') and '状态' in line and '待补理由' in line:
                start = i
    if start is None:
        return False
    last = start
    for j in range(start, len(lines)):
        if lines[j].startswith('|'):
            last = j
        elif j > start:
            break
    lines.insert(last + 1, row)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write('\n'.join(lines))
    return True
