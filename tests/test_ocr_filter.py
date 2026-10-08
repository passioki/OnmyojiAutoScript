# -*- coding: utf-8 -*-
"""OCR 关键词匹配(BaseCor.filter)的测试。

线上实测(2026-10-08, 金币妖怪, 恋鸟树)
------------------------------------
日志:

    [GOLD_50 0.817s] ['觉醒副本掉落额外的觉醒材料', '八岐大蛇掉落额外的御魂材料',
                      '战斗胜利获得的金币增加100%', '战斗胜利获得的经验增加50%',
                      '战斗胜利获得的经验增加100%']
    OCR [GOLD_50] detected in [0, 2, 3]
    OCR [GOLD_50] detected in (429.0, 141.0, 329.0, 24.0)

规则 `O_GOLD_50` 的关键词是 `战斗胜利获得的金币增加50%`。因为列表里那一条没被
OCR 单独识别出来, 旧实现走了"逐字符各找一行"的回退: 只要求关键词的**每个字符**
出现在**某一行**里, 于是

    '战''斗'... 命中第 2 行(金币增加100%)
    '5''0''%'   命中第 3 行(经验增加50%)
    其余字符    命中第 0 行(觉醒副本...)

返回 [0, 2, 3], 上层 `Full.ocr_full` 会用 `merge_area` 把这三行**合并成一大片**
(实测 429..758 x 141..165), 点击位置落在最上面那行 —— 也就是**觉醒加成**,
于是"金币妖怪加成开错了, 多开了个觉醒加成"。

修复后:
  * 逐字符只在"当前行或下一行"内推进, 结果**连续**;
  * 要求足够高的命中比例;
  * 单行都匹配不上时先尝试跨行拼接, 再用相似度兜底(容忍少读/错读一两个字)。
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from module.ocr.base_ocr import BaseCor


class _Box:
    """BoxedResult 的最小替身(只用到 ocr_text)。"""

    def __init__(self, text):
        self.ocr_text = text


class _Probe(BaseCor):
    """只承载 keyword 的最小实例。"""

    def __init__(self, keyword):
        self.keyword = keyword


def do_filter(rows, keyword):
    return _Probe(keyword).filter([_Box(r) for r in rows], keyword)


GOLD_50 = '战斗胜利获得的金币增加50%'
GOLD_100 = '战斗胜利获得的金币增加100%'
EXP_50 = '战斗胜利获得的经验增加50%'
EXP_100 = '战斗胜利获得的经验增加100%'

# 线上日志里真实出现的 5 行
LIVE_ROWS = [
    '觉醒副本掉落额外的觉醒材料',
    '八岐大蛇掉落额外的御魂材料',
    GOLD_100,
    EXP_50,
    EXP_100,
]


class TestLiveRegression:
    """线上那个 bug 的直接回归。"""

    def test_gold_50_no_longer_matches_unrelated_rows(self):
        got = do_filter(LIVE_ROWS, GOLD_50)
        assert got != [0, 2, 3], '不得再返回跨 3 行的误匹配(会导致点到觉醒加成)'
        assert got == [2], f'应只匹配金币增加100%那一行, 实际 {got}'

    def test_result_is_compact(self):
        """结果必须是连续区间 —— 否则 merge_area 会合并出一大片区域。"""
        got = do_filter(LIVE_ROWS, GOLD_50)
        assert got is None or max(got) - min(got) <= 2

    def test_other_buffs_still_work(self):
        assert do_filter(LIVE_ROWS, GOLD_100) == [2]
        assert do_filter(LIVE_ROWS, EXP_50) == [3]
        assert do_filter(LIVE_ROWS, EXP_100) == [4]


class TestNormalMatching:
    def test_substring_in_single_row(self):
        rows = [GOLD_50, EXP_50]
        assert do_filter(rows, GOLD_50) == [0]
        assert do_filter(rows, EXP_50) == [1]

    def test_exact_mode(self):
        rows = [GOLD_50, EXP_50]
        assert _Probe(GOLD_50).filter([_Box(r) for r in rows], GOLD_50,
                                      exact=True) == [0]

    def test_exact_mode_rejects_partial(self):
        rows = ['前缀' + GOLD_50]
        assert _Probe(GOLD_50).filter([_Box(r) for r in rows], GOLD_50,
                                      exact=True) is None


class TestCrossLineMatching:
    """
    目标文本被 OCR 拆到相邻两行时必须仍能匹配。

    注意旧实现这里其实是**坏的**: `keyword in concatenated_string` 为真,
    但没有任何单行包含关键词, 列表推导得到**空列表**, 而 `if result is not None`
    会把这个空列表直接返回并提前退出 —— 后续跨行逻辑根本没机会执行。
    """

    def test_split_across_two_rows(self):
        rows = ['战斗胜利获得的金币', '增加50%']
        assert do_filter(rows, GOLD_50) == [0, 1]

    def test_split_with_noise_rows(self):
        rows = ['标题', '战斗胜利获得的金币', '增加50%', '页脚']
        assert do_filter(rows, GOLD_50) == [1, 2]

    def test_concat_contains_but_no_single_row_does(self):
        """复现"整串包含但逐行都不包含"的场景(旧实现会返回空列表)。"""
        rows = ['战斗胜利获得的金币增加', '50%']
        got = do_filter(rows, GOLD_50)
        assert got is not None, '整串包含时应走跨行匹配, 而不是返回空列表'
        assert got == [0, 1]

    def test_does_not_cross_many_rows(self):
        """跨越过多行说明匹配不可靠, 应当拒绝。"""
        rows = ['战', '斗', '胜', '利', '获', '得', '5', '0', '%']
        assert do_filter(rows, GOLD_50) is None


class TestRejection:
    def test_unrelated_rows_rejected(self):
        assert do_filter(['签到奖励', '寮活动', '每日任务', '商店'], GOLD_50) is None

    def test_empty_input(self):
        assert do_filter([], GOLD_50) is None


class TestTolerance:
    def test_similarity_tolerates_one_wrong_char(self):
        """OCR 把 50% 读成 60% 时应仍能找到那一行。"""
        rows = ['战斗胜利获得的金币增加60%']
        assert do_filter(rows, GOLD_50) == [0]


class TestNoEmptyListReturn:
    """
    回归: filter 不得返回空列表。

    空列表会被调用方当作"检测到了但坐标为空", 而 None 才表示"没检测到"。
    旧实现 `if result is not None: return result` 会把空列表返回出去。
    """

    @pytest.mark.parametrize('rows', [
        ['战斗胜利获得的金币', '增加50%'],
        ['标题', '战斗胜利获得的金币', '增加50%'],
        ['战', '斗', '胜', '利'],
    ])
    def test_never_returns_empty_list(self, rows):
        got = do_filter(rows, GOLD_50)
        assert got is None or len(got) > 0, f'不得返回空列表, 实际 {got!r}'
