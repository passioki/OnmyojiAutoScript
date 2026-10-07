# This Python file uses the following encoding: utf-8
"""
识别规则缺陷扫描器。

背景: RuleImage 的模板匹配窗口由 roi_back 决定, 而候选裁剪在 image.py:corp() 中
按 roi_back 从截图里取子图。如果 roi_back 的宽高小于模板图片的宽高, matchTemplate
的源图比模板还小, match() 会静默 return False —— 这条规则永远不可能命中。

如果 roi_back 的宽高恰好等于模板宽高, 源图与模板同尺寸, matchTemplate 只会得到
一个结果, 匹配退化成"定点像素比对": 没有任何位置容差, UI 偏移一两个像素即失配。

本脚本以运行时对象的实际属性为准(而非正则解析源码), 因为 assets.py 是
dev_tools/assets_extract.py 自动生成的, 直接 import 比解析文本更可靠。

用法:
    toolkit\\python.exe dev_tools\\assets_roi_audit.py
    toolkit\\python.exe dev_tools\\assets_roi_audit.py --csv out.csv
"""
import argparse
import csv
import importlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 这些方法不依赖 roi_back 尺寸做模板匹配, 不参与本次审计
SKIP_METHODS = {
    'Sift Flann',
    'Color',
    'Brightness',
    'Saturation',
    'Mean color',
}


def image_size(path: Path) -> tuple[int, int] | None:
    """
    读取图片宽高, 不依赖 Pillow/OpenCV 的完整解码。

    :param path: 图片路径
    :return: (width, height), 读取失败返回 None
    """
    try:
        import cv2
        import numpy as np
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        img = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        h, w = img.shape[:2]
        return int(w), int(h)
    except Exception:
        return None


@dataclass
class Finding:
    """单条规则的问题记录。"""

    rule: str
    task: str
    roi_back: tuple
    template: tuple
    method: str
    threshold: float
    file: str
    level: str

    @property
    def margin_w(self) -> int:
        return self.roi_back[2] - self.template[0]

    @property
    def margin_h(self) -> int:
        return self.roi_back[3] - self.template[1]


