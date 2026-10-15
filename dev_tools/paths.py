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
| 1 | **环境变量** | `OAS_REPO` / `OASX_REPO` / `FLUTTER_ROOT` —— CI、多份克隆、临时实验用 |
| 2 | **`dev_tools/paths.local.json`** | 本机覆盖（**不进 git**），形如 `{"oasx": "D:/foo/OASX", "flutter": "D:/flutter3271"}` |
| 3 | **相对本文件推导** | OAS 仓库 = `paths.py` 的上上级 —— ★ **永不出错** |
| 4 | **候选目录探测** | ★ **[10-15] 去盘符**：一律**相对候选** —— `../frontend`（★ 现行工作区布局，**首选**）· `../OASX` · `../OASX-clean` · `../OnmyojiAutoScript-GUI` |

★ **本文件里不写盘符**（用户 [10-15]："**彻底去盘符**"）—— ★ 机器私有的绝对路径只能写在
  `dev_tools/paths.local.json`（不进 git）或环境变量里。见 `docs/LAYOUT.md`。

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
# ★ [10-15] **去盘符**：候选一律**相对** —— `../frontend` 是现行工作区布局（首选）
_OASX_CANDIDATES = (
    # ★ 工作区布局：`<workspace>/backend` 与 `<workspace>/frontend` 并排（★ 现行 · 权威）
    r'..\frontend',
    # 历史上的前端仓库名（旧命名 / 浅克隆）
    r'..\OASX',
    r'..\OASX-clean',
    r'..\OnmyojiAutoScript-GUI',
)

# ★ Flutter SDK：同样**去盘符**（环境变量 → paths.local.json → 相对候选）
ENV_FLUTTER = 'FLUTTER_ROOT'
_FLUTTER_CANDIDATES = (
    r'..\flutter',
    r'..\flutter3271',
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

    # ★★ [10-15] **绝不缓存"找不到"** —— 否则同进程里一次失败会**永久污染**后续调用
    #   （★ 实测：`test_paths_refuses_to_guess` 的 monkeypatch 走过一次之后，
    #    后续测试全部拿到缓存的 None ⇒ 跨仓测试整片变红）
    if picked is not None:
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


def workspace_root() -> Path:
    """**工作区根** = 后端仓库的上一级（`<workspace>/backend` ⇒ `<workspace>`）。

    ★ 见 `docs/LAYOUT.md`：工作区里并排 `backend/` 与 `frontend/` —— 这是**唯一**的布局约定。
    """
    return OAS_ROOT.parent


def frontend_root(verbose: bool = True) -> Path:
    """★ `oasx_root()` 的同义名（★ 统一口径叫"**前端仓库**"）。"""
    return oasx_root(verbose=verbose)


def _is_flutter_sdk(p) -> bool:
    """该目录是不是一个能用的 Flutter SDK（有 `bin/flutter.bat` 或 `bin/flutter`）。"""
    try:
        p = Path(p)
        return (p / 'bin' / 'flutter.bat').is_file() or (p / 'bin' / 'flutter').is_file()
    except OSError:
        return False


def flutter_root(verbose: bool = True) -> Path:
    """**Flutter SDK 根**（★ 去盘符：`$FLUTTER_ROOT` → `paths.local.json` → 相对候选）。

    ★ 与 `oasx_root()` 同样**不猜**：找不到返回 `None`；要强制就用 `require_flutter()`。
    """
    if 'flutter' in _resolved_cache:
        return _resolved_cache['flutter']

    picked = None
    why = ''

    env = os.environ.get(ENV_FLUTTER, '').strip()
    if env:
        if _is_flutter_sdk(env):
            picked, why = Path(env), f'来自 ${ENV_FLUTTER}'
        else:
            print(f'  ⚠ ${ENV_FLUTTER}={env} 看起来**不是** Flutter SDK'
                  f'（缺 bin/flutter.bat）—— 忽略', file=sys.stderr)

    if picked is None:
        local = _read_local().get('flutter')
        if local:
            if _is_flutter_sdk(local):
                picked, why = Path(local), f'来自 {LOCAL_FILE}'
            else:
                print(f'  ⚠ {LOCAL_FILE} 里的 flutter={local} 不是 Flutter SDK —— 忽略',
                      file=sys.stderr)

    if picked is None:
        for cand in _FLUTTER_CANDIDATES:
            p = (OAS_ROOT / cand).resolve() if cand.startswith('..') else Path(cand)
            if _is_flutter_sdk(p):
                picked, why = p, '自动探测'
                break

    # ★★ [10-15] 同样**不缓存"找不到"**（理由见 `oasx_root()`）
    if picked is not None:
        _resolved_cache['flutter'] = picked
    if verbose:
        if picked is None:
            print('  ⚠ 没找到 Flutter SDK —— 需要设置:\n'
                  f'      ${ENV_FLUTTER}=<Flutter SDK 路径>\n'
                  f'    或在 {OAS_ROOT / "dev_tools" / LOCAL_FILE} 里写\n'
                  '      {"flutter": "<Flutter SDK 路径>"}\n'
                  '    ★ 不会静默挑一个目录', file=sys.stderr)
        else:
            print(f'  Flutter SDK: {picked}（{why}）')
    return picked


def require_flutter() -> Path:
    """拿 Flutter SDK 根；**没有就抛**（给"必须编译前端"的脚本用）。"""
    p = flutter_root()
    if p is None:
        raise SystemExit(
            '找不到 Flutter SDK。请设 $FLUTTER_ROOT 或在 '
            f'{OAS_ROOT / "dev_tools" / LOCAL_FILE} 里配 flutter 路径。\n'
            '★ 本脚本**不会**猜目录。')
    return p


if __name__ == '__main__':
    print('工作区根  : ' + str(workspace_root()))
    print('OAS 仓库 : ' + str(oas_root(verbose=True)))
    print('前端仓库 : ' + str(oasx_root(verbose=True)))
    print('Flutter  : ' + str(flutter_root(verbose=True)))
