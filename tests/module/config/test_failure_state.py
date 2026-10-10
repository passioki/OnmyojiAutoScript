# -*- coding: utf-8 -*-
"""连续失败记录与冷却（`module/config/failure_state.py`）的测试。

## 这些测试守的是什么

真实运行日志里读出来的 bug: `script.py` 原先在任务连续失败 3 次时
**`exit(1)` 退出整个子进程**，而 `failure_record` 是内存字典 ——
进程一退出服务器就重新拉起一个，**计数归零**，于是:

    失败 3 次 -> exit -> 重启 -> 计数归零 -> 又能失败 3 次 -> 再重启 -> ...

**永远停不下来。** 一次 7 小时的运行有 97 次 `START` 块（90+ 次重启），
`RyouToppa` 被派发 25 次一次都没打成。

所以本文件重点守三条:

1. **落盘** —— 计数跨进程重启不丢（这是根治点）
2. **不退出** —— 到阈值是"冷却"，不是"进程死"
3. **能自愈** —— 成功清零；冷却到期后计数减半，而不是永久拉黑
"""
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    """把状态文件指到临时目录（不要 chdir —— Windows 会占用失败）。"""
    from module.config import failure_state
    monkeypatch.setattr(failure_state, '_state_file',
                        lambda: tmp_path / '.failure_state.json',
                        raising=True)
    return tmp_path / '.failure_state.json'


class TestCounting:
    def test_starts_at_zero(self, store):
        from module.config import failure_state
        assert failure_state.failure_count('acc', 'Orochi') == 0
        assert failure_state.in_cooldown('acc', 'Orochi') is False

    def test_failures_accumulate(self, store):
        from module.config import failure_state
        r1 = failure_state.record_failure('acc', 'Orochi')
        assert r1['count'] == 1
        assert r1['just_cooled'] is False
        r2 = failure_state.record_failure('acc', 'Orochi')
        assert r2['count'] == 2
        assert r2['just_cooled'] is False
        assert failure_state.failure_count('acc', 'Orochi') == 2

    def test_threshold_triggers_cooldown(self, store):
        """★ 到阈值 -> **冷却**（不是退出进程）。"""
        from module.config import failure_state
        for _ in range(2):
            failure_state.record_failure('acc', 'Orochi')
        r3 = failure_state.record_failure('acc', 'Orochi')

        assert r3['just_cooled'] is True, '第 3 次应该进入冷却'
        assert r3['should_notify'] is True, '进入冷却时要通知'
        assert r3['cooldown_until'] is not None
        assert failure_state.in_cooldown('acc', 'Orochi') is True

    def test_threshold_cooldown_zeroes_the_count(self, store):
        """
        ★★ 实机验收修复: 到阈值冷却时计数**归零**, **不再"减半"** ★★

        ## 为什么改（用户原话）

        > "契灵之境运行失败后的冷却状态**应该只在连续运行时生效**"

        **原来的"减半"与"连续"语义不符** —— 它把**上一轮的失败**计入下一轮:
          * `threshold=3`, 第 3 次失败 -> 冷却, `count = 3 // 2 = **1**`
          * 冷却结束 -> 用户重新跑 -> **再失败 2 次**就又冷却
          * ★ 实测用户状态文件里正是 **`count: 1` + 冷却中** ——
            用户看到的是"我**才失败一次**怎么就冷却了"

        ★ 冷却 = "这串连续失败已经处理过了"。冷却**结束后重新开始数**,
          才是"连续"该有的语义。
        """
        from module.config import failure_state
        for _ in range(3):
            failure_state.record_failure('acc', 'Orochi')
        # 3 -> 冷却时存 **0**（上一轮的失败不带到下一轮）
        assert failure_state.failure_count('acc', 'Orochi') == 0
        # ★ 冷却**仍然在**（清计数 ≠ 解除冷却）
        assert failure_state.in_cooldown('acc', 'Orochi') is True
        # ★ 再失败 1 次不该立刻又冷却（要重新攒够 3 次）
        r = failure_state.record_failure('acc', 'Orochi')
        assert r['just_cooled'] is False
        assert failure_state.failure_count('acc', 'Orochi') == 1

    def test_notify_only_when_just_cooled(self, store):
        """通知**只在刚进入冷却那一次**触发, 不要每次都推。"""
        from module.config import failure_state
        for _ in range(3):
            failure_state.record_failure('acc', 'Orochi')
        # 冷却中再记一次失败（正常情况下调度器不会选中它, 但容错）
        r = failure_state.record_failure('acc', 'Orochi')
        assert r['should_notify'] is False

    def test_cooldown_remaining(self, store):
        from module.config import failure_state
        for _ in range(3):
            failure_state.record_failure('acc', 'Orochi',
                                         cooldown_minutes=30)
        left = failure_state.cooldown_remaining_minutes('acc', 'Orochi')
        assert 28 <= left <= 30, f'约 30 分钟, 实际 {left}'

    def test_custom_threshold_and_cooldown(self, store):
        from module.config import failure_state
        r = failure_state.record_failure('acc', 'Orochi',
                                         threshold=1, cooldown_minutes=5)
        assert r['just_cooled'] is True
        assert 4 <= failure_state.cooldown_remaining_minutes('acc', 'Orochi') <= 5


