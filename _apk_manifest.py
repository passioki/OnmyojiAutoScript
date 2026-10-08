# -*- coding: utf-8 -*-
"""用 pyaxmlparser 完整解析大狮 APK 的 AndroidManifest.xml。

回答核心问题: **它到底用什么方式注入触摸?**
"""
import sys
import zipfile
from pathlib import Path

APK = Path(r'C:\Users\Win~Win~Win~\Downloads\大狮0802a-伪装输入法.apk')

from pyaxmlparser import APK as AXMLAPK


def short(name: str) -> str:
    return (name or '').replace('android.permission.', '')


apk = AXMLAPK(str(APK))
print('=' * 88)
print('基本信息')
print('=' * 88)
for attr in ('package', 'version_name', 'version_code', 'min_sdk_version',
             'target_sdk_version', 'main_activity'):
    try:
        print(f'  {attr:<20} {getattr(apk, attr)}')
    except Exception as e:
        print(f'  {attr:<20} (取不到: {e})')

print()
print('=' * 88)
print('权限')
print('=' * 88)
try:
    perms = sorted(str(p) for p in apk.get_permissions())
except Exception as e:
    perms = []
    print(f'  取权限失败: {e}')
for p in perms:
    print(f'  {short(p)}')
print(f'  共 {len(perms)} 条')

print()
print('=' * 88)
print('服务(services) —— 关键看有没有 Accessibility / InputMethod')
print('=' * 88)
services = []
try:
    services = list(apk.get_services())
except Exception as e:
    print(f'  取服务失败: {e}')
for s in services:
    name = str(getattr(s, 'name', s))
    perm = ''
    meta = ''
    try:
        perm = str(getattr(s, 'permission', '') or '')
    except Exception:
        pass
    try:
        # 无障碍服务的标志: meta-data 里有 accessibilityservice 配置
        md = getattr(s, 'get_meta_data', None)
        if callable(md):
            for k, v in (md() or {}).items():
                if 'accessibility' in str(k).lower() or \
                   'accessibility' in str(v).lower():
                    meta = f'{k}={v}'
    except Exception:
        pass
    line = f'  {name}'
    if perm:
        line += f'   [permission={short(perm)}]'
    if meta:
        line += f'   [meta: {meta}]'
    print(line)
print(f'  共 {len(services)} 个服务')

print()
print('=' * 88)
print('★ 关键判定')
print('=' * 88)
perm_set = {short(p) for p in perms}
svc_text = ' '.join(str(getattr(s, 'name', s)) for s in services)

has_input_method = 'BIND_INPUT_METHOD' in perm_set
has_accessibility = 'BIND_ACCESSIBILITY_SERVICE' in perm_set
has_overlay = 'SYSTEM_ALERT_WINDOW' in perm_set
has_inject = 'INJECT_EVENTS' in perm_set
has_secure = 'WRITE_SECURE_SETTINGS' in perm_set

checks = [
    ('注册为**输入法**', has_input_method, 'BIND_INPUT_METHOD'),
    ('注册为**无障碍服务**', has_accessibility, 'BIND_ACCESSIBILITY_SERVICE'),
    ('申请**悬浮窗**权限', has_overlay, 'SYSTEM_ALERT_WINDOW'),
    ('申请 **INJECT_EVENTS**', has_inject, 'INJECT_EVENTS'),
    ('申请 **WRITE_SECURE_SETTINGS**', has_secure, 'WRITE_SECURE_SETTINGS'),
]
for label, ok, key in checks:
    print(f'  {"✓ 是" if ok else "✗ 否"}   {label:<28} ({key})')

print()
print('  无障碍相关服务名:')
acc = [str(getattr(s, 'name', s)) for s in services
       if 'accessibility' in str(getattr(s, 'name', s)).lower()]
for a in acc:
    print(f'      {a}')
if not acc:
    print('      (服务名里没有 accessibility 字样)')

print()
print('  输入法相关服务名:')
ime = [str(getattr(s, 'name', s)) for s in services
       if 'input' in str(getattr(s, 'name', s)).lower()
       or 'ime' in str(getattr(s, 'name', s)).lower()]
for a in ime:
    print(f'      {a}')
if not ime:
    print('      (服务名里没有 input/ime 字样)')

print()
print('=' * 88)
print('Activities(主界面)')
print('=' * 88)
try:
    for a in list(apk.get_activities())[:25]:
        print(f'  {getattr(a, "name", a)}')
except Exception as e:
    print(f'  失败: {e}')
