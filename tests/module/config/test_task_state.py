"""
定时任务"完成记忆"(period)的测试。

背景
----
原先调度器只有 next_run + success_interval, 它回答"下次什么时候跑", 却不记录
"本周期到底做成没有"。于是想表达"每天只做一次"只能靠手工设 success_interval,
一旦任务中途失败语义就失真。

本功能为 Scheduler 增加:
    period   : none / daily / weekly
    reset_at : 游戏重置时间(周期边界), 默认 05:00
并记录每个任务在其周期内是否已成功完成。

关键保证:
  * period=none(默认) 时行为与改造前完全一致
  * 周期边界按"游戏重置时间"计算(04:00 仍算前一天), 而不是自然日
  * 任何异常都退化为"未完成", 绝不让原本能跑的任务跑不了
"""
import json
import os
from datetime import datetime, time, timedelta

import pytest

from module.config import task_state
from tasks.Component.config_scheduler import Scheduler, TaskPeriod


# ---------------------------------------------------------------------------
# 隔离: 每个测试用独立的状态文件, 不碰真实状态
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_file = tmp_path / '.task_state.json'
    monkeypatch.setenv('OAS_TASK_STATE_FILE', str(state_file))
    yield state_file
    monkeypatch.delenv('OAS_TASK_STATE_FILE', raising=False)


# ---------------------------------------------------------------------------
# 周期计算
# ---------------------------------------------------------------------------
class TestPeriodKey:
    RESET = time(hour=5)

    def test_daily_before_reset_belongs_to_previous_day(self):
        """04:00 未过 5 点重置, 仍属前一游戏日。"""
        now = datetime(2026, 10, 8, 4, 0, 0)
        assert task_state.period_key('daily', self.RESET, now) == '2026-10-07'

    def test_daily_after_reset_belongs_to_new_day(self):
        now = datetime(2026, 10, 8, 5, 1, 0)
        assert task_state.period_key('daily', self.RESET, now) == '2026-10-08'

    def test_daily_at_exact_reset_time(self):
        now = datetime(2026, 10, 8, 5, 0, 0)
        assert task_state.period_key('daily', self.RESET, now) == '2026-10-08'

    def test_daily_late_night_same_game_day(self):
        """23:00 与次日 04:00 属于同一游戏日。"""
        a = task_state.period_key('daily', self.RESET, datetime(2026, 10, 7, 23, 0))
        b = task_state.period_key('daily', self.RESET, datetime(2026, 10, 8, 4, 0))
        assert a == b == '2026-10-07'

    def test_none_returns_empty(self):
        assert task_state.period_key('none', self.RESET) == ''
        assert task_state.period_key('', self.RESET) == ''
        assert task_state.period_key(None, self.RESET) == ''

    def test_weekly_is_stable_within_a_week(self):
        """同一周内(以周一为界)各天的 weekly key 必须相同。"""
        # 2026-10-07 是周三
        mon = task_state.period_key('weekly', self.RESET, datetime(2026, 10, 5, 10, 0))
        wed = task_state.period_key('weekly', self.RESET, datetime(2026, 10, 7, 10, 0))
        sun = task_state.period_key('weekly', self.RESET, datetime(2026, 10, 11, 10, 0))
        assert mon == wed == sun

    def test_weekly_changes_on_monday(self):
        sun = task_state.period_key('weekly', self.RESET, datetime(2026, 10, 11, 10, 0))
        next_mon = task_state.period_key('weekly', self.RESET, datetime(2026, 10, 12, 10, 0))
        assert sun != next_mon

    def test_weekly_respects_reset_offset(self):
        """周一 04:00 未过重置, 仍属上一周。"""
        before = task_state.period_key('weekly', self.RESET, datetime(2026, 10, 12, 4, 0))
        after = task_state.period_key('weekly', self.RESET, datetime(2026, 10, 12, 6, 0))
        assert before != after

    def test_reset_at_accepts_string(self):
        now = datetime(2026, 10, 8, 4, 0, 0)
        assert task_state.period_key('daily', '05:00:00', now) == '2026-10-07'

    def test_custom_reset_time(self):
        """重置时间设 0 点时, 03:00 属于当天。"""
        now = datetime(2026, 10, 8, 3, 0, 0)
        assert task_state.period_key('daily', time(hour=0), now) == '2026-10-08'


class TestPeriodStart:
    """period_start 用于把"已完成"任务的 next_run 推到下个周期。"""

    RESET = time(hour=5)

    def test_daily_next_start_is_tomorrow_at_reset(self):
        now = datetime(2026, 10, 7, 23, 0, 0)
        nxt = task_state.period_start('daily', self.RESET, now)
        assert nxt == datetime(2026, 10, 8, 5, 0, 0)

    def test_daily_before_reset_points_to_today(self):
        now = datetime(2026, 10, 8, 3, 0, 0)
        nxt = task_state.period_start('daily', self.RESET, now)
        assert nxt == datetime(2026, 10, 8, 5, 0, 0)

    def test_weekly_next_start_is_next_monday(self):
        now = datetime(2026, 10, 7, 10, 0)   # 周三
        nxt = task_state.period_start('weekly', self.RESET, now)
        assert nxt.date() == datetime(2026, 10, 12).date()   # 下周一
        assert nxt.hour == 5

    def test_always_in_future(self):
        for now in (datetime(2026, 10, 8, 4, 0), datetime(2026, 10, 8, 6, 0),
                    datetime(2026, 10, 7, 23, 59)):
            assert task_state.period_start('daily', self.RESET, now) > now


