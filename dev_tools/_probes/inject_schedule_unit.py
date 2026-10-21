# -*- coding: utf-8 -*-
"""`L3-0 / R1-a` 守卫的**注入验证**（★ 铁律 P3）。

★ 注入手法（外科式）：把 `is_due()` 里对周期单元的**取反**去掉
  ⇒ `is_due` 语义反了（"已完成"被当成"该跑"）。
  ⇒ ★ 守卫 `test_is_due_periodic_delegates_and_inverts` 与
    `test_real_roundtrip_periodic` **必须变红**。

用法: python inject_schedule_unit.py inject | restore
"""
import hashlib
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
TARGET = REPO / 'module' / 'config' / 'schedule_unit.py'
BACKUP = pathlib.Path(tempfile.gettempdir()) / 'inject_schedule_unit.orig'

OLD = "    if unit.is_periodic:\n        return not TS.is_completed_in_period("
NEW = "    if unit.is_periodic:\n        return TS.is_completed_in_period("


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    mode = sys.argv[1]
    src = TARGET.read_text(encoding='utf-8')
    if mode == 'inject':
        n = src.count(OLD)
        assert n == 1, f'★ 锚点命中 {n} 次（应为 1）⇒ 注入会不生效，已中止'
        BACKUP.write_bytes(TARGET.read_bytes())
        TARGET.write_text(src.replace(OLD, NEW, 1), encoding='utf-8')
        print(f'[R1-a] inject OK (anchor hits=1)  backup sha256 = {sha(BACKUP)}')
    elif mode == 'restore':
        assert BACKUP.is_file(), '没有备份（先 inject）'
        shutil.copyfile(BACKUP, TARGET)
        print(f'[R1-a] restore OK  restored sha256 = {sha(TARGET)}')
    else:
        raise SystemExit('用法: inject | restore')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
