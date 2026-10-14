# -*- coding: utf-8 -*-
"""★ 守卫：`POST /{script}/queue/profiles` —— ★ **用户填的页名必须真的生效**（台账 `N9-4`）。

## ★★ 用户原话（[10-14] 记录第 4 条）

> "**添加任务顺序配置页时，新建时填写的名称不会生效，
>   目前是用重命名来做到第一次赋予名字的。**"

## ★★ 真因（前端，本轮已修）

★ 前端旧实现**既不弹输入框、也不传 `name`**：
```dart
final msg = await c.createQueueProfile();     // task_list_view.dart（旧）
```
★ 而后端是 `name = data.get('name') or default_name`
  ⇒ ★ **永远走自动编号**（`1/2/3`）⇒ ★ "填的名字不生效"。

★ ⇒ ★ **后端这一侧本来就是对的** ⇒ 本文件把它**钉死**（防以后有人
  "顺手"把 `name` 改成不用、或让它被别的分支覆盖）。

## ★ 覆盖的内容

| # | 断言 |
|---|---|
| ① | ★★ 传 `name='日常'` ⇒ 新建那页的名字**就是「日常」**（不是自动编号）|
| ② | ★ 不传 `name` ⇒ ★ **自动编号**（保留"懒得起名"的快捷路径）|
| ③ | ★ 名字必须落盘（重新读配置也在）|
| ④ | ★ `copy_from` 模式：★ 名字仍以**传进来的**为准（不被"源名 副本"覆盖）|
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

CFG = '__n94_profile_name_cfg__'
P = REPO / 'config' / f'{CFG}.json'


def _mk_config():
    """造一份**独立**配置（★ 绝不碰用户的账号配置）。"""
    import server  # noqa: F401
    from module.config.config import Config

    os.chdir(REPO)
    tmpl = json.loads((REPO / 'config' / 'template.json').read_text(
        encoding='utf-8'))
    opt = tmpl['script']['optimization']
    opt['run_list'] = []
    opt['period_backfilled'] = True
    # ★ 清掉可能存在的 profiles（保证"第一页"由后端自动建）
    opt.pop('profiles', None)
    P.write_text(json.dumps(tmpl, ensure_ascii=False), encoding='utf-8')
    return Config(CFG)


@pytest.fixture()
def call():
    """给出"调用端点"的工厂，并保证清理临时配置与 `cwd`。

    ★ 直接 `await` 那个 async 端点函数（★ 不起 HTTP 服务）。
    """
    cwd_before = os.getcwd()
    created = []
    try:
        _mk_config()
        created.append(P)

        def _factory(data):
            from module.server.schema_router import post_queue_profile
            import asyncio
            return asyncio.run(post_queue_profile(CFG, data))

        yield _factory
    finally:
        os.chdir(cwd_before)
        for p in created:
            try:
                p.unlink()
            except OSError:
                pass


def _names(res):
    return [str(it.get('name')) for it in (res.get('profiles') or [])
            if isinstance(it, dict)]


# ─────────────────────────── ① 传 name ⇒ 名字必须生效
def test_custom_name_is_used(call):
    """★★★ 核心（N9-4）：★ `name='日常'` ⇒ 新建那一页**就叫「日常」**。"""
    res = call({'name': '日常'})
    assert res.get('ok') is True, f'新建应成功，实际：{res}'
    assert res.get('name') == '日常', (
        f'★ 后端返回的 name 应是用户填的「日常」，实际 {res.get("name")!r}'
        '（若这里是数字，说明走了自动编号 ⇒ 用户填的名字被丢了）')
    assert '日常' in _names(res), (
        f'★ 新页必须真的叫「日常」。实际页名：{_names(res)}')


# ─────────────────────────── ② 不传 name ⇒ 自动编号
def test_default_name_still_auto_numbers(call):
    """★ 不传 `name` ⇒ ★ **自动编号**（保留"懒得起名"的快捷路径）。"""
    res = call({})
    assert res.get('ok') is True, f'新建应成功，实际：{res}'
    assert str(res.get('name', '')).isdigit(), (
        f'★ 不传名字时应自动编号（数字），实际 {res.get("name")!r}')


def test_empty_name_falls_back_to_auto(call):
    """★ `name=''` ⇒ 也走自动编号（前端的"留空"语义就是它）。"""
    res = call({'name': ''})
    assert res.get('ok') is True
    assert str(res.get('name', '')).isdigit(), (
        f'★ 空名字应回落自动编号，实际 {res.get("name")!r}')


# ─────────────────────────── ③ 名字必须落盘
def test_custom_name_is_persisted(call):
    """★ 名字必须**写进配置**（重新读盘也在）—— 否则切页/重启就丢。"""
    call({'name': '周末'})
    data = json.loads(P.read_text(encoding='utf-8'))
    names = [str(it.get('name'))
             for it in ((data.get('script') or {}).get('optimization') or {}
                        ).get('profiles', {}).get('items', [])]
    assert '周末' in names, f'★ 「周末」必须落盘。实际：{names}'


# ─────────────────────────── ④ copy_from + name
def test_copy_from_uses_given_name(call):
    """★ 复制模式下，★ **传进来的 `name` 优先**（不被"源名 副本"覆盖）。"""
    first = call({'name': '源页'})
    assert first.get('ok') is True
    pid = str(first.get('created'))
    assert pid, '前置：应返回新建页的 id'
    res = call({'copy_from': pid, 'name': '复制出来的'})
    assert res.get('ok') is True, f'复制应成功，实际：{res}'
    assert res.get('name') == '复制出来的', (
        f'★ 复制时也要用用户填的名字，实际 {res.get("name")!r}')
    assert '复制出来的' in _names(res), f'实际页名：{_names(res)}'
