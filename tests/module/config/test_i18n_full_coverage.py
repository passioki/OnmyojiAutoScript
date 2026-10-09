# -*- coding: utf-8 -*-
"""翻译完整性守卫 —— 防止"界面显示英文 key"再次发生。

## 为什么需要这组测试

本次实测: 后端全部 291 个英文字段 key 里, **113 个**在
`module/config/i18n/zh-CN.json` 与 OASX 的 `lib/config/translation/i18n_cn.dart`
**两边都没有** —— 于是界面上直接显示 `charge_enable_help`、`Raid Mode` 这类
英文。而 GetX 的 `.tr` 查不到 key 时**原样返回**，**没有任何报错**，
所以这个缺口长期无人发现。

## 覆盖

1. 所有英文字段 key（`title` / `description`）都能在后端表里查到
2. `PUT /home/chinese_translate` 是**增量合并**，不再整份覆盖
   （原来前端 746 条覆盖后端 1090 条 → 每次启动丢 344 条）
3. `GET /home/chinese_translate` 返回**全量**，且含新补的 key
4. 任务中文名与 `TaskSpec.name_zh` 一致（既有 `test_i18n_consistency` 已覆盖，
   这里只补"字段 key"这一维度）
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
ZH = REPO / 'module' / 'config' / 'i18n' / 'zh-CN.json'
OASX = Path(r'D:\OAS-dev\OASX-src')
DART_CN = OASX / 'lib' / 'config' / 'translation' / 'i18n_cn.dart'

CJK = re.compile(r'[\u4e00-\u9fff]')
# pydantic Field(...) 里形如 description='xxx_help' / title='Enable'
FIELD_KV = re.compile(r"(?:description|title)\s*=\s*'([^']+)'")


def code_only(text: str) -> str:
    """剥掉注释与文档字符串（`#` 行内/整行、`//`、三引号块）。

    ★ 必须这么做: 否则"我在注释/文档里说明**原来的错误写法**"会把
      `assert '错误写法' not in src` 这类守卫**误判成失败**。
      （踩过: `costume_base.py` 里注释含 `exit(1)`、这里文档含
      `save_zh_cn(data)` 与 `putChineseTranslate()`。）
    """
    # 三引号块(文档字符串)整体去掉
    text = re.sub(r'"""[\s\S]*?"""', '', text)
    text = re.sub(r"'''[\s\S]*?'''", '', text)
    out = []
    for line in text.split('\n'):
        s = line.strip()
        if s.startswith('//') or s.startswith('#') or s.startswith('*'):
            continue
        # 行内注释: 去掉 `#` 之后的部分（dart 的 `//` 同理）
        for marker in ('  # ', ' # ', '  // ', ' // '):
            idx = line.find(marker)
            if idx != -1:
                line = line[:idx]
                break
        out.append(line)
    return '\n'.join(out)


def _backend_map() -> dict:
    return json.loads(ZH.read_text(encoding='utf-8'))


def _dart_map() -> set:
    if not DART_CN.exists():
        return set()
    return set(re.findall(r"^\s*'([^']+)':", DART_CN.read_text(encoding='utf-8'),
                          re.M))


def _english_field_keys() -> set:
    """扫所有任务 config.py, 收集**不含中文**的 title/description。"""
    out = set()
    for p in (REPO / 'tasks').rglob('config.py'):
        text = p.read_text(encoding='utf-8', errors='replace')
        for m in re.finditer(r'Field\(((?:[^()]|\([^()]*\))*)\)', text, re.S):
            for v in FIELD_KV.findall(m.group(1)):
                if not CJK.search(v):
                    out.add(v)
    return out


class TestFieldKeyCoverage:
    """所有英文字段 key 都必须有中文。"""

    def test_no_english_field_key_left_untranslated(self):
        back = set(_backend_map())
        front = _dart_map()
        keys = _english_field_keys()

        assert keys, '没扫到任何英文字段 key —— 说明扫描逻辑坏了, 不是好事'

        missing = sorted(k for k in keys if k not in back and k not in front)
        assert not missing, (
            f'{len(missing)} 个 key 在**后端与前端都没有**中文, '
            f'界面上会直接显示英文: {missing}')

    def test_backend_covers_all_field_keys(self):
        """后端表必须**自己**覆盖全部 —— 前端不该再维护第二份。"""
        back = set(_backend_map())
        missing = sorted(k for k in _english_field_keys() if k not in back)
        assert not missing, (
            f'{len(missing)} 个 key 后端缺译文（前端有不算, 因为后端是单一数据源）: '
            f'{missing}')

    def test_previously_missing_keys_are_present(self):
        """本次补的 113 个里的代表项 —— 防止有人"清理"掉它们。"""
        back = _backend_map()
        must = [
            'charge_enable_help', 'charge_max_help', 'charge_slots_help',
            'charge_consume_help', 'zone_name_help', 'raid_mode_help',
            'Enable', 'Raid Mode', 'AP', 'Layer 10',
            'pass_group_team_help', 'enable_switch_ap_help',
            'costume_battle_scene_type_help', 'min_run_interval_help',
        ]
        missing = [k for k in must if not back.get(k)]
        assert not missing, f'这些 key 又没了: {missing}'

    def test_translated_values_are_actually_chinese(self):
        """防止用"英文占位"蒙混过关。"""
        back = _backend_map()
        bad = []
        for k in _english_field_keys():
            v = back.get(k)
            if v and not CJK.search(v):
                bad.append((k, v))
        assert not bad, f'这些 key 的"译文"里没有中文: {bad}'


class TestSingleSourceOfTruth:
    """翻译只有一个数据源：后端 `module/config/i18n/zh-CN.json`。"""

    def test_put_endpoint_merges_instead_of_overwriting(self):
        """★ 回归守卫: `PUT /home/chinese_translate` 不能整份覆盖。

        原来它是 `I18n.save_zh_cn(data)` —— 前端 746 条覆盖后端 1090 条,
        **每次启动丢 344 条**。现在必须是**增量合并**。
        """
        src = code_only((REPO / 'module' / 'server' / 'home_router.py').read_text(
            encoding='utf-8'))
        i = src.index("async def chinese_translate(data")
        j = src.index('async def', i + 10)
        body = src[i:j]
        assert 'load_zh_cn' in body, 'PUT 处理函数必须先读现有表（增量合并）'
        assert 'existing.update' in body or 'added' in body, '缺少合并逻辑'
        assert 'save_zh_cn(data)' not in body, (
            'PUT 又变成整份覆盖了 —— 会丢掉后端已有的条目')

    def test_full_map_endpoint_exists(self):
        """必须有"给前端拉全量"的 GET 端点。"""
        src = (REPO / 'module' / 'server' / 'home_router.py').read_text(
            encoding='utf-8')
        assert "get('/chinese_translate')" in src, \
            '缺少 GET /home/chinese_translate（前端拉取全量翻译的入口）'

    def test_endpoint_returns_full_map(self):
        """端点实际返回的条数必须 >= 后端表（含额外词条）。"""
        import asyncio
        import sys
        sys.path.insert(0, str(REPO))
        from module.server.home_router import chinese_translate_all

        got = asyncio.new_event_loop().run_until_complete(chinese_translate_all())
        back = _backend_map()
        assert len(got) >= len(back), (
            f'端点只返回 {len(got)} 条, 少于后端表的 {len(back)} 条')
        for k in ('charge_enable_help', 'Raid Mode', 'Enable'):
            assert got.get(k), f'端点没返回 {k}'

    def test_frontend_pulls_instead_of_pushes(self):
        """★ 回归守卫: OASX 启动必须**拉取**翻译, 不能推自己那份覆盖后端。"""
        nav = code_only((OASX / 'lib' / 'controller' / 'ctrl_nav.dart').read_text(
            encoding='utf-8'))
        assert 'loadFromBackend' in nav, \
            'OASX 启动时没有从后端拉取翻译'
        # `putChineseTranslate()` 调用必须已移除（它会触发覆盖）
        assert 'putChineseTranslate()' not in nav, \
            'OASX 启动仍在推自己那份翻译 —— 会覆盖后端'

    def test_frontend_records_missing_keys(self):
        """★ 未命中必须**可见**（记录 + 上报），不能静默返回 key。"""
        loc = code_only(
            (OASX / 'lib' / 'service' / 'locale_service.dart').read_text(
                encoding='utf-8'))
        assert 'missingKeys' in loc, '缺少未命中记录'
        assert 'trOrRecord' in loc, '缺少记录式翻译入口'
        assert 'reportMissing' in loc, '缺少上报'
        args = code_only(
            (OASX / 'lib' / 'views' / 'args' / 'args_view.dart').read_text(
                encoding='utf-8'))
        assert 'trOrRecord' in args, \
            '任务设置页没走记录式翻译 —— 缺口又会被静默吞掉'
        assert 'model.title.tr' not in args, \
            '任务设置页又直接 .tr 了（未命中不会记录）'

    def test_backend_has_missing_translate_sink(self):
        """后端要能接收前端上报的缺失 key。"""
        src = (REPO / 'module' / 'server' / 'home_router.py').read_text(
            encoding='utf-8')
        assert "missing_translate" in src, '缺少缺失 key 的接收端点'
