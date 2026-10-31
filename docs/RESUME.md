# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round20
checkpoint_seq: 49
updated_at: 2026-10-31T21:45:00+08:00
trigger: U-42b click OCR selector 已修；U-42a 展示统一待实施
status: in_progress
```

## 0. 当前状态

- 引擎代码 `3321207`；workspace **345 passed**。
- 版本 1.2.2，未 tag/release；stage 已部署 click 修复。
- U-32b/U-20 仍待。

## 1. 本轮完成（U-42b）

`failure=selector 庭院 is not declared` 根因：

- `Step::Click` 只调 `locate()`；
- `locate_one()` 只查模板 map；
- OCR 资产在 `AssetSet.ocr`，不在模板 map；
- `appear('庭院')` 有显式 OCR 分支，所以先成功；`click sel=庭院` 随即失败。

修复：

- click 识别 OCR 资产 → `ocr_read` → 点击 `action_roi` / recognized rect / OCR ROI；
- 审计 locator=`ocr`；OCR 跳过模板 stable-frame 投票；
- 测试 `click_ocr_asset_uses_action_roi_not_template_lookup`；
- stage `_diag_click`：DETECTED → click point (1085,269) → Done。

代码 `9d327bc`、`3321207`。

## 2. U-42a 展示统一（计划，未实施）

三套渲染器：

1. 工作台任务引用素材：纯文本；
2. 工作台素材库：缩略图+按钮；
3. builder 可用素材：纯文本。

计划新增共享 `asset_ui.js`：

- `makeAssetThumb`
- `createAssetRow(it, opts)`
- `renderAssetRows(container, items, opts)`

三个位置 + 集合成员统一使用；验收对比 DOM/缩略图/文案/按钮。

## 3. selector 路径举一反三

| 路径 | 状态 |
|---|---|
| click | ✅ 已支持 OCR |
| appear/wait_until | ✅ |
| dismiss_popup detect/action | 🔄 仍模板-only |
| click_target template locator | 🔄 仍模板-only |
| verify_stable_frames | OCR click 已跳过 |
| require_template | 保持模板-only |

下一步：抽 `resolve_selector` 统一 template/OCR/collection。

## 4. 下一步

1. 实现 U-42a 共享 asset_ui；
2. `resolve_selector` 收口 dismiss_popup/click_target；
3. U-32b positions 批量验收；
4. U-20 多选整组拖动；
5. 发布时才 bump/tag/release。

## 5. 证据

- PENDING §E-42；代码 `3321207`；345 tests；stage 8788。
