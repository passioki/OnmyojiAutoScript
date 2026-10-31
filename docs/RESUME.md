# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-ui-round4
checkpoint_seq: 32
updated_at: 2026-10-31T17:20:00+08:00
trigger: 第四轮 6 条反馈已修/已诊断；等用户验收
status: done
```

## 0. 当前状态

- R1~R21 ✅；U-01~U-27：主体完成；U-20 根级拖拽/多选整组拖动仍待补。
- 代码 `346adba`；workspace **339 tests passed**。
- **未 tag/release**；版本仍 1.2.2；stage UI + exe 已同步测试构建。
- 未恢复用户删除的任务/素材。

## 1. 本轮完成（U-22~U-27）

- **帧分类**：新增「当前帧分类」下拉（现有分类 + 新建分类），应用到当前帧；帧列表仍按分类过滤。
- **任务素材库**：从任务面板移除，移到「画面/素材」面板；新增「当前任务引用的素材」只显示 flow 引用；完整素材库/搜索仍在素材面板。
- **builder 素材选择**：`<select>` 改为可搜索 datalist；所有 asset 字段/结构化 click_target 共用。
- **while**：`max_iters=0`/省略 = 由 step budget 限制的“无限”；builder 默认 0；解析器接受 0；删除 if↔loop 转换按钮/函数；加载时 normalize 非法 args。
- **多行 OCR**：工作台素材“识别”测试对 derived `ocr_line` 改为用 `ocr_source_roi` + `/lines` det+rec，并显示期望文字是否匹配；runtime derived OCR 原本已存在。
- **回到庭院**：诊断 exit `dist/stage/tasks/回到庭院/flow.json` 为损坏数据：`while.cond=false`、`max_iters=1`、多余 `sel:"町中"`、内层 if 只有 sel 无 cond、assets 空；while 条件 false → 不执行。非引擎 bug；用户需重建/修正任务。builder 已 normalize + 移除转换防再生。

## 2. 发布规则

- 不自行 tag/release；只在用户明确说“发布”时发布；
- 平时只构建 release 测试；版本保持 1.2.2。

## 3. 下一步

- 等用户验收；重点看：
  - U-20 根级拖拽/多选整组拖动补全；
  - 多行 OCR 资产的实机 `测试庭院`；
  - 用户重建 `回到庭院` 时的 builder 体验。
- 若要发布，再 bump 版本/tag/release。
