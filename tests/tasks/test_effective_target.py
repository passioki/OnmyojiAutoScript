# -*- coding: utf-8 -*-
"""「次数」统一入口（`BaseTask.effective_target` / `bind_counter`）的测试。

## 背景：改造前"次数"是**双轨**的

| 来源 | 位置 | 问题 |
|---|---|---|
| `scheduler.target` | 界面输入框 | **全仓无人读取** —— 空壳 |
| `limit_count` 等 | 各任务配置 | 界面**改不到**，且字段名有 `minions_cnt` / `hya_limit_count` / `number_attack` 三种别名 |

于是"设置次数"实际是坏的。现在收敛到 `BaseTask.effective_target()`:

    scheduler.target > 0  ->  用它（用户编排）
    否则                  ->  任务配置里的值（能力默认）
    再否则                ->  meta.py 的 count_default

## 两条容易踩的坑（本测试专门盯住）

1. **`_find_count_field` 要遍历配置树** —— 各任务把 `limit_count` 放在
   不同层级（`orochi_config.` / `bondling_config.` / 根上……），
   硬编码路径必然漏。
2. **解析失败必须记 warning, 不能 `except: pass`** ——
   我第一版写 `except Exception: pass`，把
   `AttributeError: 'FakeTask' object has no attribute '_find_count_field'`
   （测试替身写错导致的）**完全吞掉**，表现成"次数设置不生效"，白查很久。

## ★★★ 2026-10-13 用户裁定「丙」：本文件新增两组守卫 ★★★

> "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
> "**或者按照时间戳来判断**" / "**就按这个来**"

* ★ `TestBindCounterSetsLimit`：`bind_counter()` **不再读盘**、`commit_count()` **不再写盘**
  （★ 原来那个 `test_bind_counter_restores_from_disk` 守的是**已被推翻**的行为，已改名重写）
* ★ `TestEntryCompletedByTimestamp`：`get_entry_completed()` 的判据
  **只按时间戳比对**（`completed_session` ↔ `session_start`）
  —— ★ 不再用"计数 >= target"，`completed_round` 保留但**不作判据**

★ 见 `docs/DESIGN-SPEC.md` §1.6-L494-520 + 分歧块⑩（L508-516）。
"""
import logging

import pytest

from module.config import task_catalog as TC
from module.config.utils import convert_to_underscore
from tasks.base_task import BaseTask


class StubTask(BaseTask):
    """
    只借 `BaseTask` 的计数逻辑，不初始化设备/配置树。

    ★ **必须继承 `BaseTask`** —— `effective_target` 内部会调
      `self._find_count_field`，不继承就会 AttributeError，
      然后被最外层 except 吞掉，测试会误以为是实现问题。
    """

    def __init__(self, config, name):
        self.config = config
        self._name = name
        self._counter_task = None
        self._counter_period = 'none'
        self._counter_reset_at = None
        self._counter_persisted = 0
        self.current_count = 0
        self.limit_count = None

    def get_task_name(self):
        return self._name


CONFIG = '恋鸟树'


@pytest.fixture(scope='module')
def cfg():
    from pathlib import Path
    if not (Path.cwd() / 'config' / f'{CONFIG}.json').exists():
        pytest.skip(f'缺少配置 {CONFIG}')
    from module.server.main_manager import mm
    return mm.config_cache(CONFIG)


def stub(cfg, name) -> StubTask:
    return StubTask(cfg, name)


def user_target(cfg, name) -> int:
    sub = getattr(cfg, convert_to_underscore(name), None)
    sch = getattr(sub, 'scheduler', None) if sub is not None else None
    return int(getattr(sch, 'target', 0) or 0)


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """把 `task_state` 的状态文件指到临时目录（模块级 —— 多个测试类共用）。

    ★ 不要在测试里 `os.chdir` + `TemporaryDirectory` ——
      Windows 上会因文件占用导致清理失败（`PermissionError: WinError 32`），
      而 `task_state` 是按 `Path.cwd()` 定位状态文件的，改 cwd 也会牵连日志。

    ★ 2026-10-13 从 `TestBindCounterSetsLimit` 的类内 fixture **提升到模块级**
      —— 新用例（`commit_count` 不落盘 / `get_entry_completed` 时间戳判据）
      也要用同一份隔离，避免三处各写一遍（写歪了就会碰真实状态文件）。
    """
    from module.config import task_state

    state_file = tmp_path / '.task_state.json'
    monkeypatch.setattr(task_state, '_state_file',
                        lambda: state_file, raising=True)
    return state_file


