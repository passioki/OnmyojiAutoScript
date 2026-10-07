# -*- coding: utf-8 -*-
"""
UI 标注工具: 让人类在浏览器里框选界面元素并写下它的含义, 输出机器可读的标注。

为什么需要它: 自动化侧(agent)没有图像输入能力, 因此"这个新 UI 是什么意思"
"这个图标代表什么"这类语义判断无法自行完成。把这类判断一次性标注下来并落成
JSON, agent 之后就能直接消费(选判据、裁模板、读语义), 不必每次再问人。

设计取向:
  - 只用标准库 http.server, 不引入 gradio/streamlit。本仓库的 toolkit 固定了
    依赖版本(如 packaging==20.9 被 uiautomator2 约束), 装新框架容易破坏运行时。
  - 标注结果落在仓库内 dev_tools/annotations/*.json, 可随 git 一起管理。
  - 框选坐标以截图原始像素记录, 并换算到 OAS 的 1280x720 坐标系, 可直接生成
    RuleImage。

用法:
    # 启动标注服务(默认 8765 端口), 浏览器打开 http://127.0.0.1:8765
    python dev_tools/ui_annotator.py serve --port 8765

    # 列出已有标注
    python dev_tools/ui_annotator.py list

    # 由标注裁出模板图并生成 RuleImage 建议
    python dev_tools/ui_annotator.py crop --name battle_ui --out tasks/DemonEncounter/demon

标注 JSON 结构(每张图一个文件):
{
  "image": "log/error/xxx/2026-10-07_18-17-26.png",
  "size": [1280, 720],
  "items": [
    {"x": 16, "y": 15, "w": 40, "h": 40,
     "name": "I_EXIT_BATTLE",
     "role": "button",
     "text": "左上角退出按钮, 战斗全程可见",
     "note": ""}
  ]
}
"""
import argparse
import json
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parent.parent
ANNOTATION_DIR = REPO_ROOT / 'dev_tools' / 'annotations'
SHOT_DIR = REPO_ROOT / 'log' / 'probe'
IMG_EXT = {'.png', '.jpg', '.jpeg', '.bmp', '.webp'}

# 角色取值: 让标注直接可用, 而不是自由文本
ROLES = [
    'button',        # 可点击按钮
    'toggle',        # 开关状态
    'battle_state',  # 可用于判断"是否在战斗中"
    'prepare_state', # 可用于判断"是否在准备界面"
    'result_state',  # 可用于判断"战斗结束/胜负"
    'ocr',           # 需要读文字的区域
    'container',     # 容器/面板, 本身不可点
    'other',
]


def to_oas_box(box, size):
    """
    把标注框从原始截图坐标换算到 OAS 的 1280x720 坐标系。

    竖屏截图(720x1280)旋转后才是 OAS 认的 1280x720, 换算关系:
    x_oas = H_orig - (y + h),  y_oas = x,  w_oas = h,  h_oas = w

    :param box: (x, y, w, h) 原始截图坐标
    :param size: (W, H) 原始截图尺寸
    :return: (x, y, w, h) 在 1280x720 下的坐标
    """
    x, y, w, h = box
    W, H = size
    if (W, H) == (1280, 720):
        return (x, y, w, h)
    if (H, W) == (1280, 720) or (W, H) == (720, 1280):
        # 顺时针旋转 90 度
        return (H - (y + h), x, h, w)
    sx, sy = 1280.0 / W, 720.0 / H
    return (int(x * sx), int(y * sy), int(w * sx), int(h * sy))


def iter_images():
    """列出可标注的候选截图(仓库内的 log 与已标注过的图)。"""
    out = []
    for base in (SHOT_DIR, REPO_ROOT / 'log'):
        if not base.exists():
            continue
        for p in base.rglob('*'):
            if p.suffix.lower() in IMG_EXT and p.is_file():
                out.append(p)
    # 去重并保序
    seen = set()
    uniq = []
    for p in out:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        uniq.append(p)
    return uniq


