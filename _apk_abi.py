# -*- coding: utf-8 -*-
"""决定性验证: 注入二进制是否只有 x86(即只能用于模拟器, 不能用于真机)。

## 为什么这决定一切

Android **真机几乎全是 ARM**(arm64-v8a / armeabi-v7a); x86 只存在于
**模拟器**(MuMu / 蓝叠 / 雷电 的 x86 镜像)。

  * 若 inject9 只有 x86/x86_64 -> 它**只能注入模拟器**, 真机用不了
  * 若有 arm64 -> 可能支持真机

注意: APK 的 `lib/` 下有 armeabi-v7a 是**正常**的(那是普通 Java/OCR 库,
能跑在设备上)。关键是**注入用的可执行二进制**有没有 ARM 版。
"""
import zipfile
from pathlib import Path

APK = Path(r'C:\Users\Win~Win~Win~\Downloads\大狮0802a-伪装输入法.apk')
z = zipfile.ZipFile(APK)
names = z.namelist()

print('=' * 90)
print('1. injectModifyCaptureMode 完整结构(注入资产)')
print('=' * 90)
for n in sorted(names):
    if 'injectModifyCaptureMode' in n or n.startswith('assets/inject'):
        info = z.getinfo(n)
        print(f'  {n:<66} {info.file_size/1024:>10.1f} KB')

print()
print('=' * 90)
print('2. 逐条判断: 注入二进制支持哪些 ABI')
print('=' * 90)
INJECT_ABIS = ('x86', 'x86_64', 'armeabi', 'armeabi-v7a', 'arm64-v8a')
found = {a: [] for a in INJECT_ABIS}
for n in names:
    if 'injectModifyCaptureMode' not in n:
        continue
    for a in INJECT_ABIS:
        if f'/{a}/' in n:
            found[a].append(n)
for a in INJECT_ABIS:
    if found[a]:
        print(f'  {a:<14} {len(found[a])} 个文件')
        for f in found[a]:
            print(f'        {f.split("injectModifyCaptureMode/")[-1]}')
    else:
        print(f'  {a:<14} (无)')

print()
print('=' * 90)
print('3. 结论')
print('=' * 90)
has_arm = bool(found['arm64-v8a'] or found['armeabi-v7a'] or found['armeabi'])
has_x86 = bool(found['x86'] or found['x86_64'])
print(f'  注入二进制含 x86    : {has_x86}')
print(f'  注入二进制含 ARM    : {has_arm}')
print()
if has_x86 and not has_arm:
    print('  ★★ 注入二进制**只有 x86/x86_64** ——')
    print('     即: 这套注入**只能用于 Android 模拟器**(MuMu/蓝叠/雷电的 x86 镜像),')
    print('     **不能用于 ARM 真机**。')
    print()
    print('     原因: 真机是 ARM, 无法执行 x86 机器码。')
elif has_arm:
    print('  ★ 注入二进制含 ARM —— 理论上可能支持真机。')
else:
    print('  (未找到注入二进制)')

print()
print('=' * 90)
print('4. 对照: 普通 lib/ 下的 ABI 分布(这些是能被真机加载的)')
print('=' * 90)
libabis = {}
for n in names:
    if n.startswith('lib/'):
        parts = n.split('/')
        if len(parts) >= 3:
            libabis.setdefault(parts[1], []).append(parts[-1])
for a, libs in sorted(libabis.items()):
    print(f'  {a:<16} {len(libs)} 个 so')
    print(f'      {sorted(set(libs))[:8]}')

print()
print('  说明: lib/ 里有 armeabi-v7a 只说明"这些 OCR/图像库能跑在真机上",')
print('        不代表**注入机制**能在真机上工作 —— 注入靠的是上面的 inject9。')
