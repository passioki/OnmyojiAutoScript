# -*- coding: utf-8 -*-
"""确认大狮的注入资产: hookzygote.apk / inject9 分别是什么。"""
import zipfile
from pathlib import Path

APK = Path(r'C:\Users\Win~Win~Win~\Downloads\大狮0802a-伪装输入法.apk')
z = zipfile.ZipFile(APK)

print('=' * 88)
print('1. hookzygote.apk 的内部(它是"被注入进 zygote 的代码")')
print('=' * 88)
for entry in ('assets/injectModifyCaptureMode/HigherThanAndroid9/hookzygote.apk',
              'assets/injectModifyCaptureMode/LowerThanAndroid9/hookzygote.apk'):
    data = z.read(entry)
    print(f'  --- {entry}  ({len(data)/1024:.1f} KB) ---')
    # 它自己也是个 zip?
    import io
    try:
        zz = zipfile.ZipFile(io.BytesIO(data))
        for n in zz.namelist():
            info = zz.getinfo(n)
            print(f'      {n:<52} {info.file_size:>9} B')
        # 看 manifest
        if 'AndroidManifest.xml' in zz.namelist():
            raw = zz.read('AndroidManifest.xml')
            print(f'      (manifest {len(raw)} B)')
            for key in (b'BIND_ACCESSIBILITY_SERVICE', b'BIND_INPUT_METHOD',
                        b'service', b'INJECT', b'Substrate'):
                n8 = raw.count(key)
                n16 = raw.count(key.decode().encode('utf-16-le'))
                if n8 or n16:
                    print(f'        {key.decode():<30} utf8={n8} utf16={n16}')
    except Exception as e:
        print(f'      不是 zip: {type(e).__name__}: {e}')
        print(f'      头部: {data[:16]!r}')
    print()

print('=' * 88)
print('2. inject9 是什么(ELF 可执行? so?)')
print('=' * 88)
for entry in ('assets/injectModifyCaptureMode/HigherThanAndroid9/x86_64/inject9',
              'assets/injectModifyCaptureMode/HigherThanAndroid9/x86/inject9'):
    data = z.read(entry)
    print(f'  --- {entry}')
    print(f'      大小 {len(data)/1024/1024:.2f} MB')
    print(f'      头部 {data[:16]!r}')
    if data[:4] == b'\x7fELF':
        ei_class = data[4]
        ei_data = data[5]
        e_type = int.from_bytes(data[16:18], 'little')
        e_machine = int.from_bytes(data[18:20], 'little')
        print(f'      ELF: class={"64" if ei_class==2 else "32"}bit  '
              f'endian={"LE" if ei_data==1 else "BE"}  '
              f'type={e_type}({ {1:"REL",2:"EXEC",3:"DYN",4:"CORE"}.get(e_type,"?") })  '
              f'machine={e_machine}({ {3:"x86",62:"x86_64",40:"ARM",183:"AArch64"}.get(e_machine,"?") })')
    # 找里面的符号/字符串
    for key in (b'zygote', b'substrate', b'ptrace', b'inject', b'libsc',
                b'VirtualDisplay', b'MediaProjection', b'screencap',
                b'/system/bin/app_process', b'MSHookFunction'):
        n = data.count(key)
        if n:
            print(f'      {key.decode():<28} 出现 {n} 次')
    print()

print('=' * 88)
print('3. test.apk 与 script.* (精灵脚本)')
print('=' * 88)
for entry in ('assets/inject/test.apk', 'assets/script.uip', 'assets/script.lc',
              'assets/script.rtd', 'assets/script.atc'):
    data = z.read(entry)
    print(f'  {entry:<48} {len(data)/1024:>9.1f} KB  头部 {data[:12]!r}')
    if entry.endswith('.apk'):
        import io
        try:
            zz = zipfile.ZipFile(io.BytesIO(data))
            print(f'      zip 内容: {zz.namelist()[:10]}')
        except Exception as e:
            print(f'      非 zip: {e}')

print()
print('=' * 88)
print('4. DEX 里的 cyjh/elfin(精灵引擎)相关类名')
print('=' * 88)
dex = z.read('classes.dex')
import re
# 从 DEX 字符串表里捞类名
classes = set(re.findall(rb'Lcom/(?:cyjh|ime|app)/[A-Za-z0-9_/$]{3,60};', dex))
interesting = [c.decode('ascii', 'replace') for c in classes]
print(f'  com.cyjh / com.ime / com.app 类: {len(interesting)} 个')
for c in sorted(interesting)[:45]:
    print(f'    {c}')
