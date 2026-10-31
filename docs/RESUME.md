# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round26
checkpoint_seq: 55
updated_at: 2026-10-31T22:50:00+08:00
trigger: 召唤素材简繁/异体字匹配已修复
status: in_progress
```

## 0. 当前状态

- 引擎代码 `e6acff0`；workspace **347 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步。

## 1. 本轮修复（U-47）

现象：同一 ROI 手动多行识别能识别；保存「召唤」素材后素材行识别失败并全屏回退。

根因：不是识别/操作区域错误。

- `/lines` 实际输出：`召喚`（score 0.826）；
- 素材 `ocr_text`：`召唤`；
- 运行期/编辑器用精确字符串比较，未命中；
- 于是触发全屏 fallback，看起来“识别失败”。

修复：`oas_runtime::ocr_text_matches`

- 去空白/标点后精确；
- 多字符再允许 Levenshtein ≤1（简繁/异体字单字差异）；
- 用于 derived OCR、click_target/drag OCR 文字、text_visible、batch；
- 前端 `ocrTextMatches` 同规则。

实测：素材「召唤」→ `召喚 (0.826)`，期望 `召唤` → 匹配，不再回退。

## 2. 仍待

1. U-32b 批量实帧验收；
2. 实时 WS 弱设备观察；
3. 发布前整体验收。

## 3. 下一步

1. 用户重试「召唤」；
2. positions 批量；
3. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-47；代码 `e6acff0`；347 tests；stage 8788。
