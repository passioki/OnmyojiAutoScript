# -*- coding: utf-8 -*-
"""**固定任务** 与 **定时任务** 分开管理的调度规则。

## 为什么分开

改造前所有任务混在一个 `pending` 桶里按顺序跑。但两者的机制根本不同:

| 类型 | 特征 | 该怎么排 |
|---|---|---|
| **固定任务**（`fixed`/`toppa`）| "打满 N 次", 没有时间窗 | 按**用户拖拽的顺序** |
| **定时任务**（`timed`/`charge`/`limited`）| 有 window / 存量 / 周期 | 按 window、剩余时间、预计耗时、自定义优先级 |

把定时任务塞进"用户顺序"里是错的 —— 它有自己的时间约束,
"排在第三个" 跟 "17:00 才开放" 会互相打脸。

## 三个开关

| 字段 | 位置 | 作用 |
|---|---|---|
| `enable_fixed` | `Script.optimization` | 固定任务总开关 |
| `enable_timed` | `Script.optimization` | 定时任务总开关 |
| `timed_priority` | `Script.optimization` | 定时任务到点时怎么跟固定任务抢 |
| `rest_interleave` | `Script.optimization` | 休息期间能否穿插定时任务 |

## 本模块只放**纯函数**

这样语义可以被测试固定下来, 不必起真实设备。
调度器（`config.py` / `script.py`）调用它们。
"""

# --------------------------------------------------------------------------- 总开关
#: 分类 -> 归哪个开关管
FIXED_CATEGORIES = ('fixed', 'toppa')
TIMED_CATEGORIES = ('timed', 'charge', 'limited')


def should_consider(category_value: str, enable_fixed: bool = True,
                    enable_timed: bool = True) -> bool:
    """
    该类别的任务现在是否参与调度。

    * 固定任务（`fixed`/`toppa`）看 `enable_fixed`
    * 定时任务（`timed`/`charge`/`limited`）看 `enable_timed`
    * 两个开关**互不影响** —— 关掉固定任务不该影响定时任务, 反之亦然
    * 不认识的类别 -> False（不崩）
    """
    cat = str(category_value or '').lower()
    if cat in FIXED_CATEGORIES:
        return bool(enable_fixed)
    if cat in TIMED_CATEGORIES:
        return bool(enable_timed)
    return False


def is_fixed(category_value: str) -> bool:
    return str(category_value or '').lower() in FIXED_CATEGORIES


def is_timed(category_value: str) -> bool:
    return str(category_value or '').lower() in TIMED_CATEGORIES


# --------------------------------------------------------------------------- 穿插
def can_interleave(rest_interleave: bool, enable_timed: bool, is_due: bool,
                   expected_minutes: int,
                   rest_remaining_minutes: int) -> bool:
    """
    **休息期间**能否穿插跑这个定时任务。

    用户确认的判据:

        定时任务的**预期完成时间** < 休息剩余时间
        -> 允许穿插

    ## 为什么要这条

    休息 = 去庭院待着。如果休息期间**一律不跑任何东西**,
    **组队任务**的完成复杂度会大幅上升（队员等不到人）。
    能塞进去就塞, 把空等的时间利用起来。

    ## 为什么 `expected_minutes == 0` 算"不能穿插"

    `0` 表示**未知**（用户没配）。拿一个未知值去比会得出错误结论 ——
    宁可少穿插, 也不要因为瞎猜而把休息时间用超。

    :param rest_interleave: 全局开关（`Script.optimization.rest_interleave`）
    :param enable_timed: 定时任务总开关
    :param is_due: 该定时任务是否已到点
    :param expected_minutes: 该任务的预期完成时间（分钟）; 0 = 未知
    :param rest_remaining_minutes: 休息还剩多少分钟
    """
    if not rest_interleave:
        return False
    if not enable_timed:
        return False
    if not is_due:
        return False

    try:
        need = int(expected_minutes)
        left = int(rest_remaining_minutes)
    except (TypeError, ValueError):
        return False

    # 未知时长 -> 保守, 不穿插
    if need <= 0:
        return False
    # 休息已经结束（或没在休息）
    if left <= 0:
        return False

    return need <= left


# --------------------------------------------------------------------------- 定时任务排序
def timed_sort_key(next_run, in_window: bool = True, window_end=None,
                   expected_minutes: int = 0, priority: int = 5):
    """
    定时任务的**内部**排序键（越小越先跑）。

    ## 排序依据（用户确认的四项）

    1. **能否跑**：不在 window 内的排后面
    2. **到点程度**：`next_run` 越早越先（已到点的是负数, 自然最前）
    3. **窗口快关的优先**：`window_end` 近的先跑（错过就没了）
    4. **预计耗时短的优先**：能快速清掉的先清, 减少"跑到一半窗口关了"
    5. **用户自定义优先级**：数字小的先跑, 作为最终裁判

    ★ 这个顺序是**刻意的** —— 时间约束（2/3）比"预计耗时"(4)重要,
      因为窗口关了就是彻底做不了; 而"耗时"只影响效率。

    :param next_run: 该任务的下次可跑时间（`datetime` 或可比较对象）
    :param in_window: 是否在开放时段内
    :param window_end: 开放时段的结束时间（`datetime` 或 None）
    :param expected_minutes: 预期完成时间（分钟）; 0 = 未知
    :param priority: 用户自定义优先级（小的先跑）
    """
    # 1) 不在窗口内的排最后
    window_rank = 0 if in_window else 1

    # 2) 到点程度（next_run 越早越先）
    try:
        run_rank = next_run
    except Exception:
        run_rank = None

    # 3) 窗口结束越近越先; 没有 window_end 的排最后
    if window_end is None:
        end_rank = 1
        end_value = None
    else:
        end_rank = 0
        end_value = window_end

    # 4) 预计耗时短的先; 未知(0)当中间值, 不前不后
    try:
        exp = int(expected_minutes)
    except (TypeError, ValueError):
        exp = 0
    exp_rank = 0 if exp > 0 else 1
    exp_value = exp if exp > 0 else 0

    # 5) 用户优先级
    try:
        pri = int(priority)
    except (TypeError, ValueError):
        pri = 5

    return (window_rank, run_rank, end_rank, end_value,
            exp_rank, exp_value, pri)
