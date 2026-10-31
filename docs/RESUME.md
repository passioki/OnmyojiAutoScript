# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-ui-round3
checkpoint_seq: 31
updated_at: 2026-10-31T15:46:00+08:00
trigger: 第三轮 11 条 UI/资产/流程反馈已修；等用户验收
status: done
```

## 0. 当前状态

- R1~R21 ✅；U-01~U-21：**10 ✅ / 1 🔄（U-20 根级拖拽/多选整组拖动待补）**。
- 代码 `e01d572`；workspace **338 tests passed**。
- **未 tag/release**；版本仍 1.2.2。
- stage `dist\stage` 的 UI + 带 OCR exe 已同步测试构建；未恢复用户删除的任务/素材。

## 1. 本轮完成（U-11~U-21）

- **builder**
  - 删除“可用素材/操作区域”下的死下拉框；
  - 子动作按钮 `是/否` 在前、动作下拉在后；loop 用“循环体”；
  - 800ms debounce 自动保存；手动按钮改“立即保存（自动保存已开启）”；
  - 流程图下新增 flow.json 代码编辑器；
  - 步骤左侧复选框 + 批量删除；if↔loop 转换保留子动作；可拖步骤进 if/loop 子容器；根级拖拽未做全。
  - 条件提示：`and/or/not` + `&&/||/!` + 括号。
- **资产保存**
  - 统一「识别结果」列表：单行 OCR / 多行行 / 图片匹配 / 独立操作区域；
  - 删除旧「存为素材」「类型」和旧「素材库（全局）」UI；
  - 单一「保存素材」按钮；有结果未勾选时按钮可点并提示“请勾选”；
  - 单行 OCR 失败/空文本 → 全屏多行 det+rec 回退；
  - 保存成功清理结果列表并刷新资产。
- **调度**
  - 删除任务时清理 scheduler.json 中对应 entries；
  - `/scheduler/status` 过滤已删任务的 entries/plan/task_choices/running；
  - 空 entries 合法。
- **帧**
  - 分类下拉，仅渲染一个类别；
  - rail 帧面板满高（不是独立页/满宽）。
- **画布**
  - `#hint` pointer-events:none；
  - 点击分布只在 panel-click active 时绘制，切换面板重绘清除。

## 2. 发布规则

- 不自行 tag/release；只在用户明确说“发布”时发布；
- 平时只构建 release 测试；版本保持 1.2.2。

## 3. 下一步

- 等用户验收；重点看 U-20 根级拖拽/多选整体拖动是否还需要补全，以及 U-15 全屏 OCR 回退实机效果。
- 若要发布，再 bump 版本并走 release。
