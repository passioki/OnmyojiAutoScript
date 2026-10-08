# -*- coding: utf-8 -*-
"""看动态加载的 dex 与 test.apk 里到底有什么(注入载荷)。"""
import io
import re
import zipfile
from pathlib import Path

APK = Path(r'C:\Users\Win~Win~Win~\Downloads\大狮0802a-伪装输入法.apk')
z = zipfile.ZipFile(APK)


def dump_dex(dex: bytes, title: str, limit=40):
    print('=' * 90)
    print(f'{title}   ({len(dex)} B)')
    print('=' * 90)
    classes = sorted({m.decode('ascii', 'replace') for m in
                      re.findall(rb'L[A-Za-z0-9_/$]{4,90};', dex)})
    # 只显示非 java/ 非 android/ 的"业务类"
    biz = [c for c in classes
           if not c.startswith(('Ljava/', 'Landroid/', 'Ldalvik/',
                                'Lorg/xml', 'Lorg/json', 'Ljavax/'))]
    print(f'  业务类 ({len(biz)}/{len(classes)}):')
    for c in biz[:limit]:
        print(f'    {c}')
    if len(biz) > limit:
        print(f'    ... 共 {len(biz)} 个')
    print()
    print('  关键 API:')
    KEYS = [b'AccessibilityService', b'dispatchGesture', b'GestureDescription',
            b'MediaProjection', b'createScreenCaptureIntent', b'ImageReader',
            b'VirtualDisplay', b'SurfaceControl', b'screencap',
            b'injectInputEvent', b'INJECT_EVENTS', b'InputManager',
            b'MotionEvent', b'sendPointerSync', b'WindowManager',
            b'InputMethodService', b'InputConnection',
            b'System.loadLibrary', b'loadLibrary', b'su', b'Runtime.exec',
            b'ProcessBuilder', b'substrate', b'MSHook']
    for k in KEYS:
        n = dex.count(k)
        if n:
            print(f'    {k.decode("ascii","replace"):<32} {n}')
    print()


# 1) AdDex
dump_dex(z.read('assets/AdDex.4.0.1.dex'), 'assets/AdDex.4.0.1.dex')

# 2) test.apk 里的 classes.dex
data = z.read('assets/inject/test.apk')
zz = zipfile.ZipFile(io.BytesIO(data))
for n in zz.namelist():
    if n.endswith('.dex'):
        dump_dex(zz.read(n), f'assets/inject/test.apk -> {n}')

# 3) test.apk 的 manifest: 有没有注册 AccessibilityService
print('=' * 90)
print('assets/inject/test.apk 的 AndroidManifest — 是否注册无障碍服务')
print('=' * 90)
raw = zz.read('AndroidManifest.xml')
print(f'  manifest {len(raw)} B')
for key in (b'BIND_ACCESSIBILITY_SERVICE', b'BIND_INPUT_METHOD',
            b'accessibilityservice', b'AccessibilityService',
            b'android.permission', b'service', b'INJECT_EVENTS',
            b'SYSTEM_ALERT_WINDOW'):
    n8 = raw.count(key)
    n16 = raw.count(key.decode().encode('utf-16-le'))
    if n8 or n16:
        print(f'    {key.decode():<34} utf8={n8} utf16={n16}')

# 4) DaemonClient.zip
print()
print('=' * 90)
print('assets/DaemonClient.zip 内容')
print('=' * 90)
try:
    zz2 = zipfile.ZipFile(io.BytesIO(z.read('assets/DaemonClient.zip')))
    for n in zz2.namelist()[:25]:
        print(f'    {n:<50} {zz2.getinfo(n).file_size:>9} B')
except Exception as e:
    print(f'    非 zip: {e}')

# 5) OnewaySdk.jar
print()
print('=' * 90)
print('assets/ow/OnewaySdk.jar 内容(前 20)')
print('=' * 90)
try:
    zz3 = zipfile.ZipFile(io.BytesIO(z.read('assets/ow/OnewaySdk.jar')))
    for n in zz3.namelist()[:20]:
        print(f'    {n}')
except Exception as e:
    print(f'    非 zip: {e}')
