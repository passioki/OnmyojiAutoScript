# -*- coding: utf-8 -*-
"""APK 静态诊断 —— 判断一个安卓自动化工具**用什么方式注入触摸/截图**。

## 用途

分析同类产品(如"按键精灵"类工具)的实现路线, 用于**技术选型参考**。
例: 分析"大狮"发现它走的是 **zygote 注入 + 无障碍 + 输入法外壳** 三合一,
而不是单纯的无障碍 —— 这直接影响"我们该走哪条路"的判断。

## 方法(纯静态, **不反编译代码**)

只读**资产文件名、原生库名、DEX 字符串表**, 因此结论是**线索级**而非确证级。
本工具会明确区分"强证据"与"推测"。

判据:
  * `assets/**/inject*`、`hookzygote.apk`、`ptrace`/`zygote` 字符串 -> 进程注入
  * `BIND_ACCESSIBILITY_SERVICE` / `AccessibilityService`       -> 无障碍
  * `BIND_INPUT_METHOD` / `InputMethodService`                  -> 输入法
  * `SYSTEM_ALERT_WINDOW` / `WindowManager$LayoutParams`        -> 悬浮窗
  * `MediaProjection` / `VirtualDisplay` / `screencap`          -> 截图方式
  * ABI 目录(x86 / x86_64 / armeabi-v7a / arm64-v8a)            -> 支持真机还是仅模拟器

## 用法

    python dev_tools/diag_apk.py <apk 路径>
"""
import io
import re
import sys
import zipfile
from pathlib import Path

# DEX 里值得关注的 API 线索
DEX_KEYS = [
    # 注入 / hook
    b'MSHookFunction', b'substrate', b'ptrace', b'zygote', b'Zygote',
    b'app_process', b'DexClassLoader', b'attachBaseContext',
    b'injectInputEvent', b'INJECT_EVENTS',
    # 无障碍
    b'AccessibilityService', b'dispatchGesture', b'GestureDescription',
    b'performGlobalAction', b'AccessibilityNodeInfo',
    # 输入法
    b'InputMethodService', b'onCreateInputView', b'InputConnection',
    b'commitText', b'sendKeyEvent',
    # 悬浮窗
    b'SYSTEM_ALERT_WINDOW', b'WindowManager', b'addView',
    b'TYPE_APPLICATION_OVERLAY',
    # 截图
    b'MediaProjection', b'createScreenCaptureIntent', b'ImageReader',
    b'VirtualDisplay', b'SurfaceControl', b'screencap',
    # 触摸
    b'MotionEvent', b'sendPointerSync', b'Instrumentation',
    # root
    b'/system/bin/su', b'Runtime.exec', b'ProcessBuilder',
]
ABIS = ('x86', 'x86_64', 'armeabi-v7a', 'arm64-v8a', 'armeabi')

# 资产名里的关键词 -> 结论
ASSET_HINTS = (
    ('inject', '进程注入资产'),
    ('hook', 'hook 相关'),
    ('zygote', 'zygote 注入'),
    ('virt', '虚拟显示(截图)'),
    ('substrate', 'Cydia Substrate hook 框架'),
    ('projection', 'MediaProjection 截图'),
)


