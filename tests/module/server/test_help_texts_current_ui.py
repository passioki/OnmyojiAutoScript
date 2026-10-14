# -*- coding: utf-8 -*-
"""★ 守卫：`/schema` 的**说明文案**不许引用**界面上已不存在的词**（台账 `T21`）。

## ★★ 这条守什么（用户报的体感）

> ★ 用户 [10-13/10-14]：★ 界面上看着"**像旧版**" ——
>   ★ 因为 `loop_times` 的 help 写着：
>   > 「★ 『**跑空后**』选『**队列循环**』时才生效」
>
> ★ 而**现行界面里这两个词都不存在**：
>   * `when_task_queue_empty` 的 label 是「**播放模式**」（`schema_router.py:428`）
>   * 它的选项文字是 **顺序 / 循环 / 乱序**（`schema_router.py:330-339`）
>
> ⇒ ★ 用户在界面上**找不到**「跑空后 / 队列循环」
>   ⇒ ★ 会以为"这功能是不是被删了"（★ 而且**没法自查**）。

## ★ 为什么必须**自动**守（而不是"记得改"）

★ 这类漂移是**静默**的：★ 文案是字符串，改 UI 名字时**没有任何东西会报错**
  ⇒ ★ 只有"用户读到并觉得不对"才发现（★ 本次就是这样发现的）。
★ ⇒ ★ 用一条**可失败的**断言把"现行 UI 词表"钉住。

## ★ 做法：**交叉一致性**（不是硬编码黑名单）

1. ★ 从 schema **自己的** `queue_labels` / `queue_hints` 里取"现行模式词"
2. ★ 断言**别的** help 文案只许引用这些词（★ 引用旧词 ⇒ 红）
3. ★ 权威来源**只有一处** ⇒ ★ 以后改 UI 名字 ⇒ 这条断言自动跟着变
"""
from pathlib import Path

import pytest

#: ★ 与 `tests/module/server/test_schema_router.py` 用**同一个**账号配置名
CONFIG = '恋鸟树'


@pytest.fixture(scope='module')
def schema():
    """★ 自己声明（**不能**依赖别的测试文件的类内 fixture —— 那不可见）。"""
    if not (Path.cwd() / 'config' / f'{CONFIG}.json').exists():
        pytest.skip(f'缺少配置 {CONFIG}')
    from module.server.schema_router import build_schema
    return build_schema(CONFIG)


def _field_helps(schema: dict) -> dict:
    """收集 `/schema` 里**所有**字段级 `help` 文案：{字段名: 文案}。

    ⚠ 注意：★ 这些字段实际挂在 **`schema['list']['global_fields']`**
      （★ 实测 `schema['global_fields']` 是**空**的 —— 我第一版就取错了，
        于是断言 `text == ''` **假红**）。★ 两处都取，避免再次踩。
    """
    out = {}
    buckets = [schema.get('global_fields'),
               (schema.get('list') or {}).get('global_fields')]
    for bucket in buckets:
        if not isinstance(bucket, dict):
            continue
        for name, spec in bucket.items():
            if not isinstance(spec, dict):
                continue
            help_text = spec.get('help')
            if help_text:
                out[name] = str(help_text)
    return out


class TestHelpTextsMatchCurrentUi:
    """★ 说明文案必须与**现行界面词**一致（★ 防"看着像旧版"）。"""

    def test_no_legacy_queue_mode_words_in_any_help(self, schema):
        """★★ 核心：**任何** help 都不许出现「跑空后」/「队列循环」这类**旧词**。

        ★ 依据：★ 现行 UI 用的是「**播放模式**」+ **顺序 / 循环 / 乱序**
          （`schema_router.py:428` / `:330-339`）。
        ★ 用户看不到"跑空后" ⇒ 看到这两个词只会**困惑**。
        """
        helps = _field_helps(schema)
        assert helps, '前置：schema 里应有带 help 的字段'
        legacy = ('跑空后', '队列循环')
        hits = {name: text for name, text in helps.items()
                for w in legacy if w in text}
        assert not hits, (
            '★★ 这些字段的 help 引用了**界面上已不存在**的旧词 '
            f'{legacy}：\n' + '\n'.join(
                f'  · {n}: {t!r}' for n, t in hits.items())
            + '\n★ 现行 UI 是「播放模式」+ 顺序/循环/乱序 —— '
              '请改用现行词（见 `queue_labels` / `queue_hints`）')

    def test_loop_times_help_points_at_current_ui(self, schema):
        """★ `loop_times` 的 help 必须指向**现行**的「播放模式」+「循环」。

        ★ 台账 `T21` 的原文：「`loop_times` 的 help 文案改"播放模式"口径
          （现仍写「跑空后/队列循环」）」。
        """
        helps = _field_helps(schema)
        text = helps.get('loop_times', '')
        assert text, '前置：`loop_times` 应有 help'
        assert '播放模式' in text, (
            '★ `loop_times` 的 help 必须提**现行**控件名「播放模式」'
            f'（否则用户对不上界面）。实际：{text!r}')
        assert '循环' in text, (
            f'★ `loop_times` 的 help 必须说清"只在【循环】模式生效"。实际：{text!r}')

    def test_help_words_exist_in_ui_vocabulary(self, schema):
        """★ 交叉一致性：help 里提到的**模式词**必须在 UI 词表里真实存在。

        ★ 为什么这样写（而不是硬编码）：★ "现行词"的**唯一权威**是
          schema 自己的 `list.global_fields.when_task_queue_empty.choices`
          （★ 实测路径 —— `schema_router.py:330-352` 的 `queue_labels` /
            `queue_hints` 就是它）。
        ★ 以后改了 UI 名字 ⇒ 本断言**自动**跟着新词表变 ⇒ 不会变成第二条死链。
        """
        mode = (((schema.get('list') or {}).get('global_fields') or {})
                .get('when_task_queue_empty') or {})
        labels = {str(c.get('label')) for c in (mode.get('choices') or [])
                  if isinstance(c, dict)}
        assert labels, (
            '★ 找不到「播放模式」的选项词表（`list.global_fields.'
            'when_task_queue_empty.choices`）—— schema 结构变了，'
            '请更新本守卫的取法（★ 不许假装通过）')

        helps = _field_helps(schema)
        text = helps.get('loop_times', '')
        referenced = {w for w in labels if w in text}
        assert referenced, (
            f'★ `loop_times` 的 help 必须引用**至少一个**现行模式词 '
            f'{sorted(labels)}（否则用户对不上界面）。实际：{text!r}')
        assert '播放模式' in text, (
            '★ `loop_times` 的 help 必须提**现行**控件名「播放模式」。'
            f'实际：{text!r}')

    def test_playlist_mode_label_is_the_current_one(self, schema):
        """★ 钉住现行控件名 = 「**播放模式**」（★ 它是别的 help 的引用锚点）。

        ★ 为什么要有：★ 上面那条断言里我引用了「播放模式」这个字符串 ——
          ★ 若它被改名而**没人同步 help**，那条断言会**假绿**。
          ★ 所以这里把"锚点"本身钉死（改名时必须**显式**改这条 + 所有 help）。
        """
        mode = (((schema.get('list') or {}).get('global_fields') or {})
                .get('when_task_queue_empty') or {})
        assert mode, '前置：schema 应有 `when_task_queue_empty` 字段'
        assert mode.get('label') == '播放模式', (
            f'★ 该控件的现行 label 应是「播放模式」，实际 {mode.get("label")!r}；'
            '★ 若确实要改名 ⇒ 请**同时**更新所有引用它的 help 文案 + 本守卫')