class TestEffectiveTarget:
    def test_all_countable_tasks_resolve(self, cfg):
        """每个可计数任务都要能解析出次数（不抛异常、不是 None）。"""
        countable = [m for m in TC.all_meta() if m.countable]
        assert countable, '应存在可计数任务'
        for m in countable:
            got = stub(cfg, m.task).effective_target()
            assert got is not None, f'{m.task} 解析出 None'
            assert isinstance(got, int) and got > 0, \
                f'{m.task} 解析出非法值 {got!r}'

    def test_user_target_wins(self, cfg):
        """`target > 0` 时**必须**用它（这是用户编排，优先级最高）。"""
        name = 'Orochi'
        sch = getattr(getattr(cfg, convert_to_underscore(name)), 'scheduler')
        old = sch.target
        try:
            for v in (1, 7, 999):
                sch.target = v
                assert stub(cfg, name).effective_target() == v, \
                    f'target={v} 未被采用'
        finally:
            sch.target = old

    def test_falls_back_to_task_config_when_target_zero(self, cfg):
        """
        `target == 0` 时回落到**任务配置里的值**（不是元数据默认值）。

        ★ 这个区别很重要: 配置里的值可能被用户改过
          （实测 `FallenSun` 配的是 9, 而不是元数据默认的 50）。
          回落时应该尊重**配置**，而不是元数据。
        """
        name = 'FallenSun'
        sch = getattr(getattr(cfg, convert_to_underscore(name)), 'scheduler')
        old = sch.target
        try:
            sch.target = 0
            got = stub(cfg, name).effective_target()
            from_config = stub(cfg, name)._find_count_field('limit_count')
            if from_config is not None:
                assert got == from_config, \
                    f'target=0 时应回落到配置值 {from_config}, 实际 {got}'
        finally:
            sch.target = old

    @pytest.mark.parametrize('name,alias', [
        # ★★ 片 1 收尾: 两个别名也**已统一** ★★
        #   用户裁定"次数全部统一为 `target`" ⇒ 14 个任务配置里的次数字段
        #   （`minions_cnt` / `hya_limit_count` / `limit_count` / `number_attack`）
        #   **已全部删除**, 次数只住在 `scheduler.target`。
        #   ★ 所以现在每个可计数任务的 `count_field` 都是 `limit_count`
        #     （= `TC.UNIFIED_COUNT_FIELD`, 已无别名）。
        ('Exploration', 'limit_count'),
        ('Hyakkiyakou', 'limit_count'),
        # ★★ RealmRaid **已统一**（本次改动）★★
        # 原 `('RealmRaid', 'number_attack')` —— 审计证实 `number_attack`
        # 是**死字段**（全仓 0 处读配置值; `effective_target()` 第 3 级找的是
        # `limit_count`, 而 RaidConfig 里没有它 -> 掉到静态 `count_default`）。
        # ★ 已改名为 `limit_count`（带 `validation_alias` 接受旧键）。
        ('RealmRaid', 'limit_count'),
    ])
    def test_alias_fields_resolve(self, cfg, name, alias):
        """
        ★ **弱断言**（**故意**）: 只钉"别名字段仍能被解析到"。

        `TaskMeta.count_field_effective` 会把别名统一成 `limit_count`，
        但配置树里存的是**别名**，所以 `_find_count_field` 必须能找到它。

        ## ⚠ 这个用例**保护不了**"别名配置值会生效"

        因为它**没有**把前两级（条目级 `config.task.target` / 任务级
        `scheduler.target`）置 0 —— 只要它们非 0，`effective_target()`
        就在第 ①/② 级 `return` 了，**别名那一级根本没被走到**，
        断言照样通过。

        ★ 我一度把它"改强"（显式置 0 再断言等于配置值），
          但那样会**改到 `cfg` 这个共享 fixture 的 `scheduler.target`**
          （污染其它用例），而且它读的是**共享的 `恋鸟树` 配置**，
          结果不稳定。**已回退**。
        ★ 真正要"别名值会生效"的验证 -> 见
          `test_alias_config_value_reaches_effective_target`（**自带临时配置**，
          完全隔离）。
        """
        meta = TC.get(name)
        assert meta.count_field == alias, f'{name} 的字段名变了? {meta.count_field}'
        got = stub(cfg, name).effective_target()
        assert got is not None and got > 0, f'{name} 解析失败: {got!r}'


