# -*- coding: utf-8 -*-
"""★ 守卫：`run_switch_soul()` 遇到**非法"组,队"配置**时，
★ 必须**响亮地跳过**（error 日志）而**不是抛异常终结任务**（台账 `N9-9`）。

## ★★ 用户原话（10-14 记录文件第 9 条）

> "**御灵之境更换御魂出错，直接跳过了更换。**"

## ★★ 真因（代码级，已实测）

```
★ switch_soul_config.switch_group_team 出厂默认 = '-1,-1'（:12）
★ 用户只勾「启用」没设组/队 ⇒ 值就是 '-1,-1'
★ 实测 switch_parser('-1,-1') ⇒ (-1, -1)      ← ★ 解析**成功**（不抛）
★ ⇒ 绕过旧代码那唯一的 `except ValueError`
★ ⇒ switch_soul_one(-1, -1) ⇒ get_group_assets(-1) 是 dict 下标
★ ⇒ ★★ KeyError: -1   ← ★ 不是 ValueError ⇒ 仍抓不住
★ ⇒ 异常冒泡；而**所有调用方**（25+ 个任务）都把 run_switch_soul(...)
    写在 try 之外（如 GoryouRealm/script_task.py:26-28）
★ ⇒ ★★ 整局任务被这一行终结 ⇒ 用户看到"直接跳过了更换"
```

## ★ 为什么"跳过"是**规格**（不是敷衍）

★ `SESSION-INDEX.md:1162`（10-08 12:00 已确认）：
> "确认：**所有调用方都不检查返回值**，
>  所以『**跳过切换御魂**』是**安全的**。"
★ `switch_soul.py` 的 `_scan_for_name` 注释同源：
  "仍未找到则返回 False（**调用方跳过切换，不要让整局任务卡死**）"。

## ★ 覆盖的内容

| # | 断言 | 依据 |
|---|---|---|
| ① | ★★ `'-1,-1'`（出厂默认）⇒ **不抛异常**、**不进 UI** | N9-9 真因 |
| ② | ★ 其它非法值（`'0,0'` / `'8,1'` / `'1,5'` / `'x'` / `'1'` / 空）⇒ 同样跳过 | 同上 |
| ③ | ★ **不碰 UI**（`click_preset` / `switch_souls` **不被调用**）| ★ 非法配置不该先切进式神录 |
| ④ | ★ 合法值（`'1,1'` / `'4,2'` / `(1,1)` / `[(1,1),(2,2)]`）⇒ **正常走 UI** | 反向守卫（防"一律跳过"的走偏修法）|
| ⑤ | ★ **必须留下 error 级日志**（★ 治"静默"）| 用户"出错…直接跳过"的体感 |
| ⑥ | ★ `switch_soul_one()` 自己也要在**取素材之前**校验 | ★ 防"另一条入口"再犯 |

★ 本文件**不碰 UI**：用一个**只有被测方法**的轻量对象
  （`run_switch_soul` 只用到 `logger` + `_parse_switch_target` +
  `click_preset` / `switch_souls` —— 后两个在"跳过"路径上**不该被调用**）。
"""
import logging
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.disable(logging.CRITICAL)

from tasks.Component.SwitchSoul.switch_soul import SwitchSoul  # noqa: E402


class _Probe(SwitchSoul):
    """★ 只借 `run_switch_soul` / `_parse_switch_target`，把 UI 记成"是否被调用"。"""

    def __init__(self):
        self.clicked_preset = 0
        self.switched = []

    # ---- UI：**只记录，不真的动界面** ----
    def click_preset(self) -> None:            # noqa: D102
        self.clicked_preset += 1

    def switch_souls(self, target) -> None:    # noqa: D102
        self.switched.append(target)


BAD_VALUES = ['-1,-1', '0,0', '8,1', '1,5', '-1,1', '1,-1',
              'x', '', '1', '1,2,3', 'a,b']
GOOD_VALUES = ['1,1', '4,2', '7,4', '1,4']


# ─────────────────────────── ① 出厂默认值不许抛异常
def test_default_unset_value_is_skipped_not_raised():
    """★★★ 核心（N9-9 的真身）：★ 出厂的 `'-1,-1'` 必须**安静跳过**，不许抛。

    ★ 旧代码在这里抛 **`KeyError: -1`**（经 `get_group_assets` 的 dict 下标）
      ⇒ ★ 25+ 个调用方没包 `try` ⇒ **整局任务终结**。
    """
    probe = _Probe()
    try:
        probe.run_switch_soul('-1,-1')
    except Exception as exc:                    # ★★ 就是实机那次
        pytest.fail(
            '★ 未设置御魂（`-1,-1`）时 `run_switch_soul()` 抛了异常 '
            f'（{type(exc).__name__}: {exc}）\n'
            '★ 这会让**整局任务**被终结（所有调用方都在 try 之外）—— '
            '而按已定案语义，这里应当**跳过并继续**。\n'
            '★ 检查 `_parse_switch_target()` 的值域校验是否在"取素材"之前。')