class TestSelfHealing:
    """★ 「自愈」—— 临时性故障过去之后要能完全恢复。"""

    def test_success_clears_everything(self, store):
        from module.config import failure_state
        for _ in range(3):
            failure_state.record_failure('acc', 'Orochi')
        assert failure_state.in_cooldown('acc', 'Orochi') is True

        failure_state.record_success('acc', 'Orochi')
        assert failure_state.failure_count('acc', 'Orochi') == 0
        assert failure_state.in_cooldown('acc', 'Orochi') is False, \
            '成功必须同时解除冷却'

    def test_success_on_clean_state_is_noop(self, store):
        from module.config import failure_state
        failure_state.record_success('acc', 'Orochi')   # 不该抛
        assert failure_state.failure_count('acc', 'Orochi') == 0

    def test_expired_cooldown_is_not_in_cooldown(self, store):
        """★ 冷却到期后**允许再试** —— 这是"不永久拉黑"的关键。"""
        from module.config import failure_state
        past = datetime.now() - timedelta(hours=2)
        failure_state.record_failure('acc', 'Orochi', threshold=1,
                                     cooldown_minutes=1, now=past)
        # 1 分钟冷却 + 2 小时前 -> 早就过期了
        assert failure_state.in_cooldown('acc', 'Orochi') is False
        assert failure_state.cooldown_remaining_minutes('acc', 'Orochi') == 0

    def test_can_fail_again_after_cooldown(self, store):
        """冷却到期后重新失败, 仍能正常累计。"""
        from module.config import failure_state
        past = datetime.now() - timedelta(hours=2)
        failure_state.record_failure('acc', 'Orochi', threshold=1,
                                     cooldown_minutes=1, now=past)
        r = failure_state.record_failure('acc', 'Orochi')
        assert r['count'] >= 1


class TestPersistence:
    def test_survives_reopen(self, store):
        """
        ★★ 核心: 计数**落盘**, 跨进程重启不丢。

        这就是"无限重启循环"的根治点 —— 改造前计数在内存里,
        进程一重启就归零。
        """
        import json
        from module.config import failure_state
        failure_state.record_failure('acc', 'Orochi')
        failure_state.record_failure('acc', 'Orochi')

        raw = json.loads(store.read_text(encoding='utf-8'))
        assert 'acc' in raw
        assert raw['acc']['orochi']['count'] == 2

    def test_cooldown_survives_reopen(self, store):
        """冷却也落盘 —— 否则重启就能绕过冷却。"""
        from module.config import failure_state
        for _ in range(3):
            failure_state.record_failure('acc', 'Orochi')
        raw = store.read_text(encoding='utf-8')
        assert 'cooldown_until' in raw

    def test_accounts_isolated(self, store):
        from module.config import failure_state
        failure_state.record_failure('accA', 'Orochi')
        assert failure_state.failure_count('accA', 'Orochi') == 1
        assert failure_state.failure_count('accB', 'Orochi') == 0

    def test_tasks_isolated(self, store):
        from module.config import failure_state
        failure_state.record_failure('acc', 'Orochi')
        assert failure_state.failure_count('acc', 'FallenSun') == 0

    def test_name_normalised(self, store):
        from module.config import failure_state
        failure_state.record_failure('acc', 'Orochi')
        assert failure_state.failure_count('acc', 'orochi') == 1

    def test_corrupt_file_does_not_crash(self, store):
        """文件坏了 -> 当作空, 且能自愈（最坏退化成改造前行为）。"""
        from module.config import failure_state
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text('{ not json', encoding='utf-8')
        assert failure_state.failure_count('acc', 'Orochi') == 0
        failure_state.record_failure('acc', 'Orochi')
        assert failure_state.failure_count('acc', 'Orochi') == 1

    def test_missing_file(self, store):
        from module.config import failure_state
        assert failure_state.failure_count('acc', 'Orochi') == 0
        assert failure_state.cooldown_until('acc', 'Orochi') is None
        assert failure_state.summarize('acc') == {}


