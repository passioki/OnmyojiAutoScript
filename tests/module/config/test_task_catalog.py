# -*- coding: utf-8 -*-
"""任务元数据目录(module/config/task_catalog)的测试。

为什么需要这个模块
------------------
OAS 里"打满 N 次就停"的字段**命名极不统一**:

    limit_count / minions_cnt / hya_limit_count / number_attack / 硬编码 30

于是任何"想统一展示或修改次数"的地方(总览页、任务列表、API)都得自己判断,
每处都要重新踩坑。`task_catalog` 把这份知识集中一处。

这些用例同时是**回归护栏**: 2026-10-08 曾多次因"凭印象写任务信息"而出错
(把 HeroTest 写成"英雄测试"、AbyssShadows 写成"御魂·深渊"、
Sougenbi 写成"真八岐大蛇"、RealmRaid 写成"阴界之门"),
下面把这些具体事实固化下来。
"""
import pytest

from module.config import task_catalog as TC
from module.config.task_catalog import Category


class TestNames:
    """中文名必须来自权威来源(OASX i18n), 不得凭印象。"""

    @pytest.mark.parametrize('task,expected', [
        ('FallenSun', '日轮之陨'),
        ('Orochi', '八岐大蛇'),
        ('EvoZone', '觉醒副本'),          # 曾误写为"御魂副本"
        ('Sougenbi', '业原火'),           # 曾误写为"真八岐大蛇"
        ('HeroTest', '英杰试炼'),         # 曾误写为"英雄测试"(编造)
        ('AbyssShadows', '狭间暗域'),     # 曾误写为"御魂·深渊"(编造)
        ('RealmRaid', '个人突破'),        # 曾误写为"阴界之门"
        ('RyouToppa', '寮突破'),          # 曾误写为"突破"
        ('SixRealms', '六道之门'),
        ('OtherWorldTwilight', '彼世逢魔'),
        ('Exploration', '探索'),
        ('GoldYoukai', '金币妖怪'),
        ('Tako', '石距'),
        ('MetaDemon', '超鬼王'),
    ])
    def test_authoritative_chinese_names(self, task, expected):
        assert TC.get(task).name_zh == expected

    def test_all_tasks_have_chinese_name(self):
        missing = [t for t, n in TC.all_names().items() if not n]
        assert missing == [], f'这些任务缺中文名: {missing}'

    def test_task_catalog_is_same_source_as_tasks_dir(self):
        """★★★ catalog 看到的任务集 == `tasks/` 里有 `meta.py` 的目录集 ★★★

        ## ★ [10-15] B 方案（用户裁定"好的"）

        原名 `test_task_count`，里面写死 `len(TC.all_tasks()) == 56`
        —— ★ 每新建一个任务都要改这个数字（`PENDING-LEDGER.md` §D.9）。

        ★★ 数字没有信息量；真正的不变量是 **"catalog 与磁盘同源"**：
        ★ 收益 = 新增任务 **零改动**；而"某个 `meta.py` 没被发现 /
          目录名与类名对不上"**仍然立刻变红**。
        """
        import pathlib
        tasks_dir = pathlib.Path(TC.__file__).resolve().parents[2] / 'tasks'
        on_disk = {d.name for d in tasks_dir.iterdir()
                   if d.is_dir() and (d / 'meta.py').is_file()}
        assert set(TC.all_tasks()) == on_disk, (
            f'catalog 与 tasks/ **不同源**: '
            f'只在 catalog {sorted(set(TC.all_tasks()) - on_disk)} · '
            f'只在磁盘 {sorted(on_disk - set(TC.all_tasks()))}')