@dataclass
class AuditResult:
    total: int = 0
    skipped_no_file: int = 0
    skipped_missing_template: int = 0
    critical: list = field(default_factory=list)   # roi_back < template, 永不命中
    degenerate: list = field(default_factory=list)  # roi_back == template, 无容差
    healthy: int = 0
    # 模板文件不存在, 但只被不读图的 click() 使用 => 无害
    missing_benign: list = field(default_factory=list)
    # 模板文件不存在, 且被 appear()/match() 调用 => 一旦执行即 FileNotFoundError
    missing_risky: list = field(default_factory=list)
    # 模板文件不存在且无任何引用 => 死规则
    missing_dead: list = field(default_factory=list)

    def by_task(self, findings: list) -> dict:
        out: dict[str, int] = {}
        for f in findings:
            out[f.task] = out.get(f.task, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _iter_py_sources():
    """
    遍历仓库内参与检索的 .py 源码(排除 assets.py 与 __pycache__)。

    判定"是否读图"必须区分调用方法: click() 只取 coord() 数值, 不触发 load_image;
    只有 appear()/appear_then_click()/match()/test_match() 才会真正读取模板文件。

    同时剔除整行注释, 否则被注释掉的调用会被误判为有效调用。

    :return: 生成 (相对路径, 参与检索的代码文本)
    """
    for base in ('tasks', 'module'):
        for py in (REPO_ROOT / base).rglob('*.py'):
            if '__pycache__' in py.parts or py.name == 'assets.py':
                continue
            try:
                raw = py.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            lines = []
            for line in raw.splitlines():
                stripped = line.lstrip()
                if stripped.startswith('#'):
                    continue
                # 去掉行尾注释(够用即可, 不做完整词法分析)
                if '#' in line:
                    line = line.split('#', 1)[0]
                lines.append(line)
            yield py.relative_to(REPO_ROOT).as_posix(), '\n'.join(lines)


def classify_missing(rule_names: set[str]) -> dict[str, str]:
    """
    判断给定规则名在代码中的使用方式。

    :param rule_names: 待判定的规则名集合
    :return: {规则名: 'risky' | 'benign' | 'dead'}
    """
    risky: set[str] = set()
    benign: set[str] = set()

    # 会触发 load_image() 的调用形态
    read_patterns = (
        r'appear_then_click\s*\(\s*(?:self\.)?{n}\b',
        r'appear\s*\(\s*(?:self\.)?{n}\b',
        r'match\s*\(\s*(?:self\.)?{n}\b',
        r'test_match\s*\(\s*(?:self\.)?{n}\b',
        r'wait_until_appear\w*\s*\(\s*(?:self\.)?{n}\b',
    )
    # 不读图的调用形态
    benign_patterns = (
        r'click\s*\(\s*(?:self\.)?{n}\b',
        r'coord\s*\(\s*(?:self\.)?{n}\b',
    )

    for name in rule_names:
        state = 'dead'
        for _, text in _iter_py_sources():
            if name not in text:
                continue
            for pat in read_patterns:
                if re.search(pat.format(n=re.escape(name)), text):
                    risky.add(name)
                    state = 'risky'
                    break
            if state == 'risky':
                break
            for pat in benign_patterns:
                if re.search(pat.format(n=re.escape(name)), text):
                    benign.add(name)
                    if state == 'dead':
                        state = 'benign'
        if state == 'dead':
            continue
    # 汇总: risky 优先于 benign
    out: dict[str, str] = {}
    for name in rule_names:
        if name in risky:
            out[name] = 'risky'
        elif name in benign:
            out[name] = 'benign'
        else:
            out[name] = 'dead'
    return out


def iter_assets_modules():
    """
    遍历 tasks/ 下所有 assets.py 模块路径。

    :return: 生成 (task_name, module_name) 二元组
    """
    tasks_dir = REPO_ROOT / 'tasks'
    for assets_path in sorted(tasks_dir.rglob('assets.py')):
        rel = assets_path.relative_to(REPO_ROOT)
        module_name = '.'.join(rel.with_suffix('').parts)
        task_name = rel.parts[1] if len(rel.parts) > 2 else rel.parts[1]
        yield task_name, module_name


def collect_rules(module) -> list:
    """
    提取模块中所有 RuleImage 实例。

    注意: assets_extract.py 生成的结构是 `class XxxAssets:` 类体, 规则挂在类属性上,
    而非模块属性。因此必须同时遍历模块顶层属性与模块内定义的类属性, 否则会漏掉全部
    规则(实测漏检会得到 0 条)。

    :param module: 已导入的 assets 模块
    :return: (归属名, 属性名, RuleImage 实例) 列表
    """
    import inspect

    from module.atom.image import RuleImage

    found = []
    seen: set[int] = set()

    def scan(owner, owner_name: str) -> None:
        for name in dir(owner):
            if name.startswith('__'):
                continue
            try:
                obj = getattr(owner, name)
            except Exception:
                continue
            if isinstance(obj, RuleImage) and id(obj) not in seen:
                seen.add(id(obj))
                found.append((owner_name, name, obj))

    # 1. 模块顶层
    scan(module, module.__name__.rsplit('.', 1)[-1])
    # 2. 模块内定义的类(即 XxxAssets)
    for attr_name, attr in vars(module).items():
        if inspect.isclass(attr) and attr.__module__ == module.__name__:
            scan(attr, attr_name)

    return found


def audit() -> AuditResult:
    """
    执行全仓库审计。

    :return: AuditResult
    """
    result = AuditResult()
    missing_names: dict[str, Finding] = {}

    for task_name, module_name in iter_assets_modules():
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            print(f'[跳过] {module_name}: 导入失败 {type(exc).__name__}: {exc}',
                  file=sys.stderr)
            continue

        for owner_name, attr_name, rule in collect_rules(module):
            method = getattr(rule, 'method', '') or ''
            if method in SKIP_METHODS:
                continue

            file_attr = getattr(rule, 'file', None)
            if not file_attr:
                continue

            template_path = (REPO_ROOT / str(file_attr).lstrip('./')).resolve()
            size = image_size(template_path)
            if size is None:
                result.skipped_missing_template += 1
                missing_names[attr_name] = Finding(
                    rule=attr_name,
                    task=task_name,
                    roi_back=tuple(int(v) for v in rule.roi_back),
                    template=(0, 0),
                    method=method,
                    threshold=float(getattr(rule, 'threshold', 0.0)),
                    file=str(file_attr),
                    level='MISSING',
                )
                continue

            roi_back = tuple(int(v) for v in rule.roi_back)
            entry = Finding(
                rule=attr_name,
                task=task_name,
                roi_back=roi_back,
                template=size,
                method=method,
                threshold=float(getattr(rule, 'threshold', 0.0)),
                file=str(file_attr),
                level='',
            )
            result.total += 1

            if roi_back[2] < size[0] or roi_back[3] < size[1]:
                entry.level = 'CRITICAL'
                result.critical.append(entry)
            elif roi_back[2] == size[0] and roi_back[3] == size[1]:
                entry.level = 'DEGENERATE'
                result.degenerate.append(entry)
            else:
                result.healthy += 1

    # 按调用方式给"模板缺失"分级, 避免把只用于 click() 的纯点击区域误判为崩溃风险
    if missing_names:
        verdict = classify_missing(set(missing_names))
        for name, entry in missing_names.items():
            kind = verdict.get(name, 'dead')
            entry.level = kind.upper()
            if kind == 'risky':
                result.missing_risky.append(entry)
            elif kind == 'benign':
                result.missing_benign.append(entry)
            else:
                result.missing_dead.append(entry)

    return result


def print_report(res: AuditResult) -> None:
    """
    打印人类可读报告。

    :param res: AuditResult
    """
    print('=' * 78)
    print('识别规则 ROI 审计报告')
    print('=' * 78)
    print(f'参与审计的 RuleImage 规则总数 : {res.total}')
    print(f'  搜索区 > 模板 (健康, 有容差) : {res.healthy}')
    print(f'  搜索区 = 模板 (退化为定点比对): {len(res.degenerate)}'
          f'  ({100.0 * len(res.degenerate) / max(res.total, 1):.1f}%)')
    print(f'  搜索区 < 模板 (永不命中)     : {len(res.critical)}')
    print(f'  模板文件缺失/不可读          : {res.skipped_missing_template}'
          f'  (risky {len(res.missing_risky)} / benign {len(res.missing_benign)}'
          f' / dead {len(res.missing_dead)})')
    print()

    if res.critical:
        print('-' * 78)
        print(f'[CRITICAL] 搜索区小于模板, 这些规则永远不可能匹配成功 ({len(res.critical)} 条)')
        print('-' * 78)
        for f in sorted(res.critical, key=lambda x: (x.task, x.rule)):
            print(f'  {f.task:<24} {f.rule:<34} '
                  f'roi_back={f.roi_back[2]}x{f.roi_back[3]} '
                  f'< template={f.template[0]}x{f.template[1]} '
                  f'(缺 {-f.margin_w}x{-f.margin_h})')
        print()

    if res.missing_risky:
        print('-' * 78)
        print(f'[MISSING-RISKY] 模板文件不存在, 且被 appear()/match() 调用'
              f' ({len(res.missing_risky)} 条)')
        print('一旦该代码路径被执行, load_image() 会抛 FileNotFoundError 硬崩溃。')
        print('-' * 78)
        for f in sorted(res.missing_risky, key=lambda x: (x.task, x.rule)):
            print(f'  {f.task:<24} {f.rule:<34} {f.file}')
        print()

    if res.missing_dead:
        print('-' * 78)
        print(f'[MISSING-DEAD] 模板文件不存在且无任何代码引用 ({len(res.missing_dead)} 条)')
        print('仅污染 assets.py, 建议删除对应数据源以防后续被误用。')
        print('-' * 78)
        for f in sorted(res.missing_dead, key=lambda x: (x.task, x.rule)):
            print(f'  {f.task:<24} {f.rule}')
        print()

    if res.missing_benign:
        print('-' * 78)
        print(f'[MISSING-BENIGN] 模板文件不存在, 但仅被不读图的 click() 使用'
              f' ({len(res.missing_benign)} 条)')
        print('click() 只取 coord() 数值, 不触发 load_image, 因此无害。')
        print('-' * 78)
        for f in sorted(res.missing_benign, key=lambda x: (x.task, x.rule)):
            print(f'  {f.task:<24} {f.rule}')
        print()

    if res.degenerate:
        print('-' * 78)
        print(f'[DEGENERATE] 搜索区等于模板, 无任何位置容差 ({len(res.degenerate)} 条)')
        print('按任务分组:')
        print('-' * 78)
        for task, n in res.by_task(res.degenerate).items():
            print(f'  {task:<28} {n} 条')
        print()

    if res.critical:
        print('按任务分组的 CRITICAL:')
        for task, n in res.by_task(res.critical).items():
            print(f'  {task:<28} {n} 条')


def write_csv(res: AuditResult, path: Path) -> None:
    """
    导出 CSV 便于逐条处理。

    :param res: AuditResult
    :param path: 输出路径
    """
    with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['level', 'task', 'rule', 'method', 'threshold',
                         'roi_back_w', 'roi_back_h', 'template_w', 'template_h',
                         'margin_w', 'margin_h', 'file'])
        for f in sorted(res.critical + res.degenerate,
                        key=lambda x: (x.level, x.task, x.rule)):
            writer.writerow([f.level, f.task, f.rule, f.method, f.threshold,
                             f.roi_back[2], f.roi_back[3],
                             f.template[0], f.template[1],
                             f.margin_w, f.margin_h, f.file])
    print(f'CSV 已写入: {path}')


def main() -> int:
    parser = argparse.ArgumentParser(description='识别规则 ROI 审计')
    parser.add_argument('--csv', type=str, default=None,
                        help='额外导出 CSV 报告到指定路径')
    args = parser.parse_args()

    # 屏蔽导入期的日志噪音, 只保留本脚本输出
    import logging
    logging.disable(logging.CRITICAL)

    res = audit()
    logging.disable(logging.NOTSET)

    print_report(res)
    if args.csv:
        write_csv(res, Path(args.csv).resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
