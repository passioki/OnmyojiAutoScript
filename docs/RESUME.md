# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round25
checkpoint_seq: 54
updated_at: 2026-10-31T22:45:00+08:00
trigger: OCR 测试识别区域标注 + 全屏回退已修
status: in_progress
```

## 0. 当前状态

- 引擎代码 `3bec494`；workspace **346 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步。

## 1. 本轮修复（U-46）

问题：
1. 识别测试疑似用操作区域；
2. 失败后没有退回全屏识别。

修复：

- `assetRecognitionBox`：
  - 普通 OCR → `roi`；
  - 多行来源 `ocr_line` → `ocr_source_roi`；
  - **永不使用 `action_roi`**。
- 结果窗口显式标注：
  - 多行来源 ROI / 行 ROI / 操作区域（仅点击）。
- 全屏回退：
  - `/ocr` 报错或空文字；
  - `/lines` 0 行；
  - derived OCR 的 `ocr_text` 未找到；
  - → `fallbackFullscreenLines()` 调 `/lines` 全屏，结果写入「识别结果」并提示勾选。

实测 `图鉴`：
- 多行来源 `[88,650,1093,36]`；
- 行 ROI `[90,650,60,36]`；
- 操作区域 `[82,601,80,89]`（仅点击）；
- 失败 → 全屏 13 行。

## 2. 仍待

1. U-32b 批量实帧验收；
2. 实时 WS 弱设备观察；
3. 发布前整体验收。

## 3. 下一步

1. 用户重试识别测试；
2. positions 批量；
3. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-46；代码 `3bec494`；346 tests；stage 8788。
