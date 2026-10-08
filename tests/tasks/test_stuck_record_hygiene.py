# -*- coding: utf-8 -*-
"""防止回归: 组队任务不能在进入战斗前清掉 BATTLE_STATUS_S 豁免。

线上实测(2026-10-08, 日轮之陨组队)
----------------------------------
FallenSun(以及 Orochi / EternitySea / EvoZone / OtherWorldTwilight)的成员/队长循环里
原本写着:

    if self.is_in_room():
        self.device.stuck_record_clear()          # ← 清掉豁免
        if self.wait_battle(...):
            self.run_general_battle(...)          # ← 走到这里才重新 add

后果: 战斗一开始 add 上的 BATTLE_STATUS_S 被 clear 掉, 之后在
`wait_battle` 与下一场 `run_general_battle` 之间没有任何豁免。而
`BATTLE_STATUS_S` 在 device.stuck_unlimited_wait_list 里, 是**无限期**豁免
(见 module/device/device.py 的注释)—— 战斗结束到结算页之间那段约 1 秒的
**转场动画**上没有任何可识别的界面状态, 全靠这个豁免兜住。

豁免一旦被清掉, 卡死看门狗就从"300s 长豁免"退化成"60s 硬判定":
只要那一刻探测不到状态, 就会 GameStuckError → 重启游戏 → 掉线 →
队长邀请等待超时(用户看到的正是"组队超时")。

注意区分两类写法, 只有前者是缺陷:
  A) clear() 之后**没有** add()        -> 缺陷(本测试拦截)
  B) clear() 之后**紧跟** add(某个状态) -> 故意的重置, 语义正确(如 Duel.reset_device)
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 本次修复涉及的 5 个组队任务(共享"进房间->等开战->打"的同一段模板代码)
TEAM_TASK_FILES = [
    'tasks/FallenSun/script_task.py',
    'tasks/Orochi/script_task.py',
    'tasks/EternitySea/script_task.py',
    'tasks/EvoZone/script_task.py',
    'tasks/OtherWorldTwilight/script_task.py',
]


def _code_lines(path: Path):
    """返回 (行号, 内容) 并去掉注释行, 避免把说明文字当成真实调用。"""
    out = []
    for i, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        s = raw.strip()
        if s.startswith('#'):
            continue
        # 去掉行尾注释
        s = re.sub(r'\s+#.*$', '', s)
        out.append((i, s))
    return out


@pytest.mark.parametrize('rel', TEAM_TASK_FILES)
def test_no_clear_without_readd(rel):
    """clear() 之后必须紧跟 add(), 否则豁免被清掉会造成误判卡死。"""
    path = REPO_ROOT / rel
    assert path.exists(), f'{rel} 不存在'

    lines = _code_lines(path)
    offenders = []
    for idx, (lineno, text) in enumerate(lines):
        if 'stuck_record_clear' not in text:
            continue
        # 看后面几行有没有重新 add
        nxt = ' '.join(t for _, t in lines[idx + 1:idx + 4])
        if 'stuck_record_add' not in nxt:
            offenders.append(lineno)

    assert not offenders, (
        f'{rel} 第 {offenders} 行调用了 stuck_record_clear() 但之后没有 '
        f'stuck_record_add(): BATTLE_STATUS_S 的无限期豁免会被清掉, '
        f'战斗结束的转场动画会被 60s 看门狗误判为卡死并重启游戏。'
        f'应改为 stuck_record_add(\'BATTLE_STATUS_S\')。'
    )


@pytest.mark.parametrize('rel', TEAM_TASK_FILES)
def test_adds_battle_exemption_before_wait_battle(rel):
    """进入 wait_battle 前必须已经加上 BATTLE_STATUS_S 豁免。"""
    path = REPO_ROOT / rel
    text = path.read_text(encoding='utf-8')
    assert 'stuck_record_add' in text and 'BATTLE_STATUS_S' in text, (
        f'{rel} 应使用 BATTLE_STATUS_S 豁免')
    # 同一文件里 is_in_room -> wait_battle 之间应有 add
    code = '\n'.join(t for _, t in _code_lines(path))
    m = re.search(r'is_in_room\([^)]*\)\s*:(.{0,400}?)wait_battle', code, re.S)
    assert m, f'{rel} 未找到 is_in_room -> wait_battle 的相邻结构'
    assert 'stuck_record_add' in m.group(1), (
        f'{rel}: is_in_room() 到 wait_battle() 之间没有 stuck_record_add(), '
        f'说明豁免在进入等待前是缺失的')
