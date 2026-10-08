# -*- coding: utf-8 -*-
"""解剖 APK: 从 AndroidManifest.xml 读出权限与服务声明。

## 为什么这是最直接的证据

"用什么方式注入触摸"这个问题, 答案**必然**体现在权限声明里:

  * AccessibilityService  -> 要有 <service android:permission=
                              "android.permission.BIND_ACCESSIBILITY_SERVICE">
  * InputMethodService    -> 要有 <service android:permission=
                              "android.permission.BIND_INPUT_METHOD">
  * 悬浮窗                -> 要申请 SYSTEM_ALERT_WINDOW
  * root 注入             -> 通常伴随 su 调用(需要看代码, 但常申请
                              REQUEST_INSTALL_PACKAGES / 读写 /system)
  * MediaProjection 截图  -> 代码里出现, 权限不需要声明(运行时请求)

AndroidManifest.xml 在 APK 里是 **AXML 二进制格式**, 需要解析。
本脚本用最简方式解出它(优先用 androguard, 不可用则手写最小 AXML 解析)。
"""
import re
import sys
import zipfile
from pathlib import Path

APK = Path(r'C:\Users\Win~Win~Win~\Downloads\大狮0802a-伪装输入法.apk')

if not APK.exists():
    print(f'APK 不存在: {APK}')
    sys.exit(1)
print(f'APK: {APK.name}  ({APK.stat().st_size/1024/1024:.1f} MB)')

z = zipfile.ZipFile(APK)
names = z.namelist()
print(f'条目数: {len(names)}')

# ---------------------------------------------------------------- 顶层结构
print()
print('=' * 84)
print('包内容概览')
print('=' * 84)
tops = {}
for n in names:
    top = n.split('/')[0]
    tops[top] = tops.get(top, 0) + 1
for k, v in sorted(tops.items(), key=lambda x: -x[1])[:20]:
    print(f'  {k:<44} {v}')

# ---------------------------------------------------------------- native 库
print()
print('=' * 84)
print('原生库(.so) —— 看是否有自研注入/图像处理')
print('=' * 84)
sos = [n for n in names if n.endswith('.so')]
seen = {}
for s in sos:
    base = s.split('/')[-1]
    seen.setdefault(base, []).append(s)
for base, paths in sorted(seen.items()):
    abis = sorted({p.split('/lib/')[-1].split('/')[0] for p in paths
                   if '/lib/' in p})
    print(f'  {base:<44} {abis}')
if not sos:
    print('  (无 .so)')

# ---------------------------------------------------------------- AXML 解析
print()
print('=' * 84)
print('AndroidManifest.xml 解析')
print('=' * 84)
raw = z.read('AndroidManifest.xml')
print(f'  原始大小 {len(raw)} 字节, 头部 {raw[:4]!r}')

text = None
# 先试 androguard
try:
    from androguard.core.axml import AXMLPrinter
    text = AXMLPrinter(raw).get_xml().decode('utf-8', 'replace')
    print('  (用 androguard 解析)')
except Exception as e1:
    # 退回到最小 AXML 解析
    print(f'  androguard 不可用({type(e1).__name__}), 用内置最小解析器')