class TestCategories:
    """分类依据是游戏机制, 不是 OAS 内部实现。"""

    def test_fixed_tasks(self):
        fixed = {m.task for m in TC.by_category(Category.FIXED)}
        assert 'Exploration' in fixed, '用户明确: 探索也是固定任务'
        assert 'HeroTest' in fixed, '用户明确: 英杰试炼是固定任务'
        # ★ [10-15] B 方案：**删掉 `len(fixed) == 13`**（写死 ⇒ 新增任务返工）
        #   ⇒ 数量改由"同源"断言保证：见 test_categories_partition_all_tasks
        #     （每类数量 = by_category 的实际大小）+ test_summary_totals（自洽）。

    def test_categories_partition_all_tasks(self):
        """★★★ `Category` 各值必须构成**全体任务的一个划分** ★★★

        ## ★ [10-15] B 方案（用户裁定"好的"）

        原来靠"写死 `fixed == 13` / `total == 56`"来守分类 —— ★ 每新增任务
        都要改。★ 真正的不变量是：**每个任务恰好属于一个 category**
        （互斥 + 完备 + 无重复），★ 且各类大小之和 = 全体。
        """
        all_tasks = set(TC.all_tasks())
        seen: dict[str, set[str]] = {}
        for c in Category:
            members = {m.task for m in TC.by_category(c)}
            # ① 类内不许重复（by_category 返回列表 ⇒ 可能重复）
            assert len(members) == len([m.task for m in TC.by_category(c)]), (
                f'{c.value} 里有重复任务')
            # ② 类间必须互斥
            for other, prev in seen.items():
                overlap = members & prev
                assert not overlap, (
                    f'★ {c.value} 与 {other} 有交集（分类不是划分）: {sorted(overlap)}')
            seen[c.value] = members
        # ③ 必须完备：并集 = 全体
        union = set().union(*seen.values())
        assert union == all_tasks, (
            f'分类不完备: 没被任何 category 覆盖 {sorted(all_tasks - union)} · '
            f'多出非任务 {sorted(union - all_tasks)}')

    def test_timed_tasks(self):
        """★ S5: 原来叫 `test_charge_tasks` 并断言 `Category.CHARGE`。
        `Category.CHARGE` **已删除**（用户裁定去掉存量机制）, 这 3 个任务
        （都靠**窗口**表达"一天几个时段各跑一次"）改判为 **`timed`**。
        """
        timed = {m.task for m in TC.by_category(Category.TIMED)}
        assert {'GoldYoukai', 'ExperienceYoukai', 'Tako'} <= timed

    def test_toppa_is_breakthrough_subcategory(self):
        """寮突破 + 个人突破 = 结界突破的两个子分类(用户确认)。"""
        toppa = {m.task for m in TC.by_category(Category.TOPPA)}
        assert toppa == {'RyouToppa', 'RealmRaid'}

    def test_limited_activities(self):
        """用户列出的 8 个限时活动(隔一段时间才推出, 非常驻)。"""
        limited = {m.task for m in TC.by_category(Category.LIMITED)}
        assert limited == {
            'ActivityShikigami', 'MetaDemon', 'FrogBoss', 'FloatParade',
            'Quiz', 'KittyShop', 'DyeTrials', 'BudokaiTournament',
        }

    def test_summary_totals(self):
        """★★★ `summary()` 必须与 `by_category` / `all_tasks()` **自洽** ★★★

        ## ★ [10-15] B 方案（用户裁定"好的"）：**不再写死 56 / 13 / 2 / 8**

        ★ 原来 `s['total'] == 56` / `s['fixed'] == 13` / `s['toppa'] == 2` /
        `s['limited'] == 8` —— ★ 每新增任务都要回来改（`§D.9`）。
        ★ 改成**同一批数据的两种算法必须一致**（★ 这才是真守卫：
          `summary()` 与 `by_category()` 若有一天算法漂移，立刻红）。
        ★ 语义钉子（toppa = 2 个具体任务名）由 `test_toppa_is_breakthrough_subcategory`
          与 `test_limited_activities` **以集合形式**钉住，不需要这里再钉数量。
        """
        s = TC.summary()
        assert s['total'] == len(TC.all_tasks()), (
            f"summary.total={s['total']} ≠ all_tasks()={len(TC.all_tasks())}")
        for c in Category:
            n = len({m.task for m in TC.by_category(c)})
            assert s[c.value] == n, (
                f"summary['{c.value}']={s[c.value]} ≠ by_category 实际 {n}")
        assert sum(s[c.value] for c in Category) == s['total'], (
            '各类之和 ≠ total（summary 自己就不自洽）')