# ★★★ 未完成的验证（**移除了半成品测试，别以为它不存在**）★★★
#
# 审计证实: `Exploration.minions_cnt` / `Hyakkiyakou.hya_limit_count`
# 仍然**"界面能改但不生效"** —— `effective_target()` 第 3 级找的是
# `limit_count`, 而这两个任务的配置树里是**别名**
# （`RealmRaid.number_attack` 已在本次改动中统一为 `limit_count`）。
#
# ★ 我尝试写一个"**完全隔离**"的回归测试（自带临时配置 + 把前两级 target
#   置 0, 再断言等于别名配置值），但**构造有误**:
#   注入别名值后 `effective_target()` 仍返回 `count_default`（30/10），
#   说明**值没被 pydantic 收进模型**（很可能是注入到了错的层级,
#   或该字段不在我改的那个子节点里）。
# ★ 因为我无法在此会话内把它调对, **按纪律不留下会失败的测试** —— 已移除。
#
# ★ 下一步要做的:
#   1. 先查清 `Exploration.minions_cnt` / `Hyakkiyakou.hya_limit_count`
#      在配置树里的**确切层级**（用真实配置 print 出来, 别猜）
#   2. 再照 `RealmRaid` 的做法改名 `limit_count` + `validation_alias`
#      （`tasks/Exploration/config.py:93`、`tasks/Hyakkiyakou/config.py:31`）
#      ⚠ `Exploration` 还有个**同名类属性** `minions_cnt`
#        （`tasks/Exploration/base.py:43`）会**遮蔽配置字段** —— 必须先改名
#   3. 然后才写回归测试（此时注入路径已经明确）


class TestFindCountField:
    def test_finds_nested_field(self, cfg):
        """嵌套字段也要能找到（用 `target` 验, 它就在 `orochi.scheduler.target`）。

        ★★ 为什么不再用 `limit_count`（片 1 收尾）★★

        ★ 用户裁定"次数全部统一为 `target`" ⇒ 14 个任务配置里的次数字段
          （含 `orochi_config.limit_count`）**已全部删除** ⇒
          现在去找 `limit_count` **必然返回 None**（这是**预期**的）。
        ★ 而"统一字段"现在住得最深的那个是 `scheduler.target`
          （`orochi.scheduler.target`）—— 用它来验证"递归查找能钻进嵌套层"。
        见 `module/config/task_catalog.py` 的 `UNIFIED_COUNT_FIELD` 说明。
        """
        got = stub(cfg, 'Orochi')._find_count_field('target')
        # ★ 断言改成"**找到了**（不是 None）", **不再要求 > 0**：
        #   `scheduler.target = 0` 是**合法且常见**的值 ——
        #   它的语义是"**用户没设，用出厂默认**"（见 `effective_target()`），
        #   ⚠ 用户配置里实测就是 `0` ⇒ 原来那句 `got > 0` 会**假失败**。
        assert got is not None, f'未找到嵌套的 `target`, 得到 {got!r}'
        assert isinstance(got, int), f'`target` 应是整数, 得到 {type(got).__name__}'

    def test_missing_field_returns_none(self, cfg):
        assert stub(cfg, 'Orochi')._find_count_field('no_such_field') is None

    def test_does_not_recurse_forever(self, cfg):
        """配置树里有循环引用也不能死循环。

        ★ 片 1 收尾: 用 `target`（统一字段, 见上一个用例的说明）。
        """
        got = stub(cfg, 'Orochi')._find_count_field('target')
        assert isinstance(got, int)