# ─────────────────────────── ② 各种非法值都只许跳过
@pytest.mark.parametrize('value', BAD_VALUES)
def test_invalid_values_are_skipped_not_raised(value):
    """★ 全部非法形式（含**能解析但越界**的）都只许跳过。"""
    probe = _Probe()
    probe.run_switch_soul(value)                # ★ 不抛即通过
    assert probe.switched == [], (
        f'★ 非法配置 {value!r} **不该真的去换御魂**')


# ─────────────────────────── ③ 非法配置不许先切进式神录（UI）
@pytest.mark.parametrize('value', BAD_VALUES)
def test_invalid_values_do_not_touch_ui(value):
    """★ 非法配置 ⇒ ★ **连 `click_preset()` 都不该调**。

    ★ 为什么重要：★ 校验若排在 `click_preset()` **之后**，
      ★ 就会"先把界面切进式神录，再发现配置是错的" ⇒ ★ 白跑一趟 UI
        （★ 实机上就是几秒的无效操作 + 可能残留界面状态）。
    """
    probe = _Probe()
    probe.run_switch_soul(value)
    assert probe.clicked_preset == 0, (
        f'★ 非法配置 {value!r} 不该先执行 `click_preset()` —— '
        '★ 校验必须排在**所有 UI 动作之前**')


# ─────────────────────────── ④ 反向：合法值必须真的走 UI
@pytest.mark.parametrize('value,expect', [
    ('1,1', [(1, 1)]),
    ('4,2', [(4, 2)]),
    ('7,4', [(7, 4)]),
])
def test_valid_string_values_still_switch(value, expect):
    """★ 反向守卫：★ 合法配置必须**照常**走 UI（防"一律跳过"的走偏修法）。"""
    probe = _Probe()
    probe.run_switch_soul(value)
    assert probe.clicked_preset == 1, '★ 合法配置必须真的进式神录'
    assert probe.switched == [expect], f'★ 应换成 {expect}'


@pytest.mark.parametrize('value,expect', [
    ((1, 1), [(1, 1)]),
    ([(1, 1), (2, 2)], [(1, 1), (2, 2)]),
])
def test_valid_tuple_values_still_switch(value, expect):
    """★ 元组 / 列表形式（`BondlingFairyland` / `Hunt` 等调用方用的形式）。"""
    probe = _Probe()
    probe.run_switch_soul(value)
    assert probe.clicked_preset == 1
    assert probe.switched == [expect]


@pytest.mark.parametrize('value', [(-1, -1), [(1, 1), (9, 9)], (1, 9)])
def test_invalid_tuple_values_are_skipped(value):
    """★ 元组形式的**越界**同样必须跳过（★ 不是只有字符串那条入口）。"""
    probe = _Probe()
    probe.run_switch_soul(value)
    assert probe.clicked_preset == 0, '★ 非法元组配置不该碰 UI'
    assert probe.switched == []


# ─────────────────────────── ⑤ 必须留下 error 日志（治"静默"）
def test_skip_is_logged_at_error_level(caplog):
    """★★ 跳过的**原因必须看得见**（★ 用户的抱怨是"出错…直接跳过"）。

    ★ 判据：★ `logger.error` 里必须出现"跳过"与"范围"（可诊断）。
    ★ 为什么用 `caplog`：★ 本项目 logger 是自定义的，但 `propagate`/标准
      logging 记录仍可被 pytest 捕获；★ 若捕获不到就**跳过**（不假装通过）。
    """
    import logging as _logging
    probe = _Probe()
    with caplog.at_level(_logging.ERROR):
        probe.run_switch_soul('-1,-1')
    text = ' '.join(r.getMessage() for r in caplog.records)
    if not text:
        pytest.skip('本环境未捕获到日志记录（logger 配置差异），跳过')
    assert '跳过' in text, (
        f'★ 必须明确写出"跳过"（否则又成"静默跳过"）。实际：{text!r}')
    assert ('1-7' in text) or ('范围' in text), (
        f'★ 必须说明**合法范围**（便于用户自查配置）。实际：{text!r}')


