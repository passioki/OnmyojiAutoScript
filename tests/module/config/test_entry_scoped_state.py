# -*- coding: utf-8 -*-
"""C-3/C-4: 完成记忆按 **entry_id** 读写 —— 让重复条目**各跑一次**。

## 用户裁定（D）

> "**D, 两个机制**, 次数是**单一任务里设置战斗跑几次**,
>  重复添加是**重复跑整个任务**。
>  **a 50次, a50次**: 50 次是**次数**, 但是 a50次**重复添加了一次**。"

所以 `a, a`（同一任务两条）应该 -> **两条都能跑**, 各自记完成。

## 此前为什么做不到

完成记忆按**任务**记:
```
第一条跑完 -> is_completed_in_period(config, 'a') 变 True
           -> **第二条也被跳过** -> 只跑了 1 次
```

## 现在的契约

* `task_state.record_success(..., entry_id=)` / `is_completed_in_period(..., entry_id=)`
  —— 有 `entry_id` 就按**条目**存/查
* **兜底**: `entry_id` 为空 -> 退回 `task`（旧状态文件仍能读到）
* `_skip_by_period` 移到 `_order_by_queue()` **之后**（那时 `entry_id` 才写好）
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TEST_CFG = '__test_entry_state__'


@pytest.fixture()
def st():
    """用**临时 config 名** —— 绝不在用户的实时状态文件上做清理。

    ★ 我踩过一次: 验证脚本调 `task_state.clear(config_name='恋鸟树')`,
      **连带清掉了该账号的充能记录**, 导致
      `test_charge_tasks_can_find_charges` 失败。已恢复并改用临时名。
    """
    from module.config import task_state
    task_state.clear(config_name=TEST_CFG)
    yield task_state
    task_state.clear(config_name=TEST_CFG)


class TestEntryScopedCompletion:
    def test_two_entries_are_independent(self, st):
        """★★ 核心: 两个条目的完成记忆**互相独立**。"""
        st.record_success(TEST_CFG, 'RealmRaid', 'daily', entry_id='E1')
        assert st.is_completed_in_period(TEST_CFG, 'RealmRaid', 'daily',
                                         entry_id='E1') is True
        assert st.is_completed_in_period(TEST_CFG, 'RealmRaid', 'daily',
                                         entry_id='E2') is False, (
            '把 E1 记为完成不该影响 E2 —— 这就是"各跑一次"的关键')

    def test_record_one_then_other(self, st):
        st.record_success(TEST_CFG, 'RealmRaid', 'daily', entry_id='E1')
        st.record_success(TEST_CFG, 'RealmRaid', 'daily', entry_id='E2')
        for eid in ('E1', 'E2'):
            assert st.is_completed_in_period(TEST_CFG, 'RealmRaid', 'daily',
                                             entry_id=eid) is True

    def test_fallback_to_task_when_no_entry_id(self, st):
        """★ 向后兼容: 无 `entry_id` 时退回按**任务**记（旧状态文件仍能读到）。"""
        st.record_success(TEST_CFG, 'RealmRaid', 'daily')
        assert st.is_completed_in_period(TEST_CFG, 'RealmRaid', 'daily') is True

    def test_entry_and_task_keys_do_not_collide(self, st):
        """条目键与任务键是**两个**键 —— 不该互相覆盖。"""
        st.record_success(TEST_CFG, 'RealmRaid', 'daily')          # 任务键
        assert st.is_completed_in_period(TEST_CFG, 'RealmRaid', 'daily',
                                         entry_id='E1') is False, (
            '任务级记录不该让某个条目"看起来已完成"')

    def test_state_key_helper(self):
        from module.config.task_state import _state_key
        assert _state_key('RealmRaid', '20261010T091805-RealmRaid') == \
            '20261010t091805-realmraid'
        assert _state_key('RealmRaid') == 'realmraid'
        assert _state_key('RealmRaid', '') == 'realmraid'


class TestWiring:
    """★ 接线: `config.py` 必须把 `entry_id` 传下去。"""

    def _src(self):
        return (REPO / 'module' / 'config' / 'config.py').read_text(
            encoding='utf-8')

    def test_skip_by_period_accepts_entry_id(self):
        import inspect
        from module.config.config import Config
        sig = inspect.signature(Config._skip_by_period)
        assert 'entry_id' in sig.parameters, \
            '_skip_by_period 必须能按条目判断'

    def test_record_task_success_accepts_entry_id(self):
        import inspect
        from module.config.config import Config
        sig = inspect.signature(Config._record_task_success)
        assert 'entry_id' in sig.parameters

    def test_task_delay_passes_running_entry_id(self):
        src = self._src()
        i = src.find('def task_delay')
        j = src.find('\n    def ', i + 10)
        body = src[i:j if j > i else i + 12000]
        assert "getattr(self.task, 'entry_id', None)" in body, \
            'task_delay 应把**正在跑的条目**的 id 传给记录函数'

    def test_skip_by_period_called_after_order_by_queue(self):
        """★ 顺序: 完成记忆检查必须在 `_order_by_queue()` **之后**。

        否则 `entry_id` 还没写好 -> 门槛退化成"按任务" -> 重复条目被合并。

        ⚠ 必须先**剥注释与 docstring** 再定位 —— 否则会找到**注释里**
          提到 `_skip_by_period` 的地方（我踩过一次: 断言失败但代码是对的）。
        """
        import re
        src = self._src()
        i = src.find('def update_scheduler')
        j = src.find('\n    def ', i + 10)
        body = src[i:j if j > i else i + 20000]
        body = re.sub(r'"""[\s\S]*?"""', '', body)
        body = '\n'.join(l.split('#', 1)[0] for l in body.split('\n'))
        k_order = body.find('_order_by_queue(pending_task)')
        k_skip = body.find('_skip_by_period(')
        assert k_order > 0, '找不到 _order_by_queue 调用'
        assert k_skip > 0, '找不到 _skip_by_period 调用'
        assert k_skip > k_order, (
            '`_skip_by_period` 必须在 `_order_by_queue` **之后**调用 —— '
            '否则 entry_id 还没写好, 重复条目会被合并')

    def test_loop_no_longer_gates_by_period(self):
        """反向守卫: 循环里**不该**再直接判 `_skip_by_period`。"""
        src = self._src()
        i = src.find('def update_scheduler')
        j = src.find('_order_by_queue(pending_task)', i)
        head = src[i:j]
        # 循环体里不该有 _skip_by_period（注释里提到是允许的）
        import re
        code = '\n'.join(l.split('#', 1)[0] for l in head.split('\n'))
        code = re.sub(r'"""[\s\S]*?"""', '', code)
        assert '_skip_by_period(' not in code, (
            '循环里仍在判 _skip_by_period —— 那时 entry_id 还是 None')
