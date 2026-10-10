# -*- coding: utf-8 -*-
"""★★ 全局测试防护（审计修复）—— **防止测试写脏用户的实时配置** ★★

## 为什么必须有这个文件

审计发现: **4 个测试文件直接改用户实时配置**，而 `tests/` 下**原本没有
`conftest.py`** —— 没有任何全局快照/还原机制，全靠各文件自觉。

**实证后果**（2026-10-10）: `config/恋鸟树.json` 的 `run_list` 被
`tests/module/config/test_entry_id.py` 覆盖成**两条 `entry_id` 完全相同**的
`RealmRaid` —— 既**丢了用户编排**, 又**在实时配置里破坏了 E2 不变量**
（`entry_id` 必须唯一）。而 `恋鸟树.json` **从未被 git 跟踪** -> **无法恢复**。

这是本项目**第 5 次**同类事故（前 4 次见 `docs/SESSION-LEDGER.md` §26/§29/§34）。
所以这次做**机制性**防护, 而不是再靠"记得还原"。

## 做什么

`autouse=True` 的 **session 级** fixture:
1. 会话开始: 把 `config/*.json`（**排除 `template.json`**）**整份快照到内存**
2. 会话结束: **逐字节比对**; 有变化就**还原**并**大声报警**（不是静默还原）
3. **额外**: 检查每个 `run_list` 里 `entry_id` 唯一（E2 不变量）, 发现重复就报警

★ **为什么还要报警而不是静默还原**:
  静默还原会让"测试在改真实配置"这件事**永远不被发现** —— 测试会继续
  依赖那个副作用（例如"先写再读"）, 而在别人机器上就挂。本项目一贯做法是
  "**让静默失败变成看得见**"（见 `build_run_list()` 的护栏注释）。

★ **为什么排除 `template.json`**:
  它是"新账号模板"的**源头**; 某些测试有意用它生成配置。审计确认它**已有个
  被测试改过的指纹**（`run_list: []` 等）, 但那是**期望值**而非污染 ——
  排除它可避免误报。
"""
import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO / 'config'

#: 这些文件**不**参与快照（有意允许测试改）
_EXEMPT = {'template.json'}


def _config_files():
    if not CONFIG_DIR.is_dir():
        return []
    return sorted(p for p in CONFIG_DIR.glob('*.json')
                  if p.name not in _EXEMPT)


def _check_entry_ids(path: Path) -> list:
    """E2 不变量: 同一个 `run_list` 里 `entry_id` 必须**唯一**。

    :return: 违规描述列表（空 = 通过）
    """
    bad = []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        rl = ((data.get('script') or {}).get('optimization') or {}
              ).get('run_list') or []
        seen = {}
        for i, e in enumerate(rl):
            if not isinstance(e, dict):
                continue
            eid = e.get('entry_id')
            if not eid:
                continue
            if eid in seen:
                bad.append(
                    f'{path.name}: run_list[{seen[eid]}] 与 [{i}] 的 '
                    f'entry_id 相同 ({eid!r}) —— 破坏 E2 不变量；'
                    f' 多半是测试用 `RunList([...])` 构造后直接 save')
            else:
                seen[eid] = i
    except Exception as exc:
        bad.append(f'{path.name}: 解析失败 {type(exc).__name__}: {exc}')
    return bad


def _snapshot(files) -> dict:
    out = {}
    for p in files:
        try:
            out[p] = p.read_bytes()
        except OSError:
            pass
    return out


def _restore(snapshot: dict) -> list:
    """把 `snapshot` 里的内容写回磁盘; 返回**被还原**的文件列表。"""
    changed = []
    for p, before in snapshot.items():
        try:
            if p.read_bytes() != before:
                p.write_bytes(before)
                changed.append(p)
        except OSError:
            pass
    return changed


#: 每测试级记录"本会话已被污染（且已还原）的文件" -> 会话末汇总报告
_POLLUTED = set()


