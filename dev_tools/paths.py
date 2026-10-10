# -*- coding: utf-8 -*-
"""**路径解析** —— 杜绝硬编码绝对路径.

## ★★★ 规矩（用户裁定）★★★

> "**杜绝硬编码，写进文档里。**"

## 为什么

实测踩到的真 bug（2026-10-11）:

`dev_tools/gen_i18n.py` 里硬编码了

```python
OASX = Path(r'D:\OAS-dev\OASX-src')       # ★ 历史仓库
```

而**实际编译的是 `D:\OASX-clean`** —— 于是新增任务的 i18n 被写进了
**没人在编译的目录**，界面显示英文 key（`Rest` 而不是「休息」）。
排查时看到的假象是"i18n 加了但界面没变"。

★ 同类的硬编码还有 `REPO = Path(r'D:\OAS-dev\OnmyojiAutoScript')`
（在 `dev_tools/*.py` 里出现多次）—— 换目录/换机器/别人克隆即失效。

## 解析顺序（**可发现、可覆盖、不静默**）

| # | 来源 | 说明 |
|---|---|---|
| 1 | **环境变量** | `OAS_REPO` / `OASX_REPO` —— CI、多份克隆、临时实验用 |
| 2 | **`dev_tools/paths.local.json`** | 本机覆盖（**不进 git**），形如 `{"oasx": "D:/foo/OASX"}` |
| 3 | **相对本文件推导** | OAS 仓库 = `paths.py` 的上上级 —— ★ **永不出错** |
| 4 | **候选目录探测** | `D:\OASX-clean` / `D:\OAS-dev\OASX-src` / 同级 `../OASX*` —— 取**第一个像样的** |

★ 第 4 步会**打印选中了哪个**（`active_oasx()` 的 `verbose`），
  **不静默**选一个 —— 否则又变成"写错地方却没人知道"。

## 判断"像样的 OASX 仓库"

必须同时有:
* `pubspec.yaml`
* `lib/config/translation/i18n_cn.dart`（★ 我们要写的就是它）

这样"一个碰巧叫 OASX 的空目录"不会被误选。
"""
import json
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------- 常量
ENV_OAS = 'OAS_REPO'
ENV_OASX = 'OASX_REPO'
LOCAL_FILE = 'paths.local.json'

# ★ OAS 仓库根 = 本文件的上上级（`<repo>/dev_tools/paths.py`）
OAS_ROOT = Path(__file__).resolve().parents[1]

# ★ OASX 的候选位置（**只是候选**, 不是断言; 选中的会打印出来）
_OASX_CANDIDATES = (
    # 用户当前用的权威仓库（分支 `oas-tasks-ui-s7`）
    r'D:\OASX-clean',
    # 早期会话用的历史仓库（浅克隆, **不是**权威）
    r'D:\OAS-dev\OASX-src',
    # 与 OAS 仓库同级（最常见的开发布局）
    r'..\OASX',
    r'..\OASX-clean',
    r'..\OnmyojiAutoScript-GUI',
)

_resolved_cache = {}


def _is_oasx_repo(p) -> bool:
    """该目录是不是一个**能用的** OASX 仓库（见模块文档的判据）。"""
    try:
        p = Path(p)
        return ((p / 'pubspec.yaml').is_file()
                and (p / 'lib' / 'config' / 'translation' / 'i18n_cn.dart').is_file())
    except OSError:
        return False


def _read_local() -> dict:
    """读 `dev_tools/paths.local.json`（不存在/坏掉 -> 空 dict, 不抛）。"""
    f = OAS_ROOT / 'dev_tools' / LOCAL_FILE
    if not f.is_file():
        return {}
    try:
        return json.loads(f.read_text(encoding='utf-8')) or {}
    except Exception as exc:
        print(f'  ⚠ {LOCAL_FILE} 读取失败({type(exc).__name__}: {exc}), 按无覆盖处理',
              file=sys.stderr)
        return {}


def oas_root(verbose: bool = False) -> Path:
    """OAS 后端仓库根。

    ★ 默认就是**相对本文件推导**的结果 —— 几乎不需要覆盖。
    """
    env = os.environ.get(ENV_OAS, '').strip()
    if env and Path(env).is_dir():
        if verbose:
            print(f'  OAS 仓库: {env}（来自 ${ENV_OAS}）')
        return Path(env)
    local = _read_local().get('oas')
    if local and Path(local).is_dir():
        if verbose:
            print(f'  OAS 仓库: {local}（来自 {LOCAL_FILE}）')
        return Path(local)
    if verbose:
        print(f'  OAS 仓库: {OAS_ROOT}（相对本文件推导）')
    return OAS_ROOT


def oasx_root(verbose: bool = True) -> Path:
    """OASX 前端仓库根。

    ## ★ 找不到时**不猜**

    返回 `None` —— 调用方必须自己决定"跳过还是报错"。
    ★ 绝不静默回退到某个"看起来像"的目录：那正是本模块要消灭的 bug。
    """
    if 'oasx' in _resolved_cache:
        return _resolved_cache['oasx']

    picked = None
    why = ''

    env = os.environ.get(ENV_OASX, '').strip()
    if env:
        if _is_oasx_repo(env):
            picked, why = Path(env), f'来自 ${ENV_OASX}'
        else:
            print(f'  ⚠ ${ENV_OASX}={env} 看起来**不是** OASX 仓库'
                  f'（缺 pubspec.yaml 或 i18n_cn.dart）—— 忽略', file=sys.stderr)

    if picked is None:
        local = _read_local().get('oasx')
        if local:
            if _is_oasx_repo(local):
                picked, why = Path(local), f'来自 {LOCAL_FILE}'
            else:
                print(f'  ⚠ {LOCAL_FILE} 里的 oasx={local} 不是 OASX 仓库 —— 忽略',
                      file=sys.stderr)

    if picked is None:
        for cand in _OASX_CANDIDATES:
            p = (OAS_ROOT / cand).resolve() if cand.startswith('..') else Path(cand)
            if _is_oasx_repo(p):
                picked, why = p, '自动探测'
                break

    _resolved_cache['oasx'] = picked
    if verbose:
        if picked is None:
            print('  ⚠ 没找到 OASX 仓库 —— 需要设置:\n'
                  f'      ${ENV_OASX}=<OASX 路径>\n'
                  f'    或在 {OAS_ROOT / "dev_tools" / LOCAL_FILE} 里写\n'
                  '      {"oasx": "<OASX 路径>"}\n'
                  '    ★ 不会静默挑一个目录（那会写错地方）', file=sys.stderr)
        else:
            print(f'  OASX 仓库: {picked}（{why}）')
    return picked


def require_oasx() -> Path:
    """拿 OASX 根；**没有就抛**（给"必须写前端"的脚本用）。"""
    p = oasx_root()
    if p is None:
        raise SystemExit(
            '找不到 OASX 仓库。请设 $OASX_REPO 或在 '
            f'{OAS_ROOT / "dev_tools" / LOCAL_FILE} 里配 oasx 路径。\n'
            '★ 本脚本**不会**猜目录 —— 写错地方比报错更难查。')
    return p


if __name__ == '__main__':
    print('OAS 仓库 : ' + str(oas_root(verbose=True)))
    print('OASX 仓库: ' + str(oasx_root(verbose=True)))
