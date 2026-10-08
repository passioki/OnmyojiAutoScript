# -*- coding: utf-8 -*-
"""安卓布局诊断 —— 求解"手机画面"与"OAS 基准 1280x720"之间的坐标关系。

## 用途

OAS 的全部资产（**1,935 条规则 + 1,926 张模板图**）都基于硬编码的 1280x720。
若要让 OAS 跑在真机上（与游戏同机共存），必须先回答:

    **手机上的画面, 能否与 1280x720 建立确定的坐标关系?**

本脚本给出定量答案。

## 方法（三层，逐层加强）

1. **尺寸/比例/边条** —— 看游戏是"保持 16:9 留黑边"还是"拉满全屏"
2. **逐条带配准** —— 把基准图按高度比放大成整行条带, 在手机图上滑动求最佳偏移。
   ★ 这是最可靠的一层: 用整行 1920x60 像素做准全局配准, 远胜单模板匹配
3. **全局模板匹配** —— 在整幅手机图里搜基准图的小块, 交叉验证

## 输出

    x_phone = sx * x_base + ox
    y_phone = sy * y_base + oy

若 `sx ≈ sy`（等比缩放）且各条带偏移一致, 则**坐标可换算复用**,
即不必重标那 1,935 条规则。

## 用法

    python dev_tools/diag_android_layout.py <手机截图> <模拟器截图>

两张图必须拍**同一个界面**（推荐庭院, 且同一账号）, 否则结论无意义。
"""
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


def load_gray(path) -> np.ndarray:
    im = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if im is None:
        # 可能是中文路径或非 ASCII, 用 PIL 兜底
        from PIL import Image
        im = np.asarray(Image.open(path).convert('L'))
    return im


def describe(name, img):
    h, w = img.shape
    from math import gcd
    g = gcd(w, h)
    print(f'  {name}: {w}x{h}   宽高比 {w/g:.0f}:{h/g:.0f} = {w/h:.4f}')
    return w, h


def find_bars(img, flat_thresh=3.0):
    """找四周的平坦边条(纯色/黑边)。返回 (左, 右, 上, 下)。"""
    h, w = img.shape
    col_std = img.std(axis=0)
    row_std = img.std(axis=1)

    def run(arr, reverse=False):
        n = 0
        it = range(len(arr) - 1, -1, -1) if reverse else range(len(arr))
        for i in it:
            if arr[i] < flat_thresh:
                n += 1
            else:
                break
        return n

    return run(col_std), run(col_std, True), run(row_std), run(row_std, True)


def band_align(base, phone, scale, band_h=40, step=3):
    """
    核心: 逐条带求最佳水平偏移。

    :param scale: 缩放系数(应由高度比给出)
    :return: [(base_y, offset, mad, second_offset, second_mad)]
    """
    bh, bw = base.shape
    out = []
    for ey in range(0, bh - band_h, 60):
        band = base[ey:ey + band_h, :]
        scaled = cv2.resize(band, (int(bw * scale), int(band_h * scale)),
                            interpolation=cv2.INTER_LANCZOS4)
        th, tw = scaled.shape
        py = int(ey * scale)
        if py + th > phone.shape[0] or tw > phone.shape[1]:
            break
        s = scaled.astype(np.float32)
        s = (s - s.mean()) / (s.std() + 1e-6)

        scored = []
        for off in range(0, phone.shape[1] - tw + 1, step):
            seg = phone[py:py + th, off:off + tw].astype(np.float32)
            seg = (seg - seg.mean()) / (seg.std() + 1e-6)
            scored.append((float(np.abs(s - seg).mean()), off))
        scored.sort()
        out.append((ey, scored[0][1], scored[0][0],
                    scored[1][1], scored[1][0]))
    return out


