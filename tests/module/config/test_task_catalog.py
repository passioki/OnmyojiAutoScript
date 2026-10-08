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

    def test_task_count(self):
        assert len(TC.all_tasks()) == 54


class TestCategories:
    """分类依据是游戏机制, 不是 OAS 内部实现。"""

    def test_fixed_tasks(self):
        fixed = {m.task for m in TC.by_category(Category.FIXED)}
        assert 'Exploration' in fixed, '用户明确: 探索也是固定任务'
        assert 'HeroTest' in fixed, '用户明确: 英杰试炼是固定任务'
        assert len(fixed) == 13

    def test_charge_tasks(self):
        charge = {m.task for m in TC.by_category(Category.CHARGE)}
        assert charge == {'GoldYoukai', 'ExperienceYoukai', 'Tako'}

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
        s = TC.summary()
        assert s['total'] == 54
        assert s['fixed'] == 13
        assert s['charge'] == 3
        assert s['toppa'] == 2
        assert s['limited'] == 8
        assert sum(s[c.value] for c in Category) == 54


class TestCountFieldAdaptation:
    """核心接口: 上层只认 limit_count, 别名由本模块适配。"""

    @pytest.mark.parametrize('task,native,unified', [
        ('FallenSun', 'limit_count', 'limit_count'),
        ('Exploration', 'minions_cnt', 'limit_count'),
        ('Hyakkiyakou', 'hya_limit_count', 'limit_count'),
        ('RealmRaid', 'number_attack', 'limit_count'),
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
        assert sorted(m.task for m in TC.needs_unify_tasks()) == [
            'Exploration', 'Hyakkiyakou', 'RealmRaid']


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
        # 13 固定 + 2 结界突破 - 1(悬赏封印暂无字段) = 14
        assert len(TC.countable_tasks()) == 14


class TestChargeParams:
    def test_gold_youkai(self):
        m = TC.get('GoldYoukai')
        assert m.has_charge is True
        assert m.charge_max == 2
        assert m.charge_slots == '0,12', '默认值里的逗号不能被正则截断'
        assert m.charge_consume == 1

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
        assert {m.task for m in TC.by_category('charge')} == {
            'GoldYoukai', 'ExperienceYoukai', 'Tako'}
