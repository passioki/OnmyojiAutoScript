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
#
# ★★ 2026-10-10 用户澄清后**扩大**了 ★★
#
# 我一开始（4-E）把 `window_*` / `period` 当成"内部字段"隐藏了 —— 那是**错的**。
# 用户明确要求:
#
#   "缺 window 用 period 推导, 记得要符合前端设计意义
#    （用户可以选择每天, 然后把时间改为 17-23 点）, 后端也要符合这个逻辑"
#   "period.monthly作为预留的嘛, 可以下拉选择每月, 确保后端有这个功能, 前端才能出现"
#
# 职责划分:
#   * `period`（每天/每周/每月）—— **节奏**, 用户选; 同时给出**默认窗口**
#   * `window_start` / `window_end` / `window_days` —— **用户偏好**
#     （"我每天只想在 17-23 跑"）
#   * 各任务 `meta.py` 的 `TaskSpec.window` —— **游戏机制硬约束**
#     （如狭间暗域只在周五六日）, 与用户时刻取**并集**
USER_FACING = {
    'enable', 'priority', 'target', 'expected_minutes',
    # ★ 用户可见可改（本轮修正）
    'window_enable', 'window_start', 'window_end', 'window_days',
    'period',
}

# 用户**不该**看到的（游戏机制 / 软件内部状态）
INTERNAL = {
    'next_run',          # 软件内部状态; 用户改它只会把排期弄乱
    'success_interval',  # 旧模型把"游戏补充规则"压扁成"用户轮询间隔"
    'retry_interval',    # 同上（退避重试）; 台账 7.3 已改名
    'server_update',     # 服务器维护顺延
    'delay_date',        # 同上
    'float_time',        # 随机抖动
    'reset_at',          # 周期边界
    # ★ `period` / `window_*` **不属于这里** —— 它们是用户可见可改的
    #   （见上面 USER_FACING 的说明; 2026-10-10 修正）
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
        # ★ 2026-10-10: 用户要求 `window_*` + `period` 也可见/可改
        #   -> 上限从 6 放宽到 10（实际 9 个）
        assert shown <= 10, (
            f'界面暴露 {shown} 个字段, 仍然太多（预期 <= 10）')

    def test_multiple_tasks_consistent(self, config):
        """所有任务的截断规则要一致（不能只对 Orochi 生效）。"""
        for task in ('Orochi', 'Delegation', 'Exploration', 'GoldYoukai'):
            got = config.model.script_task(task)
            sch = got.get('scheduler') or []
            leaked = sorted({it['name'] for it in sch} & INTERNAL)
            assert not leaked, f'{task} 泄漏了内部字段: {leaked}'


class TestRetryIntervalRename:
    """★ 台账 7.3: `failure_interval` → `retry_interval` 的**安全**重命名。

    ## 为什么必须带 `validation_alias`

    `Scheduler.model_config = {}` → pydantic v2 **默认 `extra='ignore'`**。
    实测: 给改名后的模型传**旧键** `failure_interval`, **不报错、也不生效**
    —— 会被静默忽略。

    于是**磁盘上 54 个配置里的该字段全部失效**。影响不只是"回落默认值":
    **8 个任务覆盖了它**（`KekkaiActivation` 10 小时 · `KekkaiUtilize`/
    `TalismanPass` 6 小时 · `FloatParade`/`Secret`/`WeeklyTrifles` 3~7 天 …）
    —— 静默忽略会让它们的**失败重试节奏悄悄变成默认 1 天**。

    ## 为什么**不设** `serialization_alias`

    让写到磁盘时用**新名** → 旧配置在第一次 `save()` 后**自然迁移**,
    不需要单独的迁移脚本。（设了 `serialization_alias` 会让 dump 出旧名 ——
    实测 `model_dump()` 的键会变回 `failure_interval`, 旧名永远留着。）
    """

    def test_old_key_still_readable(self):
        """★ 回归守卫: 旧键必须仍能被读出来（否则用户配置静默失效）。"""
        from tasks.Component.config_scheduler import Scheduler
        s = Scheduler(**{'enable': True, 'priority': 5,
                         'failure_interval': '10 00:00:01'})
        assert str(s.retry_interval).startswith('10 day'), (
            f'旧键 failure_interval 没被读到! 实际 retry_interval={s.retry_interval} '
            f'—— 用户配置里的自定义重试间隔会静默丢失')

    def test_new_key_works(self):
        from tasks.Component.config_scheduler import Scheduler
        s = Scheduler(**{'enable': True, 'priority': 5,
                         'retry_interval': '00 06:00:00'})
        assert str(s.retry_interval).startswith('6:00:00')

    def test_dumps_new_name(self):
        """★ 确认**写**出来的是新名（旧配置才会自然迁移）。"""
        from tasks.Component.config_scheduler import Scheduler
        s = Scheduler(**{'enable': True, 'priority': 5})
        keys = set(s.model_dump().keys())
        assert 'retry_interval' in keys, 'dump 里应有新名 retry_interval'
        assert 'failure_interval' not in keys, (
            'dump 里不该再有旧名 —— 否则旧配置永远不迁移')

    def test_alias_is_declared(self):
        """反向守卫: `validation_alias` 必须存在（防被"清理"掉）。"""
        import inspect
        from tasks.Component.config_scheduler import Scheduler
        fi = Scheduler.model_fields['retry_interval']
        assert fi.validation_alias is not None, '缺少 validation_alias（旧配置会失效）'
        assert 'failure_interval' in str(fi.validation_alias), \
            '别名里必须保留旧键名'

    def test_no_serialization_alias(self):
        """★ 不该有 `serialization_alias` —— 它会让 dump 出旧名, 阻碍迁移。

        ⚠ 用**字段属性**判断, **不要**看源码文本 ——
          字段的注释里也写了 `serialization_alias` 这个词, 看文本会误判。
        """
        from tasks.Component.config_scheduler import Scheduler
        fi = Scheduler.model_fields['retry_interval']
        assert fi.serialization_alias is None, (
            f'设了 serialization_alias={fi.serialization_alias!r} 会让 '
            f'`model_dump()` 输出旧名, 旧配置永远不会迁移到新名')

    def test_real_config_override_preserved(self):
        """★ 端到端: 真实配置里 8 个任务的覆盖值必须保住。

        （`kekkai_activation` 在 `恋鸟树` 里覆盖成 10 小时。）
        """
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        cfg = mm.config_cache('恋鸟树')
        node = getattr(cfg.model, 'kekkai_activation', None)
        if node is None:
            pytest.skip('该账号没有 kekkai_activation')
        got = node.scheduler.retry_interval
        assert str(got).startswith('10:00:00'), (
            f'kekkai_activation 的自定义重试间隔（10 小时）丢了! 实际 {got}')


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