class TestCountFieldAdaptation:
    """核心接口: 上层只认 limit_count, 别名由本模块适配。"""

    @pytest.mark.parametrize('task,native,unified', [
        ('FallenSun', 'limit_count', 'limit_count'),
        # ★★ 片 1: 这两个别名也**已统一**（次数只在 `scheduler.target`,
        #   原配置字段 `minions_cnt` / `hya_limit_count` **已删除**）★★
        ('Exploration', 'limit_count', 'limit_count'),
        ('Hyakkiyakou', 'limit_count', 'limit_count'),
        # ★★ RealmRaid **已统一**（本次改动）★★
        # 原 `('RealmRaid', 'number_attack', 'limit_count')` ——
        #   审计证实 `number_attack` 是**死字段**（全仓 0 处读配置值），
        #   已改名为 `limit_count`（带 `validation_alias` 接受旧键）。
        ('RealmRaid', 'limit_count', 'limit_count'),
    ])
    def test_native_and_unified_field(self, task, native, unified):
        m = TC.get(task)
        assert m.count_field == native
        assert TC.target_field(task) == unified

    @pytest.mark.parametrize('task', ['GoldYoukai', 'ExperienceYoukai',
                                      'Tako', 'AreaBoss', 'Duel'])
    def test_non_countable_tasks_have_no_target_field(self, task):
        assert TC.target_field(task) is None

    def test_wanted_quests_needs_new_field(self):
        """悬赏封印的 30 是硬编码在脚本里的, 用户改不了 —— 待新增字段。"""
        m = TC.get('WantedQuests')
        assert m.category == Category.FIXED
        assert m.count_field is None
        assert m.countable is False

    def test_needs_unify_list(self):
        # ★★ 片 1 收尾: **全部统一，列表应为空** ★★
        # 14 个任务配置里的次数字段（`limit_count` / `minions_cnt` /
        # `hya_limit_count` / `number_attack`）**已全部删除**,
        # 次数只住在 `scheduler.target` / `RunEntry.target`。
        assert sorted(m.task for m in TC.needs_unify_tasks()) == []


class TestCountable:
    def test_countable_includes_fixed_and_toppa(self):
        assert TC.get('FallenSun').countable is True
        assert TC.get('Exploration').countable is True
        assert TC.get('RyouToppa').countable is True
        assert TC.get('RealmRaid').countable is True

    def test_countable_excludes_charge_limited_timed(self):
        assert TC.get('GoldYoukai').countable is False
        assert TC.get('MetaDemon').countable is False
        assert TC.get('AreaBoss').countable is False

    def test_countable_count(self):
        """★ `countable_tasks()` 必须与 `meta.countable` **同源**。

        ## ★ [10-15] B 方案（用户裁定"好的"）：**不再写死 14**

        ★ 原来 `assert len(TC.countable_tasks()) == 14`（注释还写着
        "13 固定 + 2 结界突破 - 1(悬赏封印暂无字段)"）—— ★ 新增任务就返工。
        ★ 改成：两个入口（`countable_tasks()` 与 `all_meta()` 的 `countable`）
          **必须给出同一批任务**（★ 算法漂移就红）。顺便钉住
          "`countable` 的任务数 > 0"（防空集通过）。
        """
        from_meta = {m.task for m in TC.all_meta() if m.countable}
        from_api = {m.task for m in TC.countable_tasks()}
        assert from_api == from_meta, (
            f'countable_tasks() 与 meta.countable 不同源: '
            f'只在 api {sorted(from_api - from_meta)} · '
            f'只在 meta {sorted(from_meta - from_api)}')
        assert from_api, '一个 countable 任务都没有（判据坏了）'


class TestUserConfigDerivedParams:
    """★ S5: 原 `TestChargeParams.test_gold_youkai` 断言 `has_charge` /
    `charge_max` / `charge_slots` / `charge_consume` —— 这些字段**已删除**
    （用户裁定去掉存量机制）, 该测试已删。仅保留**用户配置推导**的这条。
    """

    def test_interval_from_user_config(self):
        """充能周期取自用户真实配置, 而不是代码默认值。"""
        assert TC.get('GoldYoukai').success_interval == '00 03:00:00'
        assert TC.get('Hyakkiyakou').success_interval == '00 12:00:00'
        assert TC.get('Secret').success_interval == '07 00:00:00'


class TestRobustness:
    def test_unknown_task(self):
        assert TC.get('NoSuchTask') is None
        assert TC.get('') is None
        assert TC.get(None) is None
        assert TC.exists('NoSuchTask') is False

    def test_known_task_exists(self):
        assert TC.exists('FallenSun') is True

    def test_all_names_is_a_copy_not_internal_state(self):
        a = TC.all_names()
        a['FallenSun'] = 'tampered'
        assert TC.get('FallenSun').name_zh == '日轮之陨'

    def test_categories_filter_accepts_strings(self):
        """★ S5: 原来这里断言 `by_category('charge')` —— `Category.CHARGE`
        已删除（用户裁定去掉存量机制）, 改成断言 **`'timed'` 字符串可用**。
        """
        timed = {m.task for m in TC.by_category('timed')}
        assert 'GoldYoukai' in timed
        assert 'ExperienceYoukai' in timed
        assert 'Tako' in timed
