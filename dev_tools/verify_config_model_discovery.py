# -*- coding: utf-8 -*-
"""验证: 自动发现的 ConfigModel 与手写声明**完全等价**。

## 为什么必须先验证

`config_model.py` 有 ~113 行手写声明(60 个 import + 56 个字段)。改成自动发现是
"中心化注册"的最后一块, 但它**位于配置系统的关键路径上** —— 一旦字段名或类型
不一致, 用户的配置文件就读不出来。

因此先做**只读对照**: 用 `pydantic.create_model` 动态构造, 与手写的逐项比对。

## 踩过的坑(已修正)

1. **发现过宽**: 一开始把 `tasks/*/config.py` 里**所有** ConfigBase 子类都当任务,
   结果混进 88 个类(含 `GoldYoukaiConfig`、`Scheduler`、`Strategy` 等嵌套类),
   动态字段 90 个而非 58 个。
   修正: **按目录精确选类** —— 优先与目录同名的类; 否则选带 `scheduler` 字段的那个
   (任务配置类的标志); 跳过 `*Config` 之类的嵌套类。

2. **构造方式错误**: 实际代码只调用 `ConfigModel(config_name=...)`, 由 `__init__`
   读 JSON 填入。我原先直接传 `**data` 并带上 `config_name`/`running_task`,
   而手写 `ConfigModel.__init__` 会把它们当数据字段 -> TypeError。
   修正: 一律用 `ConfigModel(config_name=...)`。

只比"集合"与"类型", 不比"顺序" —— 顺序不是契约(JSON 对象无序)。
"""
import json
import os
import sys
from pathlib import Path

from paths import oas_root  # noqa: E402  ★ 消除硬编码（见 paths.py）
REPO = oas_root()
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import logging                        # noqa: E402
logging.disable(logging.CRITICAL)

from pydantic import Field, create_model  # noqa: E402

from module.config.config_model import ConfigModel as Handwritten  # noqa: E402
from module.config.utils import convert_to_underscore  # noqa: E402
from tasks.Component.config_base import ConfigBase  # noqa: E402

fails = []


def chk(desc, ok, extra=''):
    print(f'  {"OK " if ok else "BAD"} {desc:<50} {extra}')
    if not ok:
        fails.append(desc)


def pick_task_class(mod, dirname):
    """
    从任务 config 模块里挑出**任务配置类**。

    ⚠ 关键: 并非所有配置类都继承 `ConfigBase` ——
    `tasks/Script/config.py` 的 `Script` 与 `tasks/GlobalGame/config.py` 的
    `GlobalGame` 直接继承 **`BaseModel`**。只查 `ConfigBase` 会漏掉它们
    (踩过: 因此少 2 个字段, 且默认值比对失败)。

    规则(按优先级):
      1. 与目录同名的类
      2. 带 scheduler 字段的类(任务配置类的标志)
      3. 类名转下划线 == 目录名
    """
    import inspect
    from pydantic import BaseModel

    def _is_cfg(o):
        return (inspect.isclass(o) and issubclass(o, BaseModel)
                and o is not BaseModel and o is not ConfigBase
                # 只接受**本模块定义**的类, 排除 import 进来的
                and o.__module__ == mod.__name__)

    cands = [o for o in vars(mod).values() if _is_cfg(o)]

    for c in cands:
        if c.__name__ == dirname:
            return c
    for c in cands:
        try:
            names = set(getattr(c, 'model_fields', {}) or {})
        except Exception:
            names = set()
        if 'scheduler' in names:
            return c
    for c in cands:
        if convert_to_underscore(c.__name__) == convert_to_underscore(dirname):
            return c
    return None


# 少数配置类**没有 scheduler 字段**(它们是全局设置而非"任务"), 因此上文的
# 启发式找不到它们。这里显式列出 —— 这也如实反映了真实契约: 它们确实是特例。
NO_SCHEDULER = {'GlobalGame', 'Script'}


def discover():
    import importlib
    tasks_dir = REPO / 'tasks'
    found = {}
    skipped = []
    for d in sorted(tasks_dir.iterdir()):
        if not d.is_dir() or not (d / 'config.py').exists():
            continue
        if d.name.startswith('_'):
            continue
        try:
            mod = importlib.import_module(f'tasks.{d.name}.config')
        except Exception as exc:
            skipped.append(f'{d.name} (导入失败 {type(exc).__name__}: {exc})')
            continue
        cls = pick_task_class(mod, d.name)
        if cls is None:
            skipped.append(f'{d.name} (未找到任务配置类)')
            continue
        found[d.name] = cls
    return found, skipped


print('=' * 92)
print('步骤 1: 自动发现任务配置类(按目录精确选类)')
print('=' * 92)
classes, skipped = discover()
print(f'  发现 {len(classes)} 个任务配置类')
if skipped:
    print(f'  跳过: {skipped}')

hw_fields = dict(Handwritten.__annotations__)
print(f'  手写声明 {len(hw_fields)} 个字段')
print()

