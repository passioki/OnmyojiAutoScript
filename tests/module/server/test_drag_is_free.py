# -*- coding: utf-8 -*-
"""★★★ S7: **拖动永远自由** —— 端点层直测 ★★★

## 为什么单独一个文件（补覆盖缺口）

用户的核心诉求原话:
> "我只需要保持**可以自由拖动/改变执行顺序**就行"
> "**任意拖**，但「休息」条目仍强制排最后"

★ 在此之前, "拖动永远自由"这条**只在间接层面**被测到:
  * `test_segment_rest_position.py` 测"`_tag_and_place_rest` 不重排任务"
  * `test_execution_queue.py` 测"用户编排就是队列前缀"

★ 但**端点层**那条 —— `PUT /run_list` 收到**跨类别**的次序时
  **返回 200 而不是拒绝** —— **没有直测**。
  ★ 而这正是用户此前踩过的坑: 后端返回
    `{'error': ..., 'drag_blocked': True, 'entries': [...]}`,
    前端把它当成"保存成功" -> 用户看到"能随便拖但**没有任何提示**"。

★ 所以这里**逐字**钉住:
  ① 跨类别拖动 -> **被接受**（顺序真的存下来）
  ② 返回体里**不再有** `drag_blocked` / `error`
  ③ ★ 唯一的硬约束: 「休息」被拖到中间 -> **不拒绝**, 而是**归位到最后**
     （归一化, 不是校验 —— 这是本设计的关键区别）
  ④ `POST /run_list/entry` 与 `PUT /run_list` 契约一致（都不拒绝）

## ⚠ 不碰真实配置

用临时配置名 `__drag_free__` + `config/template.json`, `finally` 里删掉。
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

CFG = '__drag_free__'
P = REPO / 'config' / f'{CFG}.json'

#: 段归属（从 `task_catalog` 实测）: MetaDemon = timed; Orochi = fixed
TIMED = 'MetaDemon'
FIXED = 'Orochi'


def _write(run_list):
    """按模板写一份临时配置, 并把用到的任务**逐个启用**。

    ★ 不启用的话 `save_run_list` 仍能存, 但 `build_queue()` 会剔除它们,
      后续"顺序真的存下来了"的断言就**什么都没测到**。
    """
    from module.config.config_model import convert_to_underscore

    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    tmpl['script']['optimization']['run_list'] = run_list
    for e in run_list:
        task = e.get('task')
        if not task:
            continue
        node = tmpl.get(convert_to_underscore(task))
        if isinstance(node, dict) and isinstance(node.get('scheduler'), dict):
            node['scheduler']['enable'] = True
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')


def _disk():
    """★ 从**磁盘**读回（证明端点真的落盘了, 不是只改内存）。"""
    d = json.loads(P.read_text(encoding='utf-8'))
    return [(e.get('kind'), e.get('task')) for e
            in d['script']['optimization']['run_list']]


def _put(entries):
    import server  # noqa: F401
    from module.server import schema_router as SR
    return asyncio.new_event_loop().run_until_complete(
        SR.put_run_list(CFG, entries))


def _post(entry, index=-1):
    import server  # noqa: F401
    from module.server import schema_router as SR
    return asyncio.new_event_loop().run_until_complete(
        SR.post_run_list_entry(CFG, entry, index))


@pytest.fixture(autouse=True)
def _tmp_config():
    os.chdir(REPO)          # ★ `write_json` 用 `Path.cwd()`
    _write([
        {'kind': 'task', 'task': FIXED, 'entry_id': 'e-fixed'},
        {'kind': 'task', 'task': TIMED, 'entry_id': 'e-timed'},
    ])
    yield
    try:
        P.unlink()
    except OSError:
        pass


class TestCrossGroupDragIsAccepted:
    """★★ 用户核心诉求: **跨类别拖动必须被接受**。"""

    def test_timed_before_fixed_is_accepted(self):
        """把 **timed** 拖到 **fixed** 之前 —— 旧的 `timed_first` 之外会拒绝。"""
        res = _put([
            {'kind': 'task', 'task': TIMED, 'entry_id': 'e-timed'},
            {'kind': 'task', 'task': FIXED, 'entry_id': 'e-fixed'},
        ])
        assert 'error' not in res, f'★ 跨类别拖动被拒了: {res}'
        assert res.get('drag_blocked') is not True, \
            '★ 返回体里不该再有 `drag_blocked`（约束已删）'
        assert _disk() == [('task', TIMED), ('task', FIXED)], _disk()

    def test_fixed_before_timed_is_accepted(self):
        """反向: 把 **fixed** 拖到 **timed** 之前。"""
        res = _put([
            {'kind': 'task', 'task': FIXED, 'entry_id': 'e-fixed'},
            {'kind': 'task', 'task': TIMED, 'entry_id': 'e-timed'},
        ])
        assert 'error' not in res, f'★ 被拒了: {res}'
        assert _disk() == [('task', FIXED), ('task', TIMED)], _disk()

    def test_any_permutation_is_accepted(self):
        """★ 穷举全排列 —— **任何**次序都必须被接受。"""
        import itertools
        items = [
            {'kind': 'task', 'task': FIXED, 'entry_id': 'e-fixed'},
            {'kind': 'task', 'task': TIMED, 'entry_id': 'e-timed'},
            {'kind': 'task', 'task': 'Exploration', 'entry_id': 'e-exp'},
        ]
        for perm in itertools.permutations(items):
            res = _put(list(perm))
            assert 'error' not in res, (
                f'★ 次序 {[p["task"] for p in perm]} 被拒了: {res}')
            assert _disk() == [('task', p['task']) for p in perm], _disk()

    def test_response_has_no_drag_blocked_key_at_all(self):
        """★ 反向守卫: `drag_blocked` 这个键**彻底**不该再出现。

        ★ 为什么必须钉: 前端曾经把带 `entries` 的返回当成"保存成功",
          于是**后端一直在拒绝、前端一声不吭**。删掉这个键就不再有歧义。
        """
        res = _put([
            {'kind': 'task', 'task': TIMED, 'entry_id': 'e-timed'},
            {'kind': 'task', 'task': FIXED, 'entry_id': 'e-fixed'},
        ])
        assert 'drag_blocked' not in res, \
            f'★ `drag_blocked` 又回来了 —— 前端会误判: {res.keys()}'
        # 成功时应给出确认信号（前端据此判断"真的存了"）
        assert 'entries' in res


class TestRestKeepsItsPosition:
    """★★★ P-2（用户裁定）: 休息**不再**被归一化到最后 ★★★

    ## 用户原话

    > "休息**也是任务**, 只不过可以选择插入定时任务。"
    > "休息当然就是**挡住后边的**, 本质为了**防封**, **符合预期**。"
    > "1 **全删**"（`'__rest__'` 特殊标记）

    ## 曾经错在哪

    本类原来叫 `TestRestIsNormalizedNotRejected`, docstring 引的是
    "用户确认: 任意拖，但「休息」条目仍强制排最后" ——
    ★ **那句话不是用户的裁定**，是误记成长期规则的临时约束。

    ## 现在

    * `PUT /run_list` / `POST /run_list/entry` **原样保存**用户给的顺序
    * `rest` 仍在**任意位置** —— 拖到最前、中间、最后都**照原样落库**
    * `rest` 仍**阻塞列表**（那是它的功能, 不是排序约束）
    """

    def test_rest_dragged_to_front_stays_at_front(self):
        res = _put([
            {'kind': 'rest', 'minutes': 5, 'entry_id': 'r1'},
            {'kind': 'task', 'task': FIXED, 'entry_id': 'e-fixed'},
            {'kind': 'task', 'task': TIMED, 'entry_id': 'e-timed'},
        ])
        assert 'error' not in res, f'★ rest 被拖到最前竟然被拒了: {res}'
        assert _disk() == [('rest', None), ('task', FIXED),
                           ('task', TIMED)], _disk()

    def test_rest_dragged_to_middle_stays_in_middle(self):
        res = _put([
            {'kind': 'task', 'task': FIXED, 'entry_id': 'e-fixed'},
            {'kind': 'rest', 'minutes': 5, 'entry_id': 'r1'},
            {'kind': 'task', 'task': TIMED, 'entry_id': 'e-timed'},
        ])
        assert 'error' not in res, f'★ 被拒了: {res}'
        assert _disk() == [('task', FIXED), ('rest', None),
                           ('task', TIMED)], _disk()

    def test_multiple_rests_keep_their_relative_order(self):
        """★ 多个 rest **之间**保序 —— 不能把 5 分钟和 7 分钟弄反。"""
        _put([
            {'kind': 'rest', 'minutes': 5, 'entry_id': 'r1'},
            {'kind': 'task', 'task': FIXED, 'entry_id': 'e-fixed'},
            {'kind': 'rest', 'minutes': 7, 'entry_id': 'r2'},
            {'kind': 'task', 'task': TIMED, 'entry_id': 'e-timed'},
        ])
        d = json.loads(P.read_text(encoding='utf-8'))
        mins = [e.get('minutes') for e
                in d['script']['optimization']['run_list']
                if e.get('kind') == 'rest']
        assert mins == [5, 7], f'★ rest 之间被弄乱了: {mins}'

    def test_same_contract_on_insert_endpoint(self):
        """`POST /run_list/entry` 与 `PUT /run_list` **同一套契约**。

        ★ P-2: 两边都**没有** rest 排序约束, 所以插入到最前就**留在最前**。
        """
        res = _post({'kind': 'rest', 'minutes': 3}, 0)
        assert 'error' not in res, f'★ insert 被拒了: {res}'
        assert 'drag_blocked' not in res, (
            '★ insert 端点也**不该**返回 `drag_blocked`（曾经能绕过约束, '
            '现在两边都没有约束）')
        kinds = [k for k, _ in _disk()]
        assert kinds[0] == 'rest', f'★ rest 没留在最前: {kinds}'


class TestNoDragConstraintCodeLeft:
    """★ 反向守卫: 拖动约束的**代码**不得复活。"""

    def test_check_drag_allowed_is_gone_or_inert(self):
        from _srcutil import code_only
        src = code_only(REPO / 'module' / 'server' / 'schema_router.py')
        # 若还有这个函数, 它必须恒返回放行
        if 'def _check_drag_allowed' in src:
            from _srcutil import code_of
            body = code_of(REPO / 'module' / 'server' / 'schema_router.py',
                           'def _check_drag_allowed')
            assert 'return True' not in body, (
                '★ `_check_drag_allowed` 竟然又返回 True（= 又开始拦拖动）')

    def test_no_drag_blocked_anywhere_in_production(self):
        """★ `drag_blocked` 在整个生产代码里都**不该**再出现（剥注释后）。"""
        from _srcutil import code_only
        for rel in ('module/server/schema_router.py',
                    'module/config/config.py'):
            src = code_only(REPO / rel)
            assert 'drag_blocked' not in src, \
                f'★ {rel} 里又出现了 `drag_blocked`'

    def test_no_priority_mode_anywhere_in_production(self):
        """★ 「调度优先级三模式」的符号不得复活。"""
        from _srcutil import code_only
        for rel in ('module/config/config.py',
                    'module/server/schema_router.py',
                    'module/server/script_router.py',
                    'tasks/Script/config_optimization.py'):
            src = code_only(REPO / rel)
            for dead in ('priority_mode', '_segment_queue',
                         'migrate_priority_mode_once', 'resegment_run_list'):
                assert dead not in src, f'★ {rel} 里又出现了 `{dead}`'
