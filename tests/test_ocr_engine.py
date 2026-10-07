"""
验证 OCR 引擎替换为 RapidOCR(PP-OCRv6) 后的接口契约与依赖边界。

为什么需要这些测试:
    1. module/ocr/ppocr.py 的 TextSystem 被 module/ocr/base_ocr.py、atom/list.py、
       rpc.py 与 SixRealms 共同依赖, 接口一旦漂移会波及全仓 OCR。
    2. 该模块曾因间接 import ppocronnx 而把 onnxruntime 拉进同一进程, 在
       onnxruntime 1.21+ 下触发 Windows DLL 加载顺序冲突
       ("DLL load failed while importing onnxruntime_pybind11_state")。
       这里用"源码不含 ppocronnx 引用"来锁住这个边界, 防止回归。
    3. requirements 里 onnxruntime 被钉在 1.20.1(既支持 PP-OCRv6 的 IR v10,
       又能与 zerorpc/gevent 共存), 上限需要被显式断言。
"""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PPOCR_PATH = REPO_ROOT / 'module' / 'ocr' / 'ppocr.py'


# --------------------------------------------------------------------------
# 依赖边界: 不得再引入 ppocronnx
# --------------------------------------------------------------------------
def test_ppocr_module_does_not_import_ppocronnx():
    """
    源码中不得出现实际的 ppocronnx 导入语句。

    注释里提到 ppocronnx 是允许的(用于说明兼容契约), 因此只检查导入语句。
    """
    source = PPOCR_PATH.read_text(encoding='utf-8')
    import_lines = [
        line.strip() for line in source.splitlines()
        if line.strip().startswith(('import ', 'from '))
    ]
    offenders = [line for line in import_lines if 'ppocronnx' in line]
    assert offenders == [], f'ppocr.py 不应再导入 ppocronnx: {offenders}'


def test_consumers_import_boxed_result_from_our_module():
    """BoxedResult 必须来自 module.ocr.ppocr, 而不是 ppocronnx。"""
    for rel in ('module/ocr/base_ocr.py', 'module/atom/list.py'):
        source = (REPO_ROOT / rel).read_text(encoding='utf-8')
        import_lines = [
            line.strip() for line in source.splitlines()
            if line.strip().startswith(('import ', 'from '))
        ]
        assert not any('ppocronnx' in line for line in import_lines), \
            f'{rel} 仍从 ppocronnx 导入: {import_lines}'


def test_onnxruntime_pin_supports_v6_and_zerorpc():
    """
    onnxruntime 必须钉在 1.20.1:
      < 1.18  -> 不支持 PP-OCRv6 的 IR version 10
      >= 1.21 -> 与 zerorpc/gevent 在 Windows 上 DLL 冲突
    """
    req_in = (REPO_ROOT / 'requirements-in.txt').read_text(encoding='utf-8')
    assert 'onnxruntime==1.20.1' in req_in

    req = (REPO_ROOT / 'requirements.txt').read_text(encoding='utf-8')
    assert 'onnxruntime==1.20.1' in req


def test_rapidocr_declared_in_requirements():
    req_in = (REPO_ROOT / 'requirements-in.txt').read_text(encoding='utf-8')
    assert 'rapidocr==' in req_in
    req = (REPO_ROOT / 'requirements.txt').read_text(encoding='utf-8')
    assert 'rapidocr==' in req


# --------------------------------------------------------------------------
# BoxedResult 契约
# --------------------------------------------------------------------------
def test_boxed_result_exposes_the_same_fields_as_ppocronnx():
    from module.ocr.ppocr import BoxedResult

    box = np.array([[0, 0], [10, 0], [10, 5], [0, 5]], dtype=float)
    result = BoxedResult(box, None, '测试', 0.9)

    assert result.ocr_text == '测试'
    assert result.score == 0.9
    assert result.text_img is None
    assert np.array_equal(result.box, box)


def test_boxed_result_ocr_text_is_mutable():
    """base_ocr.detect_and_ocr 会原地改写 result.ocr_text。"""
    from module.ocr.ppocr import BoxedResult

    result = BoxedResult(None, None, '原文', 1.0)
    result.ocr_text = '改后'
    assert result.ocr_text == '改后'


def test_boxed_result_box_is_two_dimensionally_indexable():
    """
    module/ocr/sub_ocr.py 与 atom/list.py 依赖 box[0, 0] / box[1, 0] 这类索引,
    因此 box 必须是可按 (行, 列) 索引的二维结构。
    """
    from module.ocr.ppocr import BoxedResult

    box = np.array([[1, 2], [11, 3], [12, 8], [2, 7]], dtype=float)
    result = BoxedResult(box, None, 'x', 1.0)

    assert result.box[0, 0] == 1
    assert result.box[0, 1] == 2
    assert result.box[1, 0] - result.box[0, 0] == 10   # width
    assert result.box[2, 1] - result.box[0, 1] == 6    # height