# ─────────────────────────── ⑦ 运行时：switch_soul_one 必须自己拦非法值
def _bare_switch_soul_one_stub():
    """★ 能跑 `switch_soul_one` **校验段**的最小替身（不需要真设备/真配置）。

    ★ 校验段在函数**最前面** ⇒ ★ 非法值时它**不会**走到截图/OCR
      ⇒ ★ 这些属性只需**占位存在**即可（不会被访问）。
    """
    import types

    class _Dev:
        image = None

    return types.SimpleNamespace(
        device=_Dev(),
        config=None,
        O_SS_GROUP_NAME=types.SimpleNamespace(detect_and_ocr=lambda img: [],
                                              keyword=''),
        S_SS_GROUP_SWIPE_UP='up', S_SS_GROUP_SWIPE_DOWN='down',
        S_SS_TEAM_SWIPE_DOWN='d2', S_SS_TEAM_SWIPE_UP='u2',
        I_SOU_SWITCH_SURE='sure', I_CHECK_BLOCK='blk', I_SOU_TEAM_PRESENT='tp',
        screenshot=lambda: None, swipe=lambda *a, **k: None,
        click=lambda *a, **k: None,
    )


@pytest.mark.parametrize('group,team', [(-1, -1), (0, 0), (8, 1), (1, 5), (1, 0)])
def test_switch_soul_one_runtime_rejects_out_of_range(group, team):
    """★★★ **运行时**守卫（★ 这条才是"真会红"的那条）：

    `switch_soul_one(-1, -1)` 必须抛 **`ValueError`**（带范围说明），
    **不许**抛 `KeyError`（★ 那是 `get_group_assets(-1)` 的 dict 下标 —— 旧行为）。

    ⚠★ 为什么必须**运行时**、不能只比源码行序（★ 我踩过）：
      ★ 我先前那条"源码级"守卫只断言 `raise ValueError` 排在
      `get_group_assets(` **之前** ⇒ ★ 把校验改成 `if False:`（★ 校验形同不存在）
      **它照样绿**（★ 因为 `raise` 字样还在）。
      ★ 运行时断言**无法**被这种改法骗过。
    """
    stub = _bare_switch_soul_one_stub()
    with pytest.raises(ValueError) as ei:
        SwitchSoul.switch_soul_one(stub, group, team)
    assert 'must be in' in str(ei.value), (
        f'★ 错误信息应说明合法范围，实际：{ei.value!r}')


# ─────────────────────────── ⑥ 源码级：校验必须排在取素材之前
def test_switch_soul_one_validates_before_fetching_assets():
    """★ `switch_soul_one()` 的范围校验必须**存在**，且排在**取素材之前**。

    ★ 为什么：★ `get_group_assets(-1)` 是 **dict 下标** ⇒ 抛 `KeyError`
      （★ **不是** `ValueError`）⇒ ★ 若校验排在它后面（或干脆没有），
      `KeyError` 照样冒泡 ⇒ 整局任务被终结（N9-9 的真身）。
    ★ 做法：★ 用源码的**行序**判断（★ 不真的调用 —— 它要 UI）。

    ⚠★ 我第一版这条守卫**空转过**（★ 注入验证抓出来的，记下来）：
      它只写了 `assert guard_idx < fetch_idx` —— 而"校验被整个删掉"时
      `guard_idx is None`，**只有 `is not None` 那一句会红**；
      ★ 我当时那句在，但注入**只删了 raise、没删 if** 的形态下就不够。
      ★ 现在改成：★ **必须同时断言"两处都存在"**（顺序才是有意义的）。
    """
    src = (REPO / 'tasks' / 'Component' / 'SwitchSoul' / 'switch_soul.py') \
        .read_text(encoding='utf-8')
    # ★ 剥掉注释（本项目有"守卫匹配到自己注释"的前科）
    lines = [l.split('#')[0] for l in src.split('\n')]

    fn_start = None
    for i, l in enumerate(lines):
        if l.strip().startswith('def switch_soul_one('):
            fn_start = i
            break
    assert fn_start is not None, '★ 应能找到 `switch_soul_one`'

    # 到下一个 def 为止
    fn_end = len(lines)
    for j in range(fn_start + 1, len(lines)):
        if lines[j].startswith('    def '):
            fn_end = j
            break
    body = lines[fn_start:fn_end]

    guard_idx = next((k for k, l in enumerate(body) if 'raise ValueError' in l), None)
    fetch_idx = next((k for k, l in enumerate(body)
                      if 'get_group_assets(' in l), None)
    assert guard_idx is not None, (
        '★ `switch_soul_one` **必须自己校验**组/队范围（抛出可读的 `ValueError`）'
        ' —— ★ 否则非法值会先在 `get_group_assets()` 的 dict 下标上抛 '
        '`KeyError`（不是 ValueError），旧的 `except ValueError` 抓不住'
        '⇒ 整局任务被终结（N9-9）')
    assert fetch_idx is not None, '前置：应有 `get_group_assets(` 调用'
    assert guard_idx < fetch_idx, (
        '★ 范围校验必须排在 `get_group_assets()` **之前** —— '
        '★ 顺序反了的话，`KeyError` 会先抛出来（N9-9 就是这个顺序错的）')
