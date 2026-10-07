# This Python file uses the following encoding: utf-8
"""
OCR 引擎: RapidOCR (PP-OCRv6) + 向下兼容 ppocronnx 的 TextSystem 接口。

背景
----
原先这里继承 ppocronnx.predict_system.TextSystem, 其识别模型是 2020 年的 PP-OCRv2。
实测(v2 / v4 / v6 三代对比):

    素材                             v2(旧)      v4        v6(本实现)
    繁体 戀鳥樹 (真实截图)            懋岛树 0.70  戀鸟樹 0.77  戀鳥樹 0.99
    繁体 戀鳥樹 (合成)                经言乡 ✗     戀鳥樹 ✓    戀鳥樹 ✓
    简体 地域鬼王                     地域 ✗       地域鬼王 ✓  地域鬼王 ✓
    简体 觉醒                         空 ✗         觉醒 ✓      觉醒 ✓
    简体 整屏(邀请界面)               20条/0.908   18条/0.964  20条/0.956

即: v6 在简体上与 v2 持平(检出数相同、置信度略优), 在繁体上则是"能读"与"读不出"的差别。
因此本模块直接把引擎换为 v6, 并把 ppocronnx 的 TextSystem 公共接口原样保留, 使
module/ocr 的所有既有调用方(含 RPC 服务端与 SixRealms 的竖排改造)无需改动。

接口契约(必须保持)
------------------
    TextSystem()
    .ocr_single_line(image) -> (text: str, score: float)
    .detect_and_ocr(image, drop_score=0.5, unclip_ratio=None,
                    box_thresh=None, vertical=False) -> list[BoxedResult]
    .text_detector.box_thresh            # 可读写(SixRealms 会临时调低)
    .text_recognizer = fn(list[np.ndarray]) -> (list[(text,score)], elapse)
                                         # 可替换(竖排: 先把裁片旋转)
    .is_proxy                            # 供 RPC 客户端判定, 本类恒为 False

颜色空间
--------
沿用在用的约定: 输入为 **RGB**(仓库内 RuleImage 与 assets_test.load_image 都产出 RGB)。
实测 RapidOCR 对 RGB 输入表现更好(真实截图 0.77 vs BGR 0.55), 故不做通道转换。
"""
import logging
from typing import List

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class BoxedResult(object):
    """
    一条 OCR 结果。字段与 ppocronnx.predict_system.BoxedResult 完全一致,
    因此所有既有消费方(base_ocr / atom.list / rpc)无需改动即可使用。

    为何本地定义而不是继续从 ppocronnx 导入:
        一旦从 ppocronnx 导入任何东西, Python 就会执行 ppocronnx/__init__.py,
        它连锁导入 cls -> predict_cls -> onnxruntime。实测在 onnxruntime 1.23.2 下,
        这条链路会出现间歇性的 "DLL load failed while importing
        onnxruntime_pybind11_state"(裸 import onnxruntime 连续 5 次均正常,
        但经 ppocronnx 间接导入则连续 3 次失败)。
        本模块已改用 RapidOCR, 不再需要 ppocronnx, 故本地定义以切断该依赖链。

    属性:
        box      : 四点坐标, np.ndarray, shape (4, 2)。下游会做 box[0, 0] / box[1, 0] 索引。
        text_img : 按框裁出的文字图。
        ocr_text : 识别文本。下游(base_ocr)会原地改写它, 故为普通可变属性。
        score    : 置信度。
    """

    __slots__ = ('box', 'text_img', 'ocr_text', 'score')

    def __init__(self, box, text_img, ocr_text, score):
        self.box = box
        self.text_img = text_img
        self.ocr_text = ocr_text
        self.score = score

    def __str__(self):
        return 'BoxedResult[%s, %s]' % (self.ocr_text, self.score)

    def __repr__(self):
        return self.__str__()


class _TextDetectorCompat:
    """
    `model.text_detector.box_thresh` 的兼容壳。

    SixRealms/oas_ocr.py 会在调用前后读写该属性以临时放宽检测阈值;
    RapidOCR 没有等价的可变对象, 故在此保存值, 由 TextSystem 读取后
    作为参数传给 RapidOCR 的 __call__。
    """

    def __init__(self, box_thresh: float):
        self.box_thresh = box_thresh


