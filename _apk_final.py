# -*- coding: utf-8 -*-
"""整理大狮 APK 的最终结论(先自行核对, 避免又给出错误结论)。"""
import io
import zipfile
from pathlib import Path

APK = Path(r'C:\Users\Win~Win~Win~\Downloads\大狮0802a-伪装输入法.apk')
z = zipfile.ZipFile(APK)
names = z.namelist()

print('=' * 92)
print('大狮 APK 分析 · 事实清单(每条都基于文件/字符串, 不推测)')
print('=' * 92)

# ---- 1. 基本身份
print()
print('【1】基本身份')
print(f'  package        : com.app.wkinput        ("wkinput" = 伪装输入法)')
print(f'  versionName    : 6.1.1')
print(f'  体积           : {APK.stat().st_size/1024/1024:.1f} MB / {len(names)} 条目')
print(f'  主 dex         : classes.dex 7.5MB + classes2.dex 0.8MB')

# ---- 2. 组件
print()
print('【2】声明的组件(来自 AndroidManifest)')
svcs = [
    'com.cyjh.elfin.floatingwindowprocess.service.FloatingWindowService',
    'com.ime.input.InputKb',
    'com.cyjh.elfin.services.BootService',
    'com.cyjh.elfin.services.PhoneStateService',
    'com.cyjh.elfin.services.TimerService',
    'com.didi.virtualapk.delegate.LocalService / RemoteService',
    'com.cyjh.mq.service.IpcService',
    'com.hlzn.socketclient.service.SocketService',
]
for s in svcs:
    print(f'  {s}')
print('  权限 49 条, 含 SYSTEM_ALERT_WINDOW / WRITE_SECURE_SETTINGS /')
print('       INTERACT_ACROSS_USERS_FULL / REQUEST_INSTALL_PACKAGES /')
print('       FOREGROUND_SERVICE / PACKAGE_USAGE_STATS / MOUNT_UNMOUNT_FILESYSTEMS')
print('  ★ manifest 字符串池含 BIND_INPUT_METHOD(UTF-16), 证实注册为输入法')

# ---- 3. ABI 矩阵(重点纠正)
print()
print('【3】注入资产的 ABI 覆盖(★ 这里我先前判断错了, 已纠正)')
groups = {}
for n in names:
    if 'injectModifyCaptureMode' in n or n.startswith('assets/inject/'):
        parts = n.split('/')
        abi = next((p for p in parts
                    if p in ('x86', 'x86_64', 'armeabi-v7a', 'arm64-v8a')), None)
        groups.setdefault(abi or '(无ABI)', []).append(n.split('/')[-1])
for abi in ('x86', 'x86_64', 'armeabi-v7a', 'arm64-v8a', '(无ABI)'):
    if abi in groups:
        print(f'  {abi:<15} {sorted(set(groups[abi]))}')

print()
print('  分成两套(按 Android 版本):')
print('    android < 9  : inject7 + libyafa.so + libzygote.so  → 有 x86/x86_64/'
      'armeabi-v7a/arm64-v8a 四种')
print('    android >= 9 : inject9 + libyafa.so + libzygote.so  → 只有 x86/x86_64')
print('    另有 assets/inject/{arm64-v8a,armeabi-v7a,x86}/Inject  → 也有 ARM')

# ---- 4. 机制线索
print()
print('【4】机制线索(从资产名与字符串)')
facts = [
    ('hookzygote.apk 内含 classes.dex',
     '被注入进 zygote 的 Java 载荷'),
    ('Hook_Application_attachBaseContext',
     'hook Application 启动, 拿到每个 app 的早期控制权'),
    ('Hook_ContextWrapper_attachBaseContext',
     '同上, 走 ContextWrapper 路径'),
    ('Ldalvik/system/DexClassLoader;',
     '运行期动态加载额外 dex'),
    ('Lcom/cyjh/myapplication/Main;',
     '注入后执行的载荷入口'),
    ('android.view.WindowManager$LayoutParams',
     '建立悬浮窗'),
    ('inject9 = ELF DYN x86_64/x86, 含 ptrace/zygote/inject 字符串',
     '原生注入器, 目标是 zygote'),
    ('libzygote.so / libyafa.so',
     'zygote 注入配套 + yafa 虚拟空间(容器)'),
    ('libsubstrate.so',
     'Cydia Substrate hook 框架'),
    ('libsc*.so / libscVirtDisplay{19,21}.so',
     '截图, 按 Android 版本适配; VirtDisplay = VirtualDisplay/MediaProjection'),
    ('libtinyCnn.so + assets/model/TinyCnnModel',
     '自带 CNN 推理(图像识别)'),
    ('liblept.so + libtess.so + libzbarjni.so',
     'Tesseract/Leptonica OCR + 条码识别'),
    ('com.didi.virtualapk.delegate.*',
     'VirtualAPK 插件化框架'),
]
for a, b in facts:
    print(f'  {a}')
    print(f'      → {b}')

# ---- 5. 诚实的边界
print()
print('【5】我没能确认的(不推测)')
for x in [
    '运行时究竟走哪条路(注入 / 无障碍 / 输入法), 我读的是字符串与资产文件名, 不是反编译后的代码',
    '是否必须 root —— 有 ptrace+zygote 注入的强证据, 但未确认实际是否强制要求 root',
    'libyafa.so 是否就是"八爪鱼虚拟空间"(名字吻合, 未核实)',
    'x86-only 的 >=9 那套是否意味着"新系统上只支持模拟器"',
    '与阴阳师之间是否有反检测对抗',
]:
    print(f'  · {x}')

# ---- 6. 桌面脚本
print()
print('【6】脚本文件(说明它是"脚本化"产品)')
for n in ('assets/script.uip', 'assets/script.lc', 'assets/script.rtd',
          'assets/script.atc'):
    if n in names:
        print(f'  {n:<24} {z.getinfo(n).file_size/1024:>9.1f} KB')
print('  (精灵/按键精灵的脚本格式: 用户自己录脚本)')
