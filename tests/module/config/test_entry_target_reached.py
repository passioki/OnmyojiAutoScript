# -*- coding: utf-8 -*-
"""★ 守卫：`Config.entry_target_reached()` —— 「本轮这条跑完了没有」

## ★★★ 为什么需要这个文件（台账 `T10b`：**零覆盖**）★★★

★ 2026-10-13 的审计点名：`entry_target_reached()` 的**语义被改过**
  （`runs >= target` ➜ 「临时任务成功跑完一次即 `True`」），
  而 `tests/` 里**一个用例都没有**（全仓 `grep` 零命中）。

★ 这条函数是**用户痛点本体的判据**：

> ★★ **用户原话**：
> > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
> > "**或者按照时间戳来判断**"

★ 它的返回值**直接决定** `mark_entry_completed()` 会不会被调用
  （`script.py` 收尾，见 `docs/DESIGN-SPEC.md` §1.6.x-Z6 / §4.5-⑱）。
  ⇒ ★ 判错**任一方向**都是真 bug：
    * 该 `True` 却 `False` ➜ ★ 该条被**反复派发**（探索跑完又跑 —— §7.6 用户实测过）
    * 该 `False` 却 `True` ➜ ★ 该条**本轮再也不跑**（"任务被跳过"）

## ★ 覆盖的内容

| # | 断言 | 依据 |
|---|---|---|
| ① | 空 / 空白 `entry_id` ➜ `False`（**不误标**）| §1.5-C3 |
| ② | 未知 `entry_id` ➜ `False`（**不误标**）| 同上 |
| ③ | ★ 临时任务（`period = none`）➜ `True`（**跑完即本轮完成**）| **Z6** |
| ④ | ★ 周期任务（`daily` / `weekly` / `monthly`）➜ `False`（**不越权判**）| **Z6** |
| ⑤ | ★ 临时任务**不看目标次数**（`target=0` 与 `target=99` 都是 `True`）| **Z6 / §4.5-⑱** |
| ⑥ | ★ 源码守卫：**可执行代码里不许再出现 `runs >= target` 判据** | **Z6** |

★ 对齐 `docs/DESIGN-SPEC.md`：§1.6.x-Z6（L607）· §1.5-C1/C3（L371/L373）·
  §4.5-⑱（L1712）· §6.6「四类矛盾」第 3 条。

⚠ 本文件**不碰**用户实时配置：用**独立配置名** `__entry_target_cfg__`
  （`tests/conftest.py` 会快照 `config/*.json`，本文件在 `finally` 里自行删除）。
"""
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

CFG = '__entry_target_cfg__'
P = REPO / 'config' / f'{CFG}.json'

#: 临时任务（`period = none`）—— 出厂默认就是 `none`
TEMP_TASK = 'AreaBoss'
#: 周期任务 —— 出厂默认 `daily`
CYCLE_TASK = 'Orochi'


def _entry(task, eid, target=0):
    """造一条 `run_list` 条目（字段名与 `RunEntry.to_dict()` 一致）。"""
    return {'kind': 'task', 'task': task, 'target': target, 'entry_id': eid}


def _make(entries):
    """按 `template.json` 造一份**独立**配置，返回 `Config` 实例。"""
    import server  # noqa: F401  （★ 必须先 import，ConfigModel 才自动发现配置类）
    from module.config.config import Config

    os.chdir(REPO)
    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    opt = tmpl['script']['optimization']
    opt['run_list'] = list(entries)
    # ★ 一次性「周期回填」迁移已跑过 —— 否则它可能覆盖我们刻意设的 period
    #   （与 `test_period_classification.py` 同一手法）
    opt['period_backfilled'] = True
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    return Config(CFG)


def _set_period(cfg, task, period):
    """把任务级 `scheduler.period` 改成指定值（判据读的就是它）。"""
    from module.config.config_model import convert_to_underscore
    node = getattr(cfg.model, convert_to_underscore(task), None)
    assert node is not None, f'配置里应有 {task} 节点'
    node.scheduler.period = period
    return cfg


@pytest.fixture()
def make_cfg():
    """给出"造配置"的工厂，并保证**无论如何**都清理掉临时配置与 `cwd`。

    ⚠⚠ **必须还原 `cwd`**（★ 我踩过，有对照实验证据）：本文件要
      `os.chdir(REPO)`（因为 `Config()` 用 `Path.cwd()` 找 `config/`），
      而**测试进程是共享的** ⇒ ★ 不还原就污染**后面所有**依赖相对路径的用例。
      ★ 实测：不还原时 `tests/test_docs_no_dead_refs.py` 会**假红** ——
        对照实验：**无本文件 50 failed / 有本文件 49 failed**，
        差的正是那条"文档里的相对路径是否存在"。
    """
    created = []
    cwd_before = os.getcwd()

    def _factory(entries):
        created.append(P)
        return _make(entries)

    try:
        yield _factory
    finally:
        os.chdir(cwd_before)
        for p in created:
            try:
                p.unlink()
            except OSError:
                pass


