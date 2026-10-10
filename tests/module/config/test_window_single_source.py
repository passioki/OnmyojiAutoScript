# -*- coding: utf-8 -*-
"""★★★ 窗口定义**只有一处权威** —— 迁移表不得与 meta 打架 ★★★

## 用户报的问题

> "**寮突破 window 设置混乱、不生效**而且**不再开放时间段**"

## 实测根因（两套窗口定义打架）

`Function.window` 的优先级是 **用户配置 > meta**:

```
Function.window = ① 用户配置里的 windows   ← 最权威
                  ② 否则 meta.py 的 window  ← 兜底
```

★ 而 `tasks/Component/config_scheduler.py` 的**一次性推荐窗口迁移**
（`RECOMMENDED_WINDOWS` / `RECOMMENDED_SECONDS`）会把值**写进用户配置**
-> ★ **永久压住** meta 的游戏机制窗口。

实测 `RyouToppa`（寮突破）:

| 来源 | 窗口 |
|---|---|
| `tasks/RyouToppa/meta.py`（游戏机制）| `00:00-23:59` = **全天** |
| 迁移表写进配置的值 | `07:00-09:00` |

-> 寮突破每天只有 2 小时能跑, 其余时间一律"不在开放时段"
   —— 用户看到的"设置混乱 + 不生效 + 不再开放时间段"。

★ 用户裁定 **A（全天可跑, 跟 meta）** -> 已把 `ryou_toppa` 从推荐表移除。

★ 本文件钉住这条规则: **meta 声明了窗口的任务, 迁移表不许再给它塞一个**
  （除了用户**明确要求**过的 `restart` —— 那是"一天两次领体力", 不是残留）。
"""
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestRecommendedWindowsDoNotFightMeta:
    def test_ryou_toppa_removed_from_recommended(self):
        """★ 寮突破**必须**从推荐表移除（用户选 A: 全天可跑）。"""
        from tasks.Component.config_scheduler import (
            RECOMMENDED_SECONDS, RECOMMENDED_WINDOWS)
        assert 'ryou_toppa' not in RECOMMENDED_WINDOWS, (
            '★ `ryou_toppa` 不该在推荐窗口表里 —— '
            '它会压住 meta 的全天窗口（用户报的"设置混乱"）')
        assert 'ryou_toppa' not in RECOMMENDED_SECONDS, (
            '★ 同上（SECONDS 表也要清掉）')

    def test_restart_kept(self):
        """★ `restart` **保留**（用户明确要的"一天两次领体力"）。"""
        from tasks.Component.config_scheduler import (
            RECOMMENDED_SECONDS, RECOMMENDED_WINDOWS)
        assert 'restart' in RECOMMENDED_WINDOWS, (
            '★ `restart` 的 12:00-14:00 / 20:00-22:00 是用户**明确要的**, '
            '不是历史残留 —— 不许顺手删掉')
        assert 'restart' in RECOMMENDED_SECONDS

    def test_no_recommended_overrides_unrestricted_meta(self):
        """★★ 通用守卫: **meta 声明全天窗口的任务**, 迁移表不许再塞窗口。

        ★ 为什么: 迁移值是**写进用户配置**的, 而配置优先级**高于** meta
          -> 一旦塞了, meta 的游戏机制定义就**永久失效**。
          这正是 `RyouToppa` 那个 bug 的一般形式。

        ★ **白名单 `restart`**（不是漏网, 是**已知且经用户确认**的例外）:
          用户原话要的是"**一天跑两次领体力**"（12:00-14:00 / 20:00-22:00）
          —— 那是**用户的偏好**, 本就该覆盖 meta 的全天兜底。
          ⚠ 它是**唯一**允许覆盖"全天 meta"的项; 以后要加必须在此写明理由。
        """
        import logging
        os.chdir(REPO)
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.config import task_catalog as TC
        from tasks.Component.config_scheduler import RECOMMENDED_SECONDS

        # ★ 已知且经用户确认的例外（见 docstring）
        ALLOW = {'restart'}

        bad = []
        for key in RECOMMENDED_SECONDS:
            if key in ALLOW:
                continue
            cmd = ''.join(p.capitalize() for p in key.split('_'))
            spec = TC.get_spec(cmd)
            if spec is None:
                continue
            ws = [w for w in (spec.windows_effective or [])
                  if getattr(w, 'enabled', False)]
            if not ws:
                continue
            if all(bool(getattr(w, 'is_unrestricted', False)) for w in ws):
                bad.append((key, cmd))
        assert not bad, (
            '★ 这些任务的 meta 声明的是**全天窗口**（= 无时段限制）, '
            '但迁移表还要给它塞窗口 -> 会永久压住 meta:\n  ' + str(bad) + '\n'
            '  （若确要覆盖, 请加进 ALLOW 并在 docstring 写明用户要求的理由）')


class TestRyouToppaIsFullDay:
    def test_live_config_is_unrestricted(self):
        """★ 实测: 寮突破的**生效**窗口必须是全天（配置里不该有它的窗口）。"""
        import logging
        os.chdir(REPO)
        logging.disable(logging.CRITICAL)
        import server  # noqa: F401
        from module.config.config import Function
        from module.server.main_manager import mm

        cfg = mm.config_cache('恋鸟树')
        value = cfg.model.model_dump().get('ryou_toppa')
        if value is None:
            pytest.skip('配置里没有 ryou_toppa')
        sch = value.get('scheduler') or {}
        assert not (sch.get('windows') or []), (
            '★ 寮突破配置里还有窗口 ' + repr(sch.get('windows')) + ' —— '
            '它会压住 meta 的全天窗口, 于是每天只有那几小时能跑')
        f = Function('ryou_toppa', value)
        assert f.in_window() is True, (
            '★ 寮突破应当是全天可跑（meta 声明 00:00-23:59）')
        assert not getattr(f, 'window_reason', None), (
            '★ 全天窗口不该有"不在开放时段"的理由')

    def test_next_run_is_a_datetime_not_none(self):
        """★ `next_run` **不许**是 `None` —— 它是 datetime 字段。

        ⚠ 我踩过: 修配置时把它写成 `None` -> `ConfigModel` 校验失败
          -> **配置加载直接崩**（`Input should be a valid datetime`）。
        """
        import json
        import logging
        os.chdir(REPO)
        logging.disable(logging.CRITICAL)
        p = REPO / 'config' / '恋鸟树.json'
        if not p.exists():
            pytest.skip('配置不存在')
        d = json.loads(p.read_text(encoding='utf-8'))
        bad = []
        for key, node in d.items():
            if not isinstance(node, dict):
                continue
            sch = node.get('scheduler')
            if not isinstance(sch, dict):
                continue
            if 'next_run' in sch and sch['next_run'] is None:
                bad.append(key)
        assert not bad, (
            '★ 这些任务的 `next_run` 是 None -> 配置会**加载失败**: ' + str(bad))
