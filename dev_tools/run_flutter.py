# -*- coding: utf-8 -*-
"""★ 前端命令包装 —— **去盘符** + 自动 `--no-version-check`。

## 为什么不写死路径

见 `docs/LAYOUT.md`（R1~R5）：Flutter SDK 的**绝对**位置只允许写在
`dev_tools/paths.local.json` 或 `$FLUTTER_ROOT` 里；★ 本文件与 `flutter.bat`
里**不出现任何盘符**。

## 为什么强制 `--no-version-check`

★ 坑 **P16**：`flutter` 的版本检查会对 SDK 仓库跑 `git fetch --tags`
（实测要拉 **611285 个对象**）⇒ 在当前网络下**挂死**十几分钟。
所以这里**默认补上**；调用方已显式传了就不重复加。

## cwd

★ 自动切到**前端仓库**（`oasx_root()`）—— 这样 `dev_tools\\flutter.bat test`
在任何目录下都能跑（★ `flutter test` 必须在 package 根下执行）。
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dev_tools.paths import oasx_root, require_flutter  # noqa: E402


def main() -> int:
    flutter = require_flutter() / 'bin' / 'flutter.bat'
    args = list(sys.argv[1:])
    if '--no-version-check' not in args:
        args.insert(0, '--no-version-check')
    cwd = oasx_root(verbose=False) or REPO.parent
    print(f'★ Flutter SDK : {flutter}')
    print(f'★ 执行目录    : {cwd}')
    print(f'★ 参数        : {" ".join(args)}')
    return subprocess.call([str(flutter), *args], cwd=str(cwd))


if __name__ == '__main__':
    raise SystemExit(main())