def global_match(base, phone, scale, ts=70, conf=0.5):
    """在整幅手机图里搜基准图小块的全局最优位置(交叉验证)。"""
    bh, bw = base.shape
    out = []
    for gy in range(0, bh - ts, 110):
        for gx in range(0, bw - ts, 150):
            t = base[gy:gy + ts, gx:gx + ts]
            if t.std() < 12:
                continue
            t2 = cv2.resize(t, (int(ts * scale), int(ts * scale)),
                            interpolation=cv2.INTER_LANCZOS4)
            res = cv2.matchTemplate(phone, t2, cv2.TM_CCOEFF_NORMED)
            _, mx, _, loc = cv2.minMaxLoc(res)
            if mx < conf:
                continue
            out.append((gx, gy, loc[0], loc[1], float(mx)))
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    phone_p, base_p = Path(sys.argv[1]), Path(sys.argv[2])
    if not phone_p.exists():
        print(f'手机截图不存在: {phone_p}')
        return 1
    if not base_p.exists():
        print(f'基准截图不存在: {base_p}')
        return 1

    phone = load_gray(phone_p)
    base = load_gray(base_p)

    print('=' * 88)
    print('1. 尺寸与比例')
    print('=' * 88)
    pw, ph = describe('手机', phone)
    bw, bh = describe('基准(OAS 1280x720 应为 1280x720)', base)
    print()
    if (bw, bh) != (1280, 720):
        print(f'  !! 基准图不是 1280x720(OAS 的硬编码基准), 结论不可直接套用')
    print(f'  高度比 phone/base = {ph / bh:.4f}')

    print()
    print('=' * 88)
    print('2. 边条检测(判断是否留黑边)')
    print('=' * 88)
    l, r, t, b = find_bars(phone)
    print(f'  手机图平坦边条: 左 {l}  右 {r}  上 {t}  下 {b}')
    if max(l, r, t, b) > 10:
        print('  -> 检测到边条: 游戏**保持比例**(letterbox)')
    else:
        print('  -> 无侧边条: 游戏**铺满**整个屏幕')

    print()
    print('=' * 88)
    print('3. 逐条带配准(核心证据)')
    print('=' * 88)
    scale = ph / bh
    rows = band_align(base, phone, scale)
    print(f'  缩放系数取高度比 {scale:.4f}')
    print()
    print(f'  {"基准y":<8}{"最佳偏移":<10}{"MAD":<10}{"次优偏移":<10}'
          f'{"差值":<10}判读')
    print('  ' + '-' * 84)
    expect = (pw - int(bw * scale)) / 2
    for ey, off, mad, off2, mad2 in rows:
        if abs(off) < 8:
            j = '贴左'
        elif abs(off - expect) < 20:
            j = f'居中(+{expect:.0f})'
        else:
            j = '其它'
        print(f'  {ey:<8}{off:<10}{mad:<10.4f}{off2:<10}{mad2-mad:<10.4f}{j}')

    print()
    offs = [r[1] for r in rows]
    hist = Counter()
    for o in offs:
        if abs(o) < 8:
            hist['贴左(0)'] += 1
        elif abs(o - expect) < 20:
            hist[f'居中(+{expect:.0f})'] += 1
        else:
            hist[f'其它({o})'] += 1
    print(f'  偏移分布: {dict(hist)}')
    print(f'  中位偏移: {np.median(offs):.0f}')

    print()
    print('=' * 88)
    print('4. 全局模板匹配(交叉验证)')
    print('=' * 88)
    gm = global_match(base, phone, scale)
    hits = Counter()
    for gx, gy, fx, fy, mx in gm:
        pred = gx * scale + expect
        if abs(fx - pred) < 25:
            hits['居中'] += 1
        elif abs(fx - gx * scale) < 25:
            hits['贴左'] += 1
        else:
            hits['其它'] += 1
    print(f'  有效样本 {len(gm)}')
    print(f'  分布: {dict(hits)}')
    if gm:
        print(f'  相似度: 均值 {np.mean([g[4] for g in gm]):.3f}  '
              f'最高 {max(g[4] for g in gm):.3f}')

    print()
    print('=' * 88)
    print('结论')
    print('=' * 88)
    center_wins = hist.get(f'居中(+{expect:.0f})', 0)
    total = max(1, len(rows))
    if center_wins >= total * 0.8:
        print(f'  ✓ 手机画面 = 基准图 × {scale:.4f} ，居中')
        print(f'      x_phone = {scale:.4f} * x_base + {expect:.0f}')
        print(f'      y_phone = {scale:.4f} * y_base')
        print()
        print('  ★ 坐标可**换算复用** —— 不必重标 1,935 条规则。')
        print('     建议做法: 在设备层做"裁剪 + 缩放", 让 assets.py 保持 1280x720:')
        print()
        print('     【截图侧】把手机画面还原成 1280x720:')
        print(f'        crop({expect:.0f}, 0, {expect + bw*scale:.0f}, {ph})'
              f'  ->  {int(bw*scale)}x{ph}  ->  resize 到 1280x720')
        print()
        print('     【点击侧】把 1280x720 坐标换算到手机坐标:')
        print(f'        x_phone = {scale:.4f} * x_base + {expect:.0f}')
        print(f'        y_phone = {scale:.4f} * y_base')
        print('        (反向, 若需要: x_base = (x_phone - '
              f'{expect:.0f}) / {scale:.4f})')

        # 关键提醒: 反向换算的**顺序**容易写错
        print()
        print('     ⚠ 注意顺序: 是"先减偏移再除以缩放", 即 (x - 210) / 1.5;')
        print('        写成 (x / 1.5) - 210 是**错的**(差了 210/1.5 = 140 像素)。')
    else:
        print(f'  ✗ 偏移不一致(居中仅 {center_wins}/{total}) —— 画面可能被**重排**。')
        print('     若确认重排, 现有 1,935 条规则与 1,926 张模板图都需重做。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