@pytest.fixture(autouse=True)
def _guard_live_config_per_test():
    """★★ 第二轮复审（待办 #1）: **每测试级**快照 -> 还原。

    ## 为什么在 session 级之外**还要**加这一层

    session 级只在**会话结束**比对/还原。如果测试在**中途**改了配置:
      * 会话内**后续测试**看到的就是**被污染**的配置 ->
        **顺序相关的偶发失败**（实测踩过好几次）
      * 脚本被 **Ctrl-C / 硬杀 / `os._exit`** -> session 的 finalizer
        **跑不到** -> 污染**留在磁盘上**

    ★ 每测试级把窗口收窄到"**单个测试**": 它跑完立刻还原, 于是
      下一个测试总是从**干净**的配置开始。

    ★ **不做**"把 `config/` 整个重定向到 `tmp_path`"那种彻底隔离 ——
      因为 `write_json` 用 `Path.cwd()`, 那需要 `os.chdir(tmp)` +
      在 tmp 里造一份 `config/`（还牵扯 `tasks/` 的导入路径）,
      而**很多测试有意读真实配置的现值**（`live` fixture）。收益不抵风险。
      本层 + session 层各管一段, 已经覆盖实测到的**全部**事故形态。
    """
    files = _config_files()
    before = _snapshot(files)
    yield
    changed = _restore(before)
    if changed:
        names = ', '.join(p.name for p in changed)
        _POLLUTED.update(p.name for p in changed)
        import warnings as _w
        _w.warn(
            f'★★★ 某个测试污染了用户实时配置 —— **已在测试结束时还原**: '
            f'{names} ★★★ 请修那个测试（应在 finally 里自己备份 + 还原; '
            f'正确范例: tests/module/config/test_queue_clear_and_settings.py）',
            UserWarning, stacklevel=1)


@pytest.fixture(scope='session', autouse=True)
def _guard_live_config():
    """会话级: 快照 -> 跑测试 -> 比对/还原/报警。"""
    files = _config_files()
    snapshot = _snapshot(files)

    # 进会话前先体检一次（也可能是上次跑测试留下的）
    pre_bad = []
    for p in files:
        pre_bad.extend(_check_entry_ids(p))

    yield

    # ---------- 会话结束: 比对 ----------
    changed = _restore(snapshot)

    post_bad = []
    for p in files:
        post_bad.extend(_check_entry_ids(p))

    if changed:
        names = ', '.join(p.name for p in changed)
        # ★★ 第二轮复审修复: **用 `warnings.warn` 让告警默认可见** ★★
        #
        # ## 原来的 bug（测试复审员实测）
        #
        # 原来只用 `print()` —— 而 **`pytest -q`（不加 `-s`）会捕获
        # stdout, 一个字都看不到**。也就是说默认跑法下, 这个"大声报警"
        # **退化成它自己 docstring 明令禁止的"静默还原"**。
        # ★ 复审员因此**复现不出**台账里反复写的"配置污染告警 ★ 无"。
        #
        # ★ 修法: 既 `print`（`-s` 时看得到全文）**也** `warnings.warn`
        #   —— pytest 会把 warning 收进 **warnings summary**,
        #   `-q` 下**照样显示**（且默认退出码不变, 不会把套件判红）。
        import warnings as _w
        _w.warn(
            f'★★★ 测试污染了用户实时配置 —— 已自动还原: {names} ★★★ '
            f'请修那个测试（应在 finally 里自己备份 + 还原; 正确范例: '
            f'tests/module/config/test_queue_clear_and_settings.py）',
            UserWarning, stacklevel=1)
        print('\n' + '=' * 72)
        print('★★★ 测试污染了用户实时配置 —— 已自动还原 ★★★')
        print(f'  被改的文件: {names}')
        print('  ★ 请修那个测试: 它应当在 `finally` 里自己备份 + 还原')
        print('    （正确范例: tests/module/config/test_queue_clear_and_settings.py）')
        print('=' * 72)

    if post_bad:
        # ★ 同样: 用 warning 保证默认可见（原来只 print -> 被吞掉）
        import warnings as _w
        _w.warn('★★★ E2 不变量告警（entry_id 必须唯一）★★★ '
                + ' / '.join(post_bad), UserWarning, stacklevel=1)
        print('\n★★★ E2 不变量告警（entry_id 必须唯一）★★★')
        for line in post_bad:
            print(f'  {line}')

    # ★★ 第二轮复审: **E2 体检必须能失败**（原来只 print, 不可失败）★★
    #
    # 复审员指出: `pre_bad`（进会话前的体检）**算完从未使用**, 而
    # `post_bad` 只 print —— 双向都"不可失败"。
    # ★ 这里对**会话结束时**的重复 `entry_id` 直接**判定失败**
    #   （它是数据损坏级问题: 两条条目共用一个 id -> 完成记忆会互相影响）。
    assert not post_bad, (
        'E2 不变量被破坏: `run_list` 里有**重复 entry_id**（同一 id 出现在'
        '两条条目上）—— 完成记忆会互相影响, 且"按 id 删"会一删全删。\n  '
        + '\n  '.join(post_bad)
        + '\n★ 这是**数据损坏**级问题; 若确实是某个测试造成的, 请修那个测试。')