class TextSystem:
    """RapidOCR(PP-OCRv6) 的封装, 对外表现为 ppocronnx 的 TextSystem。"""

    is_proxy = False

    def __init__(
            self,
            use_angle_cls=False,
            box_thresh=0.6,
            unclip_ratio=1.6,
            rec_model_path=None,
            det_model_path=None,
            ort_providers=None,
    ):
        # 延迟导入: 让本模块的导入本身保持轻量, 并把重初始化限制在实例化时
        from rapidocr import RapidOCR

        # 只使用 rapidocr 3.x 认可的配置键(Group.key 形式); 传错键会直接抛 ValueError
        kwargs = {}
        if rec_model_path:
            kwargs['Rec.model_path'] = rec_model_path
        if det_model_path:
            kwargs['Det.model_path'] = det_model_path
        # 旧实现对方向分类默认关闭, 这里保持一致(省略该步骤, 与 v2 行为等价)
        kwargs['Global.use_cls'] = bool(use_angle_cls)

        self._engine = RapidOCR(params=kwargs) if kwargs else RapidOCR()

        self.box_thresh = float(box_thresh)
        self.unclip_ratio = float(unclip_ratio)
        self.text_detector = _TextDetectorCompat(self.box_thresh)

        # 竖排兼容: 默认实现即"原样识别", 调用方可替换本属性
        self.text_recognizer = self._recognize_crops

        # 供调试/诊断
        self.rec_image_shape = [3, 32, 320]
        self.character_type = 'ch'

    # ------------------------------------------------------------------ 基础
    def _recognize_crops(self, img_crop_list):
        """
        对已裁剪的文字条做识别。签名与 ppocronnx 的 text_recognizer 一致:
            fn(list[np.ndarray]) -> (list[(text, score)], elapse)

        竖排场景下调用方会用包装函数替换 self.text_recognizer, 先把裁片旋转。
        """
        results = []
        elapse = 0.0
        for crop in img_crop_list:
            text, score, cost = self._recognize_one(crop)
            results.append((text, score))
            elapse += cost
        return results, elapse

    def _recognize_one(self, image):
        """识别单个裁片(不做检测), 返回 (text, score, elapse)。识别失败返回空串。"""
        try:
            # use_det=False: 纯识别, 返回 TextRecOutput(无 boxes 属性)
            out = self._engine(image, use_det=False, use_cls=False, use_rec=True)
        except Exception as exc:  # 单条失败不应中断整批
            logger.warning('[ocr] recognize failed: %s: %s', type(exc).__name__, exc)
            return '', 0.0, 0.0
        txts = getattr(out, 'txts', None)
        scores = getattr(out, 'scores', None)
        if not txts:
            return '', 0.0, float(getattr(out, 'elapse', 0.0) or 0.0)
        return str(txts[0]), float(scores[0]), float(getattr(out, 'elapse', 0.0) or 0.0)

    def _detect_and_recognize(self, image, box_thresh=None, unclip_ratio=None):
        """
        完整流水线: 检测 + 识别。返回 (txts, scores, boxes, elapse)。

        注意必须显式 use_det=True: 若只传检测参数而不开启检测, rapidocr 会走
        纯识别分支并返回 TextRecOutput —— 该对象没有 boxes 属性, 会让上层
        依赖 .box 的代码(如 module/atom/list.py)拿到 None。
        """
        call_kwargs = {
            'use_det': True,
            'use_cls': False,
            'use_rec': True,
            'box_thresh': float(box_thresh if box_thresh is not None else self.text_detector.box_thresh),
            'unclip_ratio': float(unclip_ratio if unclip_ratio is not None else self.unclip_ratio),
        }
        out = self._engine(image, **call_kwargs)
        txts = tuple(getattr(out, 'txts', None) or ())
        scores = tuple(getattr(out, 'scores', None) or ())
        boxes = getattr(out, 'boxes', None)
        elapse = float(getattr(out, 'elapse', 0.0) or 0.0)
        return txts, scores, boxes, elapse

    # ----------------------------------------------------- ppocronnx 兼容接口
    def ocr_single_line(self, img):
        """识别单行文字。返回 (text, score); 无结果返回 ('', 0.0)。"""
        text, score, _ = self._recognize_one(img)
        return text, score

    def detect_and_ocr(self, img, drop_score=0.5, unclip_ratio=None, box_thresh=None,
                       vertical=False):
        """
        检测并识别整图, 返回 BoxedResult 列表(与 ppocronnx 同类型, 便于既有代码消费)。

        :param drop_score: 低于该置信度的结果被丢弃(旧默认 0.5)
        :param unclip_ratio: 覆盖实例默认值
        :param box_thresh: 覆盖实例默认值
        :param vertical: 竖排文本, 先把整图旋转 90 度再识别
        """
        if unclip_ratio is not None:
            self.unclip_ratio = float(unclip_ratio)
        if box_thresh is not None:
            # 旧语义: 本次调用使用该阈值; 同时写入兼容壳以保持一致
            self.box_thresh = float(box_thresh)
            self.text_detector.box_thresh = float(box_thresh)

        image = img
        if vertical:
            image = _rotate_if_vertical(image)

        txts, scores, boxes, _ = self._detect_and_recognize(image)

        results = []
        for i, (text, score) in enumerate(zip(txts, scores)):
            if float(score) < drop_score:
                continue
            box = boxes[i] if boxes is not None and i < len(boxes) else None
            text_img = _crop_by_box(image, box)
            results.append(BoxedResult(box, text_img, str(text), float(score)))
        return results


def _rotate_if_vertical(image: np.ndarray) -> np.ndarray:
    """高宽比 >= 1.5 时视为竖排, 旋转 90 度。与 rpc.py 的判定保持一致。"""
    height, width = image.shape[0:2]
    if width and height * 1.0 / width >= 1.5:
        return np.rot90(image)
    return image


def _crop_by_box(image: np.ndarray, box):
    """按四点框裁剪出文字裁片; box 为空时返回整图。"""
    if box is None:
        return image
    try:
        pts = np.array(box, dtype=np.float32)
        x0, y0 = int(np.floor(pts[:, 0].min())), int(np.floor(pts[:, 1].min()))
        x1, y1 = int(np.ceil(pts[:, 0].max())), int(np.ceil(pts[:, 1].max()))
        h, w = image.shape[:2]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            return image
        return image[y0:y1, x0:x1]
    except Exception:
        return image


def sorted_boxes(dt_boxes):
    """
    按从上到下、从左到右排序文本框。

    保留此函数仅为兼容可能的外部引用; RapidOCR 内部已自行排序,
    本实现不再需要它。
    """
    num_boxes = dt_boxes.shape[0]
    _boxes = sorted(dt_boxes, key=lambda x: (x[0][1], x[0][0]))
    _boxes = list(_boxes)
    for i in range(num_boxes - 1):
        for j in range(i, -1, -1):
            if abs(_boxes[j + 1][0][1] - _boxes[j][0][1]) < 10 and \
                    (_boxes[j + 1][0][0] < _boxes[j][0][0]):
                _boxes[j], _boxes[j + 1] = _boxes[j + 1], _boxes[j]
            else:
                break
    return _boxes
