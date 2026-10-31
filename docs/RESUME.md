# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round21
checkpoint_seq: 50
updated_at: 2026-10-31T22:00:00+08:00
trigger: U-42a 素材卡片统一 + U-42b selector OCR 收口完成
status: in_progress
```

## 0. 当前状态

- 引擎代码 `567917c`；workspace **346 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步/重启 8788。
- U-32b 批量实帧验收、U-20 多选整组拖动仍待。

## 1. 本轮完成（U-42）

### 素材展示统一

新增 `apps/oasd/ui/asset_ui.js`：

- `makeThumb` / `createRow` / `renderRows`；
- 工作台「当前任务引用的素材」、工作台「素材库」、builder「可用素材」三处共用；
- 统一缩略图、kind、ROI/操作区域/位置帧、测试/点测/拖测/步骤；
- 素材库 header 保留；builder compact 模式。

CDP stage 验收：

- 任务引用 5 行、素材库 23 行，均 `asset-row`；
- builder 23 行 `asset-row asset-row-compact`；
- `__oasErrors=[]`。

### selector 收口

- `locate()` 支持 OCR 资产（single/multi/derived）及集合 OCR 成员；
- `click` / `dismiss_popup` / `click_target` 的 template locator 都能落到 OCR `action_roi`；
- `selector_threshold` 对 OCR 返回 0，避免被模板默认 0.9 拒绝；
- 新增 `click_ocr_asset_uses_action_roi_not_template_lookup`、`click_target_template_locator_also_accepts_ocr_assets`。

## 2. 仍待

1. U-32b 批量实帧验收（positions + 匹配帧）；
2. U-20 多选整组拖动；
3. 编辑器/runtime 一致性自动守卫（§E-41 遗留）。

## 3. 下一步

1. 用户重跑「回到庭院」确认 click；
2. 设置 positions 跑批量；
3. U-20；
4. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-42；代码 `567917c`；346 tests；stage 8788。
