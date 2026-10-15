# -*- coding: utf-8 -*-
"""F9 守卫的【注入验证】探针（★ 铁律 P3 / 后端台账 §C.3 教训-C）。

## 为什么要有这个文件

★ 本项目已**三次**抓到"源码级守卫是空转的" ⇒ ★ 每个新守卫都**必须**做一次
"注入破坏 ⇒ 守卫必须变红 ⇒ 还原 ⇒ 必须回绿"。

★ F9 的守卫是**运行时**的（`frontend/test/task_list_panel_test.dart` 的
`_f9PauseReachableTests()`）。本探针把"**条件重复的死分支**"重新塞回
`queue_panel.dart`，用来证明那两条断言**真的会红**。

## 用法（★ 在 backend\\ 下）

```
toolkit\\python.exe dev_tools\\_probes\\inject_f9.py inject    # 破坏
dev_tools\\flutter.bat test --plain-name F9                   # 必须 1 failed
toolkit\\python.exe dev_tools\\_probes\\inject_f9.py restore   # 还原
dev_tools\\flutter.bat test --plain-name F9                   # 必须 2 passed
```

★ [10-15] 实测：inject ⇒ **1 failed（`+1 -1`）** · restore ⇒ SHA256
**逐字节一致**（`6AD94E42…`）· 复跑 ⇒ **2 passed**。

## 为什么用 Python 而不是 pwsh

★ 坑 P7：`pwsh -replace` 是**正则**且 `$` 会展开 ⇒ ★ 注入会"**静默不生效**"
（本项目为此连试 3 次都"没生效"，还一度误判守卫有效）。
★ 所以这里用 `str.replace` + **打印锚点命中次数**（★ 不静默）。
"""
import hashlib
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dev_tools.paths import require_oasx  # noqa: E402

TARGET = require_oasx() / 'lib' / 'views' / 'tasks' / 'queue_panel.dart'
# ★ 备份放到**系统临时目录** —— 绝不放进仓库（否则会被 `git add -A` 误提交，
#   ★ 而且它是**前端**文件的副本，放进后端仓库立刻就会过期）。
BACKUP = pathlib.Path(tempfile.gettempdir()) / 'f9_probe_queue_panel.dart.orig'

ANCHOR = """                    else if (isTask && e['running'] == true)
                      Tooltip(
                        message: '★ **暂停调度** —— 跑完**当前这一场**就停手。\\n'"""

PROBE = """                    else if (isTask && e['running'] == true)
                      Tooltip(
                        message: '★ 注入探针（F9 注入验证）—— 重现"条件重复的死分支"',
                        child: IconButton(
                          onPressed: null,
                          icon: const Icon(Icons.play_circle_filled, size: 18),
                        ),
                      )
                    else if (isTask && e['running'] == true)
                      Tooltip(
                        message: '★ **暂停调度** —— 跑完**当前这一场**就停手。\\n'"""


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    assert TARGET.is_file(), f'找不到前端文件: {TARGET}'
    if mode == 'inject':
        src = TARGET.read_text(encoding='utf-8')
        n = src.count(ANCHOR)
        assert n == 1, f'★ 锚点命中 {n} 次（应为 1）⇒ 注入会不生效，已中止'
        BACKUP.write_bytes(TARGET.read_bytes())
        TARGET.write_text(src.replace(ANCHOR, PROBE, 1), encoding='utf-8')
        print(f'inject: OK (anchor hits={n})')
        print(f'backup sha256 = {sha(BACKUP)}')
    elif mode == 'restore':
        assert BACKUP.is_file(), '没有备份（先跑 inject）'
        shutil.copyfile(BACKUP, TARGET)
        print('restore: OK')
        print(f'restored sha256 = {sha(TARGET)}')
    else:
        raise SystemExit('用法: inject_f9.py inject | restore')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
