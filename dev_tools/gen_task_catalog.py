# -*- coding: utf-8 -*-
"""生成 module/config/task_catalog_data.json —— 54 个任务的权威元数据。

**设计原则: 一切靠实测, 不手写、不靠猜。**
之所以强调这点: 2026-10-08 出现过多次因"凭印象写任务信息"导致的错误
(把 HeroTest 写成"英雄测试"、AbyssShadows 写成"御魂·深渊"、
Sougenbi 写成"真八岐大蛇"、RealmRaid 写成"阴界之门"), 全部是编造。

数据来源:
  中文名        OASX lib/config/translation/i18n_cn.dart (含 I18n.x / 'X' / camelCase 三种 key 变体)
  目标次数字段  扫描 tasks/*/script_task.py 里 "current_count >= X" 模式实测得出
  其它字段      tasks/*/config.py 的 Field(default=...) 解析
  充能周期      config/*.json 里各任务的 scheduler.success_interval(用户真实配置)

用法:
    python dev_tools/gen_task_catalog.py            # 在 OAS 仓库根目录执行
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TASKS = REPO / 'tasks'
OUT = REPO / 'module' / 'config' / 'task_catalog_data.json'

# OASX 源码位置(用于取权威中文名)。可用环境变量覆盖。
OASX_DEFAULT = REPO.parent / 'OASX-src'
import os
OASX = Path(os.environ.get('OASX_SRC', OASX_DEFAULT))
I18N = OASX / 'lib' / 'config' / 'translation' / 'i18n_cn.dart'

CJK = r'\u4e00-\u9fa5'


# --------------------------------------------------------------------------- 中文名
def build_name_index() -> dict:
    """从 OASX i18n_cn.dart 建立 任务名 -> 中文名 映射(处理 3 种 key 变体)。"""
    if not I18N.exists():
        print(f'!! 未找到 {I18N}, 中文名将留空')
        print(f'   可用环境变量 OASX_SRC 指定 OASX 源码目录')
        return {}

    text = I18N.read_text(encoding='utf-8')
    entries = []
    # I18n.fallen_sun: '日轮之陨'   (snake_case)
    # I18n.kekkaiUtilize: '结界蹭卡' (camelCase)
    for m in re.finditer(rf"I18n\.([A-Za-z_][A-Za-z0-9_]*)\s*:\s*'([^']*[{CJK}][^']*)'", text):
        entries.append((m.start(), m.group(1), m.group(2)))
    # 'AbyssShadows': '狭间暗域'    (PascalCase 补充表)
    for m in re.finditer(rf"'([A-Za-z_][A-Za-z0-9_]*)'\s*:\s*'([^']*[{CJK}][^']*)'", text):
        entries.append((m.start(), m.group(1), m.group(2)))
    entries.sort()

    index = {}
    for _pos, key, val in entries:
        for variant in {key, key.lower(),
                        re.sub(r'(?<!^)(?=[A-Z])', '_', key).lower()}:
            index[variant] = val
    return index


MANUAL_NAMES = {
    # 补充表里 key 与任务目录名对不上, 已逐个 grep 确认
    'GotoMain': '回到庭院',
    'GuildActivityMonitor': '寮活动监控',
    'BudokaiTournament': '武道大会',
    'OtherWorldTwilight': '彼世逢魔',
}


# --------------------------------------------------------------------------- 分类
# 依据: 游戏机制 + 用户确认(2026-10-08)
CATEGORY = {
    # 固定任务: 有"打满 N 次"的语义
    'FallenSun': 'fixed', 'Orochi': 'fixed', 'EternitySea': 'fixed',
    'EvoZone': 'fixed', 'Sougenbi': 'fixed', 'BondlingFairyland': 'fixed',
    'GoryouRealm': 'fixed', 'OtherWorldTwilight': 'fixed', 'SixRealms': 'fixed',
    'HeroTest': 'fixed', 'Exploration': 'fixed', 'Hyakkiyakou': 'fixed',
    'WantedQuests': 'fixed',
    # 充能: 按存量(slots 时刻补充)
    'GoldYoukai': 'charge', 'ExperienceYoukai': 'charge', 'Tako': 'charge',
    # 结界突破的两个子分类(用户确认: 寮突破 + 个人突破)
    'RyouToppa': 'toppa', 'RealmRaid': 'toppa',
    # 限时活动: 隔一段时间才推出, 非常驻(用户列出的 8 个)
    'ActivityShikigami': 'limited', 'MetaDemon': 'limited', 'FrogBoss': 'limited',
    'FloatParade': 'limited', 'Quiz': 'limited', 'KittyShop': 'limited',
    'DyeTrials': 'limited', 'BudokaiTournament': 'limited',
}
DEFAULT_CATEGORY = 'timed'

# 目标次数字段: 按脚本里 "current_count >= X" 的判据人工核定(见下方 verify 输出)
COUNT_FIELD = {
    'FallenSun': 'limit_count', 'Orochi': 'limit_count',
    'EternitySea': 'limit_count', 'EvoZone': 'limit_count',
    'Sougenbi': 'limit_count', 'BondlingFairyland': 'limit_count',
    'GoryouRealm': 'limit_count', 'OtherWorldTwilight': 'limit_count',
    'RyouToppa': 'limit_count', 'HeroTest': 'limit_count',
    'SixRealms': 'limit_count',
    'Exploration': 'minions_cnt',       # 待统一
    'Hyakkiyakou': 'hya_limit_count',   # 待统一
    'RealmRaid': 'number_attack',       # 待统一
    'WantedQuests': None,               # 脚本里硬编码 30, 需新增字段
}
UNIFIED_COUNT_FIELD = 'limit_count'

# 用于把任务目录名转成 i18n key
def snake(n: str) -> str:
    return re.sub(r'(?<!^)(?=[A-Z])', '_', n).lower()


def camel(n: str) -> str:
    head, *rest = snake(n).split('_')
    return head + ''.join(w.capitalize() for w in rest)


# --------------------------------------------------------------------------- 解析 config.py
# 坑: 默认值里可能含逗号(charge_slots='0,12'); 其"外层引号"要保留到清洗阶段,
# 否则无法区分"值内部的逗号"与"参数之间的逗号"。因此:
#   1) 先把带引号的字面量('...' / "...") 或裸值([^,)]*) 整段取出来;
#   2) 再由 _clean_default 去掉外层引号。
# 用非贪婪 + lookahead 停在右括号, 避免把 description=... 一起吃进来。
_FIELD_RE = re.compile(
    r"""^\s{4,8}(\w+)\s*:\s*(int|bool|str|float)\s*=\s*Field\(
        \s*[^)]*?default\s*=\s*(?P<val>'[^']*'|"[^"]*"|[^,)]*)
    """,
    re.M | re.X)


def _clean_default(raw: str) -> str:
    """把 Field(default=...) 抓到的片段清成可用的字面量。"""
    s = (raw or '').strip().rstrip(',').strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        s = s[1:-1]
    return s


def read_config_fields(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding='utf-8', errors='replace')
    out = {}
    for m in _FIELD_RE.finditer(text):
        name, typ, raw = m.group(1), m.group(2), m.group('val')
        out.setdefault(name, {'type': typ, 'default': _clean_default(raw)})
    return out


# --------------------------------------------------------------------------- 实测次数字段
def detect_count_field(task: str) -> str or None:
    """扫描 script_task.py 找 "current_count >= X" 里的 X(实测判据)。"""
    f = TASKS / task / 'script_task.py'
    if not f.exists():
        return None
    text = f.read_text(encoding='utf-8', errors='replace')
    hits = re.findall(r'current_count\s*>=\s*(?:self\.)?([A-Za-z_][A-Za-z0-9_\.]*)', text)
    for h in hits:
        h = h.split('.')[-1]
        if h != 'current_count':
            return h
    return None


def read_intervals() -> tuple:
    """
    从用户配置读各任务真实的 success_interval(即充能周期)。

    注意: 多个配置文件(每个账号一个)的 interval 可能不同。**不能混用**,
    否则同一任务会被后读到的配置覆盖(实测踩过: 金币妖怪被覆盖成 1 天,
    而实际是 3 小时)。这里只取第一个配置作为基准, 并返回它的文件名供追溯。
    """
    files = sorted((REPO / 'config').glob('*.json'))
    if not files:
        return {}, None
    # 排除模板; 在其余配置里选"启用任务最多"的那个(最可能是用户真实在用的),
    # 平手时取修改时间较新的。实测: oas1.json 是废弃配置(全是默认 1 天),
    # 而恋鸟树.json 才有用户调过的 3 小时。
    cands = []
    for p in files:
        if p.name == 'template.json':
            continue
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        n_on = sum(1 for v in data.values()
                   if isinstance(v, dict)
                   and (v.get('scheduler') or {}).get('enable'))
        cands.append((n_on, p.stat().st_mtime, p, data))
    if not cands:
        return {}, None
    cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _n, _mt, src, data = cands[0]
    out = {}
    for k, v in data.items():
        s = (v or {}).get('scheduler') if isinstance(v, dict) else None
        if s and s.get('success_interval'):
            out[k] = s['success_interval']
    return out, src.name


def main() -> int:
    names = build_name_index()
    intervals, interval_src = read_intervals()

    # --dump-names: 只导出"任务名 -> 权威中文名"对照表。
    # 用途: OASX 仓库不可用时(未 clone / 环境变量没设), 仍能查看或人工核对
    # 各任务的中文名。生成物是**派生产物**, 不应手工编辑。
    if '--dump-names' in sys.argv:
        out = REPO / 'dev_tools' / 'data' / 'task_names.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        tasks = sorted(d.name for d in TASKS.iterdir()
                       if d.is_dir() and (d / 'script_task.py').exists())
        mapping = {}
        for t in tasks:
            mapping[t] = (names.get(t) or names.get(snake(t)) or names.get(camel(t))
                          or MANUAL_NAMES.get(t))
        out.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + '\n',
                       encoding='utf-8')
        missing = [k for k, v in mapping.items() if not v]
        print(f'已写出 {out.relative_to(REPO)}  ({len(mapping)} 个任务)')
        if missing:
            print(f'!! 缺中文名: {", ".join(missing)}')
        return 0

    rows = []
    for d in sorted(TASKS.iterdir()):
        if not d.is_dir() or not (d / 'script_task.py').exists():
            continue
        task = d.name
        fields = read_config_fields(d / 'config.py')
        cat = CATEGORY.get(task, DEFAULT_CATEGORY)
        declared = COUNT_FIELD.get(task, '__absent__')
        detected = detect_count_field(task)

        # 实测优先; 若与人工核定不一致则报警(说明判据或核定表要更新)
        count_field = declared if declared != '__absent__' else detected
        mismatch = (detected and declared not in ('__absent__', None)
                    and detected != declared)

        name_zh = (names.get(task) or names.get(snake(task)) or names.get(camel(task))
                   or MANUAL_NAMES.get(task))

        rows.append({
            'task': task,
            'name_zh': name_zh,
            'category': cat,
            'count_field': count_field,
            'count_field_detected': detected,
            'count_field_mismatch': bool(mismatch),
            'count_default': (fields.get(count_field, {}) or {}).get('default')
                             if count_field else None,
            'needs_unify': bool(count_field and count_field != UNIFIED_COUNT_FIELD),
            'has_charge': 'charge_max' in fields,
            'charge_max': (fields.get('charge_max', {}) or {}).get('default'),
            'charge_slots': (fields.get('charge_slots', {}) or {}).get('default') or None,
            'charge_consume': (fields.get('charge_consume', {}) or {}).get('default'),
            'has_limit_time': 'limit_time' in fields,
            'fixed_schedule_time': (fields.get('next_ryoutoppa_time', {}) or {}).get('default'),
            'success_interval': intervals.get(snake(task)),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        '_note': '由 dev_tools/gen_task_catalog.py 生成, 请勿手工编辑。'
                 '中文名取自 OASX i18n; 次数字段为脚本实测; 周期取自用户配置。',
        '_interval_source': interval_src,
        'tasks': rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')

    # ---------------- 报告 ----------------
    print(f'已写出 {OUT.relative_to(REPO)}  ({len(rows)} 个任务)')
    print(f'充能周期取自配置: {interval_src or "(无)"}')
    print()

    no_name = [r['task'] for r in rows if not r['name_zh']]
    if no_name:
        print(f'!! 缺中文名({len(no_name)}): {", ".join(no_name)}')
        print()

    bad = [r for r in rows if r['count_field_mismatch']]
    if bad:
        print('!! 实测次数字段与核定表不一致(需人工确认):')
        for r in bad:
            print(f"   {r['task']}: 核定={r['count_field']} 实测={r['count_field_detected']}")
        print()

    print('=' * 100)
    print(f'{"任务":<22}{"中文名":<12}{"类别":<9}{"次数字段":<18}{"默认":<6}{"周期":<14}{"统一"}')
    print('=' * 100)
    for r in rows:
        print(f'{r["task"]:<22}{str(r["name_zh"] or "?"):<12}{r["category"]:<9}'
              f'{str(r["count_field"] or "-"):<18}{str(r["count_default"] or "-"):<6}'
              f'{str(r["success_interval"] or "-"):<14}'
              f'{"待统一" if r["needs_unify"] else ""}')

    print()
    from collections import Counter
    print('分类分布:', dict(Counter(r['category'] for r in rows)))
    print('待统一字段:',
          [f"{r['task']}.{r['count_field']}" for r in rows if r['needs_unify']])
    print('需新增字段:',
          [r['task'] for r in rows if r['category'] == 'fixed' and not r['count_field']])

    return 0


if __name__ == '__main__':
    sys.exit(main())