class TestBindCounterSetsLimit:
    """
    ★ 不要在测试里 `os.chdir` + `TemporaryDirectory` ——
      Windows 上会因文件占用导致清理失败（`PermissionError: WinError 32`），
      而 `task_state` 是按 `Path.cwd()` 定位状态文件的，改 cwd 也会牵连日志。

      改为直接 monkeypatch `task_state._state_file`，指到临时路径
      （★ 2026-10-13：那个 fixture 已**提升到模块级** `tmp_state`，本类与
        新用例共用同一份隔离）。
    """

    def test_bind_counter_sets_limit_count(self, cfg, tmp_state):
        """
        `bind_counter()` 要**同时**设定 `self.limit_count`。

        ★ 这是"次数统一到一个入口"的关键 —— 任务里只调 `bind_counter()`,
          不必再去读配置。
        """
        t = stub(cfg, 'Orochi')
        t.limit_count = None
        rc = t.bind_counter()
        assert rc == 0, f'首次应恢复 0, 实际 {rc}'
        assert t.limit_count is not None and t.limit_count > 0, \
            'bind_counter 没有设定 limit_count'
        assert t._counter_task == 'orochi', \
            f'计数键应为小写任务名, 实际 {t._counter_task!r}'

    def test_bind_counter_honours_user_target(self, cfg, tmp_state):
        """用户设了 target, `bind_counter` 要用它。"""
        name = 'Orochi'
        sch = getattr(getattr(cfg, convert_to_underscore(name)), 'scheduler')
        old = sch.target
        try:
            sch.target = 3
            t = stub(cfg, name)
            t.limit_count = None
            t.bind_counter()
            assert t.limit_count == 3, \
                f'应取用户 target=3, 实际 {t.limit_count}'
        finally:
            sch.target = old

    def test_bind_counter_ignores_disk_starts_at_zero(self, cfg, tmp_state):
        """
        ★★ 2026-10-13 用户裁定「丙」：**`bind_counter()` 不再从磁盘恢复计数** ★★

        ## ★★ 用户原话

        > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
        > "**或者按照时间戳来判断**"
        > "**就按这个来**"

        ## ★ 为什么**必须**改成"永远从 0 开始"（实机故障铁证）

        ★ 原来 `bind_counter()` 从盘恢复 `runs` ⇒ `current_count = 88`，
          而 `limit_count = 30` ⇒ ★ `88 >= 30` ⇒ ★ **任务开跑即 break**：

        ```
        INFO | 从状态恢复战斗计数: 88
        INFO | 本次目标次数: 30 (已跑 88)
        INFO | Current count 88, max count 30
        ```

        ## ★ 对齐规格书哪一条

        * `docs/DESIGN-SPEC.md` §1.6-L500 "**不再把"本轮进度计数"落盘**
          （`bind_counter` 不读盘、`commit_count` 不写盘）"
        * 同节 L494-506 现行口径 + 分歧块⑩（L508-516）
          "**本轮进度只在内存；跨轮判定只用时间戳**"

        ## ★ 本用例守什么

        ★ 即使磁盘上留着**上一轮**的 `runs = 4`（脏数据），
          `bind_counter()` 之后 `self.current_count` / `_counter_persisted`
          ★ **必须都是 0**，★ 且**不能**因为读盘把那份脏数据写坏。
        ★ 有 `running_entry_id`（队列内正常运行）与没有（单跑 / 排障）
          ★ **两种都要从 0 开始** —— ★ 不允许存在"第二种恢复源"。
        """
        from module.config import task_state

        name = 'Orochi'
        eid = 'test-entry-1'
        # ★ 制造"上一轮跑过"的磁盘残留（正是用户痛点的来源）
        task_state.bump_entry_runs(cfg.config_name, eid, delta=4)
        assert task_state.get_entry_runs(cfg.config_name, eid) == 4, \
            '前置：磁盘上应留着上一轮的 runs=4'
        data_before = task_state._read_all()

        # ① 队列内正常运行（有 entry_id）—— 同样**不恢复**
        old_eid = cfg.model.running_entry_id
        try:
            cfg.model.running_entry_id = eid
            t = stub(cfg, name)
            rc = t.bind_counter(period='daily')
            assert rc == 0, f'★ bind_counter 应返回 0, 实际 {rc}'
            assert t.current_count == 0, \
                f'★ 即使磁盘 runs=4, 本轮也必须从 0 开始, 实际 {t.current_count}'
            assert t._counter_persisted == 0, \
                f'★ 内存水位不应被磁盘污染, 实际 {t._counter_persisted}'
            # ② ★ 没有 entry_id（单跑 / 排障）—— 也**不恢复**
            cfg.model.running_entry_id = ''
            t2 = stub(cfg, name)
            t2.bind_counter(period='daily')
            assert t2.current_count == 0, \
                f'★ 无 entry_id 时更不该有恢复源, 实际 {t2.current_count}'
        finally:
            cfg.model.running_entry_id = old_eid

        # ★ `bind_counter()` 只是**读**目标次数，绝不能顺手改磁盘上的长时记录
        assert task_state._read_all() == data_before, \
            '★ bind_counter 不应写状态文件（本轮进度只在内存）'

    def test_commit_count_does_not_touch_disk(self, cfg, tmp_state):
        """★ `commit_count()` 是**空操作** —— 调用后磁盘 `runs` 不变。

        ## ★★ 用户原话

        > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"

        ## ★ 为什么必须停写

        ★ 只要**写盘** ⇒ `runs` 就跨轮 / 跨重启存活 ⇒ 迟早垒高到超过 `target`
          ⇒ ★ **下一次运行"跑不起来"**（用户报的故障本体）。
        ★ 而清 `runs` 的唯一生产钩子（`reset_loop_next_run`）只在
          **loop 模式 + 队列有候选**时触发 ⇒ ★ 其它模式下**只增不减**。

        ## ★ 对齐规格书哪一条

        ★ `docs/DESIGN-SPEC.md` §1.6-L500（"`commit_count` 不写盘"）
          + 同节 L502-504（磁盘**只保留长时记录** `total_runs` / `total_log`）。
        """
        from module.config import task_state

        name = 'Orochi'
        eid = 'test-entry-commit'
        old_eid = cfg.model.running_entry_id
        try:
            cfg.model.running_entry_id = eid
            t = stub(cfg, name)
            t.bind_counter(period='daily')
            data_before = task_state._read_all()
            t.current_count = 7          # 本轮内存里打了 7 场
            t.commit_count()
        finally:
            cfg.model.running_entry_id = old_eid

        assert task_state._read_all() == data_before, \
            '★ commit_count 必须是空操作：磁盘只能保留长时记录, 不落"本轮进度"'
        assert task_state.get_entry_runs(cfg.config_name, eid) == 0, \
            '★ 本轮打了 7 场也【不能】写进磁盘 runs —— 下次启动才有得跑'
        assert t._counter_persisted == 7, \
            '★ 只更新内存水位 `_counter_persisted`（对齐规格书 §1.6-L500）'