def test_boxed_result_repr_matches_ppocronnx_shape():
    from module.ocr.ppocr import BoxedResult

    text = str(BoxedResult(None, None, '文案', 0.5))
    assert text.startswith('BoxedResult[')
    assert '文案' in text


# --------------------------------------------------------------------------
# TextSystem 接口契约
# --------------------------------------------------------------------------
@pytest.fixture(scope='module')
def text_system():
    from module.ocr.ppocr import TextSystem
    return TextSystem()


def test_text_system_reports_not_proxy(text_system):
    """rpc.py 用 is_proxy 区分本地模型与 RPC 代理。"""
    assert text_system.is_proxy is False


def test_text_system_has_detector_compat_shell(text_system):
    """SixRealms 会读写 text_detector.box_thresh。"""
    assert hasattr(text_system.text_detector, 'box_thresh')
    text_system.text_detector.box_thresh = 0.2
    assert text_system.text_detector.box_thresh == 0.2
    text_system.text_detector.box_thresh = 0.6


def test_text_system_text_recognizer_is_replaceable(text_system):
    """
    rpc.py 与 SixRealms 会临时替换 text_recognizer(竖排场景),
    替换函数签名为 fn(list[ndarray]) -> (list[(text, score)], elapse)。
    """
    original = text_system.text_recognizer
    calls = []

    def fake(crops):
        calls.append(len(crops))
        return [('假', 1.0) for _ in crops], 0.0

    text_system.text_recognizer = fake
    try:
        result, _ = text_system.text_recognizer([np.zeros((10, 10, 3), dtype=np.uint8)])
        assert result == [('假', 1.0)]
        assert calls == [1]
    finally:
        text_system.text_recognizer = original


def test_ocr_single_line_returns_text_and_score(text_system):
    """base_ocr.ocr_single_line 依赖 result, score = model.ocr_single_line(image)。"""
    image = np.full((30, 120, 3), 255, dtype=np.uint8)
    out = text_system.ocr_single_line(image)

    assert isinstance(out, tuple), f'必须是二元组, 实际 {type(out).__name__}'
    assert len(out) == 2
    text, score = out
    assert isinstance(text, str)
    assert isinstance(score, float)


def test_detect_and_ocr_returns_boxed_results_with_boxes(text_system):
    """
    detect_and_ocr 必须返回 BoxedResult, 且 box 非 None。

    曾经的缺陷: 只传检测参数而未显式 use_det=True, 会走 rapidocr 的纯识别分支
    并返回不带 boxes 属性的 TextRecOutput, 导致所有调用方的 .box 变成 None。
    这里显式断言 box 不是 None 且形状为 (4, 2)。
    """
    from module.ocr.ppocr import BoxedResult

    image = np.full((60, 200, 3), 255, dtype=np.uint8)
    results = text_system.detect_and_ocr(image)

    assert isinstance(results, list)
    for item in results:
        assert isinstance(item, BoxedResult)
        assert item.box is not None, 'box 不应为 None'
        assert np.array(item.box).shape == (4, 2)


def test_detect_and_ocr_honours_drop_score(text_system):
    """drop_score 必须真正过滤低置信度结果。"""
    image = np.full((60, 200, 3), 255, dtype=np.uint8)
    kept = text_system.detect_and_ocr(image, drop_score=0.0)
    dropped = text_system.detect_and_ocr(image, drop_score=1.1)

    assert len(dropped) == 0
    assert len(kept) >= len(dropped)


def test_detect_and_ocr_accepts_all_parameter_names_used_in_repo():
    """
    兼容性: 仓库里出现过的调用形态都要能接受。
      base_ocr      : detect_and_ocr(image)
      rpc.py        : (image, drop_score=, unclip_ratio=, box_thresh=, vertical=)
      SixRealms     : functools.partial(detect_and_ocr, drop_score=0.1) 后再传参
    """
    import functools

    from module.ocr.ppocr import TextSystem

    image = np.full((60, 200, 3), 255, dtype=np.uint8)
    model = TextSystem()

    assert isinstance(model.detect_and_ocr(image), list)
    assert isinstance(
        model.detect_and_ocr(image, drop_score=0.1, unclip_ratio=1.6,
                             box_thresh=0.2, vertical=True), list)
    assert isinstance(functools.partial(model.detect_and_ocr, drop_score=0.1)(image), list)
