# -*- coding: utf-8 -*-
"""解剖 hookzygote.apk 的 DEX —— 它只有 25KB, 能看清到底 hook 了什么。"""
import io
import re
import zipfile
from pathlib import Path

APK = Path(r'C:\Users\Win~Win~Win~\Downloads\大狮0802a-伪装输入法.apk')
z = zipfile.ZipFile(APK)

for entry in ('assets/injectModifyCaptureMode/HigherThanAndroid9/hookzygote.apk',
              'assets/injectModifyCaptureMode/LowerThanAndroid9/hookzygote.apk'):
    data = z.read(entry)
    zz = zipfile.ZipFile(io.BytesIO(data))
    dex = zz.read('classes.dex')
    print('=' * 90)
    print(f'{entry.split("/")[-2]} / hookzygote.apk   DEX {len(dex)} B')
    print('=' * 90)

    # 类名
    classes = sorted({m.decode('ascii', 'replace') for m in
                      re.findall(rb'L[A-Za-z0-9_/$]{4,90};', dex)})
    print(f'  类名 ({len(classes)} 个):')
    for c in classes:
        print(f'    {c}')

    # 方法名/字段名(粗略)
    print()
    print('  关键 API 字符串:')
    KEYS = [
        b'MSHookFunction', b'substrate', b'Substrate', b'hook',
        b'zygote', b'Zygote', b'app_process', b'ptrace',
        b'MediaProjection', b'createScreenCaptureIntent', b'VirtualDisplay',
        b'SurfaceControl', b'Surface', b'ImageReader', b'screencap',
        b'injectInputEvent', b'INJECT_EVENTS', b'InputManager',
        b'MotionEvent', b'dispatchGesture', b'AccessibilityService',
        b'System.loadLibrary', b'loadLibrary', b'System.load',
        b'Method', b'Field', b'ClassLoader', b'reflect',
        b'com.android.internal', b'android.view', b'android.hardware',
        b'service', b'Service', b'Binder', b'IBinder',
        b'ActivityManager', b'WindowManager', b'PackageManager',
        b'setAccessible', b'AccessibilityNodeInfo',
    ]
    for k in KEYS:
        n = dex.count(k)
        if n:
            print(f'    {k.decode("ascii", "replace"):<34} {n}')

    # 方法签名字符串(通常是 (参数)返回值)
    sigs = sorted({m.decode('ascii', 'replace') for m in
                   re.findall(rb'\([^)]{0,60}\)[A-Za-z0-9_/$;]{0,80}', dex)})
    print()
    print(f'  方法签名片段 ({len(sigs)} 个, 前 25):')
    for s in sigs[:25]:
        print(f'    {s}')

    # 可读的中文/英文常量
    texts = sorted({m.decode('utf-8', 'replace') for m in
                    re.findall(rb'[\x20-\x7e]{6,60}', dex)})
    interesting = [t for t in texts if any(
        w in t.lower() for w in ('hook', 'inject', 'screencap', 'virtual',
                                 'projection', 'surface', 'zygote', 'input',
                                 'touch', 'gesture', 'reflect', 'native'))]
    print()
    print(f'  可疑可读字符串:')
    for t in interesting[:35]:
        print(f'    {t}')
    print()
