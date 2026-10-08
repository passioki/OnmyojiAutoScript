# -*- coding: utf-8 -*-
"""深挖: 确认输入法服务 + 找动态加载的插件。"""
import re
import zipfile
from pathlib import Path

APK = Path(r'C:\Users\Win~Win~Win~\Downloads\大狮0802a-伪装输入法.apk')
z = zipfile.ZipFile(APK)

print('=' * 88)
print('1. 从 AXML 字符串池直接搜 BIND_* (pyaxmlparser 可能漏掉)')
print('=' * 88)
raw = z.read('AndroidManifest.xml')
# 用宽字符与 UTF-8 两种方式找
for key in (b'BIND_INPUT_METHOD', b'BIND_ACCESSIBILITY_SERVICE',
            b'INJECT_EVENTS', b'InputKb', b'InputMethod',
            b'AccessibilityService', b'InputMethodService',
            b'android.view.InputChannel', b'MediaProjection'):
    n = raw.count(key)
    # UTF-16LE
    n16 = raw.count(key.decode().encode('utf-16-le'))
    if n or n16:
        print(f'  {key.decode():<28} UTF8={n}  UTF16={n16}')

print()
print('=' * 88)
print('2. assets / 目录里的可疑文件(被动态加载的插件?)')
print('=' * 88)
names = z.namelist()
for n in names:
    if n.startswith('assets/') and not n.endswith('/'):
        try:
            sz = z.getinfo(n).file_size
        except Exception:
            sz = 0
        if sz > 50_000:            # 只看较大的
            print(f'  {n:<60} {sz/1024:>10.1f} KB')

print()
print('=' * 88)
print('3. 所有 .apk / .jar / .dex / .zip 条目(插件候选)')
print('=' * 88)
for n in names:
    low = n.lower()
    if low.endswith(('.apk', '.jar', '.dex', '.zip')) or '.apk' in low:
        try:
            sz = z.getinfo(n).file_size
        except Exception:
            sz = 0
        print(f'  {n:<60} {sz/1024:>10.1f} KB')

print()
print('=' * 88)
print('4. lib/ 下的完整路径(看 ABI 与是否有注入相关)')
print('=' * 88)
for n in names:
    if n.startswith('lib/'):
        try:
            sz = z.getinfo(n).file_size
        except Exception:
            sz = 0
        print(f'  {n:<58} {sz/1024:>9.1f} KB')

print()
print('=' * 88)
print('5. DEX 里的关键类/方法(用字符串搜索)')
print('=' * 88)
dex = z.read('classes.dex')
print(f'  classes.dex 大小: {len(dex)/1024/1024:.1f} MB')

KEYS = [
    # 输入法
    b'InputMethodService', b'InputKb', b'onCreateInputView',
    b'InputConnection', b'commitText', b'sendKeyEvent',
    # 无障碍
    b'AccessibilityService', b'dispatchGesture', b'GestureDescription',
    b'performGlobalAction',
    # 注入
    b'INJECT_EVENTS', b'injectInputEvent', b'MotionEvent',
    b'InputManager', b'Instrumentation',
    # 截图
    b'MediaProjection', b'createScreenCaptureIntent', b'ImageReader',
    b'VirtualDisplay', b'screencap', b'Surface',
    # root / hook
    b'substrate', b'Zygote', b'ptrace', b'Runtime.exec',
    b'ProcessBuilder', b'/system/bin/su', b'\bsu\b',
    # 精灵引擎
    b'cyjh', b'elfin', b'VirtualAPK', b'PluginManager',
    # 无障碍辅助(仿冒输入法的常见手法)
    b'sendPointerSync', b'dispatchTouchEvent', b'InputChannel',
    b'WindowManager', b'TYPE_APPLICATION_OVERLAY', b'addView',
]
found = {}
for k in KEYS:
    n = dex.count(k)
    if n:
        found[k.decode('ascii', 'replace')] = n
for k, v in sorted(found.items(), key=lambda x: -x[1]):
    print(f'  {k:<32} {v}')
if not found:
    print('  (未找到)')

print()
print('  也搜一下 UTF-16 形式(某些字符串表):')
found16 = {}
for k in KEYS:
    k16 = k.decode('ascii', 'replace')
    try:
        n = dex.count(k16.encode('utf-16-le'))
    except Exception:
        n = 0
    if n:
        found16[k16] = n
for k, v in sorted(found16.items(), key=lambda x: -x[1])[:15]:
    print(f'  {k:<32} {v} (utf16)')