def parse_axml_strings(data: bytes):
    """
    最小 AXML 解析: 提取字符串池 + 权限/服务相关的原始字符串。

    完整解析 AXML 较复杂; 这里只需**字符串池**即可回答"声明了哪些权限/服务",
    因此只解析 string pool 段。
    """
    out = []
    # AXML 头部: magic(0x00080003) + size(4)
    if len(data) < 8 or data[:4] != b'\x03\x00\x08\x00':
        return out
    # 遍历 chunk
    off = 8
    while off + 8 <= len(data):
        ctype = int.from_bytes(data[off:off + 2], 'little')
        csize = int.from_bytes(data[off + 4:off + 8], 'little')
        if csize <= 0 or off + csize > len(data):
            break
        if ctype == 0x0001:                      # STRING_POOL
            cnt = int.from_bytes(data[off + 8:off + 12], 'little')
            utf8 = int.from_bytes(data[off + 16:off + 20], 'little') != 0
            offs = [int.from_bytes(data[off + 20 + i*4: off + 24 + i*4], 'little')
                    for i in range(cnt)]
            base = off + 20 + cnt * 4
            for o in offs:
                p = base + o
                if utf8:
                    try:
                        # u16len(可变) + u8len + bytes + 0
                        i = p
                        while data[i] & 0x80: i += 1
                        i += 1
                        ln = data[i]; i += 1
                        out.append(data[i:i + ln].decode('utf-8', 'replace'))
                    except Exception:
                        pass
                else:
                    try:
                        ln = int.from_bytes(data[p:p + 2], 'little')
                        s = data[p + 2:p + 2 + ln * 2].decode('utf-16-le', 'replace')
                        out.append(s)
                    except Exception:
                        pass
            break
        off += csize
    return out


if text is None:
    strs = parse_axml_strings(raw)
    print(f'  字符串池: {len(strs)} 条')
    text = '\n'.join(strs)

# ---------------------------------------------------------------- 关键信息提取
def find_all(pattern, flags=re.I):
    return sorted(set(re.findall(pattern, text, flags)))


print()
print('--- 权限 ---')
perms = find_all(r'android\.permission\.[A-Z_]+')
for p in perms:
    print(f'  {p}')
if not perms:
    print('  (未提取到, 可能解析不完整)')

print()
print('--- 关键服务/组件 ---')
for pat, label in (
    (r'[A-Za-z0-9_.]*Accessibility[A-Za-z0-9_.]*', 'Accessibility(无障碍)'),
    (r'[A-Za-z0-9_.]*InputMethod[A-Za-z0-9_.]*', 'InputMethod(输入法)'),
    (r'[A-Za-z0-9_.]*Service[A-Za-z0-9_.]*', 'Service'),
):
    hits = find_all(pat)
    if hits:
        print(f'  [{label}]')
        for h in hits[:15]:
            print(f'      {h}')

print()
print('--- 关键权限字符串(BIND_* / SYSTEM_ALERT_WINDOW / INJECT) ---')
for pat in (r'BIND_[A-Z_]+', r'SYSTEM_ALERT_WINDOW', r'INJECT_EVENTS',
            r'WRITE_SECURE_SETTINGS', r'MEDIA_PROJECTION', r'su\b',
            r'REQUEST_INSTALL_PACKAGES', r'FOREGROUND_SERVICE'):
    hits = find_all(pat)
    if hits:
        print(f'  {pat}  ->  {hits[:6]}')

print()
print('--- package / 版本 ---')
for pat in (r'package="[^"]+"', r'android:versionName="[^"]+"',
            r'platformBuildVersionName="[^"]+"'):
    hits = find_all(pat)
    if hits:
        print(f'  {hits[:3]}')

# ---------------------------------------------------------------- 代码线索(DEX 字符串)
print()
print('=' * 84)
print('DEX 里的关键 API 线索')
print('=' * 84)
dexes = [n for n in names if n.endswith('.dex')]
print(f'  dex 文件: {dexes}')
KEY = [
    b'dispatchGesture', b'AccessibilityService', b'InputMethodService',
    b'MediaProjection', b'createScreenCaptureIntent', b'ImageReader',
    b'MotionEvent', b'INJECT_EVENTS', b'injectInputEvent',
    b'SystemClock', b'su', b'Shell', b'Runtime.exec', b'ProcessBuilder',
    b'Shizuku', b'com.android.internal', b'IAccessibilityService',
]
for d in dexes:
    data = z.read(d)
    print(f'  --- {d} ({len(data)/1024/1024:.1f} MB) ---')
    for k in KEY:
        n = data.count(k)
        if n:
            print(f'      {k.decode("ascii", "replace"):<28} 出现 {n} 次')
