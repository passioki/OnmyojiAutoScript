# This Python file uses the following encoding: utf-8
"""
生成任务目录: 把 tasks/ 下的拼音目录名对应到游戏功能, 并汇总每个任务的规模。

用途
----
OAS 的任务目录以拼音命名(Dokan / RyouToppa / Sougenbi / TrueOrochi ...),
不看代码很难知道对应游戏里的哪个功能。本工具从以下权威来源自动汇总:
  - module/config/i18n/zh-CN.json 与 zh_CN.xml : 中文名与配置项说明
  - tasks/<Task>/config.py        : 配置字段及其 description
  - tasks/<Task>/assets.py 等     : 资产数量
  - 代码中对任务的引用            : 谁在调用它

用法
----
    python -m dev_tools.task_catalog                 # 打印
    python -m dev_tools.task_catalog --md TASKS.md   # 写入 Markdown
    python -m dev_tools.task_catalog --task Dokan    # 只看某个任务
"""
import argparse
import importlib
import inspect
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TASKS_DIR = REPO_ROOT / 'tasks'
# 这些是基础设施目录, 不是"游戏玩法任务"
INFRA_DIRS = {'Component', 'GameUi', 'Utils', 'Script', '__pycache__'}

# i18n 里没有中文名、但已人工确认游戏功能的目录
MANUAL_CN_NAMES = {
    'BudokaiTournament': '武道大会/每日修行',
    'GotoMain': '回主界面(工具)',
    'GuildActivityMonitor': '寮活动监听',
}


def load_i18n():
    """合并 zh-CN.json 与 zh_CN.xml, 得到 {英文键: 中文}。"""
    mapping = {}
    j = REPO_ROOT / 'module' / 'config' / 'i18n' / 'zh-CN.json'
    if j.exists():
        try:
            mapping.update(json.loads(j.read_text(encoding='utf-8')))
        except Exception:
            pass
    x = REPO_ROOT / 'module' / 'config' / 'i18n' / 'zh_CN.xml'
    if x.exists():
        try:
            root = ET.parse(x).getroot()
            for msg in root.iter('message'):
                src = msg.findtext('source')
                tr = msg.findtext('translation')
                if src and tr:
                    mapping.setdefault(src.strip(), tr.strip())
        except Exception:
            pass
    return mapping


def task_dirs():
    out = []
    for d in sorted(TASKS_DIR.iterdir()):
        if not d.is_dir() or d.name in INFRA_DIRS or d.name.startswith('__'):
            continue
        out.append(d)
    return out


def describe_task(d: Path, i18n: dict):
    """汇总单个任务的信息。"""
    name = d.name
    info = {
        'dir': name,
        'cn': i18n.get(name, '') or MANUAL_CN_NAMES.get(name, ''),
        'has_config': (d / 'config.py').exists(),
        'has_task': (d / 'script_task.py').exists(),
        'readme': None,
        'fields': [],
        'assets': Counter(),
        'uses': [],
    }
    rm = next((p for p in d.glob('README*')), None)
    if rm:
        info['readme'] = rm.name

    # 配置字段: 从 config.py 里的 Field(description=...) 抽取
    if info['has_config']:
        mod_name = f'tasks.{name}.config'
        try:
            mod = importlib.import_module(mod_name)
            for cls_name, cls in list(vars(mod).items()):
                if not inspect.isclass(cls) or cls.__module__ != mod_name:
                    continue
                fields = getattr(cls, 'model_fields', None)
                if not fields:
                    continue
                for fname, f in fields.items():
                    desc = ''
                    extra = getattr(f, 'json_schema_extra', None) or {}
                    if isinstance(extra, dict):
                        desc = extra.get('description', '') or ''
                    if not desc:
                        desc = getattr(f, 'description', '') or ''
                    cn = i18n.get(desc, desc)
                    if fname == 'scheduler':
                        continue
                    info['fields'].append((fname, cn))
        except Exception:
            pass

    # 资产统计: 直接读 json 规则文件
    for jp in d.rglob('*.json'):
        if '__pycache__' in jp.parts:
            continue
        info['assets'][jp.stem] += 1
    info['png'] = sum(1 for _ in d.rglob('*.png') if '__pycache__' not in _.parts)

    return info


def find_usages(all_dirs, task_names):
    """统计每个任务被其他任务/模块引用的次数。"""
    uses = defaultdict(set)
    files = []
    for base in ('tasks', 'module'):
        r = REPO_ROOT / base
        if r.exists():
            files.extend(p for p in r.rglob('*.py') if '__pycache__' not in p.parts)
    files.extend(REPO_ROOT.glob('*.py'))
    for f in files:
        try:
            text = f.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        for t in task_names:
            if re.search(rf'\b{re.escape(t)}\b', text):
                rel = str(f.relative_to(REPO_ROOT))
                # 排除任务自身目录
                if f'tasks{chr(92)}{t}{chr(92)}' in rel or f'tasks/{t}/' in rel:
                    continue
                uses[t].add(rel)
    return uses


