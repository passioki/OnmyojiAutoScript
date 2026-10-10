# -*- coding: utf-8 -*-
"""④⑤⑦: 队列行的**设置入口** / **次数类免确认** / **一键清空**。

## ④ 用户反馈

> "任务设置入口只在**正在运行的任务行**上有, 别的任务行上也应该有"

**实测根因**: 调度 tab 的 `TaskRowView` 有 `onTap -> openTaskSettings`,
而队列行**没有**。

## ⑤ 用户反馈

> "**次数类任务被移除时不需要弹窗确认, 只有定时类任务才需要。**"

## ⑦ 用户要求

> "添加**一键清空队列**, 弹窗确认。"
"""
import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OASX = Path(r'D:\OAS-dev\OASX-src')


class TestClearQueueEndpoint:
    """⑦ 后端: `POST /queue/clear`。"""

    @pytest.fixture()
    def live(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_clears_run_list(self, live):
        from module.config.run_list import RunEntry, RunList
        from module.server import schema_router as SR
        cfg = live
        backup = cfg.model.script.optimization.run_list
        try:
            rl = RunList()
            rl.add(RunEntry(kind='task', task='RealmRaid'))
            rl.add(RunEntry(kind='task', task='AreaBoss'))
            cfg.save_run_list(rl)
            res = asyncio.run(SR.post_queue_clear('恋鸟树'))
            assert res.get('ok') is True, res
            assert res.get('cleared_entries') == 2, res
            from module.server.main_manager import mm
            assert len(mm.config_cache('恋鸟树').build_run_list()) == 0
        finally:
            cfg.model.script.optimization.run_list = backup
            cfg.save()

    def test_disables_auto_queue_tasks(self, live):
        """★ 必须**停用**自动任务 —— 否则 `build_queue()` 会把它们补回来。

        ⚠⚠ **这个测试会改用户的实时配置** —— 所以必须**完整备份 + 完整还原**:
          * 备份在**调用端点之前**取（我第一版取晚了 -> 还原成空列表, 踩过）
          * `run_list` 与**所有** `enable` 都要还原
          * 结束时**断言还原成功**（否则以后又会悄悄破坏）
        """
        from module.config.config_model import convert_to_underscore
        from module.config.run_list import RunList
        from module.server import schema_router as SR
        from module.server.main_manager import mm

        cfg = live
        # ① 备份（**改动之前**）
        backup_rl = cfg.model.script.optimization.run_list
        backup_en = {}
        for key, value in cfg.model.model_dump().items():
            if isinstance(value, dict) and value.get('scheduler'):
                node = getattr(cfg.model, key, None)
                s = getattr(node, 'scheduler', None) if node else None
                if s is not None:
                    backup_en[key] = bool(s.enable)
        assert backup_en, '备份为空 —— 环境异常'

        try:
            res = asyncio.run(SR.post_queue_clear('恋鸟树'))
            assert res.get('ok') is True, res
            auto = res.get('disabled') or []
            assert auto, '应停用至少一个 auto_queue 任务'
            cfg2 = mm.config_cache('恋鸟树')
            for task in auto[:3]:
                key = convert_to_underscore(task)
                node = getattr(cfg2.model, key, None)
                if node is None:
                    continue
                assert node.scheduler.enable is False, f'{key} 应已停用'
        finally:
            # ② **完整**还原
            cfg.model.script.optimization.run_list = backup_rl
            for key, was in backup_en.items():
                node = getattr(cfg.model, key, None)
                s = getattr(node, 'scheduler', None) if node else None
                if s is not None:
                    s.enable = was
            cfg.save()
            # ③ 断言还原成功
            cfg3 = mm.config_cache('恋鸟树')
            bad = []
            for key, was in backup_en.items():
                node = getattr(cfg3.model, key, None)
                s = getattr(node, 'scheduler', None) if node else None
                if s is not None and bool(s.enable) != was:
                    bad.append(key)
            assert not bad, (
                f'还原失败: {bad} —— 测试污染了用户配置（见台账 §29）')

    def test_endpoint_registered(self):
        from module.server import schema_router as SR
        assert hasattr(SR, 'post_queue_clear'), 'queue/clear 端点未注册'


class TestFrontendWiring:
    def _src(self, rel):
        return (OASX / rel).read_text(encoding='utf-8')

    def test_api_client_has_clear_queue(self):
        assert 'clearQueue' in self._src('lib/api/api_client.dart')

    def test_controller_has_clear_queue(self):
        assert 'Future<String> clearQueue' in self._src(
            'lib/controller/task_list/task_list_controller.dart')

    def test_panel_has_clear_button_and_confirm(self):
        src = self._src('lib/views/tasks/queue_panel.dart')
        assert '_confirmClearQueue' in src, '⑦ 缺确认弹窗'
        assert '清空队列' in src, '⑦ 缺按钮文案'

    def test_panel_has_settings_entry(self):
        """★ ④: 队列行必须有进设置页的入口。"""
        src = self._src('lib/views/tasks/queue_panel.dart')
        assert 'openTaskSettings' in src, \
            '④ 队列行没有设置入口（openTaskSettings）'

    def test_count_task_skips_confirm(self):
        """★ ⑤: 次数类移除**不该**走 `_confirmAndRemove`。"""
        src = self._src('lib/views/tasks/queue_panel.dart')
        # 应存在 isAutoQueue 的分支: 非 auto -> 直接移除
        assert 'isAutoQueue(cmd)' in src, '⑤ 缺少"按类别决定是否确认"的分支'
        i = src.find('if (!c.isAutoQueue(cmd))')
        assert i > 0, '⑤ 未找到"次数类直接移除"的分支'
        body = src[i:i + 500]
        assert 'removeFromQueue' in body, '⑤ 次数类应直接调 removeFromQueue'
