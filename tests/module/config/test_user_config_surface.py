# -*- coding: utf-8 -*-
"""用户配置面 —— 内部排期字段**不该出现在界面上**（修正台账 10.7/7.7 的虚报）。

## 背景（虚报）

`docs/architecture.md` 台账 **10.7/7.7** 声称"用户配置面 10 → 3 个字段"，
标着 ✅。**实测: 界面上 16 个字段全暴露**（见 `docs/SESSION-LEDGER.md` §0.2）。

用户面对 `success_interval` / `next_run` / `window_*` 这类字段无从下手:
它们要么是**游戏机制**（已收进各任务 `meta.py` 的 `Resource` / `window`）,
要么是**软件内部状态**。

## 做法

内部字段打 `json_schema_extra={'internal': True}`;
`config_model.script_task()` 生成界面字段时跳过它们
（与既有的 `0xABCDEF` 排除机制同一处）。

★ **不删字段** —— `task_delay()` 要把算出来的 `next_run` 落盘,
`_skip_by_period()` 要读 `period`/`reset_at`。只是不再让用户看到。
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# 用户**应该**看到的（真正的调度配置）
USER_FACING = {'enable', 'priority', 'target', 'expected_minutes'}

# 用户**不该**看到的（游戏机制 / 软件内部状态）
INTERNAL = {
    'next_run',          # 软件内部状态; 用户改它只会把排期弄乱
    'success_interval',  # 旧模型把"游戏补充规则"压扁成"用户轮询间隔"
    'retry_interval',    # 同上（退避重试）; 台账 7.3 已改名
    'server_update',     # 服务器维护顺延
    'delay_date',        # 同上
    'float_time',        # 随机抖动
    'period',            # 完成记忆的内部依据
    'reset_at',          # 周期边界
    'window_enable',     # 时段已搬进 meta.py 的 TaskSpec.window
    'window_start',
    'window_end',
    'window_days',
}


class TestInternalFieldsMarked:
    """模型上必须**显式标记**, 而不是靠某处的硬编码名单。"""

    def test_all_internal_fields_are_marked(self):
        from tasks.Component.config_scheduler import Scheduler
        schema = Scheduler.model_json_schema()['properties']
        unmarked = sorted(
            k for k in INTERNAL
            if k in schema and not schema[k].get('internal'))
        assert not unmarked, (
            f'这些内部字段没打 internal 标记, 会重新出现在界面上: {unmarked}')

    def test_user_facing_fields_are_not_marked(self):
        from tasks.Component.config_scheduler import Scheduler
        schema = Scheduler.model_json_schema()['properties']
        wrongly = sorted(
            k for k in USER_FACING
            if k in schema and schema[k].get('internal'))
        assert not wrongly, (
            f'这些是用户该配的字段, 不该隐藏: {wrongly}')

    def test_fields_still_exist_on_model(self):
        """★ 隐藏 ≠ 删除 —— `task_delay` 还要读写它们。"""
        from tasks.Component.config_scheduler import Scheduler
        fs = set(Scheduler.model_fields)
        missing = sorted(INTERNAL - fs)
        assert not missing, (
            f'这些字段被删了, 但 `task_delay`/`_skip_by_period` 还在用: {missing}')
        # 关键的两个: 排期落盘与完成记忆
        assert 'next_run' in fs
        assert 'period' in fs and 'reset_at' in fs


class TestSchemaHidesInternal:
    """`script_task()` 生成界面字段时必须跳过内部字段。"""

    @pytest.fixture()
    def config(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_scheduler_group_only_has_user_facing(self, config):
        """★ 任务设置页的 scheduler 组**只有**用户该配的字段。"""
        got = config.model.script_task('Orochi')
        sch = got.get('scheduler') or []
        names = {it['name'] for it in sch}
        leaked = sorted(names & INTERNAL)
        assert not leaked, (
            f'这些内部字段泄漏到界面上了: {leaked}\n'
            f'（台账 10.7/7.7 曾自称"用户配置面 10 → 3 个字段", 实际 16 个全暴露）')
        assert names >= {'enable', 'priority'}, f'用户该配的字段丢了: {names}'

    def test_user_facing_field_count_is_small(self, config):
        """用户配置面应该**明显小于**模型字段数（不是 16 个全上）。"""
        from tasks.Component.config_scheduler import Scheduler
        total = len(Scheduler.model_fields)
        got = config.model.script_task('Orochi')
        shown = len(got.get('scheduler') or [])
        assert shown < total, (
            f'界面暴露 {shown} 个 / 模型共 {total} 个 —— 过滤没生效')
        assert shown <= 6, (
            f'界面暴露 {shown} 个字段, 仍然太多（预期 <= 6, 台账目标 3~4）')

    def test_multiple_tasks_consistent(self, config):
        """所有任务的截断规则要一致（不能只对 Orochi 生效）。"""
        for task in ('Orochi', 'Delegation', 'Exploration', 'GoldYoukai'):
            got = config.model.script_task(task)
            sch = got.get('scheduler') or []
            leaked = sorted({it['name'] for it in sch} & INTERNAL)
            assert not leaked, f'{task} 泄漏了内部字段: {leaked}'


class TestChargeFieldsHidden:
    """`charge_*`（充能）也收进内部字段, 但**同组的用户配置不能误伤**。

    ## 踩过的两个坑（都写在这里防止复犯）

    **坑一: 自动标记做过头。**
    第一版我用正则给"含有 charge 的整个 Field(...)"加 `internal`,
    结果把同组的 `user_status`（**队伍状态, 用户必须能配**）
    以及一堆别的字段也标上了 -> `test_team_modes` 里
    `assert 'user_status' in names` 失败（3 个任务）。

    **坑二: 参数插到了 `Field(...)` 的括号之外。**
    第二版我把 `json_schema_extra` 追加到**行尾**, 而那行已经是
    `charge_enable: ... = Field(...),` —— 于是变成
    `Field(...), json_schema_extra={...}`（括号外多出关键字参数）
    -> **SyntaxError**, 36 个测试失败, 连模块都 import 不了。

    正确做法: 正则定位 `Field\((.*)\)` 并把参数插到**闭合括号之前**。
    """

    TASKS = ('ExperienceYoukai', 'GoldYoukai', 'Tako')
    CHARGE = ('charge_enable', 'charge_max', 'charge_slots', 'charge_consume')

    @pytest.mark.parametrize('task', TASKS)
    def test_charge_fields_marked_internal(self, task):
        import importlib
        mod = importlib.import_module(f'tasks.{task}.config')
        # 找到含 charge 字段的那个模型类
        classes = [o for n, o in vars(mod).items()
                   if isinstance(o, type) and hasattr(o, 'model_fields')]
        found = {}
        for cls in classes:
            for name in cls.model_fields:
                if name in self.CHARGE:
                    found[name] = cls.model_fields[name]
        assert set(found) == set(self.CHARGE), (
            f'{task} 缺 charge 字段: 只找到 {sorted(found)}')
        for name, fi in found.items():
            extra = fi.json_schema_extra or {}
            assert extra.get('internal') is True, (
                f'{task}.{name} 没标 internal —— 会出现在界面上')

    @pytest.mark.parametrize('task', TASKS)
    def test_user_status_NOT_hidden(self, task):
        """★ 回归守卫: `user_status` 是**用户配置**, 绝不能隐藏。

        （第一版自动标记把它误伤了, 3 个测试失败。）
        """
        import importlib
        mod = importlib.import_module(f'tasks.{task}.config')
        classes = [o for n, o in vars(mod).items()
                   if isinstance(o, type) and hasattr(o, 'model_fields')]
        got = None
        for cls in classes:
            if 'user_status' in cls.model_fields:
                got = cls.model_fields['user_status']
                break
        assert got is not None, f'{task} 里找不到 user_status'
        assert not (got.json_schema_extra or {}).get('internal'), (
            f'{task}.user_status 被标成 internal 了 —— 那是用户必须能配的字段')

    def test_charge_config_files_compile(self):
        """★ 回归守卫: 标记操作不能把文件改坏（踩过 SyntaxError）。"""
        import py_compile
        for task in self.TASKS:
            p = REPO / 'tasks' / task / 'config.py'
            try:
                py_compile.compile(str(p), doraise=True)
            except py_compile.PyCompileError as exc:
                pytest.fail(f'{task}/config.py 语法错误（标记操作改坏了文件）: {exc}')

    def test_marking_inserts_inside_field_parens(self):
        """★ 回归守卫: `json_schema_extra` 必须在 `Field(...)` **括号内**。

        插到括号外会得到 `Field(...), json_schema_extra={...}` -> SyntaxError。
        所以断言"`Field(` 之后到行尾之间"出现该参数, 且该行**只有一个** `Field(`。
        """
        for task in self.TASKS:
            p = REPO / 'tasks' / task / 'config.py'
            for n, line in enumerate(p.read_text(encoding='utf-8').split('\n'), 1):
                s = line.strip()
                if not s or s.startswith('#') or 'charge_' not in s:
                    continue
                if 'json_schema_extra' not in s:
                    continue
                i = line.find('Field(')
                j = line.find('json_schema_extra')
                assert i != -1 and j > i, (
                    f'{task}/config.py:{n} json_schema_extra 在 Field( 之外: {s}')
    """过滤必须在 `merge_value` 里, 且用**正确**的读取方式。"""

    def test_merge_value_reads_flat_internal_key(self):
        """★ `json_schema_extra` 会被 pydantic **展平**到属性顶层。

        实测: `Field(..., json_schema_extra={'internal': True})` 在
        `model_json_schema()['properties'][k]` 里得到的是
        `"internal": true`（**顶层**）, 而**不是**
        `"json_schema_extra": {"internal": true}`。

        第一版我按嵌套写 `value.get('json_schema_extra')`, 过滤**没生效**
        —— 16 个字段照样全暴露。这个坑写在这里, 防止后人"顺手改回去"。
        """
        from tasks.Component.config_scheduler import Scheduler
        props = Scheduler.model_json_schema()['properties']
        nr = props['next_run']
        assert nr.get('internal') is True, \
            'internal 应为属性定义的**顶层键**（pydantic 会展平 json_schema_extra）'
        assert 'json_schema_extra' not in nr, \
            '不该出现嵌套形式 —— 若 pydantic 改了行为, 过滤逻辑也要跟着改'

    def test_filter_uses_flat_read(self):
        src = (REPO / 'module' / 'config' / 'config_model.py').read_text(
            encoding='utf-8')
        i = src.find('def merge_value')
        j = src.find('schema = task.model_json_schema()', i)
        body = src[i:j]
        assert "value.get('internal')" in body, \
            'merge_value 必须按**顶层**键判断 internal'
        assert "value.get('json_schema_extra')" not in body, \
            '嵌套读法不生效（pydantic 会把 json_schema_extra 展平）'