def main():
    ap = argparse.ArgumentParser(description='生成 OAS 任务目录')
    ap.add_argument('--md', type=str, default=None, help='输出 Markdown 文件')
    ap.add_argument('--task', type=str, default=None, help='只看指定任务')
    args = ap.parse_args()

    i18n = load_i18n()
    dirs = task_dirs()
    print(f'i18n 键 {len(i18n)} 个, 任务目录 {len(dirs)} 个')
    print()

    infos = []
    if args.task:
        target = TASKS_DIR / args.task
        if not target.exists():
            raise SystemExit(f'没有该任务目录: {args.task}')
        dirs = [target]
    for d in dirs:
        infos.append(describe_task(d, i18n))

    names = [i['dir'] for i in infos]
    uses = find_usages(dirs, names)
    for i in infos:
        i['uses'] = sorted(uses.get(i['dir'], []))

    # 中文名缺失的
    missing_cn = [i['dir'] for i in infos if not i['cn']]

    if args.md:
        write_markdown(infos, args.md, missing_cn)
        print(f'已写入 {args.md}')
        return

    print('=' * 100)
    print('%-24s %-14s %-7s %-8s %s' % ('目录名', '中文名', '配置', '资产', '被引用'))
    print('=' * 100)
    for i in sorted(infos, key=lambda x: x['dir'].lower()):
        n_asset = sum(i['assets'].values())
        print('%-24s %-14s %-7s %-8s %s' % (
            i['dir'], i['cn'] or '(无中文名)',
            'yes' if i['has_task'] else '-',
            f"{n_asset}json/{i['png']}png",
            len(i['uses'])))
    print()
    if missing_cn:
        print(f'{len(missing_cn)} 个目录缺少中文名: {missing_cn}')


def write_markdown(infos, path, missing_cn):
    L = []
    L.append('# OAS 任务目录\n')
    L.append('> 本文件由 `dev_tools/task_catalog.py` 自动生成, 请勿手工编辑。'
             '重新生成: `python -m dev_tools.task_catalog --md tasks/CATALOG.md`\n')
    L.append(f'共 {len(infos)} 个任务目录。\n')

    # 总表
    L.append('## 总览\n')
    L.append('| 目录 | 中文名 | 资产(json/png) | 配置项 | 说明文档 | 被引用 |')
    L.append('|---|---|---|---|---|---|')
    for i in sorted(infos, key=lambda x: x['dir'].lower()):
        n = sum(i['assets'].values())
        cn = i['cn'] or '(缺)'
        L.append(f"| `{i['dir']}` | {cn} | {n} / {i['png']} | "
                 f"{len(i['fields'])} | {i['readme'] or '-'} | {len(i['uses'])} |")
    L.append('')

    # 明细
    L.append('## 明细\n')
    for i in sorted(infos, key=lambda x: x['dir'].lower()):
        L.append(f"### `{i['dir']}` — {i['cn'] or '(缺中文名)'}\n")
        if not i['has_task']:
            L.append('*（无 script_task.py，可能是共享资源目录）*\n')
        if i['fields']:
            L.append('**可配置项**\n')
            for fname, cn in i['fields'][:25]:
                L.append(f'- `{fname}` — {cn}')
            if len(i['fields']) > 25:
                L.append(f'- ...另有 {len(i["fields"]) - 25} 项')
            L.append('')
        if i['assets']:
            L.append('**资产文件**\n')
            for k, v in i['assets'].most_common(8):
                L.append(f'- `{k}.json` × {v}')
            L.append('')
        if i['uses']:
            L.append('**被以下代码引用**\n')
            for u in i['uses'][:6]:
                L.append(f'- `{u}`')
            if len(i['uses']) > 6:
                L.append(f'- ...另有 {len(i["uses"]) - 6} 处')
            L.append('')
        if i['readme']:
            L.append(f"**自带文档**: `{i['dir']}/{i['readme']}`\n")

    if missing_cn:
        L.append('## 缺少中文名的目录\n')
        L.append('i18n 中没有对应条目, 需要人工确认其游戏功能:\n')
        for m in missing_cn:
            L.append(f'- `{m}`')
        L.append('')

    Path(path).write_text('\n'.join(L), encoding='utf-8')


if __name__ == '__main__':
    main()
