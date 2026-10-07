# -*- coding: utf-8 -*-
"""
截图探针：抓图 + OCR + 批量模板匹配，用于 UI 变更后的资产维护。

设计背景: 本仓库的 agent 侧没有图像输入能力, 因此"看画面"只能靠
  1. OCR 读出可见文字(含坐标)
  2. 模板匹配给出相似度与阈值对比
  3. 指定 ROI 的像素统计(主色、亮度、边缘密度)与低分辨率 ASCII 预览
三者叠加足以定位"按钮在不在""模板是否漂移""UI 是否改版", 但不如人眼直观,
凡涉及审美/语义判断仍需人工确认。

用法:
    # 抓当前画面并存档
    python dev_tools/shot_probe.py capture --serial 127.0.0.1:16416

    # 对已有截图做 OCR
    python dev_tools/shot_probe.py ocr --image shot.png

    # 批量匹配规则  规则写法 Module.Attr 或 Module.Sub.Attr
    python dev_tools/shot_probe.py match --image shot.png GeneralBattle.I_PREPARE_HIGHLIGHT DemonEncounter.I_EXIT_13

    # 分析 ROI(像素统计 + ASCII 预览)  格式 x,y,w,h
    python dev_tools/shot_probe.py roi --image shot.png --box 0,0,120,120

    # 一次性体检: 抓图 + OCR + 指定规则 + 指定 ROI
    python dev_tools/shot_probe.py probe --serial 127.0.0.1:16416 --rules ... --box 0,0,120,120
"""
import argparse
import io
import logging
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 读图与单规则匹配一律复用仓库既有实现, 不自行重写:
#   assets_test.load_image        内部做 cvtColor(BGR2RGB), 与 RuleImage 的模板同空间
#   assets_test.detect_image_detail  即标注器"测试"按钮走的判定路径
# 自行用 cv2.imdecode(..., IMREAD_COLOR) 会拿到 BGR, 与 RGB 模板错配, 分数被系统性
# 压低(实测同一张战斗截图: 正确口径 1.0000, 错配后 0.8151)且不报错, 极易误导。
from dev_tools.assets_test import load_image, detect_image_detail  # noqa: E402

ADB = REPO_ROOT / 'toolkit' / 'Lib' / 'site-packages' / 'adbutils' / 'binaries' / 'adb.exe'
SHOT_DIR = REPO_ROOT / 'log' / 'probe'


# ---------------------------------------------------------------------------
# 基础: 截图与读图
# ---------------------------------------------------------------------------
def capture(serial: str, save: Path) -> Path:
    """
    用 adb screencap 抓一张图并 pull 回本地。

    :param serial: adb 串号, 如 127.0.0.1:16416
    :param save: 本地保存路径
    :return: 保存后的路径
    """
    save.parent.mkdir(parents=True, exist_ok=True)
    remote = '/sdcard/_oas_probe.png'
    subprocess.run([str(ADB), '-s', serial, 'shell', 'screencap', '-p', remote],
                   check=True, capture_output=True)
    subprocess.run([str(ADB), '-s', serial, 'pull', remote, str(save)],
                   check=True, capture_output=True)
    subprocess.run([str(ADB), '-s', serial, 'shell', 'rm', remote],
                   check=False, capture_output=True)
    return save


def load_shot(path: str):
    """
    读图, 直接复用 dev_tools/assets_test.load_image。

    它内部执行 cv2.cvtColor(BGR2RGB), 与 RuleImage 的模板处于同一颜色空间,
    因此产出的分数与 appear() / 标注器"测试"按钮一致。
    本仓库的截图(adb screencap 与标注器 capture)均已统一为 1280x720,
    无需再做旋转或缩放。
    """
    img = load_image(str(path), strict_size=False)
    if img is None:
        raise SystemExit(f'无法解码图片: {path}')
    if img.shape[:2] != (720, 1280):
        print(f'提示: {path} 尺寸为 {img.shape[1]}x{img.shape[0]}, '
              f'而非 OAS 坐标系 1280x720, 匹配结果可能不可比', file=sys.stderr)
    return img


# ---------------------------------------------------------------------------
# 规则解析与匹配
# ---------------------------------------------------------------------------
def resolve_rule(dotted: str):
    """把 'Module.Attr' 或 'Module.Sub.Attr' 解析成 RuleImage。"""
    import importlib
    parts = dotted.split('.')
    attr = parts[-1]
    mod_parts = parts[:-1]
    candidates = [
        'tasks.' + '.'.join(mod_parts) + '.assets',
        'tasks.Component.' + '.'.join(mod_parts) + '.assets',
        'tasks.' + '.'.join(mod_parts),
    ]
    for full in candidates:
        try:
            mod = importlib.import_module(full)
        except Exception:
            continue
        # 先找类属性
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and hasattr(obj, attr):
                return getattr(obj, attr)
        if hasattr(mod, attr):
            return getattr(mod, attr)
    return None