print('=' * 92)
print('步骤 2: 用 create_model 动态构造')
print('=' * 92)
fields = {}
keys_used = {}
for dirname, cls in classes.items():
    # **用类名派生 key**, 而非目录名 —— 因为手写声明的 key 来自
    # `convert_to_underscore(ClassName)`(见 config_model.py 的 import 行)。
    # 有些目录名与类名不同(如目录 GlobalGame -> 类 GlobalGame -> 键 global_game),
    # 用目录名会得到同名但语义不同键, 或漏掉。
    key = convert_to_underscore(cls.__name__)
    keys_used[dirname] = key
    fields[key] = (cls, Field(default_factory=cls))
fields['config_name'] = (str, 'oas')
fields['running_task'] = (str, '')

dyn = create_model('ConfigModel', __base__=ConfigBase, **fields)

# 与手写版相同的 __init__(读 JSON)
def _dyn_init(self, config_name=None):
    if not config_name:
        ConfigBase.__init__(self)
        return
    data = self.read_json(config_name)
    data['config_name'] = config_name
    ConfigBase.__init__(self, **data)


# 保留 ConfigBase 的自定义方法。
# 注意: **不能盲目 setattr(会破坏 staticmethod/classmethod 描述符** ——
# 裸函数被赋成类属性后变成普通方法, self 会占掉第一个参数,
# 于是 `self.read_json(name)` 报 "takes 1 positional argument but 2 were given")。
from module.config.config_model import ConfigModel as _HW   # noqa: E402
for name, raw in vars(_HW).items():
    if name.startswith('__') or name in dyn.__dict__:
        continue
    if isinstance(raw, staticmethod):
        setattr(dyn, name, staticmethod(raw.__func__))
    elif isinstance(raw, classmethod):
        setattr(dyn, name, classmethod(raw.__func__))
    elif callable(raw):
        setattr(dyn, name, raw)

dyn.__init__ = _dyn_init
print(f'  动态模型字段数: {len(dyn.__annotations__)}')

print()
print('=' * 92)
print('步骤 3: 等价性比对')
print('=' * 92)
hw_keys, dyn_keys = set(hw_fields), set(dyn.__annotations__)

chk('字段名集合完全一致', hw_keys == dyn_keys,
    f'手写 {len(hw_keys)} / 动态 {len(dyn_keys)}')
if hw_keys != dyn_keys:
    if hw_keys - dyn_keys:
        print(f'      仅手写有: {sorted(hw_keys - dyn_keys)}')
    if dyn_keys - hw_keys:
        print(f'      仅动态有: {sorted(dyn_keys - hw_keys)}')

bad_type = []
for k in sorted(hw_keys & dyn_keys):
    hn = str(hw_fields[k]).split('.')[-1].rstrip("']>")
    dn = str(dyn.__annotations__[k]).split('.')[-1].rstrip("']>")
    if hn != dn:
        bad_type.append((k, hn, dn))
chk('每个字段的类型一致', not bad_type)
for k, h, d in bad_type[:6]:
    print(f'      {k}: 手写={h} 动态={d}')

print()
print('=' * 92)
print('步骤 4: 实例化与序列化比对')
print('=' * 92)
h_inst, d_inst = Handwritten(), dyn()
h_dump, d_dump = h_inst.model_dump(), d_inst.model_dump()

chk('model_dump() 键一致', set(h_dump) == set(d_dump),
    f'{len(h_dump)} vs {len(d_dump)}')
chk('默认值一致', h_dump == d_dump,
    '相同' if h_dump == d_dump else
    f'差异 {[k for k in set(h_dump) & set(d_dump) if h_dump[k] != d_dump[k]][:5]}')

nested_bad = []
for k in sorted(hw_keys):
    tn_h = type(getattr(h_inst, k, None)).__name__
    tn_d = type(getattr(d_inst, k, None)).__name__
    if tn_h != tn_d:
        nested_bad.append((k, tn_h, tn_d))
chk('嵌套模型类型一致', not nested_bad)
for k, h, d in nested_bad[:6]:
    print(f'      {k}: 手写={h} 动态={d}')

print()
print('=' * 92)
print('步骤 5: 对真实配置文件的解析比对')
print('=' * 92)
for name in ('恋鸟树', '伴生树', 'oas1'):
    p = REPO / 'config' / f'{name}.json'
    if not p.exists():
        continue
    errs = []
    try:
        h = Handwritten(config_name=name)
    except Exception as exc:
        errs.append(f'手写失败 {type(exc).__name__}: {exc}')
    try:
        d = dyn(config_name=name)
    except Exception as exc:
        errs.append(f'动态失败 {type(exc).__name__}: {exc}')
    chk(f'{name}: 两者都能解析', not errs, '; '.join(errs))
    if not errs:
        hd, dd = h.model_dump(), d.model_dump()
        diffs = [k for k in set(hd) & set(dd) if hd[k] != dd[k]]
        chk(f'{name}: 解析结果一致', not diffs,
            f'差异 {len(diffs)} 项' + (f': {diffs[:4]}' if diffs else ''))

print()
print('=' * 92)
if fails:
    print(f'*** {len(fails)} 项失败 ***')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('*** 全部通过 —— 自动发现与手写声明等价 ***')
print('=' * 92)