class TestClear:
    def test_clear_one_task(self, store):
        from module.config import failure_state
        for _ in range(3):
            failure_state.record_failure('acc', 'Orochi')
        failure_state.record_failure('acc', 'FallenSun')
        failure_state.clear('acc', 'Orochi')
        assert failure_state.failure_count('acc', 'Orochi') == 0
        assert failure_state.in_cooldown('acc', 'Orochi') is False, \
            '清除失败必须同时解除冷却（用户"我修好了, 让我重试"）'
        assert failure_state.failure_count('acc', 'FallenSun') == 1

    def test_clear_account(self, store):
        from module.config import failure_state
        failure_state.record_failure('accA', 'Orochi')
        failure_state.record_failure('accB', 'Orochi')
        failure_state.clear('accA')
        assert failure_state.failure_count('accA', 'Orochi') == 0
        assert failure_state.failure_count('accB', 'Orochi') == 1


class TestSummarize:
    def test_only_lists_problem_tasks(self, store):
        from module.config import failure_state
        failure_state.record_failure('acc', 'Orochi')
        failure_state.record_failure('acc', 'FallenSun')
        failure_state.record_success('acc', 'FallenSun')
        s = failure_state.summarize('acc')
        assert 'orochi' in s
        assert 'fallensun' not in s, '成功过的任务不该出现在问题列表里'

    def test_summary_shape(self, store):
        from module.config import failure_state
        for _ in range(3):
            failure_state.record_failure('acc', 'Orochi')
        s = failure_state.summarize('acc')['orochi']
        # ★ 实机验收修复: 冷却时计数**归零**（原来断言 `>= 1`, 那是"减半"时代的）
        assert s['count'] == 0
        assert s['cooldown_until'] is not None
        assert s['cooldown_minutes'] >= 1


class TestScriptNoLongerExits:
    """
    ★★ 源码级守卫: `script.py` 的失败分支**不再** `exit()` ★★

    这条是**行为回归守卫** —— 如果以后有人把"失败 3 次就退出进程"
    改回来, 这里立刻红。
    """

    @staticmethod
    def _failure_block() -> str:
        """
        取出 `script.py` 里失败记录那一段**代码**（不含注释）。

        ⚠ 锚点必须选**唯一**且**不在注释里**的串。
        第一版我用 `'失败记录：落盘 + 冷却'` 当锚点, 结果它命中的是
        **注释行**（"---- 失败记录：落盘 + 冷却（**不再 exit(1)**）----"）,
        于是截取区间里带上了那个 `exit(1)` 说明, 断言误报。
        """
        from pathlib import Path
        # 本文件在 `tests/module/config/` -> 上 3 层才是仓库根
        src = Path(__file__).resolve().parents[3] / 'script.py'
        text = src.read_text(encoding='utf-8')
        anchor = 'from module.config import failure_state\n'
        i = text.find(anchor)
        assert i > 0, '找不到失败记录分支（被改名了?）'
        blk = text[i:i + 2600]
        # 剥掉行注释 —— 注释里会提到历史行为（"不再 exit(1)"）
        return '\n'.join(l for l in blk.split('\n')
                         if not l.strip().startswith('#'))

    def test_uses_failure_state(self):
        assert 'failure_state' in self._failure_block()

    def test_does_not_exit_process(self):
        code = self._failure_block()
        assert 'exit(1)' not in code, \
            '失败分支不该再退出进程 —— 那会造成无限重启循环'
        assert 'exit(-1)' not in code
        assert 'sys.exit' not in code

    def test_records_success_and_failure(self):
        blk = self._failure_block()
        assert 'record_success' in blk
        assert 'record_failure' in blk
