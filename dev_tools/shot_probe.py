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
    读图并旋转/缩放到 OAS 的 1280x720 坐标系。

    adb screencap 在竖屏模拟器上得到 720x1280, 旋转后才是 OAS 认的 1280x720。
    """
    import cv2
    import numpy as np
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f'无法解码图片: {path}')
    if img.shape[0] > img.shape[1]:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if img.shape[:2] != (720, 1280):
        img = cv2.resize(img, (1280, 720))
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


def match_rule(img, rule) -> dict:
    """对单条 RuleImage 做匹配, 返回分数等细节。"""
    import cv2
    from module.atom.image import RuleImage
    if not isinstance(rule, RuleImage):
        return {'error': f'不是 RuleImage: {type(rule).__name__}'}
    try:
        source = rule.corp(img)
        mat = rule.image
    except Exception as exc:
        return {'error': f'{type(exc).__name__}: {exc}'}
    th, tw = mat.shape[:2]
    sh, sw = source.shape[:2]
    if sh < th or sw < tw:
        return {
            'roi_back': tuple(int(v) for v in rule.roi_back),
            'template': (tw, th),
            'error': f'搜索区 {sw}x{sh} 装不下模板 {tw}x{th} -> 永不命中',
        }
    res = cv2.matchTemplate(source, mat, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    score = float(max_val)
    thres = float(rule.threshold)
    return {
        'roi_back': tuple(int(v) for v in rule.roi_back),
        'template': (tw, th),
        'threshold': thres,
        'score': round(score, 4),
        'matched': score >= thres,
        'hit_xy': (int(max_loc[0] + rule.roi_back[0]), int(max_loc[1] + rule.roi_back[1])),
    }


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------
def run_ocr(img, min_score: float = 0.5) -> list:
    """整屏 OCR, 返回 [(文本, x, y, w, h, score)]。"""
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
    """
    import cv2
    import numpy as np
    x, y, w, h = box
    sub = img[y:y + h, x:x + w]
    if sub.size == 0:
        return {'error': f'ROI 越界: {box}'}

    gray = cv2.cvtColor(sub, cv2.COLOR_BGR2GRAY)
    b, g, r = (float(sub[:, :, i].mean()) for i in range(3))
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
        'mean_bgr': (round(b, 1), round(g, 1), round(r, 1)),
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
    img = load_shot(args.image)
    print(f'图片: {args.image}  尺寸 {img.shape[1]}x{img.shape[0]}')
    print('%-40s %8s %7s %-6s %-16s %s' % ('规则', 'score', '阈值', '命中', 'hit_xy', '备注'))
    print('-' * 112)
    for dotted in args.rules:
        rule = resolve_rule(dotted)
        if rule is None:
            print('%-40s %s' % (dotted, '找不到该规则'))
            continue
        info = match_rule(img, rule)
        if 'score' not in info:
            print('%-40s %s' % (dotted, info.get('error', '未知错误')))
            continue
        print('%-40s %8.4f %7.2f %-6s %-16s %s' % (
            dotted, info['score'], info['threshold'],
            'YES' if info['matched'] else 'no',
            str(info['hit_xy']),
            '' if info['matched'] else '低于阈值'))
    return 0


def cmd_roi(args) -> int:
    img = load_shot(args.image)
    box = tuple(int(v) for v in args.box.split(','))
    info = analyze_roi(img, box, ascii_w=args.width)
    if 'error' in info:
        print(info['error'])
        return 1
    print(f"ROI {info['box']}  平均BGR={info['mean_bgr']}  亮度={info['brightness']} "
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
