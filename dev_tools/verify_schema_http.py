# -*- coding: utf-8 -*-
"""用真实 HTTP 请求验证 /schema 与 /overview —— 端到端。

直接调用 builder 只能证明逻辑对; 这里起一个真实的 uvicorn 服务并请求,
证明**路由真的挂上了**、序列化没问题、状态码正确。

(不用 FastAPI TestClient —— 它依赖 httpx, 本项目的 toolkit 里没装。)
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(r'D:\OAS-dev\OnmyojiAutoScript')
sys.path.insert(0, str(REPO))
os.chdir(REPO)

PORT = 22399
fails = []


def chk(desc, ok, extra=''):
    print(f'  {"OK " if ok else "BAD"} {desc:<48} {extra}')
    if not ok:
        fails.append(desc)


def get(path, timeout=10):
    url = f'http://127.0.0.1:{PORT}{urllib.parse.quote(path, safe="/")}'
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read().decode('utf-8')


import urllib.parse  # noqa: E402

print('=' * 92)
print(f'启动 uvicorn 于 :{PORT}')
print('=' * 92)

proc = subprocess.Popen(
    # 必须用 `fastapi_app` 工厂 —— 它负责设置 `app.state.script_instances`;
    # 直接用 `app` 会在 lifespan 里 AttributeError(踩过)。
    [str(REPO / 'toolkit' / 'python.exe'), '-m', 'uvicorn',
     'module.server.app:fastapi_app', '--factory',
     '--host', '127.0.0.1', '--port', str(PORT), '--log-level', 'error'],
    cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, encoding='utf-8', errors='replace')

try:
    # 等服务起来
    ok = False
    for _ in range(40):
        time.sleep(0.5)
        try:
            get('/config_list', timeout=3)
            ok = True
            break
        except Exception:
            if proc.poll() is not None:
                break
    if not ok:
        print('  !! 服务未能启动')
        out = proc.stdout.read() if proc.stdout else ''
        print(out[-1500:])
        sys.exit(1)
    print('  服务已就绪')
    print()

    print('--- GET /恋鸟树/schema ---')
    st, body = get('/恋鸟树/schema')
    chk('状态码 200', st == 200, str(st))
    data = json.loads(body)
    chk('返回 54 个任务', data.get('count') == 54, str(data.get('count')))
    chk('含 categories', len(data.get('categories') or []) == 5)
    chk('含 window_fields', len(data.get('window_fields') or []) == 4)
    fs = (data.get('tasks') or {}).get('FallenSun') or {}
    chk('FallenSun 中文名正确', fs.get('name_zh') == '日轮之陨',
        repr(fs.get('name_zh')))
    chk('FallenSun 资源正确', (fs.get('resource') or {}).get('capacity') == 50)
    print(f'    JSON 大小: {len(body)} 字节')

    print()
    print('--- GET /恋鸟树/overview ---')
    st2, body2 = get('/恋鸟树/overview')
    chk('状态码 200', st2 == 200, str(st2))
    d = json.loads(body2)
    chk('无 error', 'error' not in d, str(d.get('error'))[:60])
    chk('有 tasks 列表', isinstance(d.get('tasks'), list))
    chk('total == len(tasks)', d.get('total') == len(d.get('tasks') or []))
    chk('runnable 数自洽',
        sum(1 for t in d.get('tasks') or [] if t.get('can_run'))
        == d.get('runnable'))
    chk('含 teams', isinstance(d.get('teams'), list))
    print(f'    可跑 {d.get("runnable")}/{d.get("total")}, '
          f'JSON {len(body2)} 字节')

    print()
    print('--- 既有接口未被破坏 ---')
    st3, body3 = get('/恋鸟树/task_status')
    chk('/task_status 仍 200', st3 == 200, str(st3))
    if st3 == 200:
        ts = json.loads(body3)
        chk('/task_status 有 tasks', isinstance(ts.get('tasks'), list),
            f'{len(ts.get("tasks") or [])} 个')

finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    print()
    print('  服务已停止')

print()
print('=' * 92)
if fails:
    print(f'*** {len(fails)} 项失败 ***')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('*** 全部通过 —— 两个接口可通过 HTTP 正常访问 ***')
print('=' * 92)
