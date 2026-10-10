# -*- coding: utf-8 -*-
"""守卫:
* ① `period` 下拉的**选项值**必须有译文（否则界面显示英文 daily/weekly/monthly）
* ② `MemoryScrolls` **只做停止用途, 不做排期**（不给别的任务排期）
* ③ 前端 `period` 下拉由后端 `enumEnum` 动态生成 —— 后端有 `monthly` 前端就会出现
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(r'D:\OAS-dev\OnmyojiAutoScript')
sys.path.insert(0, str(REPO))


class TestPeriodOptionTranslations:
    """★ `period` 是**下拉**, 显示的是**选项值**（`daily`/`weekly`/…）而不是 `_help`。

    i18n 守卫原本只扫带 `_help` 后缀的**字段 key** —— **漏了枚举选项值**。
    于是下拉里会赤裸裸显示 `daily` / `weekly` / `monthly`。
    """

    def test_enum_values_have_translation(self):
        from tasks.Component.config_scheduler import TaskPeriod
        d = json.loads(
            (REPO / 'module' / 'config' / 'i18n' / 'zh-CN.json')
            .read_text(encoding='utf-8'))
        missing = [p.value for p in TaskPeriod if not d.get(p.value)]
        assert not missing, (
            f'`period` 下拉的选项值缺译文: {missing} —— '
            f'界面会显示英文（踩过: 只查了 *_help, 漏了选项值）')

    def test_translation_is_chinese(self):
        from tasks.Component.config_scheduler import TaskPeriod
        d = json.loads(
            (REPO / 'module' / 'config' / 'i18n' / 'zh-CN.json')
            .read_text(encoding='utf-8'))
        for p in TaskPeriod:
            v = d.get(p.value, '')
            assert re.search(r'[\u4e00-\u9fff]', v), \
                f'{p.value} 的译文没有中文: {v!r}'

    def test_monthly_is_offered_by_backend(self):
        """★ 用户: "period.monthly作为预留的嘛, 可以下拉选择每月,
        确保**后端有这个功能**, 前端才能出现"。

        ⚠ 不能直接查 `model_json_schema()['properties']['period']['enum']` ——
          `period` 是 `$ref` 引用, `enum` 在 **`$defs`** 里, 顶层 properties
          只有 `$ref`（实测 `enum` 取到 `[]` -> **假失败**）。
          改用**端到端**的 `/schema` 输出（它已经把 `enumEnum` 展开好了）。
        """
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm

        cfg = mm.config_cache('恋鸟树')
        got = cfg.model.script_task('Orochi')['scheduler']
        period = next((it for it in got if it['name'] == 'period'), None)
        assert period is not None, '界面字段里没有 period'
        enums = period.get('enumEnum') or []
        assert 'monthly' in enums, (
            f'后端 period 的 enumEnum 里没有 monthly: {enums} —— '
            f'前端下拉就不会有"每月"')
        # 四个值都该在（顺序不保证）
        assert set(enums) >= {'none', 'daily', 'weekly', 'monthly'}, enums

    def test_period_field_is_user_visible(self):
        from tasks.Component.config_scheduler import Scheduler
        s = Scheduler.model_json_schema()['properties']
        assert not s['period'].get('internal'), \
            'period 不该是内部字段（用户要能选每天/每周/每月）'


class TestWindowFieldsAreUserEditable:
    """★★ 用户: "用户可以选择每天, 然后把时间改为 17-23 点" ★★

    我一开始（4-E）把 `window_*` 当"内部字段"隐藏了 —— 那是**错的**。

    ## ★★ S3: 字段模型换了 ★★

    单值 `window_*` 已删除（用户裁定: "不是 window slots, 而是**设置多个
    window**！"）。现在只有 **`windows`（列表）** —— 它**必须**用户可见可改。
    """

    def test_windows_field_not_internal(self):
        from tasks.Component.config_scheduler import Scheduler
        s = Scheduler.model_json_schema()['properties']
        assert 'windows' in s, '`windows` 不存在'
        assert not s['windows'].get('internal'), \
            '`windows` 不该是内部字段 —— 用户必须能改窗口'

    def test_dead_fields_are_gone(self):
        """★ S3: 被 `windows` 替代的字段**必须不存在**了。"""
        from tasks.Component.config_scheduler import Scheduler
        for dead in ('window_enable', 'window_start', 'window_end',
                     'window_days', 'window_period', 'window_dom',
                     'window_slots'):
            assert dead not in Scheduler.model_fields, \
                f'{dead} 已废弃, 不该还在（单一数据源）'

    def test_window_help_translated(self):
        d = json.loads(
            (REPO / 'module' / 'config' / 'i18n' / 'zh-CN.json')
            .read_text(encoding='utf-8'))
        for f in ('window_windows_help', 'period_help'):
            assert d.get(f), f'{f} 缺译文（字段对用户可见了, 必须翻）'

    def test_schema_exposes_window_fields(self):
        """端到端: `/schema` 的 scheduler 组里应能看到 `windows`。"""
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        cfg = mm.config_cache('恋鸟树')
        names = {it['name'] for it in cfg.model.script_task('Orochi')['scheduler']}
        for f in ('windows', 'period'):
            assert f in names, (
                f'{f} 没出现在界面字段里 —— 用户改不了窗口（实际: {sorted(names)}）')


class TestMemoryScrollsOnlyStops:
    """★ 用户: "MemoryScrolls **只做停止用途, 不做排期**"。"""

    TASK_FILE = REPO / 'tasks' / 'MemoryScrolls' / 'script_task.py'

    def _code(self) -> str:
        """剥掉注释与 docstring —— 否则"说明我删了什么"的注释会被误判。"""
        src = self.TASK_FILE.read_text(encoding='utf-8')
        src = re.sub(r'"""[\s\S]*?"""', '', src)
        out = []
        for line in src.split('\n'):
            s = line.strip()
            if s.startswith('#'):
                continue
            i = line.find('  # ')
            if i != -1:
                line = line[:i]
            out.append(line)
        return '\n'.join(out)

    def test_no_custom_next_run(self):
        code = self._code()
        assert 'custom_next_run' not in code, (
            'MemoryScrolls 仍在用 custom_next_run —— 用户要求它只做停止用途')

    def test_does_not_schedule_other_tasks(self):
        """★ 不该**替别的任务**排期。"""
        code = self._code()
        for other in ('Exploration', 'Orochi', 'Delegation'):
            bad = re.search(
                rf"custom_next_run\([^)]*task\s*=\s*['\"]{other}['\"]", code)
            assert bad is None, (
                f'MemoryScrolls 仍在替 {other} 排期: {bad.group(0) if bad else ""}')

    def test_still_ends_task(self):
        """只做停止用途 —— 仍应让本任务结束（不能变成什么都不做）。"""
        code = self._code()
        assert 'raise TaskEnd' in code, 'MemoryScrolls 应该仍然会结束任务'