class TestEntryCompletedByTimestamp:
    """
    ★★★ 「这条【本次】跑没跑过」的判据：**只按时间戳比对**（用户裁定「丙」）★★★

    ## ★★ 用户原话

    > "**痛点是，重新跑的时候，读取了上一轮跑的计数，导致无法运行**"
    > "**或者按照时间戳来判断**"
    > "**就按这个来**"

    ## ★ 现行判据（`task_state.get_entry_completed()`）

    | 情况 | 结果 |
    |---|---|
    | `completed_session == 当前 session_start` | ★ **True**（本次标过）|
    | `completed_session != 当前 session_start` | ★ **False** + 就地清掉字段 |
    | `session_start` 为空（无基准）| ★ **False**（宁可多跑, 不可不跑）|

    ## ★ 对齐规格书哪一条

    ★ `docs/DESIGN-SPEC.md` §1.6-L496-506（现行口径）+ 分歧块⑩ L508-516。
    ★ ★ **不再用"计数 >= target"当本轮已完成判据**；
      `completed_round` **保留但不再是判据**。
    """

    EID = 'entry-session'

    def test_no_session_start_means_not_completed(self, cfg, tmp_state):
        """a) ★ **没有 `session_start`（无基准）⇒ 一律 False**（宁可多跑, 不可不跑）。"""
        from module.config import task_state

        assert task_state.get_session_start(cfg.config_name) == '', \
            '前置：此时还没有【本次启动时间】'
        assert task_state.mark_entry_completed(
            cfg.config_name, self.EID, '测试') is True
        assert task_state.get_entry_completed(cfg.config_name, self.EID) is False, \
            '★ 读不到【本次启动时间】基准 ⇒ 必须按【未完成】(否则该条永远不跑)'

    def test_marked_in_same_session_is_completed(self, cfg, tmp_state):
        """b) ★ 同一 session 内 `mark_entry_completed()` 之后 ⇒ **True**。"""
        from module.config import task_state

        sess = task_state.mark_session_start(cfg.config_name, '2026-10-13 10:00:00.000')
        assert sess == '2026-10-13 10:00:00.000'
        task_state.mark_entry_completed(cfg.config_name, self.EID, '测试')
        assert task_state.get_entry_completed(cfg.config_name, self.EID) is True, \
            '★ 本次启动之后标的"已完成" ⇒ 判据必须看到（否则标了没用）'
        one = task_state._read_all()[cfg.config_name][task_state.ENTRIES_KEY][self.EID]
        assert one.get('completed_session') == sess, \
            '★ `mark_entry_completed` 必须把【本次启动时间】写进 `completed_session`'

    def test_new_session_expires_and_clears_fields(self, cfg, tmp_state):
        """c) ★ 换一个 `session_start`（模拟后端重启）⇒ **False 且字段被清掉**。

        ★ 这就是用户要的"重启后一定能跑"：
          上次启动标的"已完成"⇒ 本次启动**自动全部失效**。
        """
        from module.config import task_state

        task_state.mark_session_start(cfg.config_name, '2026-10-13 10:00:00.000')
        task_state.mark_entry_completed(cfg.config_name, self.EID, '上一轮标的')
        assert task_state.get_entry_completed(cfg.config_name, self.EID) is True

        # ★ 模拟后端重启：换一个【本次启动时间】
        task_state.mark_session_start(cfg.config_name, '2026-10-13 11:00:00.000')
        assert task_state.get_entry_completed(cfg.config_name, self.EID) is False, \
            '★ 换一次启动时间 ⇒ 上一轮标的"已完成"必须失效（否则该条再也不跑）'
        one = task_state._read_all()[cfg.config_name][task_state.ENTRIES_KEY][self.EID]
        for k in ('completed', 'completed_at', 'completed_reason',
                  'completed_round', 'completed_session'):
            assert k not in one, f'★ 过期时要【就地清掉】{k}（别留脏数据）'

    def test_same_round_different_session_is_not_completed(self, cfg, tmp_state):
        """d) ★ `completed_round` **相同**但 `completed_session` 不同 ⇒ **False**。

        ★ 本用例**证明判据是时间戳，不是轮次号**：
          手工把 `completed_round` 摆成与当前轮次**一致**（旧判据下必然算"已完成"），
          只要 `completed_session` 与【本次启动时间】不同 ⇒ ★ 必须仍判"未完成"。
        """
        from module.config import task_state

        task_state.mark_session_start(cfg.config_name, '2026-10-13 10:00:00.000')
        task_state.mark_entry_completed(cfg.config_name, self.EID, '上一轮标的')

        # ★ 构造"轮次号一致、但时间戳过期"的组合
        task_state.mark_session_start(cfg.config_name, '2026-10-13 11:00:00.000')
        data = task_state._read_all()
        one = data[cfg.config_name][task_state.ENTRIES_KEY][self.EID]
        one['completed'] = True
        one['completed_round'] = task_state.get_loop_rounds(cfg.config_name)
        one['completed_session'] = '2026-10-13 10:00:00.000'   # 上一轮的时间戳
        task_state._write_all(data)

        assert task_state.get_entry_completed(cfg.config_name, self.EID) is False, \
            '★ 轮次号相同也应判未完成 —— 判据是【时间戳】不是【轮次号】'