def match_rule(path_or_img, rule) -> dict:
    """
    对单条 RuleImage 做匹配, 直接委托给仓库的 assets_test.detect_image_detail
    (即标注器"测试"按钮走的同一条路径), 避免自写比较逻辑引入偏差。

    detect_image_detail 会在命中时改写 rule.roi_front, 因此这里先浅拷贝一份,
    避免污染调用方持有的规则对象。
    """
    import copy as _copy
    from module.atom.image import RuleImage
    if not isinstance(rule, RuleImage):
        return {'error': f'不是 RuleImage: {type(rule).__name__}'}
    detail = detect_image_detail(str(path_or_img), _copy.copy(rule))
    return {
        'roi_back': detail.get('roiBack'),
        'roi_front': detail.get('roiFront'),
        'threshold': float(rule.threshold),
        'score': float(detail.get('similarity', 0.0)),
        'matched': bool(detail.get('matched', False)),
        'message': detail.get('message', ''),
    }


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def run_ocr(img, min_score: float = 0.5) -> list:
    """
    整屏 OCR, 返回 [(文本, x, y, w, h, score)]。

    通道处理与仓库 assets_test.detect_ocr 一致: 直接把 load_image 产出的图交给
    OCR, 不额外转换(仓库自身在该路径上也不做 cvtColor)。
    """
    import numpy as np
    from module.ocr.ppocr import TextSystem
    ocr = TextSystem()
    out = []
    for item in ocr.detect_and_ocr(img):
        box = item.box
        x0, y0 = int(np.min(box[:, 0])), int(np.min(box[:, 1]))
        x1, y1 = int(np.max(box[:, 0])), int(np.max(box[:, 1]))
        score = float(item.score)
        if score < min_score:
            continue
        out.append((str(item.ocr_text), x0, y0, x1 - x0, y1 - y0, score))
    out.sort(key=lambda t: (t[2], t[1]))
    return out


# ---------------------------------------------------------------------------
# ROI 像素分析(无图像输入时的"看图"替代手段)
# ---------------------------------------------------------------------------
def analyze_roi(img, box, ascii_w: int = 60) -> dict:
    """
    对 ROI 做像素统计并给出 ASCII 预览。

    ASCII 预览用亮度分档映射到字符, 可在纯文本环境里看出大致结构(按钮轮廓、
    血条、图标位置), 这是没有图像输入能力时唯一能"看到"形状的办法。

    入参 img 是 RGB(见 load_shot); 灰度与 BGR 均值都按正确的通道顺序换算,
    否则 R/B 会被调换、灰度的通道权重也会反。
    """
    import cv2
    import numpy as np
    x, y, w, h = box
    sub = img[y:y + h, x:x + w]
    if sub.size == 0:
        return {'error': f'ROI 越界: {box}'}

    gray = cv2.cvtColor(sub, cv2.COLOR_RGB2GRAY)
    r, g, b = (float(sub[:, :, i].mean()) for i in range(3))  # RGB 顺序
    edges = cv2.Canny(gray, 60, 180)
    edge_density = float((edges > 0).mean())

    # 亮度分档 -> ASCII
    small = cv2.resize(gray, (ascii_w, max(1, int(ascii_w * h / w * 0.5))),
                       interpolation=cv2.INTER_AREA)
    ramp = ' .:-=+*#%@'
    lo, hi = float(small.min()), float(small.max())
    span = max(1.0, hi - lo)
    lines = []
    for row in small:
        lines.append(''.join(ramp[min(len(ramp) - 1, int((v - lo) / span * (len(ramp) - 1)))]
                             for v in row))

    return {
        'box': box,
        'mean_rgb': (round(r, 1), round(g, 1), round(b, 1)),
        'brightness': round(float(gray.mean()), 1),
        'std': round(float(gray.std()), 1),
        'edge_density': round(edge_density, 4),
        'ascii': lines,
    }


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
def cmd_capture(args) -> int:
    stamp = args.name or 'shot'
    save = SHOT_DIR / f'{stamp}_{args.serial.replace(":", "_").replace(".", "_")}.png'
    capture(args.serial, save)
    print(f'已保存: {save}  ({save.stat().st_size} 字节)')
    return 0


