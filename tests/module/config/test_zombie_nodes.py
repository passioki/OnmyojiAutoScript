# -*- coding: utf-8 -*-
"""S1: 僵尸配置节点清理（用户: "僵尸配置节点清理掉"）。

## 定义

`tasks/<Name>/` **存在且有 `config.py`**, 但**缺 `meta.py`** -> 没类别、没窗口,
`script_task.py` 也缺 -> **根本跑不了**。它在配置里留的 `scheduler` 节点就是僵尸。

实测: `tasks/OrochiMoans/` 只有 `assets.py` + `config.py`。

## ★★ 我第一版把它做错了两遍 ★★

1. **判据只有"有 config.py 但缺 meta.py"** -> 把 **`Script`** 与
   **`GlobalGame`** 也当僵尸**删掉了**。
   它们是 `config_model.EXTRA_GLOBAL` 里的**必需配置节点**（继承 `BaseModel`,
   **本来就不该有 `meta.py`**）-> 删掉等于**丢了脚本/全局设置**。
   已从 `config/template.json`（git 跟踪）恢复。
2. 所以现在用**白名单 + 双保险**（`TC.get()` 查不到才认）。
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestZombieDetection:
    def test_finds_orochi_moans(self):
        from module.config import task_catalog as TC
        z = TC.zombie_task_keys()
        assert 'OrochiMoans' in z, (
            f'OrochiMoans 缺 meta.py, 应被识别为僵尸; 实际 {sorted(z)}')

    def test_excludes_required_non_task_nodes(self):
        """★★ 必需的**非任务**配置节点**绝不能**被当成僵尸（我踩过）。"""
        from module.config import task_catalog as TC
        from module.config.config_model import EXTRA_GLOBAL
        z = TC.zombie_task_keys()
        for name in EXTRA_GLOBAL:
            assert name not in z, (
                f'{name} 是必需配置节点（EXTRA_GLOBAL）, 不该是僵尸 —— '
                f'删掉会丢脚本/全局设置')

    def test_excludes_resource_dirs(self):
        from module.config import task_catalog as TC
        z = TC.zombie_task_keys()
        for name in ('Component', 'GameUi', 'Utils', 'General'):
            assert name not in z, f'{name} 是资源库目录, 不是僵尸'

    def test_zombie_has_no_spec(self):
        """★ 双保险: 僵尸在 catalog 里**查不到**。"""
        from module.config import task_catalog as TC
        for name in TC.zombie_task_keys():
            assert TC.get_spec(name) is None, \
                f'{name} 能查到 spec -> 不该判成僵尸'

    def test_is_zombie_config_key(self):
        from module.config import task_catalog as TC
        assert TC.is_zombie_config_key('orochi_moans') is True
        assert TC.is_zombie_config_key('script') is False
        assert TC.is_zombie_config_key('global_game') is False
        assert TC.is_zombie_config_key('realm_raid') is False


class TestCleanup:
    @pytest.fixture()
    def config(self):
        import logging
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.server.main_manager import mm
        return mm.config_cache('恋鸟树')

    def test_missing_meta_task_has_no_window(self, config):
        """★ 僵尸任务在 catalog 里没有 spec -> 也就没有窗口/类别（这就是害处）。"""
        from module.config import task_catalog as TC
        assert TC.get_spec('OrochiMoans') is None
        assert TC.get('OrochiMoans') is None

    def test_required_nodes_still_present(self, config):
        """★★ `script` / `global_game` 必须**还在**（我误删过, 已恢复）。"""
        raw = config.model.model_dump()
        for key in ('script', 'global_game'):
            assert key in raw, (
                f'{key} 不见了 —— 它是必需配置节点, 不该被僵尸清理删掉')

    def test_idempotent(self, config):
        """★ 幂等: 没有僵尸键时 `clean_zombie_nodes()` 返回 False。"""
        # 先确保清干净
        config.clean_zombie_nodes()
        assert config.clean_zombie_nodes() is False, \
            'clean_zombie_nodes 应幂等（第二次无事可做）'

    def test_zombie_key_gone_after_clean(self, config):
        config.clean_zombie_nodes()
        raw = config.model.model_dump()
        from module.config import task_catalog as TC
        bad = [k for k in raw if TC.is_zombie_config_key(k)]
        assert not bad, f'清理后仍有僵尸键: {bad}'