# ---------------------------------------------------------------------------
# 状态读写
# ---------------------------------------------------------------------------
class TestRecordAndQuery:
    def test_not_completed_initially(self):
        assert task_state.is_completed_in_period('cfg', 'Task', 'daily') is False

    def test_record_then_completed(self):
        task_state.record_success('cfg', 'Task', 'daily')
        assert task_state.is_completed_in_period('cfg', 'Task', 'daily') is True

    def test_periods_are_independent(self):
        """daily 的完成不应影响 weekly 的判断。"""
        task_state.record_success('cfg', 'Task', 'daily')
        assert task_state.is_completed_in_period('cfg', 'Task', 'daily') is True
        # weekly 记录里没有本周期 key
        assert task_state.is_completed_in_period('cfg', 'Task', 'weekly') is False

    def test_configs_are_independent(self):
        """多账号互不干扰。"""
        task_state.record_success('acc1', 'Task', 'daily')
        assert task_state.is_completed_in_period('acc1', 'Task', 'daily') is True
        assert task_state.is_completed_in_period('acc2', 'Task', 'daily') is False

    def test_task_name_case_insensitive(self):
        task_state.record_success('cfg', 'DailyTrifles', 'daily')
        assert task_state.is_completed_in_period('cfg', 'dailytrifles', 'daily') is True

    def test_none_period_never_completed(self):
        """period=none 时永远返回未完成(即不参与记忆)。"""
        task_state.record_success('cfg', 'Task', 'none')
        assert task_state.is_completed_in_period('cfg', 'Task', 'none') is False

    def test_stale_period_key_not_completed(self):
        """记录属于过去周期时, 应视为未完成。"""
        task_state.record_success('cfg', 'Task', 'daily')
        data = task_state._read_all()
        data['cfg']['task']['period_key'] = '2000-01-01'
        task_state._write_all(data)
        assert task_state.is_completed_in_period('cfg', 'Task', 'daily') is False

    def test_records_last_success_timestamp(self):
        task_state.record_success('cfg', 'Task', 'daily')
        rec = task_state._read_all()['cfg']['task']
        assert 'last_success' in rec
        datetime.fromisoformat(rec['last_success'])   # 必须可解析

    def test_clear_specific_task(self):
        task_state.record_success('cfg', 'A', 'daily')
        task_state.record_success('cfg', 'B', 'daily')
        task_state.clear('cfg', 'a')
        assert task_state.is_completed_in_period('cfg', 'A', 'daily') is False
        assert task_state.is_completed_in_period('cfg', 'B', 'daily') is True

    def test_clear_all(self):
        task_state.record_success('cfg', 'A', 'daily')
        task_state.clear()
        assert task_state.is_completed_in_period('cfg', 'A', 'daily') is False


class TestDegradation:
    """
    异常时必须退化为"未完成", 保证任务照常运行 —— 这是本功能最重要的约束。
    """

    def test_corrupted_file_returns_false(self, isolated_state):
        isolated_state.write_text('{ 不是合法 JSON', encoding='utf-8')
        assert task_state.is_completed_in_period('cfg', 'Task', 'daily') is False

    def test_non_dict_content_returns_false(self, isolated_state):
        isolated_state.write_text('[1, 2, 3]', encoding='utf-8')
        assert task_state.is_completed_in_period('cfg', 'Task', 'daily') is False

    def test_missing_keys_returns_false(self):
        assert task_state.is_completed_in_period('no_such_cfg', 'NoTask', 'daily') is False

    def test_invalid_reset_at_falls_back(self):
        """reset_at 非法时不应抛异常。"""
        result = task_state.period_key('daily', 'not-a-time',
                                       datetime(2026, 10, 8, 10, 0))
        assert isinstance(result, str) and result

    def test_unwritable_path_does_not_raise(self, monkeypatch):
        """状态不可写时 record_success 只告警, 不抛异常。"""
        monkeypatch.setenv('OAS_TASK_STATE_FILE',
                           'Z:\\no\\such\\dir\\x.json')
        task_state.record_success('cfg', 'Task', 'daily')   # 不应抛出


# ---------------------------------------------------------------------------
# 配置模型
# ---------------------------------------------------------------------------
class TestSchedulerConfig:
    def test_period_defaults_to_none(self):
        """默认必须是 none, 否则会改变既有用户的行为。"""
        assert Scheduler().period == TaskPeriod.NONE

    def test_reset_at_defaults_to_5am(self):
        assert Scheduler().reset_at == time(hour=5)

    def test_task_period_values(self):
        assert [p.value for p in TaskPeriod] == ['none', 'daily', 'weekly']

    def test_existing_fields_unchanged(self):
        s = Scheduler()
        assert s.priority == 5
        assert s.delay_date == 1
        assert s.server_update == time(hour=9)

    def test_i18n_has_text_for_new_fields(self):
        """新字段要有中文文案, 否则 UI 显示英文键名。"""
        import io
        from pathlib import Path
        repo = Path(__file__).resolve().parents[3]
        d = json.load(io.open(repo / 'module' / 'config' / 'i18n' / 'zh-CN.json',
                              encoding='utf-8'))
        for key in ('period', 'period_help', 'reset_at', 'reset_at_help'):
            assert key in d, f'i18n 缺少 {key}'
            assert d[key], f'i18n 中 {key} 为空'
