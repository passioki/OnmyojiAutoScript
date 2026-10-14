# -*- coding: utf-8 -*-
"""★ C4 判断结果 —— 流程控制面（`docs/DESIGN-SPEC.md` §1.19-C4）。

## 为什么要有这个模块

★ 实测（SPEC §1.19-二-C4）：★ 现在的"判断"**返回值有三种形状**：

| 入口 | 返回 | 出处 |
|---|---|---|
| `RuleImage.match()` | ★ `bool` | `module/atom/image.py:219` |
| `RuleOcr.ocr()` | ★ `tuple` | `module/atom/ocr.py:31`（★ mode 不同长度还不同）|
| `RuleList` 的查找 | ★ `int` / `tuple` / `bool` | `module/atom/list.py` |

★ ⇒ ★ **同一张流程图上的"菱形"没法统一接**：
  ★ 想拿"分数/位置/识别到的文本"就得**因类型而异**地解包。

## ★ P0 只加不改

★ 本模块**只提供统一的载体**，★ **不动** `appear()` / `RuleImage.match()` 的现有签名
  （★ 那会碰 20+ 个任务与大量测试替身 —— 见 §1.18-七 风险 4）。
★ 接入（让 `appear()` 返回 `Match`）是 **P1** 的事。
"""
from dataclasses import dataclass

__all__ = ['Match']

#: ★ 匹配框的类型别名：`(x, y, w, h)`（★ 与 `RuleImage.match_all` 一致）
Roi = tuple


@dataclass(frozen=True)
class Match:
    """★★ C4：一次"判断"的结论（★ 统一的载体）。

    ★ 它一次装下四种信息（★ 现在要**四种不同解包方式**才拿得到）：

    | 字段 | 现在从哪来 | 用途 |
    |---|---|---|
    | `ok` | ★ `appear()` 的 `bool` | ★ 分支 |
    | `score` | ★ `RuleImage.last_score`（`atom/image.py:35`）| ★ 调阈值 / 记日志 |
    | `roi` | ★ `match_all()` 的 `(score,x,y,w,h)`（`image.py:351`）| ★ 点判定框（★ 而不是素材 ROI）|
    | `text` | ★ `RuleOcr.ocr()` 的文本 | ★ 日志 / 再解析 |
    """

    ok: bool
    #: ★ 成立吗

    score: float = 0.0
    #: ★ 相似度 / 置信度（★ 不适用时 0.0）

    roi: Roi | None = None
    #: ★ 命中框 `(x, y, w, h)`（★ 不适用时 `None`）

    text: str = ''
    #: ★ 识别到的文本（★ 非 OCR 判断时为空串）

    # ---------------------------------------------------------------- 构造器
    @classmethod
    def hit(cls, score: float = 0.0, roi: Roi = None,
            text: str = '') -> 'Match':
        """★ 成立。"""
        return cls(ok=True, score=float(score or 0.0), roi=roi,
                   text=str(text or ''))

    @classmethod
    def miss(cls, score: float = 0.0, text: str = '') -> 'Match':
        """★ 不成立（★ 保留 `score` —— ★ "差多少"对调阈值有用）。"""
        return cls(ok=False, score=float(score or 0.0), roi=None,
                   text=str(text or ''))

    def __bool__(self) -> bool:
        """★ 让判断结果能直接当条件用：`if match:`"""
        return bool(self.ok)