# ─────────────────────────────────────────────── ① 空 entry_id ⇒ 不误标
def test_empty_entry_id_is_false(make_cfg):
    """★ 没有 `entry_id` ⇒ **必须 `False`**（否则会"整任务被跳过"）。

    ★ 依据：§1.5-C3「标记完成 ⇒ 本轮不再派发这一条」——
      没有身份就标完成 = 分不清是哪一条 = 可能误伤同任务的其它条目。
    """
    cfg = make_cfg([_entry(TEMP_TASK, 'e1')])
    assert cfg.entry_target_reached('') is False
    assert cfg.entry_target_reached('   ') is False
    assert cfg.entry_target_reached(None) is False


# ─────────────────────────────────────────────── ② 未知 entry_id ⇒ 不误标
def test_unknown_entry_id_is_false(make_cfg):
    """★ 队列里**没有这一条** ⇒ 必须 `False`（保守：不标完成）。

    ★ 若这里返回 `True`，一条**已被用户移除**的条目会被写进完成记忆
      ⇒ ★ 用户再加回来时会"跑不起来"。
    """
    cfg = make_cfg([_entry(TEMP_TASK, 'e1')])
    assert cfg.entry_target_reached('does-not-exist') is False


# ─────────────────────────────────────────────── ③ 临时任务 ⇒ True（核心）
def test_temp_task_reached_after_one_run(make_cfg):
    """★★★ 核心（Z6）：**临时任务成功跑完一次 ⇒ `True`**。

    ★ 走到这里 = 任务已经跑完（`script.py` 收尾）⇒ ★ 必须记「本轮完成」
      ⇒ ★ 否则它被**反复派发**（★ 用户实测：探索跑完又跑，§7.6）。
    ★ 与「计数」**无关** —— 这就是 [10-13] 裁定「丙」的落地。
    """
    cfg = make_cfg([_entry(TEMP_TASK, 'e1')])
    _set_period(cfg, TEMP_TASK, 'none')
    assert cfg.task_period(TEMP_TASK) == 'none', '前置：它应是临时任务'
    assert cfg.entry_target_reached('e1') is True, \
        '★ 临时任务跑完一次 = 本轮完成（Z6）'


# ─────────────────────────────────────────────── ④ 周期任务 ⇒ False
@pytest.mark.parametrize('period', ['daily', 'weekly', 'monthly'])
def test_cycle_task_is_false(make_cfg, period):
    """★★ Z6：**周期任务 ⇒ `False`（本函数不越权判）**。

    ★ 周期任务的完成由**周期记忆**负责：`Config._skip_by_period()`
      （`config.py:3746`，按 `period_key`）。
    ★ 若这里越权返回 `True` ⇒ ★ 周期任务会被当成"本轮已完成"
      ⇒ ★ 与周期记忆**两套口径打架**（§6.6 矛盾第 1 类的同一病根）。
    """
    cfg = make_cfg([_entry(CYCLE_TASK, 'c1')])
    _set_period(cfg, CYCLE_TASK, period)
    assert cfg.task_period(CYCLE_TASK) == period, f'前置：应为 {period}'
    assert cfg.entry_target_reached('c1') is False, \
        f'★ 周期任务（{period}）的完成判定不归本函数（Z6）'


# ─────────────────────────────────────────────── ⑤ 不看 target
@pytest.mark.parametrize('target', [0, 1, 30, 99])
def test_temp_task_ignores_target(make_cfg, target):
    """★★ Z6：临时任务的判据**与 `target` 无关**（这才是"痛点"的修法）。

    ## ★★ 用户原话（这组参数就是它）

    > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"

    ★ 旧实现是 `get_entry_runs(eid) >= target` —— `runs` 是**落盘计数器**
      ⇒ ★ 残留值让任务"开跑即结束"。
    ★ 现行：★ 临时任务**跑完即 `True`**，不论 `target` 是 0 还是 99。
    """
    cfg = make_cfg([_entry(TEMP_TASK, 'e1', target=target)])
    _set_period(cfg, TEMP_TASK, 'none')
    assert cfg.entry_target_reached('e1') is True, \
        f'★ target={target} 时临时任务仍应判「本轮完成」（判据不看计数）'


# ─────────────────────────────────────────────── ⑥ 源码守卫：不许退回计数判据
def test_source_has_no_count_based_judgement():
    """★★★ 源码级守卫：`entry_target_reached()` 里**不许**再出现
    「`runs >= target`」那种**计数判据**。

    ★ 为什么必须钉死：★ 那正是用户痛点（"重新跑时读到上一轮计数 ⇒ 跑不起来"）
      —— 一旦有人"顺手改回去"，判据会**静默退化成旧行为**，而其它测试看不出来。
    ★ 做法：`tokenize` 剥掉**注释**（本文件的 `_target_reached` 里保留了
      大量"旧写法"的说明文字，★ 直接正则匹配会**假红** —— 本项目有前科）。
    """
    import io
    import tokenize

    src = (REPO / 'module' / 'config' / 'config.py').read_text(encoding='utf-8')
    code_only = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        code_only.append(tok.string)
    code = ' '.join(code_only)

    # ★ 旧判据的两种写法都不允许出现在**可执行代码**里
    for bad in ("get_entry_runs ( self . config_name , eid ) >= target",
                "get_entry_runs(self.config_name, eid) >= target"):
        assert bad not in code, \
            f'★ 不许把「计数 >= target」判据改回去：{bad}'

    # ★ 正例钉死：现行判据必须**存在**（临时任务那一支）
    assert "'none'" in code, \
        "★ entry_target_reached() 必须按 period == 'none' 判临时任务（Z6）"
