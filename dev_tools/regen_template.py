# -*- coding: utf-8 -*-
"""
重建 config/template.json, 使其与实时 pydantic 模型一致。

背景
----
模板是手工维护的, 而更新它的 ConfigUpdater.update_template() /
update_config() 早已在 OAS 从旧配置系统迁到 pydantic 时被改成 `pass`
(见 module/config/config_updater.py), 于是模板逐步滞后。实测差异:
  * scheduler 分组缺 period / reset_at
  * 53 个任务共缺 233 个字段
  * 缺 other_world_twilight / guild_activity_monitor / budokai_tournament 三个任务
后果: 用模板新建的配置从一开始就不含这些字段。

做法(保守, 避免丢信息)
----------------------
  1. 以**模型**为准确定结构与字段全集, 值取模型的默认值;
  2. 用**当前模板里已有的值**覆盖(保留上游设定的默认值, 不丢信息);
  3. 顶层 config_name / running_task 保持与模板一致;
  4. 只重建 template.json, 不动用户的 config/*.json
     (那些由 Config() 加载时按模型补默认值)。

用法
----
    python -m dev_tools.regen_template            # 预演, 只打印差异
    python -m dev_tools.regen_template --write    # 实际写入(自动备份 .bak)
"""
import io
import json
import logging
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.chdir(REPO)
logging.disable(logging.CRITICAL)

from module.config.config_model import ConfigModel

WRITE = '--write' in sys.argv
TPL = REPO / 'config' / 'template.json'

old = json.load(io.open(TPL, encoding='utf-8'))
m = ConfigModel()
# 用 python 模式 dump(保留 datetime/time/timedelta 对象), 再自行序列化
dumped = m.model_dump()

# 顶层顺序: config_name / running_task 在前, 其余按模型顺序
META = ['config_name', 'running_task']
new = {}
for k in META:
    if k in dumped:
        new[k] = old.get(k, dumped[k])
for k, v in dumped.items():
    if k in META:
        continue
    new[k] = v


def jsonable(obj):
    """把 datetime/time/timedelta 等转成仓库既有的字符串写法。"""
    import datetime as _dt
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, _dt.timedelta):
        total = int(obj.total_seconds())
        days, rem = divmod(total, 86400)
        h, rem = divmod(rem, 3600)
        mnt, s = divmod(rem, 60)
        return f'{days:02d} {h:02d}:{mnt:02d}:{s:02d}'
    if isinstance(obj, _dt.datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(obj, _dt.time):
        return obj.strftime('%H:%M:%S')
    return obj


def overlay(node_new, node_old):
    """用旧模板里已有的值覆盖新结构(只覆盖两边都有的叶子)。"""
    if not isinstance(node_new, dict) or not isinstance(node_old, dict):
        return node_new
    out = {}
    for k, v in node_new.items():
        if k in node_old:
            oldv = node_old[k]
            if isinstance(v, dict) and isinstance(oldv, dict):
                out[k] = overlay(v, oldv)
            elif not isinstance(v, dict) and not isinstance(oldv, dict):
                out[k] = oldv          # 保留模板里的值
            else:
                out[k] = overlay(v, oldv) if isinstance(v, dict) else v
        else:
            out[k] = overlay(v, {}) if isinstance(v, dict) else v
    return out


new = overlay(jsonable(new), old)
text = json.dumps(new, indent=2, ensure_ascii=False, default=str) + '\n'

# --- 差异报告 ---
print('=== 重建结果差异 ===')
print(f'  旧模板顶层键: {len(old)}   新模板顶层键: {len(new)}')
added_tasks = [k for k in new if k not in old]
print(f'  新增任务: {added_tasks}')
removed_tasks = [k for k in old if k not in new]
print(f'  移除任务: {removed_tasks}')

# scheduler 字段对比
o_s = old.get('dokan', {}).get('scheduler', {})
n_s = new.get('dokan', {}).get('scheduler', {})
print(f'  dokan.scheduler 旧 {len(o_s)} 字段 -> 新 {len(n_s)} 字段')
print(f'    新增: {sorted(set(n_s) - set(o_s))}')

# 统计补了多少字段
def leaf_count(d):
    n = 0
    for v in d.values():
        if isinstance(v, dict):
            n += leaf_count(v)
        else:
            n += 1
    return n

print(f'  叶子总数: 旧 {leaf_count(old)} -> 新 {leaf_count(new)}')

# 抽查几个值是否被保留
checks = [('script', 'device', 'serial'), ('script', 'optimization', 'screenshot_interval')]
for path in checks:
    ov = old
    nv = new
    for p in path:
        ov = (ov or {}).get(p) if isinstance(ov, dict) else None
        nv = (nv or {}).get(p) if isinstance(nv, dict) else None
    print(f'  {"/".join(path)}: 旧={ov!r} 新={nv!r} 保留={"OK" if ov == nv else "变化"}')

if WRITE:
    backup = TPL.with_suffix('.json.bak')
    shutil.copy2(TPL, backup)
    io.open(TPL, 'w', encoding='utf-8').write(text)
    print()
    print(f'  已写入 {TPL.name} (备份: {backup.name})')
else:
    print()
    print('  预演模式, 未写入。加 --write 实际写入。')
