# -*- coding: utf-8 -*-
"""
扫描全仓规则，报告在当前截图上命中的规则，用于定位"能代表当前界面"的模板。

用途: UI 改版或需要新判据时, 先看现有哪些模板真的命中, 而不是凭名字猜。
默认按分数排序输出前 N 条, 并可只看某个任务/组件下的规则。

用法:
    python dev_tools/find_matching_assets.py --image shot.png
    python dev_tools/find_matching_assets.py --image shot.png --top 40
    python dev_tools/find_matching_assets.py --image shot.png --filter Battle
"""
import argparse
import importlib
import inspect
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 读图复用仓库既有实现(内部 BGR2RGB), 与 RuleImage 的模板同颜色空间。
# 自写 cv2.imdecode(..., IMREAD_COLOR) 会得到 BGR, 与 RGB 模板错配,
# 使所有分数被系统性压低且不报错(实测 1.0000 会被压到 0.8151)。
from dev_tools.assets_test import load_image  # noqa: E402


def load_shot(path: str):
    """读取截图, 复用 assets_test.load_image 以保证颜色空间一致。"""
    img = load_image(str(path), strict_size=False)
    if img is None:
        raise SystemExit(f'无法解码: {path}')
    if img.shape[:2] != (720, 1280):
        print(f'提示: {path} 尺寸为 {img.shape[1]}x{img.shape[0]}, '
              f'而非 OAS 坐标系 1280x720, 结果可能不可比', file=sys.stderr)
    return img


def iter_rules(filter_kw: str | None):
    """产出 (模块名, 类名, 规则名, RuleImage)。"""
    from module.atom.image import RuleImage
    for ap in sorted((REPO_ROOT / 'tasks').rglob('assets.py')):
        mod_name = '.'.join(ap.relative_to(REPO_ROOT).with_suffix('').parts)
        if filter_kw and filter_kw.lower() not in mod_name.lower():
            continue
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for cls_name, cls in list(vars(mod).items()):
            if not inspect.isclass(cls) or cls.__module__ != mod_name:
                continue
            for attr in dir(cls):
                obj = getattr(cls, attr, None)
                if isinstance(obj, RuleImage):
                    yield mod_name, cls_name, attr, obj


def main() -> int:
    import cv2
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--top', type=int, default=30)
    ap.add_argument('--filter', default=None, help='只扫描模块名含该子串的规则')
    ap.add_argument('--all', action='store_true', help='列出全部命中而非仅前 N 条')
    args = ap.parse_args()

    img = load_shot(args.image)
    print(f'图片: {args.image}  尺寸 {img.shape[1]}x{img.shape[0]}')
    print()

    hits = []
    errors = 0
    total = 0
    for mod_name, cls_name, attr, rule in iter_rules(args.filter):
        total += 1
        try:
            source = rule.corp(img)
            mat = rule.image
        except Exception:
            errors += 1
            continue
        if mat is None:
            errors += 1
            continue
        th, tw = mat.shape[:2]
        sh, sw = source.shape[:2]
        if sh < th or sw < tw:
            continue
        res = cv2.matchTemplate(source, mat, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        score = float(max_val)
        thres = float(rule.threshold)
        if score >= thres:
            hits.append((score, thres, mod_name, attr,
                         (int(max_loc[0] + rule.roi_back[0]), int(max_loc[1] + rule.roi_back[1])),
                         tuple(int(v) for v in rule.roi_back)))

    hits.sort(reverse=True)
    print(f'扫描 {total} 条规则, 读取失败 {errors} 条, 命中 {len(hits)} 条')
    print()
    print('%-8s %-7s %-28s %-30s %-14s %s' % ('score', '阈值', '模块', '规则', 'hit_xy', 'roi_back'))
    print('-' * 118)
    shown = hits if args.all else hits[:args.top]
    for score, thres, mod_name, attr, xy, roi in shown:
        short = mod_name.replace('tasks.', '').replace('.assets', '')
        print('%-8.4f %-7.2f %-28s %-30s %-14s %s' % (score, thres, short, attr, str(xy), roi))
    if not args.all and len(hits) > args.top:
        print(f'... 另有 {len(hits) - args.top} 条命中, 用 --all 查看')
    return 0


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    raise SystemExit(main())
