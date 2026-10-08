# -*- coding: utf-8 -*-
"""从 `tasks/<Name>/meta.py` 同步任务名到各 i18n 副本。

## 解决的问题

任务中文名此前散落在 **4 处**手写副本, 靠人工同步, **必然漂移**。实测漂移:

| 任务 | `zh_CN.xml` | 权威 |
|---|---|---|
| `AreaBoss` | 地**狱**鬼王 | 地域鬼王 |
| `DemonEncounter` | **封**魔之时 | 逢魔之时 |
| `TrueOrochi` | 真·八岐大蛇 | 真八岐大蛇 |
| `ActivityShikigami` | 当期**式神**爬塔 | 当期爬塔 |
| `Secret` | 秘闻之**境** | 秘闻副本 |

另有 17 个任务在 OAS 侧**完全没有**条目, 17 个在 OASX 侧没有。

## 设计

**唯一来源**: `tasks/<Name>/meta.py` 的 `TaskSpec.name_zh`
(由 `task_catalog` 汇总为权威表)。

本脚本把它分发到:
  1. `module/config/i18n/zh_CN.xml` (OAS)   —— 插入缺失 + 修正错误
  2. OASX `lib/config/translation/i18n_cn.dart` —— 插入缺失 + 修正错误

★ **只改任务名条目**, 不动其它 UI 文案 —— 那些是人工撰写的, 不该被脚本重排。

## 安全

* `--dry-run` 先看要改什么
* 修正前逐条打印"旧值 -> 新值", 便于人工确认
* 若同名条目出现多次且值不同(真漂移), 会全部改成权威值
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(r'D:\OAS-dev\OnmyojiAutoScript')
OASX = Path(r'D:\OAS-dev\OASX-src')
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'dev_tools'))
import os
os.chdir(REPO)

import logging                        # noqa: E402
logging.disable(logging.CRITICAL)

import i18n_data as ID                # noqa: E402
from module.config import task_catalog as TC   # noqa: E402


def authoritative_table() -> dict:
    return {m.task: (m.name_zh or '') for m in TC.all_meta()}


# --------------------------------------------------------------------------- OAS XML
def sync_oas_xml(auth: dict, dry: bool) -> int:
    """
    同步 `zh_CN.xml`。

    做两件事:
      * **新增**: 权威里有、XML 里没有的 -> 在末尾插入标准条目
      * **修正**: 两边都有但值不同 -> 替换 translation
    """
    f = REPO / 'module' / 'config' / 'i18n' / 'zh_CN.xml'
    text = f.read_text(encoding='utf-8')
    current = ID.load_oas_xml(REPO, set(auth))
    missing, wrong = ID.diff(current, auth)
    changes = 0

    print(f'--- OAS {f.relative_to(REPO)} ---')

    # 修正错译: 逐个替换该 source 对应的 translation
    for task, got, want in wrong:
        # 精确定位 `<source>Task</source>` 后紧跟的 translation
        pattern = (r'(<source>' + re.escape(task) + r'</source>\s*'
                   r'<translation>)(.*?)(</translation>)')
        def _repl(m, want=want):
            return m.group(1) + want + m.group(3)
        new_text, n = re.subn(pattern, _repl, text, flags=re.S)
        if n:
            print(f'    修正 {task:<22} {got!r} -> {want!r}  ({n} 处)')
            text = new_text
            changes += n
        else:
            print(f'    !! 找不到 {task} 的条目, 跳过')

    # 新增缺失
    if missing:
        # ⚠ 必须插进**任务名所在的 context** —— 实测是 `FluTreeView`
        # (QML 的任务树)。一开始插到文件末尾, 落进了某个 `Args` context:
        # xml 里有了、.qm 里 `FluTreeView` 查不到, 界面照样显示英文键 ——
        # 与 `FallenSun` 当初的问题一模一样(踩过)。
        block = ('\n\t\t<!-- 由 dev_tools/gen_i18n.py 从 tasks/<Name>/meta.py '
                 '生成; 请勿手改, 改 meta.py -->\n')
        for task in missing:
            block += (f'\t\t<message><source>{task}</source>'
                      f'<translation>{auth[task]}</translation></message>\n')

        # 取**最后一个** FluTreeView 段的结束位置(文件被拼接多份, 末份生效)
        ctx = 'FluTreeView'
        idx_insert = None
        for m in re.finditer(r'<name>' + re.escape(ctx) + r'</name>', text):
            # 该 context 的结束: 之后第一个 </context>
            end = text.find('</context>', m.end())
            if end != -1:
                idx_insert = end        # 记住最后一个
        if idx_insert is None:
            print(f'    !! 找不到 context {ctx}, 无法插入')
        else:
            text = text[:idx_insert] + block + text[idx_insert:]
            print(f'    新增 {len(missing)} 条到 context {ctx}: {missing}')
            changes += len(missing)

    if changes and not dry:
        f.write_text(text, encoding='utf-8')
    return changes


# --------------------------------------------------------------------------- OASX dart
def sync_oasx_content(auth: dict, dry: bool) -> int:
    """
    同步 OASX `i18n_content.dart` —— **补键常量**。

    这里定义的是键常量, 如 `static const String fallen_sun = 'FallenSun';`。
    没有常量 = 代码里无法引用该任务名 = 界面显示英文 key。
    实测缺 15 个(如 `abyss_shadows`、`hero_test`、`quiz`)。

    键名用 `task_to_key()`(snake_case), 与多数既有常量一致。
    """
    f = OASX / 'lib' / 'config' / 'translation' / 'i18n_content.dart'
    if not f.exists():
        print(f'--- OASX {f} 不存在, 跳过 ---')
        return 0

    text = f.read_text(encoding='utf-8')
    consts = ID.load_oasx_content_keys(OASX)
    # 值 -> 常量名(判断某个任务是否已有常量, 不论命名变体)
    have_task = {v for v in consts.values()}
    missing = sorted(t for t in auth if t not in have_task)

    print(f'--- OASX {f.relative_to(OASX)} ---')
    if not missing:
        print('    无需新增')
        return 0

    # 同时避免常量名冲突(如已存在同名但值不同的常量)
    taken = set(consts)
    lines = []
    for task in missing:
        key = ID.task_to_key(task)
        if key in taken:
            print(f'    !! 常量名 {key} 已被占用, 跳过 {task}')
            continue
        lines.append(f"  static const String {key} = '{task}';")
        taken.add(key)

    if not lines:
        return 0

    block = ('  // ---- 以下由 dev_tools/gen_i18n.py 从 tasks/<Name>/meta.py 生成; '
             '请勿手改 ----\n' + '\n'.join(lines) + '\n')

    # 插到 class I18n 的最后一个 `}` 之前 —— 用 rfind 定位类结束
    idx = text.rfind('}')
    if idx == -1:
        print('    !! 找不到类结束位置')
        return 0
    if not dry:
        f.write_text(text[:idx] + block + text[idx:], encoding='utf-8')
    print(f'    新增 {len(lines)} 个键常量: '
          f'{[l.split()[3] for l in lines]}')
    return len(lines)


def _find_lrelease() -> Path or None:
    """定位 Qt 的 `lrelease`(PySide6 自带)。"""
    cands = [
        REPO / 'toolkit' / 'Lib' / 'site-packages' / 'PySide6' / 'lrelease.exe',
        REPO / 'toolkit' / 'Lib' / 'site-packages' / 'PySide6' / 'lrelease',
        REPO / 'toolkit' / 'lrelease.exe',
    ]
    for c in cands:
        if c.exists():
            return c
    # PATH 里找
    import shutil
    p = shutil.which('lrelease') or shutil.which('lrelease.exe')
    return Path(p) if p else None


def compile_qm(dry: bool) -> int:
    """
    用 `lrelease` 把 `zh_CN.xml` 编译成 `zh_CN.qm`。

    ## ⚠ 定位说明(死代码清扫时核实)

    **`.qm` 在生产代码里已经没有任何读者。** 核实结果:

    | 谁读 `.qm` | 结论 |
    |---|---|
    | OAS 生产代码 | ❌ **无** —— Python 侧只用 `I18n.trans_zh_cn()`, 它读的是 `zh-CN.json` |
    | OASX(Flutter) | ❌ 无 —— 它用自己的 Dart i18n, 并通过 `/home/chinese_translate` 把 map **推给** OAS |
    | 测试 / 本生成器 | ✅ 有 |

    原本的读者是**已删除的 PySide6/QML GUI**(QTranslator 是 Qt 的东西),
    见提交 `7d980485`。

    ## 那为什么还保留生成

    因为 `zh_CN.qm` **已随仓库发布**, 无法排除旧版本 OASX 或第三方前端仍会读它。
    删掉文件是**破坏性**的; 保留生成的代价很小。

    ★ 因此这里的定位是: **仅为向后兼容而保留**。若确认无人在用, 可连同
    `zh_CN.xml` 一起退役(那时 `meta.py` -> `zh_CN.xml` 这条链也可以简化)。
    """
    src = REPO / 'module' / 'config' / 'i18n' / 'zh_CN.xml'
    dst = REPO / 'module' / 'config' / 'i18n' / 'zh_CN.qm'
    print('--- 编译 zh_CN.qm ---')

    lrelease = _find_lrelease()
    if lrelease is None:
        print('    !! 找不到 lrelease, 跳过(请手动编译)')
        return 0
    if dry:
        print(f'    将执行: {lrelease.name} {src.name} -qm {dst.name}')
        return 0

    import subprocess
    try:
        r = subprocess.run([str(lrelease), str(src), '-qm', str(dst)],
                           capture_output=True, text=True, timeout=120)
    except Exception as exc:
        print(f'    !! 编译失败: {type(exc).__name__}: {exc}')
        return 0

    out = (r.stdout or '') + (r.stderr or '')
    # lrelease 会把 "Generated N translations" 之类的信息写到 stdout/stderr
    for line in out.strip().splitlines()[-4:]:
        print(f'    {line.strip()}')
    if r.returncode == 0 and dst.exists():
        print(f'    OK 已生成 {dst.relative_to(REPO)} '
              f'({dst.stat().st_size // 1024} KB)')
        return 1
    print(f'    !! lrelease 返回 {r.returncode}')
    return 0


def sync_oasx_dart(auth: dict, dry: bool) -> int:
    """
    同步 OASX `i18n_cn.dart`。

    条目形如 `I18n.fallen_sun: '日轮之陨',`。
    对**任务名条目**做修正与新增; 其它 UI 文案一律不动。
    """
    f = OASX / 'lib' / 'config' / 'translation' / 'i18n_cn.dart'
    if not f.exists():
        print(f'--- OASX {f} 不存在, 跳过 ---')
        return 0
    text = f.read_text(encoding='utf-8')
    current = ID.load_oasx_dart(OASX, set(auth))
    missing, wrong = ID.diff(current, auth)
    changes = 0

    print(f'--- OASX {f} ---')

    for task, got, want in wrong:
        key = ID.task_to_key(task)
        pattern = (r"(I18n\." + re.escape(key) + r":\s*')([^']*)(')")
        new_text, n = re.subn(pattern, lambda m, w=want: m.group(1) + w + m.group(3),
                              text)
        if n:
            print(f'    修正 {task:<22} {got!r} -> {want!r}  ({n} 处)')
            text = new_text
            changes += n
        else:
            print(f'    !! 找不到 I18n.{key}, 跳过')

    # 新增: 追加到 _cn_ui 区块末尾(那里就是任务名条目的所在)
    if missing:
        lines = []
        for task in missing:
            key = ID.task_to_key(task)
            lines.append(f"  I18n.{key}: '{auth[task]}',")
        block = '\n'.join(lines) + '\n'

        # _cn_ui 区块结束位置: 找 `final Map<String, String> _cn_ui = {` 之后的第一个 `};`
        start = text.find('final Map<String, String> _cn_ui = {')
        if start == -1:
            print('    !! 找不到 _cn_ui 区块, 无法插入')
        else:
            end = text.find('};', start)
            if end == -1:
                print('    !! _cn_ui 区块未闭合')
            else:
                marker = ('  // ---- 以下由 dev_tools/gen_i18n.py 从 '
                          'tasks/<Name>/meta.py 生成; 请勿手改 ----\n')
                text = text[:end] + marker + block + text[end:]
                print(f'    新增 {len(missing)} 条: {missing}')
                changes += len(missing)

    if changes and not dry:
        f.write_text(text, encoding='utf-8')
    return changes


# --------------------------------------------------------------------------- main
def check_qm(auth: dict) -> int:
    """
    校验**编译产物** `zh_CN.qm` 里的任务名是否为权威值。

    ## ⚠ 定位说明

    `.qm` 在生产代码里**已无读者**(原读者是已删除的 QML GUI) ——
    详细核实见 `compile_qm()` 的文档。这里的校验是**向后兼容的守门**:
    确保这个已发布的产物不会悄悄漂移。

    为什么既有测试不够: `test_task_state.py` 只抽查 `Period` / `Reset At` 等键,
    **完全不覆盖任务名**, 所以任务名漂移测不出来。
    """
    qm = REPO / 'module' / 'config' / 'i18n' / 'zh_CN.qm'
    print('--- 编译产物 zh_CN.qm ---')
    if not qm.exists():
        print('    !! zh_CN.qm 不存在')
        return 1
    try:
        from PySide6.QtCore import QCoreApplication, QTranslator
    except ImportError:
        print('    (未安装 PySide6, 跳过)')
        return 0

    QCoreApplication.instance() or QCoreApplication([])
    tr = QTranslator()
    if not tr.load(str(qm)):
        print('    !! 无法加载 zh_CN.qm')
        return 1

    # .qm 里任务名所在 context(QML 的任务树)
    contexts = ['FluTreeView', 'TaskList', 'Args', '']
    bad = []
    for task, want in sorted(auth.items()):
        got = ''
        for ctx in contexts:
            got = tr.translate(ctx, task)
            if got:
                break
        if not got:
            bad.append((task, '(缺失)', want))
        elif got != want:
            bad.append((task, got, want))

    if bad:
        print(f'    {len(bad)} 个任务名在 .qm 里缺失或不符:')
        for t, got, want in bad[:12]:
            print(f'      {t:<22} {got!r} != {want!r}')
        if len(bad) > 12:
            print(f'      ... 共 {len(bad)} 个')
        print('    -> 需重新编译: python dev_tools/gen_i18n.py')
        return 1
    print(f'    ✓ {len(auth)} 个任务名均与权威一致')
    return 0


def main() -> int:
    dry = '--dry-run' in sys.argv
    check = '--check' in sys.argv
    auth = authoritative_table()

    print('=' * 96)
    print(f'i18n 同步{"  (--dry-run 仅预览)" if dry else ""}'
          f'{"  (--check 仅检查)" if check else ""}')
    print(f'权威来源: tasks/<Name>/meta.py  —— {len(auth)} 个任务')
    print('=' * 96)
    print()

    if check:
        bad = 0
        for name, data in (
                ('OAS zh_CN.xml', ID.load_oas_xml(REPO, set(auth))),
                ('OASX i18n_cn.dart', ID.load_oasx_dart(OASX, set(auth))),
        ):
            missing, wrong = ID.diff(data, auth)
            bad += len(missing) + len(wrong)
            if missing or wrong:
                print(f'  {name}: 缺失 {len(missing)}, 不一致 {len(wrong)}')
                for t, got, want in wrong[:8]:
                    print(f'      {t:<22} {got!r} != {want!r}')
                if missing:
                    print(f'      缺失: {missing[:10]}'
                          + (' ...' if len(missing) > 10 else ''))
            else:
                print(f'  {name}: ✓ 一致')

        # 键常量覆盖
        consts = ID.load_oasx_content_keys(OASX)
        have = set(consts.values())
        miss_const = sorted(t for t in auth if t not in have)
        bad += len(miss_const)
        if miss_const:
            print(f'  OASX i18n_content.dart: 缺 {len(miss_const)} 个键常量: '
                  f'{miss_const[:10]}')
        else:
            print('  OASX i18n_content.dart: ✓ 键常量齐全')

        print()
        bad += check_qm(auth)

        print()
        if bad:
            print(f'*** 共 {bad} 处待修正 —— 执行 `python dev_tools/gen_i18n.py` ***')
            return 1
        print('*** 全部一致 ***')
        return 0

    n1 = sync_oas_xml(auth, dry)
    print()
    n2 = sync_oasx_content(auth, dry)
    print()
    n3 = sync_oasx_dart(auth, dry)
    print()
    n4 = compile_qm(dry)

    print()
    print('=' * 96)
    print(f'合计改动: OAS zh_CN.xml {n1} 条, '
          f'OASX i18n_content.dart {n2} 条, OASX i18n_cn.dart {n3} 条, '
          f'重新编译 .qm {"是" if n4 else "否"}')
    if dry:
        print('(预览模式, 未写入。去掉 --dry-run 以实际执行)')
    else:
        print('已写入。请重跑 dev_tools/gen_i18n.py --check 确认。')
    print('=' * 96)
    return 0


if __name__ == '__main__':
    sys.exit(main())
