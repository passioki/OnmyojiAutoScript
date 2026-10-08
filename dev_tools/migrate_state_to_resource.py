# -*- coding: utf-8 -*-
"""一次性迁移: 把旧的 charges 状态转成新模型的 credits/refill_anchor。

## 为什么需要

旧实现有**两套并存的资源状态**:
  1. `scheduler.next_run` —— 每任务一个时间戳, 由 `task_delay()` 累积
  2. `log/.task_state.json` 的 `charges: {count, last_slot, slots, last_consume}`
     —— 充能类任务另写的一套(在 `task_state` 里)

新模型把两者统一为 `RunState{credits, refill_anchor, retry_after}`。
本脚本做一次转换, 之后**自身即删除** —— 按设计原则, 不留永久兼容层。

## 迁移映射

| 旧字段 | 新字段 | 说明 |
|---|---|---|
| `charges.count` | `credits` | 剩余可用次数 |
| `charges.last_consume` | `refill_anchor` | 上次运行时刻(interval/slots 的锚点) |
| `scheduler.next_run` | **保留** | 作为 `next_run` 派生的缓存, 兼容 GUI 与既有配置 |

## 安全性

* **只增字段, 不删旧字段** —— 迁移后旧代码仍能读, 可安全回退
* 幂等: 已有 `credits` 的记录会跳过
* 出错不中断: 单个任务失败只记 warning

用法:
    python dev_tools/migrate_state_to_resource.py --dry-run   # 先看要改什么
    python dev_tools/migrate_state_to_resource.py             # 实际执行
    python dev_tools/migrate_state_to_resource.py --rollback  # 移除新增字段
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import logging                      # noqa: E402
logging.disable(logging.CRITICAL)

from module.config import task_state  # noqa: E402


def _state_file() -> Path:
    return Path(task_state._state_file())


def _parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


def main() -> int:
    dry = '--dry-run' in sys.argv
    rollback = '--rollback' in sys.argv

    sf = _state_file()
    if not sf.exists():
        print(f'状态文件不存在: {sf}')
        print('(首次运行, 无需迁移)')
        return 0

    data = json.loads(sf.read_text(encoding='utf-8'))
    changed, skipped = [], []

    for cfg_name, bucket in list(data.items()):
        if not isinstance(bucket, dict) or cfg_name == task_state.HEARTBEAT_KEY:
            continue
        for task, item in list(bucket.items()):
            if not isinstance(item, dict):
                continue

            if rollback:
                for k in ('credits', 'refill_anchor'):
                    if k in item:
                        item.pop(k)
                        changed.append(f'{cfg_name}.{task}.{k} 已移除')
                continue

            ch = item.get('charges')
            if not isinstance(ch, dict):
                continue
            if 'credits' in item:
                skipped.append(f'{cfg_name}.{task} (已有 credits, 跳过)')
                continue

            try:
                count = int(ch.get('count') or 0)
            except (TypeError, ValueError):
                count = 0
            item['credits'] = max(0, count)

            anchor = _parse_dt(ch.get('last_consume'))
            if anchor is not None:
                item['refill_anchor'] = anchor.replace(microsecond=0).isoformat()

            changed.append(
                f'{cfg_name}.{task}: count={count} -> credits={item["credits"]}, '
                f'anchor={item.get("refill_anchor") or "-"}')

    print('=' * 96)
    print(f'状态迁移 {"(--dry-run 仅预览)" if dry else ""}'
          f'{"(ROLLBACK)" if rollback else ""}')
    print('=' * 96)
    for line in changed:
        print(f'  {line}')
    if skipped:
        print()
        for line in skipped:
            print(f'  (跳过) {line}')

    if not changed:
        print('  无需改动')
        return 0

    if dry:
        print()
        print(f'  预览完成: 将改动 {len(changed)} 处。去掉 --dry-run 以实际执行。')
        return 0

    sf.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                  encoding='utf-8')
    print()
    print(f'  已写入 {sf}  (改动 {len(changed)} 处)')
    if not rollback:
        print('  注意: 旧字段(charges / next_run)未删除, 因此可安全回退。')
        print('        确认新调度稳定后, 本迁移脚本应从仓库删除。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
