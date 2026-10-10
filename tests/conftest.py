# -*- coding: utf-8 -*-
"""★★ 全局测试防护（审计修复）—— **防止测试写脏用户的实时配置** ★★

## 为什么必须有这个文件

审计发现: **4 个测试文件直接改用户实时配置**，而 `tests/` 下**原本没有
`conftest.py`** —— 没有任何全局快照/还原机制，全靠各文件自觉。

**实证后果**（2026-10-10）: `config/恋鸟树.json` 的 `run_list` 被
`tests/module/config/test_entry_id.py` 覆盖成**两条 `entry_id` 完全相同**的
`RealmRaid` —— 既**丢了用户编排**, 又**在实时配置里破坏了 E2 不变量**
（`entry_id` 必须唯一）。而 `恋鸟树.json` **从未被 git 跟踪** -> **无法恢复**。

这是本项目**第 5 次**同类事故（前 4 次见 `docs/SESSION-LEDGER.md` §26/§29/§34）。
所以这次做**机制性**防护, 而不是再靠"记得还原"。

## 做什么

`autouse=True` 的 **session 级** fixture:
1. 会话开始: 把 `config/*.json`（**排除 `template.json`**）**整份快照到内存**
2. 会话结束: **逐字节比对**; 有变化就**还原**并**大声报警**（不是静默还原）
3. **额外**: 检查每个 `run_list` 里 `entry_id` 唯一（E2 不变量）, 发现重复就报警

★ **为什么还要报警而不是静默还原**:
  静默还原会让"测试在改真实配置"这件事**永远不被发现** —— 测试会继续
  依赖那个副作用（例如"先写再读"）, 而在别人机器上就挂。本项目一贯做法是
  "**让静默失败变成看得见**"（见 `build_run_list()` 的护栏注释）。

★ **为什么排除 `template.json`**:
  它是"新账号模板"的**源头**; 某些测试有意用它生成配置。审计确认它**已有个
  被测试改过的指纹**（`run_list: []` 等）, 但那是**期望值**而非污染 ——
  排除它可避免误报。
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO / 'config'

#: 这些文件**不**参与快照（有意允许测试改）
_EXEMPT = {'template.json'}


def _config_files():
    if not CONFIG_DIR.is_dir():
        return []
    return sorted(p for p in CONFIG_DIR.glob('*.json')
                  if p.name not in _EXEMPT)


def _check_entry_ids(path: Path) -> list:
    """E2 不变量: 同一个 `run_list` 里 `entry_id` 必须**唯一**。

    :return: 违规描述列表（空 = 通过）
    """
    bad = []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        rl = ((data.get('script') or {}).get('optimization') or {}
              ).get('run_list') or []
        seen = {}
        for i, e in enumerate(rl):
            if not isinstance(e, dict):
                continue
            eid = e.get('entry_id')
            if not eid:
                continue
            if eid in seen:
                bad.append(
                    f'{path.name}: run_list[{seen[eid]}] 与 [{i}] 的 '
                    f'entry_id 相同 ({eid!r}) —— 破坏 E2 不变量；'
                    f' 多半是测试用 `RunList([...])` 构造后直接 save')
            else:
                seen[eid] = i
    except Exception as exc:
        bad.append(f'{path.name}: 解析失败 {type(exc).__name__}: {exc}')
    return bad


@pytest.fixture(scope='session', autouse=True)
def _guard_live_config():
    """会话级: 快照 -> 跑测试 -> 比对/还原/报警。"""
    files = _config_files()
    snapshot = {}
    for p in files:
        try:
            snapshot[p] = p.read_bytes()
        except OSError:
            pass

    # 进会话前先体检一次（也可能是上次跑测试留下的）
    pre_bad = []
    for p in files:
        pre_bad.extend(_check_entry_ids(p))

    yield

    # ---------- 会话结束: 比对 ----------
    changed = []
    for p, before in snapshot.items():
        try:
            after = p.read_bytes()
        except OSError:
            continue
        if after != before:
            changed.append(p)
            try:
                p.write_bytes(before)      # ★ 还原
            except OSError:
                pass

    post_bad = []
    for p in files:
        post_bad.extend(_check_entry_ids(p))

    if changed:
        names = ', '.join(p.name for p in changed)
        # ★ 大声报警（不是静默还原）
        print('\n' + '=' * 72)
        print('★★★ 测试污染了用户实时配置 —— 已自动还原 ★★★')
        print(f'  被改的文件: {names}')
        print('  ★ 请修那个测试: 它应当在 `finally` 里自己备份 + 还原')
        print('    （正确范例: tests/module/config/test_queue_clear_and_settings.py）')
        print('=' * 72)

    if post_bad:
        print('\n★★★ E2 不变量告警（entry_id 必须唯一）★★★')
        for line in post_bad:
            print(f'  {line}')