def dex_strings(data: bytes) -> dict:
    return {k.decode('ascii', 'replace'): data.count(k)
            for k in DEX_KEYS if data.count(k)}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    apk_path = Path(sys.argv[1])
    if not apk_path.exists():
        print(f'APK 不存在: {apk_path}')
        return 1

    z = zipfile.ZipFile(apk_path)
    names = z.namelist()
    print('=' * 90)
    print(f'{apk_path.name}   {apk_path.stat().st_size/1024/1024:.1f} MB   '
          f'{len(names)} 条目')
    print('=' * 90)

    # ---------------- manifest ----------------
    print()
    print('【1】AndroidManifest 关键声明')
    raw = z.read('AndroidManifest.xml') if 'AndroidManifest.xml' in names else b''

    def axml_has(key: str) -> bool:
        b = key.encode()
        return bool(raw.count(b) or raw.count(b.decode().encode('utf-16-le')))

    checks = [
        ('注册为输入法', 'BIND_INPUT_METHOD'),
        ('注册为无障碍服务', 'BIND_ACCESSIBILITY_SERVICE'),
        ('申请悬浮窗', 'SYSTEM_ALERT_WINDOW'),
        ('申请 INJECT_EVENTS', 'INJECT_EVENTS'),
        ('申请 WRITE_SECURE_SETTINGS', 'WRITE_SECURE_SETTINGS'),
        ('跨用户权限', 'INTERACT_ACROSS_USERS_FULL'),
        ('可安装包', 'REQUEST_INSTALL_PACKAGES'),
    ]
    for label, key in checks:
        print(f'  {"✓ 是" if axml_has(key) else "✗ 否"}   {label:<26} ({key})')

    # ---------------- ABI ----------------
    print()
    print('【2】注入资产的 ABI 覆盖(决定能否用于真机)')
    abi_files = {a: [] for a in ABIS}
    for n in names:
        if 'inject' not in n.lower():
            continue
        for a in ABIS:
            if f'/{a}/' in n:
                abi_files[a].append(n.split('/')[-1])
    for a in ABIS:
        if abi_files[a]:
            print(f'  {a:<14} {sorted(set(abi_files[a]))}')
    has_arm = bool(abi_files['arm64-v8a'] or abi_files['armeabi-v7a']
                   or abi_files['armeabi'])
    has_x86 = bool(abi_files['x86'] or abi_files['x86_64'])
    print()
    if has_arm and has_x86:
        print('  -> 含 ARM: **理论支持真机**')
    elif has_x86:
        print('  -> 只有 x86: **仅支持模拟器**(真机是 ARM, 无法执行 x86 机器码)')
    else:
        print('  -> (未找到注入资产)')

    # ---------------- 资产 ----------------
    print()
    print('【3】可疑资产(名字即线索)')
    shown = 0
    for n in sorted(names):
        low = n.lower()
        if not any(h in low for h in
                   ('inject', 'hook', 'zygote', 'virt', 'substrate',
                    'projection', 'script.')):
            continue
        try:
            sz = z.getinfo(n).file_size
        except Exception:
            continue
        if sz < 5_000:
            continue
        hint = next((d for k, d in ASSET_HINTS if k in low), '')
        print(f'  {n:<64} {sz/1024:>9.1f} KB  {hint}')
        shown += 1
        if shown >= 30:
            print('  ... (更多省略)')
            break

    # ---------------- 原生库 ----------------
    print()
    print('【4】原生库(.so)')
    sos = sorted({n.split('/')[-1] for n in names if n.endswith('.so')})
    for s in sos:
        print(f'  {s}')
    if not sos:
        print('  (无)')

    # ---------------- DEX ----------------
    print()
    print('【5】DEX 里的关键 API 线索')
    for n in names:
        if not n.endswith('.dex'):
            continue
        data = z.read(n)
        found = dex_strings(data)
        if not found:
            continue
        print(f'  --- {n} ({len(data)/1024/1024:.1f} MB) ---')
        for k, v in sorted(found.items(), key=lambda x: -x[1]):
            print(f'      {k:<32} {v}')

    # ---------------- 内嵌 APK/DEX ----------------
    print()
    print('【6】内嵌的 APK / DEX(常为"被注入的载荷")')
    for n in sorted(names):
        if not n.lower().endswith(('.apk', '.dex')):
            continue
        if n.endswith('.dex') and n.count('/') == 0:
            continue
        try:
            sz = z.getinfo(n).file_size
        except Exception:
            continue
        print(f'  {n:<62} {sz/1024:>9.1f} KB')
        if n.lower().endswith('.apk'):
            try:
                zz = zipfile.ZipFile(io.BytesIO(z.read(n)))
                inner = zz.namelist()
                print(f'       内含: {inner[:6]}')
                for m in inner:
                    if m.endswith('.dex'):
                        d = dex_strings(zz.read(m))
                        cls = sorted({c.decode('ascii', 'replace') for c in
                                      re.findall(rb'L[A-Za-z0-9_/$]{6,70};',
                                                 zz.read(m))
                                      if b'android/' not in c
                                      and b'java/' not in c})[:12]
                        if cls:
                            print(f'       {m} 业务类: {cls}')
            except Exception as e:
                print(f'       (非 zip: {e})')

    # ---------------- 结论 ----------------
    print()
    print('=' * 90)
    print('结论(线索级 —— 本工具不反编译代码, 不做运行时验证)')
    print('=' * 90)
    routes = []
    if axml_has('BIND_INPUT_METHOD'):
        routes.append('输入法(外壳/伪装)')
    if axml_has('BIND_ACCESSIBILITY_SERVICE'):
        routes.append('无障碍服务')
    if has_arm or has_x86:
        routes.append('进程注入(root)')
    if axml_has('SYSTEM_ALERT_WINDOW'):
        routes.append('悬浮窗(仅显示)')
    for r in routes:
        print(f'  · {r}')
    print()
    print('  ⚠ 注意:')
    print('    · "伪装成输入法"**单独做不到点击** —— InputMethodService 的 API')
    print('      目标是"向输入框提交文本", 没有点击任意坐标的能力。')
    print('      真正能点别处 app 的是 AccessibilityService 或 INJECT_EVENTS(root)。')
    print('    · 本工具读的是**资产名与字符串**, 不能确定运行时实际走哪条路,')
    print('      也不能确定是否强制要求 root。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
