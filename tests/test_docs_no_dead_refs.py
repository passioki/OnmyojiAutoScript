# -*- coding: utf-8 -*-
"""★ 文档守卫（T3）: 文档里提到的**代码路径必须存在**。

## 为什么需要（审计 T3 最有价值的产出）

审计发现文档里**大量**提到**已删除**的代码:
`architecture.md` 列了 `module/config/scheduler_core.py`（**已删**）,
`dev_tools/gen_resource_specs.py`（**已删**）,
`tests/.../test_availability.py`（**已删**）—— 后面接手的人会**照着已删除的
代码写实现**。

★ 一条测试就能消灭大部分这类问题: 抽出文档里所有 `` `xxx.py` `` 路径,
  断言**文件存在**。

## ★★ 豁免策略（我在这里翻了 4 次车, 教训写下来）★★

**第一版**: "以 `#` 开头就是标题" —— Markdown 的**代码块**里有 Python 注释
  （`# 复现该问题`）也被当标题 -> 区段**被自己的示例打断**。

**第二版**: 只认 `^(#{1,6})\s` —— 文档是 **CRLF**, `### x` 行尾带 `\r`,
  `re.match` **匹配失败** -> 豁免完全不生效。

**第三版**: 先规范化换行 —— 但**调用方切行没规范化** -> **行号错位**。

**第四版**: 用"标题层级"判断（`###` 不结束 `##`）—— 但**标记文字本身**
  会出现在**别处的示例代码里**, 豁免区被**意外开启/关闭**。

★★ **结论**: "扫描出一段区间"**本质脆弱** —— 它靠启发式猜"这段讲的是不是
  已删的东西"。**改成显式**: 文档级白名单 + 就地标注。
  比"聪明的扫描"**可靠得多**, 也**好维护**（加一份文档 = 加一行）。
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = REPO / 'docs'

#: ── 允许提到"已删除路径 / 已删字段"的文档（相对 `docs/`）──
_ALLOW_DEAD_PATHS = {
    'deprecated.md',             # 唯一废弃清单 —— 它就得写已删的东西
    'SESSION-LEDGER.md',         # 历史台账 —— 记录当时发生了什么
    # ★★ 第二轮复审: rchitecture.md **已移出白名单** ★★
    #
    # 原来整份豁免 —— 结果这条守卫**抓不到它自己举的例子**
    # （docstring 说动机就是 rchitecture.md 列了已删的
    # scheduler_core.py / gen_resource_specs.py / 	est_availability.py）。
    # ★ 复审员实测: 全仓 153 条路径引用里 **143 条被白名单豁免**,
    #   真正被断言的只剩 **2 条** —— 等于空转。
    # ★ 现在改成**就地标注**（该文档里已删的路径都写了已删）；
    #   若还有漏的, 守卫会**真的红**。
    'team-coordination.md',      # 引用了已删的 team_coordinator（待重设计）
    'oasx-task-list-ui.patch',   # 历史 patch
}

#: 同行出现这些字样 -> 视为"就地标注了已删", 豁免该行
_DEAD_MARKERS = ('已删', '删除', '已废弃', '废弃', '不存在', '已移除',
                 'deprecated', 'MISSING', '已并入', '【已删】')

#: 路径形态
_PATH_RE = re.compile(
    r'`((?:module|dev_tools|tests|tasks|config)/[A-Za-z0-9_./-]+\.py)`')


def _md_files():
    if not DOCS.is_dir():
        return []
    return sorted(p for p in DOCS.rglob('*.md')
                  if 'archive' not in p.relative_to(DOCS).parts)


def _read_lines(md: Path):
    """读文档并**规范化换行**后按行返回。

    ⚠ 必须规范化: 文档是 **CRLF**, 不处理会让"行内匹配"与"行号"错位。
    """
    text = md.read_text(encoding='utf-8', errors='replace')
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.split('\n')


def _line_has_dead_marker(line: str) -> bool:
    return any(m in line for m in _DEAD_MARKERS)


class TestDocsNoDeadPaths:
    """★ 文档里提到的 `.py` 路径**必须存在**。"""

    def test_all_referenced_py_paths_exist(self):
        bad = []
        checked = 0
        for md in _md_files():
            rel = md.relative_to(DOCS).as_posix()
            if rel in _ALLOW_DEAD_PATHS:
                continue
            for i, line in enumerate(_read_lines(md), 1):
                if _line_has_dead_marker(line):
                    continue          # 就地标注了"已删" -> 豁免
                for m in _PATH_RE.finditer(line):
                    p = m.group(1)
                    checked += 1
                    if not (REPO / p).exists():
                        bad.append(f'{rel}:{i}  提到不存在的 `{p}`')

        # ★ 防空转: 一条路径都没抽到 -> 正则坏了, 守卫形同虚设
        #
        # ⚠ 阈值**不能定太高**: 大部分文档已被加进 _ALLOW_DEAD_PATHS
        #   （它们**本来就**是讲历史/废弃的）, 真正被检查的只有
        #   ui-api-mapping.md / deprecated.md 等少数几份。
        #   ★ 我第一版写 > 20 -> **假失败**。**阈值要按实际**定。
        # ★★ 第二轮复审: 阈值从 1 提到 **25** ★★
        #
        # 复审员实测: 原来 >= 1, 而**实际只校验 2 条**
        # （153 条引用里 143 条被白名单豁免）—— 距空转仅 1 行之遥。
        # 把 rchitecture.md 移出白名单后升到 **31 条**。
        # ★ 阈值定在 25（略低于实测 31）—— 既防空转, 又不脆到改一行就红。
        assert checked >= 25, (
            f'只抽到 {checked} 条路径引用（应 >= 25）—— '
            f'★ 要么正则失效, 要么有人把文档大量加进了 _ALLOW_DEAD_PATHS。'
            f'守卫的覆盖面积**不能靠白名单缩小**。')
        assert not bad, (
            '文档提到了**不存在**的代码路径（后面的人会照着写）:\n  '
            + '\n  '.join(bad[:20])
            + f'\n  （共 {len(bad)} 条; 若该处是"已删除"的说明, '
              f'请在同行写明"已删"以豁免; 或把该文档加入 `_ALLOW_DEAD_PATHS`）')


class TestCurrentDocsFreeOfRemovedSymbols:
    """★ **现行**文档的正文不得出现已删的字段名。"""

    REMOVED = (
        ('window_slots', 'S3 已改成 `windows` 列表'),
        ('charge_max', 'S5 已删掉整个存量机制'),
        ('charge_slots', '同上'),
        ('charge_enable', '同上'),
        ('charge_consume', '同上'),
        ('Category.CHARGE', '同上'),
        ('Recharge', '同上'),
        ('scheduler_core', 'S5 已删（死代码）'),
        ('team_coordinator', 'S5 已删（待重设计为独立模块）'),
        # ★★ 第二轮复审补录: 这三项当时**漏了**, 于是"契约文档仍在教人用"\n        #   已废弃字段**守卫抓不到**（复审员实测）。\n        ('schedule_rule', 'T1/S6 已并入 priority_mode（3 模式）'),
        ('timed_priority', 'S6 已并入 priority_mode'),
        ('window_fields', 'T4 已删（单值窗口全废, 改成 windows 列表）'),
        ('list.modes', 'T1/S6 后是死链（四个旧调度模式）'),
    )

    @pytest.mark.parametrize('needle,why', REMOVED)
    def test_not_in_current_docs(self, needle, why):
        hits = []
        for md in _md_files():
            rel = md.relative_to(DOCS).as_posix()
            if rel in _ALLOW_DEAD_PATHS:
                continue
            for i, line in enumerate(_read_lines(md), 1):
                if needle not in line:
                    continue
                if _line_has_dead_marker(line):
                    continue          # 就地标注了"已删" -> 豁免
                hits.append(f'{rel}:{i}  {line.strip()[:90]}')

        assert not hits, (
            f'现行文档里出现了已删的 `{needle}`（{why}）:\n  '
            + '\n  '.join(hits[:8])
            + '\n  ★ 要么改掉, 要么在同行写明"已删"以豁免')


class TestDeprecatedListExists:
    """★ 唯一废弃清单必须存在 —— 否则"某东西还在不在"无处可查。"""

    def test_deprecated_md_exists(self):
        p = DOCS / 'deprecated.md'
        assert p.is_file(), 'docs/deprecated.md（唯一废弃清单）不存在'
        text = p.read_text(encoding='utf-8')
        for kw in ('Recharge', 'Resource', 'window_slots', 'schedule_rule',
                   'timed_priority', 'scheduler_core', 'team_coordinator'):
            assert kw in text, f'废弃清单漏了 `{kw}`'


class TestAuthorityLayering:
    """★ 分层定权威: 每份**现行**文档都要声明**状态**与**冲突时以谁为准**。"""

    CURRENT = ('scheduler-architecture.md', 'ui-api-mapping.md',
               'architecture.md', 'SESSION-LEDGER.md', 'deprecated.md')

    @pytest.mark.parametrize('name', CURRENT)
    def test_has_status_header(self, name):
        p = DOCS / name
        assert p.is_file(), f'缺 {name}'
        head = '\n'.join(_read_lines(p)[:18])
        assert '状态' in head, f'{name} 头部没声明「状态」'
        assert ('冲突时以' in head or '当前状态请看' in head
                or '为准' in head), (
            f'{name} 头部没写清「冲突时以谁为准」—— 这正是"三份文档同时自称'
            f'唯一权威"的根因')

    def test_only_one_claims_scheduler_authority(self):
        """★ 调度域只能有**一处**自称权威。

        审计发现 `architecture.md` / `SESSION-LEDGER.md` /
        `scheduler-architecture.md` **同时**自称"唯一权威" -> 必然漂移。
        """
        claims = []
        for name in self.CURRENT:
            # ★ 只认**「状态」那一行**里的权威声明。
            #
            # 其它行提到"XX 是唯一权威"往往只是**指针** —— 例如
            # `architecture.md` 写"冲突时以 scheduler-architecture.md 为准
            # （调度域唯一权威是它）" —— 那是**合法**的, 不该判成
            # "它自称权威"。
            # ★ 我第一版扫**整个头部** -> `architecture.md` 被**误判**。
            for line in _read_lines(DOCS / name)[:18]:
                if '状态' not in line:
                    continue
                if ('调度域唯一权威' in line or '设计的唯一权威' in line):
                    claims.append(name)
                    break
        assert claims == ['scheduler-architecture.md'], (
            f'调度域权威声明不唯一: {claims}（应只有 scheduler-architecture.md）')