def annotation_path(name: str) -> Path:
    return ANNOTATION_DIR / f'{name}.json'


def load_annotation(name: str) -> dict:
    p = annotation_path(name)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_annotation(name: str, data: dict) -> Path:
    ANNOTATION_DIR.mkdir(parents=True, exist_ok=True)
    p = annotation_path(name)
    data['updated_at'] = datetime.now().isoformat(timespec='seconds')
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return p


# ---------------------------------------------------------------------------
# HTTP 服务
# ---------------------------------------------------------------------------
PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>OAS UI 标注</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.5 "Microsoft YaHei", system-ui, sans-serif;
         background: #1e1f22; color: #e6e6e6; }
  header { padding: 10px 14px; background: #2b2d31; border-bottom: 1px solid #3a3d42;
           display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  header h1 { font-size: 15px; margin: 0 8px 0 0; font-weight: 600; }
  button { background: #3a3d42; color: #e6e6e6; border: 1px solid #4a4d52;
           border-radius: 4px; padding: 5px 10px; cursor: pointer; font-size: 13px; }
  button:hover { background: #45484e; }
  button.primary { background: #2d6cdf; border-color: #2d6cdf; }
  button.primary:hover { background: #3a7aef; }
  button.danger { background: #7a2d2d; border-color: #8a3a3a; }
  select, input, textarea { background: #1e1f22; color: #e6e6e6;
           border: 1px solid #4a4d52; border-radius: 4px; padding: 4px 6px;
           font-size: 13px; font-family: inherit; }
  main { display: flex; height: calc(100vh - 52px); }
  #left { flex: 1; overflow: auto; padding: 12px; }
  #right { width: 380px; border-left: 1px solid #3a3d42; overflow: auto; padding: 12px;
           background: #232428; }
  #stage { position: relative; display: inline-block; }
  #stage img { display: block; max-width: 100%; user-select: none; -webkit-user-drag: none; }
  #overlay { position: absolute; inset: 0; cursor: crosshair; }
  .box { position: absolute; border: 2px solid #2d6cdf; background: rgba(45,108,223,0.18);
         pointer-events: none; }
  .box span { position: absolute; top: -18px; left: 0; font-size: 11px; color: #9ecbff;
              white-space: nowrap; }
  .row { background: #2b2d31; border: 1px solid #3a3d42; border-radius: 4px;
         padding: 8px; margin-bottom: 8px; }
  .row .name { font-weight: 600; color: #9ecbff; }
  .row .meta { color: #9a9da3; font-size: 12px; }
  .row .desc { margin-top: 4px; }
  .row .acts { margin-top: 6px; display: flex; gap: 6px; }
  .hint { color: #9a9da3; font-size: 12px; margin: 6px 0 10px; }
  .field { margin-bottom: 8px; }
  .field label { display: block; font-size: 12px; color: #9a9da3; margin-bottom: 2px; }
  .field input, .field textarea, .field select { width: 100%; }
  #drop { border: 1px dashed #4a4d52; border-radius: 6px; padding: 14px;
          text-align: center; color: #9a9da3; }
  #toast { position: fixed; bottom: 16px; left: 50%; transform: translateX(-50%);
           background: #2d6cdf; color: #fff; padding: 8px 16px; border-radius: 4px;
           opacity: 0; transition: opacity .2s; pointer-events: none; }
</style>
</head>
<body>
<header>
  <h1>OAS UI 标注</h1>
  <label>图片
    <select id="imgSelect"></select>
  </label>
  <button id="btnReload">重新载入标注</button>
  <button id="btnSave" class="primary">保存到仓库</button>
  <button id="btnExport">导出 JSON</button>
  <span class="hint" id="status"></span>
</header>
<main>
  <div id="left">
    <div class="hint">
      在图上<b>拖拽框选</b>一个元素 → 右侧填名称/角色/含义 → 保存。
      框选坐标会同时记录原始像素与 OAS 1280x720 坐标。
    </div>
    <div id="stage">
      <img id="shot" alt="截图">
      <div id="overlay"></div>
    </div>
  </div>
  <div id="right">
    <div class="row">
      <div class="name">当前选中区域</div>
      <div class="field"><label>名称 (会用作 RuleImage 变量名建议)</label>
        <input id="fName" placeholder="如 I_EXIT_BATTLE"></div>
      <div class="field"><label>角色</label>
        <select id="fRole"></select></div>
      <div class="field"><label>含义 / 说明 (必填, 这是要传达给 agent 的知识)</label>
        <textarea id="fText" rows="3" placeholder="如: 左上角退出按钮, 战斗全程可见, 准备界面也有"></textarea></div>
      <div class="field"><label>备注 (可选)</label>
        <input id="fNote" placeholder="如: 皮肤 13 号下位置相同"></div>
      <div class="acts">
        <button id="btnAdd" class="primary">添加标注</button>
        <button id="btnClear">清空当前框</button>
      </div>
    </div>
    <div class="row">
      <div class="name">已有标注 <span id="cnt">0</span> 条</div>
      <div id="list"></div>
    </div>
  </div>
</main>
<div id="toast"></div>
<script>
const ROLES = __ROLES__;
let cur = { img: null, size: [0,0], items: [], drag: null, selected: null };

const $ = id => document.getElementById(id);
function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.style.opacity = 1;
  setTimeout(() => t.style.opacity = 0, 1600);
}
function fillRoles() {
  const sel = $('fRole');
  sel.innerHTML = ROLES.map(r => `<option value="${r}">${r}</option>`).join('');
  sel.value = 'button';
}
async function loadImages() {
  const r = await fetch('/api/images'); const data = await r.json();
  const sel = $('imgSelect');
  sel.innerHTML = data.images.map(p => `<option value="${p}">${p}</option>`).join('');
  if (data.images.length) { sel.value = data.current || data.images[0]; await loadImage(sel.value); }
}
async function loadImage(path) {
  cur.img = path;
  const img = $('shot');
  img.src = '/img?path=' + encodeURIComponent(path);
  await new Promise(res => { img.onload = res; img.onerror = res; });
  cur.size = [img.naturalWidth, img.naturalHeight];
  const r = await fetch('/api/annotation?name=' + encodeURIComponent(baseName(path)));
  const data = await r.json();
  cur.items = data.items || [];
  cur.selected = null;
  $('fName').value = ''; $('fText').value = ''; $('fNote').value = '';
  render();
  $('status').textContent = `图片 ${cur.size[0]}x${cur.size[1]}, 已有 ${cur.items.length} 条标注`;
}
function baseName(path) {
  return path.replace(/\\/g, '/').split('/').pop().replace(/\.[^.]+$/, '');
}
function render() {
  const ov = $('overlay');
  ov.innerHTML = '';
  const img = $('shot');
  const scale = img.clientWidth / (cur.size[0] || 1);
  ov.style.width = img.clientWidth + 'px';
  ov.style.height = img.clientHeight + 'px';
  cur.items.forEach((it, i) => {
    const d = document.createElement('div');
    d.className = 'box';
    d.style.left = (it.x * scale) + 'px';
    d.style.top = (it.y * scale) + 'px';
    d.style.width = (it.w * scale) + 'px';
    d.style.height = (it.h * scale) + 'px';
    if (i === cur.selected) { d.style.borderColor = '#ffd166'; d.style.background = 'rgba(255,209,102,0.22)'; }
    d.innerHTML = `<span>${it.name || '(未命名)'}</span>`;
    ov.appendChild(d);
  });
  const list = $('list');
  list.innerHTML = cur.items.map((it, i) => `
    <div class="row" style="margin:6px 0;border-color:${i===cur.selected?'#ffd166':'#3a3d42'}">
      <div class="name">${i+1}. ${it.name || '(未命名)'} <span class="meta">[${it.role}]</span></div>
      <div class="meta">原始 (${it.x},${it.y},${it.w},${it.h}) &nbsp; OAS (${it.oaX},${it.oaY},${it.oaW},${it.oaH})</div>
      <div class="desc">${it.text || ''}</div>
      <div class="acts">
        <button onclick="selectItem(${i})">选中</button>
        <button class="danger" onclick="delItem(${i})">删除</button>
      </div>
    </div>`).join('');
  $('cnt').textContent = cur.items.length;
}
window.selectItem = i => { cur.selected = i; const it = cur.items[i];
  $('fName').value = it.name || ''; $('fRole').value = it.role || 'button';
  $('fText').value = it.text || ''; $('fNote').value = it.note || '';
  render(); };
window.delItem = i => { cur.items.splice(i, 1); cur.selected = null; render(); };

// 拖拽框选
const ov = $('overlay');
ov.addEventListener('mousedown', e => {
  const r = ov.getBoundingClientRect();
  cur.drag = { x0: e.clientX - r.left, y0: e.clientY - r.top, x1: 0, y1: 0 };
  cur.drag.x1 = cur.drag.x0; cur.drag.y1 = cur.drag.y0;
});
ov.addEventListener('mousemove', e => {
  if (!cur.drag) return;
  const r = ov.getBoundingClientRect();
  cur.drag.x1 = e.clientX - r.left; cur.drag.y1 = e.clientY - r.top;
  const img = $('shot'); const scale = cur.size[0] / (img.clientWidth || 1);
  const x = Math.min(cur.drag.x0, cur.drag.x1) * scale;
  const y = Math.min(cur.drag.y0, cur.drag.y1) * scale;
  const w = Math.abs(cur.drag.x1 - cur.drag.x0) * scale;
  const h = Math.abs(cur.drag.y1 - cur.drag.y0) * scale;
  $('status').textContent = `框选 原始(${Math.round(x)},${Math.round(y)},${Math.round(w)},${Math.round(h)})`;
});
window.addEventListener('mouseup', () => {
  if (!cur.drag) return;
  const img = $('shot'); const scale = cur.size[0] / (img.clientWidth || 1);
  const x = Math.round(Math.min(cur.drag.x0, cur.drag.x1) * scale);
  const y = Math.round(Math.min(cur.drag.y0, cur.drag.y1) * scale);
  const w = Math.round(Math.abs(cur.drag.x1 - cur.drag.x0) * scale);
  const h = Math.round(Math.abs(cur.drag.y1 - cur.drag.y0) * scale);
  cur.drag = null;
  if (w < 4 || h < 4) { $('status').textContent = '框太小, 忽略'; return; }
  cur.pending = { x, y, w, h };
  $('status').textContent = `待添加: 原始(${x},${y},${w},${h}) —— 填好右侧后点"添加标注"`;
  toast('已框选, 请填写含义');
});
$('btnAdd').onclick = () => {
  if (!cur.pending) { toast('请先在图上拖拽框选'); return; }
  const text = $('fText').value.trim();
  if (!text) { toast('"含义/说明" 必填'); return; }
  const p = cur.pending;
  const oas = toOas(p, cur.size);
  cur.items.push({
    x: p.x, y: p.y, w: p.w, h: p.h,
    oaX: oas[0], oaY: oas[1], oaW: oas[2], oaH: oas[3],
    name: $('fName').value.trim() || 'UNNAMED',
    role: $('fRole').value, text, note: $('fNote').value.trim()
  });
  cur.pending = null;
  $('fName').value = ''; $('fText').value = ''; $('fNote').value = '';
  render(); toast('已添加');
};
function toOas(b, size) {
  const [W, H] = size;
  if (W === 1280 && H === 720) return [b.x, b.y, b.w, b.h];
  if (W === 720 && H === 1280) return [H - (b.y + b.h), b.x, b.h, b.w];
  return [Math.round(b.x*1280/W), Math.round(b.y*720/H),
          Math.round(b.w*1280/W), Math.round(b.h*720/H)];
}
$('btnClear').onclick = () => { cur.pending = null; $('status').textContent = '已清空当前框'; };
$('btnReload').onclick = () => loadImage(cur.img);
$('btnSave').onclick = async () => {
  const body = { name: baseName(cur.img), image: cur.img, size: cur.size, items: cur.items };
  const r = await fetch('/api/annotation', { method: 'POST', body: JSON.stringify(body) });
  const d = await r.json();
  toast(d.ok ? '已保存: ' + d.path : '保存失败: ' + d.error);
};
$('btnExport').onclick = () => {
  const body = { name: baseName(cur.img), image: cur.img, size: cur.size, items: cur.items };
  const blob = new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = baseName(cur.img) + '.json'; a.click();
};
$('imgSelect').onchange = e => loadImage(e.target.value);
window.addEventListener('resize', render);
fillRoles(); loadImages();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    """极简 HTTP 处理器: 提供页面、图片、以及标注读写接口。"""

    current_image = None

    def log_message(self, *args):
        pass  # 静音访问日志

    def _send(self, code, body: bytes, ctype='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ('/', '/index.html'):
            html = PAGE.replace('__ROLES__', json.dumps(ROLES))
            self._send(200, html.encode('utf-8'), 'text/html; charset=utf-8')
            return
        if u.path == '/api/images':
            qs = dict(p.split('=', 1) for p in u.query.split('&') if '=' in p)
            raw = unquote(qs.get('dir', ''))
            imgs = iter_images()
            if raw:
                base = (REPO_ROOT / raw).resolve()
                imgs = [p for p in imgs if str(p.resolve()).startswith(str(base))]
            rel = [p.relative_to(REPO_ROOT).as_posix() for p in imgs]
            # 最近的排前面
            rel.sort(key=lambda s: (REPO_ROOT / s).stat().st_mtime, reverse=True)
            self._json({'images': rel, 'current': Handler.current_image})
            return
        if u.path == '/img':
            qs = dict(p.split('=', 1) for p in u.query.split('&') if '=' in p)
            rel = unquote(qs.get('path', ''))
            p = (REPO_ROOT / rel).resolve()
            if not str(p).startswith(str(REPO_ROOT)) or not p.is_file():
                self._send(404, b'not found', 'text/plain')
                return
            ctype = 'image/png' if p.suffix.lower() == '.png' else 'image/jpeg'
            self._send(200, p.read_bytes(), ctype)
            return
        if u.path == '/api/annotation':
            qs = dict(p.split('=', 1) for p in u.query.split('&') if '=' in p)
            name = unquote(qs.get('name', ''))
            self._json(load_annotation(name))
            return
        self._send(404, b'not found', 'text/plain')

    def do_POST(self):
        u = urlparse(self.path)
        if u.path != '/api/annotation':
            self._send(404, b'not found', 'text/plain')
            return
        try:
            n = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(n).decode('utf-8'))
            name = data.get('name') or 'unnamed'
            Handler.current_image = data.get('image')
            p = save_annotation(name, data)
            self._json({'ok': True, 'path': p.relative_to(REPO_ROOT).as_posix()})
        except Exception as exc:
            self._json({'ok': False, 'error': f'{type(exc).__name__}: {exc}'}, 500)


def cmd_serve(args) -> int:
    init = args.image
    if init:
        Handler.current_image = init
    srv = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    url = f'http://127.0.0.1:{args.port}/'
    print(f'标注服务已启动: {url}')
    print(f'标注将保存到: {ANNOTATION_DIR}')
    print('按 Ctrl+C 停止')
    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止')
    finally:
        srv.server_close()
    return 0


def cmd_list(args) -> int:
    if not ANNOTATION_DIR.exists():
        print('还没有任何标注')
        return 0
    files = sorted(ANNOTATION_DIR.glob('*.json'))
    if not files:
        print('还没有任何标注')
        return 0
    for f in files:
        data = json.loads(f.read_text(encoding='utf-8'))
        items = data.get('items', [])
        print(f'{f.name}  图片={data.get("image")}  标注 {len(items)} 条  '
              f'更新于 {data.get("updated_at", "?")}')
        for it in items:
            print(f'    [{it.get("role", "?"):13}] {it.get("name", "?"):28} '
                  f'OAS({it.get("oaX")},{it.get("oaY")},{it.get("oaW")},{it.get("oaH")})  '
                  f'{it.get("text", "")}')
    return 0


def cmd_crop(args) -> int:
    """把标注框裁成模板 PNG, 并输出 RuleImage 建议代码。"""
    import cv2
    import numpy as np

    data = load_annotation(args.name)
    if not data:
        print(f'找不到标注: {annotation_path(args.name)}')
        return 1
    image_rel = data.get('image')
    if not image_rel:
        print('标注里没有 image 字段')
        return 1
    src = (REPO_ROOT / image_rel).resolve()
    if not src.is_file():
        print(f'找不到截图: {src}')
        return 1

    img = cv2.imdecode(np.fromfile(str(src), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        print('截图解码失败')
        return 1
    if img.shape[0] > img.shape[1]:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

    out_dir = (REPO_ROOT / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # RuleImage 的 file= 需要仓库相对路径(OAS 的工作目录是仓库根)。
    # 若 --out 落在仓库外(例如临时目录), 无法表达为相对路径, 退化为绝对路径并给出提示。
    try:
        out_rel = out_dir.relative_to(REPO_ROOT).as_posix()
        file_prefix = f'./{out_rel}'
        outside_repo = False
    except ValueError:
        file_prefix = out_dir.as_posix()
        outside_repo = True
        print(f'提示: --out 落在仓库之外({out_dir}), 生成的 file= 将是绝对路径, '
              f'仅适合临时验证; 正式资产请输出到仓库内。')

    sugg_path = out_dir / f'{args.name}_rules.txt'
    lines = []
    n_ok = 0
    for it in data.get('items', []):
        x, y, w, h = it['oaX'], it['oaY'], it['oaW'], it['oaH']
        sub = img[y:y + h, x:x + w]
        if sub.size == 0:
            print(f'  跳过 {it.get("name")}: 区域越界')
            continue
        fname = f'{args.name}_{it.get("name", "unnamed").lower()}.png'
        cv2.imencode('.png', sub)[1].tofile(str(out_dir / fname))
        n_ok += 1
        rel_file = f'{file_prefix}/{fname}'
        lines.append(
            f'# {it.get("role")}: {it.get("text", "")}'
            + (f'  (备注: {it["note"]})' if it.get('note') else '')
        )
        lines.append(
            f'{it.get("name", "UNNAMED")} = RuleImage('
            f'roi_front=({x},{y},{w},{h}), roi_back=({x},{y},{w},{h}), '
            f'threshold=0.8, method="Template matching", file="{rel_file}")'
        )
        lines.append('')
    sugg_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'已裁出 {n_ok} 张模板到 {out_dir}')
    print(f'RuleImage 建议已写入 {sugg_path}')
    print()
    print('\n'.join(lines))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description='UI 标注工具')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('serve', help='启动标注服务')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--image', default=None, help='初始图片(仓库相对路径)')
    p.add_argument('--no-open', action='store_true', help='不自动打开浏览器')
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser('list', help='列出已有标注')
    p.set_defaults(func=cmd_list)

    p = sub.add_parser('crop', help='由标注裁剪模板并生成 RuleImage 建议')
    p.add_argument('--name', required=True, help='标注名(JSON 文件名, 不含扩展名)')
    p.add_argument('--out', required=True, help='模板输出目录(仓库相对路径)')
    p.set_defaults(func=cmd_crop)

    args = ap.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