def cmd_ocr(args) -> int:
    img = load_shot(args.image)
    print(f'图片: {args.image}  尺寸 {img.shape[1]}x{img.shape[0]}')
    items = run_ocr(img, min_score=args.min_score)
    print('%-5s %-5s %-5s %-5s %s' % ('x', 'y', 'w', 'h', '文本(置信度)'))
    for text, x, y, w, h, score in items:
        print('%-5d %-5d %-5d %-5d %s (%.2f)' % (x, y, w, h, text, score))
    print(f'共 {len(items)} 个文本框')
    return 0


def cmd_match(args) -> int:
    print(f'图片: {args.image}')
    print('%-40s %9s %7s %-6s %-16s %s' % ('规则', 'score', '阈值', '命中', 'roi_front', '备注'))
    print('-' * 112)
    for dotted in args.rules:
        rule = resolve_rule(dotted)
        if rule is None:
            print('%-40s %s' % (dotted, '找不到该规则'))
            continue
        info = match_rule(args.image, rule)
        if 'score' not in info:
            print('%-40s %s' % (dotted, info.get('error', '未知错误')))
            continue
        print('%-40s %9.4f %7.2f %-6s %-16s %s' % (
            dotted, info['score'], info['threshold'],
            'YES' if info['matched'] else 'no',
            str(info.get('roi_front')),
            info.get('message', '')))
    return 0


def cmd_roi(args) -> int:
    img = load_shot(args.image)
    box = tuple(int(v) for v in args.box.split(','))
    info = analyze_roi(img, box, ascii_w=args.width)
    if 'error' in info:
        print(info['error'])
        return 1
    print(f"ROI {info['box']}  平均RGB={info['mean_rgb']}  亮度={info['brightness']} "
          f"标准差={info['std']}  边缘密度={info['edge_density']}")
    print('ASCII 预览(暗 -> 亮: " .:-=+*#%@")')
    for line in info['ascii']:
        print('  |' + line + '|')
    return 0


def cmd_probe(args) -> int:
    if args.serial:
        stamp = args.name or 'probe'
        save = SHOT_DIR / f'{stamp}_{args.serial.replace(":", "_").replace(".", "_")}.png'
        capture(args.serial, save)
        image = str(save)
        print(f'已抓图: {image}')
    else:
        image = args.image
    img = load_shot(image)
    print(f'图片: {image}  尺寸 {img.shape[1]}x{img.shape[0]}')

    if args.rules:
        print()
        cmd_match(argparse.Namespace(image=image, rules=args.rules))
    if args.box:
        print()
        cmd_roi(argparse.Namespace(image=image, box=args.box, width=args.width))
    if not args.no_ocr:
        print()
        cmd_ocr(argparse.Namespace(image=image, min_score=args.min_score))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description='截图探针: 抓图/OCR/模板匹配/ROI 分析')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('capture', help='抓一张当前画面')
    p.add_argument('--serial', required=True)
    p.add_argument('--name', default=None)
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser('ocr', help='对截图做 OCR')
    p.add_argument('--image', required=True)
    p.add_argument('--min-score', type=float, default=0.5)
    p.set_defaults(func=cmd_ocr)

    p = sub.add_parser('match', help='批量匹配规则')
    p.add_argument('--image', required=True)
    p.add_argument('rules', nargs='+')
    p.set_defaults(func=cmd_match)

    p = sub.add_parser('roi', help='分析 ROI 像素并输出 ASCII 预览')
    p.add_argument('--image', required=True)
    p.add_argument('--box', required=True, help='格式 x,y,w,h')
    p.add_argument('--width', type=int, default=60)
    p.set_defaults(func=cmd_roi)

    p = sub.add_parser('probe', help='抓图并一次性做规则匹配/ROI/OCR')
    p.add_argument('--serial', default=None)
    p.add_argument('--image', default=None)
    p.add_argument('--name', default=None)
    p.add_argument('--rules', nargs='*', default=[])
    p.add_argument('--box', default=None)
    p.add_argument('--width', type=int, default=60)
    p.add_argument('--min-score', type=float, default=0.5)
    p.add_argument('--no-ocr', action='store_true')
    p.set_defaults(func=cmd_probe)

    args = ap.parse_args()
    if args.cmd == 'probe' and not (args.serial or args.image):
        ap.error('probe 需要 --serial 或 --image')
    logging.disable(logging.CRITICAL)
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
