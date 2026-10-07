"""
验证 OCR 检测的"先不补边、检不出再补边"自适应策略。

背景:
    原先 detect_and_ocr / detect_text 一律先 enlarge_canvas 再检测。
    该函数是为旧引擎 PaddleOCR 写的(方形图 + 32 的倍数更友好), 但换成
    PP-OCRv6 后补边反而有害: 窄长区域会引入大片白边, 检测框偏小并丢失末字。

    实测(真实游戏截图, 18 个区域组合):
        结果相同 10、补边更差 5、补边更好 3
        补边更差的例子: 不补边 ['壹层','贰层','叁层','日蚀'] vs 补边 [...,'日']
                        -> 导致 FallenSun 选取层数时 '日蚀' 匹配失败并抛 ValueError
        补边更好的例子: 不补边 [] vs 补边 ['大蛇','业原火']
                        -> 说明不能简单地一律不补边

    故采用自适应: 先不补边, 无结果时才补边重试。

这些测试锁定该策略不被改回"一律补边"或"一律不补边"。
"""
import re
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_OCR = REPO_ROOT / 'module' / 'ocr' / 'base_ocr.py'


# --------------------------------------------------------------------------
# 源码层面的约束
# --------------------------------------------------------------------------
def test_detect_and_ocr_does_not_unconditionally_enlarge():
    """
    detect_and_ocr 中不得再出现"无条件 enlarge_canvas(image)"的旧写法。
    """
    source = BASE_OCR.read_text(encoding='utf-8')

    # 取出 detect_and_ocr 方法体
    start = source.index('def detect_and_ocr')
    # 下一个同级 def
    nxt = source.find('\n    def ', start + 10)
    body = source[start:nxt if nxt != -1 else len(source)]

    # 旧写法是单独一行 image = enlarge_canvas(image)
    assert not re.search(r'^\s*image\s*=\s*enlarge_canvas\(image\)\s*$', body, re.MULTILINE), \
        'detect_and_ocr 又变回无条件补边了'


def test_detect_text_uses_the_same_fallback():
    """detect_text 与 detect_and_ocr 必须走同一套补边策略, 否则两者行为不一致。"""
    source = BASE_OCR.read_text(encoding='utf-8')

    start = source.index('def detect_text')
    nxt = source.find('\n    def ', start + 10)
    body = source[start:nxt if nxt != -1 else len(source)]

    assert '_detect_with_fallback' in body, 'detect_text 未使用统一的补边策略'
    assert not re.search(r'^\s*image\s*=\s*enlarge_canvas\(image\)\s*$', body, re.MULTILINE), \
        'detect_text 又变回无条件补边了'


def test_fallback_helper_exists_and_is_documented():
    source = BASE_OCR.read_text(encoding='utf-8')
    assert 'def _detect_with_fallback' in source
    assert 'enlarge_canvas' in source, '辅助函数应说明为何仍保留 enlarge_canvas'


# --------------------------------------------------------------------------
# 行为层面的验证
# --------------------------------------------------------------------------
class _StubModel:
    """记录调用参数的假模型。"""

    def __init__(self, results_by_shape):
        self.calls = []
        self._results = results_by_shape

    def detect_and_ocr(self, image):
        self.calls.append(image.shape)
        return self._results.get(image.shape[:2], [])


def test_fallback_returns_first_non_empty_without_enlarging():
    from module.ocr.base_ocr import _detect_with_fallback

    small = np.zeros((20, 40, 3), dtype=np.uint8)
    model = _StubModel({(20, 40): ['命中']})

    result = _detect_with_fallback(model, small)

    assert result == ['命中']
    assert len(model.calls) == 1, '首次就命中时不应再补边重试'


def test_fallback_retries_with_enlarged_canvas_when_empty():
    from module.ocr.base_ocr import _detect_with_fallback, enlarge_canvas

    small = np.zeros((20, 40, 3), dtype=np.uint8)
    enlarged_shape = enlarge_canvas(small).shape[:2]
    model = _StubModel({enlarged_shape: ['补边后命中']})

    result = _detect_with_fallback(model, small)

    assert result == ['补边后命中']
    assert len(model.calls) == 2, '首次为空时应补边重试一次'
    assert model.calls[0] != model.calls[1]


def test_fallback_returns_empty_when_both_fail():
    from module.ocr.base_ocr import _detect_with_fallback

    small = np.zeros((20, 40, 3), dtype=np.uint8)
    model = _StubModel({})

    assert _detect_with_fallback(model, small) == []


def test_fallback_retry_uses_a_different_image():
    """
    补边重试必须换一张(补过边的)图, 否则第二次检测与第一次等价, 毫无意义。

    注: enlarge_canvas 的公式是 max(w,h)//32*32+32, 因此它总会增大尺寸,
    不会返回与原图相同的 shape —— 这里验证重试用的确实是不同的输入。
    """
    from module.ocr.base_ocr import _detect_with_fallback, enlarge_canvas

    small = np.zeros((20, 40, 3), dtype=np.uint8)
    assert enlarge_canvas(small).shape != small.shape  # 补边必然改变尺寸

    model = _StubModel({})
    _detect_with_fallback(model, small)

    assert len(model.calls) == 2
    assert model.calls[0] != model.calls[1], '重试必须使用补边后的不同输入'


def test_enlarge_canvas_makes_square_multiple_of_32():
    """锁定 enlarge_canvas 的语义, 便于日后判断是否可以安全移除。"""
    from module.ocr.base_ocr import enlarge_canvas

    for h, w in ((579, 65), (65, 579), (50, 50), (100, 33)):
        out = enlarge_canvas(np.zeros((h, w, 3), dtype=np.uint8))
        oh, ow = out.shape[:2]
        assert oh == ow, '应为正方形'
        assert oh % 32 == 0, '边长应为 32 的倍数'
        assert oh >= max(h, w), '不应缩小原图'


# --------------------------------------------------------------------------
# FallenSun 资产修复
# --------------------------------------------------------------------------
def test_fallen_sun_layer_array_matches_layer_enum():
    """
    tasks/FallenSun/res/list.json 的 itemName 曾只有首字('壹','贰','叁','日'),
    与游戏实际显示的 '壹层/贰层/叁层/日蚀' 不符, 导致选取层数时必定失败。
    """
    from tasks.FallenSun.assets import FallenSunAssets
    from tasks.FallenSun.config import Layer

    array = FallenSunAssets.L_LAYER_LIST.array
    enum_values = [m.value for m in Layer]

    for value in enum_values:
        assert value in array, f'{value!r} 不在 L_LAYER_LIST.array={array} 中'

    # 反向: array 中不应再有被截断的旧名字
    for truncated in ('壹', '贰', '叁', '日'):
        assert truncated not in array, f'array 中仍存在截断名 {truncated!r}'


def test_check_layer_accepts_both_enum_and_str():
    """check_layer 统一取 .value, 传入枚举或字符串都应可用。"""
    source = (REPO_ROOT / 'tasks' / 'FallenSun' / 'script_task.py').read_text(encoding='utf-8')
    assert 'getattr(layer, \'value\', layer)' in source
