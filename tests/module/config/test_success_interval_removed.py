# -*- coding: utf-8 -*-
"""#4c: `Scheduler.success_interval` **已删除**（用户: "如果没有用到那么就删掉"）。

## 为什么现在可以删

* `task_delay()` 的成功路径已改为**窗口兜底**（台账 §21.5）
  —— 用户裁定: "排期应该是用具体的 **window** 来算"
* `DailyTrifles` / `TrueOrochi` 已改用 `Config.next_run_after()`（§17.1）
* 所以**没有执行代码**再读 `scheduler.success_interval`

## 保留什么（**故意不删**）

| 保留项 | 原因 |
|---|---|
| `Resource.from_legacy(success_interval=...)` | 它是**迁移桥**的参数名, 读的是旧 JSON 的原始字符串, 与 `Scheduler` 字段无关 |
| `TaskMeta.success_interval` | `task_catalog` 的**数据字段**（记录旧配置原文用于迁移）, 测试依赖 |
| 注释/文档里的说明 | 它们解释**为什么**废弃 —— 删了就没人知道这段历史 |

## 与 `failure_interval` -> `retry_interval` 的区别

那个是**改名**: 要保旧配置的**值**（用户覆盖不能丢）-> `validation_alias`。
这个是**彻底不用**: 旧 JSON 里的键被 pydantic 静默忽略（`extra='ignore'`）
—— **这是预期的**, 因为它不再影响任何行为。
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestSuccessIntervalRemoved:
    def test_field_is_gone(self):
        """★ `Scheduler` 里**不该**再有 `success_interval`。"""
        from tasks.Component.config_scheduler import Scheduler
        assert 'success_interval' not in Scheduler.model_fields, (
            'success_interval 又回来了 —— 它已被窗口排期取代')

    def test_not_in_schema(self):
        from tasks.Component.config_scheduler import Scheduler
        props = Scheduler.model_json_schema()['properties']
        assert 'success_interval' not in props

    def test_retry_interval_still_there(self):
        """★ 反向守卫: **失败退避**是独立概念（台账 7.6）, 不能连带删掉。"""
        from tasks.Component.config_scheduler import Scheduler
        assert 'retry_interval' in Scheduler.model_fields

    def test_no_execution_code_reads_it(self):
        """★ 全库**不该**有 `.scheduler.success_interval` 这种读取。

        （注释/文档/`from_legacy` 的参数名不算 —— 只查"属性访问"。
         剥掉注释再查, 否则"说明我删了什么"的注释会被误判。）
        """
        bad = []
        # ⚠ 只查 `module/` 与 `tasks/` —— **不查 tests**
        #   （测试里引用该名字是正常的; 本文件自己就含这个正则 -> 会自我命中, 踩过）。
        targets = list(REPO.glob('module/**/*.py')) + \
            list(REPO.glob('tasks/**/*.py'))
        for p in targets:
            if '__pycache__' in str(p):
                continue
            src = p.read_text(encoding='utf-8', errors='replace')
            # 剥掉整行注释与 docstring
            src = re.sub(r'"""[\s\S]*?"""', '', src)
            src = re.sub(r"'''[\s\S]*?'''", '', src)
            for i, line in enumerate(src.split('\n'), 1):
                # ★ 剥掉**行内注释**（`#` 之后）—— 否则注释里解释
                #   "以前用 success_interval" 会被误判（我踩过一次）。
                s = line.split('#', 1)[0].strip()
                if not s:
                    continue
                # 只认"**属性访问**"形式（`.success_interval`）,
                # 不认 `success_interval=` 这种**关键字参数**
                # （`from_legacy(success_interval=...)` 是保留的迁移桥），
                # 也不认 `TaskMeta` 的数据字段（那个**故意保留**）。
                if re.search(r'\.success_interval\b', s) and \
                        'TaskMeta' not in s and 'TC.get' not in s:
                    bad.append(f'{p.relative_to(REPO)}:{i}: {s[:80]}')
        assert not bad, (
            f'这些地方还在读 `success_interval`: {bad}\n'
            f'（成功路径应改为窗口兜底 —— 见 docs/SESSION-LEDGER.md §21.5）')

    def test_task_overrides_removed(self):
        """7 个任务的 `config.py` 覆盖也应删掉。"""
        bad = []
        for f in (REPO / 'tasks').rglob('config.py'):
            src = f.read_text(encoding='utf-8')
            src = re.sub(r'"""[\s\S]*?"""', '', src)
            for line in src.split('\n'):
                s = line.strip()
                if s.startswith('#'):
                    continue
                if re.match(r'success_interval\s*:', s):
                    bad.append(f'{f.relative_to(REPO)}: {s[:70]}')
        assert not bad, f'这些任务还覆盖 success_interval: {bad}'
    def test_task_catalog_field_kept(self):
        """★ `TaskMeta.success_interval`（数据字段）保留 —— 迁移与测试依赖它。"""
        from module.config import task_catalog as TC
        meta = TC.get('GoldYoukai')
        assert meta is not None
        assert hasattr(meta, 'success_interval'), \
            'TaskMeta 的 success_interval 数据字段被删了'

    def test_task_delay_uses_window_not_interval(self):
        """★ `task_delay()` 成功路径必须用**窗口**, 不能退回 interval。"""
        src = (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')
        i = src.find('def task_delay')
        j = src.find('\n    def ', i + 10)
        body = src[i:j if j > i else i + 9000]
        # ★ 剥注释与 docstring —— 否则注释里解释"以前是
        #   `start_time + success_interval`"会被误判（踩过）。
        code = re.sub(r'"""[\s\S]*?"""', '', body)
        code = '\n'.join(l.split('#', 1)[0] for l in code.split('\n'))
        assert 'next_run_after(' in code, \
            'task_delay 的成功路径应调用 next_run_after（窗口兜底）'
        assert not re.search(r'\.success_interval\b', code), \
            'task_delay 里还有 success_interval 的属性读取'
