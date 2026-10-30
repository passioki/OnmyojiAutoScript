# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-r-audit
checkpoint_seq: 27
updated_at: 2026-10-31T01:55:00+08:00
trigger: 修复 R21（动作库被覆盖）；R1~R21 全部关闭
status: done
```

## 0. 当前状态

**R1~R21 全部关闭；未自行发布；版本仍 1.2.2。**

## 1. 本轮完成

- **R21 布局修复**（引擎 `d455f6e`）
  - 根因：全局 `aside { width:320px; flex:0 0 320px; }` 作用到 builder 的 palette/inspector，覆盖了 grid 的 220px/340px 轨道；
  - 实测：palette 实际 320px，center 从 x=244 开始 → 重叠 90px；
  - 修法：`.builder-main > .builder-palette/.builder-inspector { width:auto; flex:none; }`；
  - 验证：computed rect palette=220、center.x=244、inspector=340；
  - 这是之前 v1.2.1 “布局已修”只验证素材/图存在、未测 bounding rect 导致的漏检；已写入 §E-26 C7。
- R9 SVG 真流程图已完成（`3aa1a0a`）；R6/R14/R19/R20 已完成（`ed2ae6a`）。

## 2. 发布规则

- 不自行 tag/release；只在用户明确说“发布”时发布；
- 平时只构建 release 测试；版本保持 1.2.2；
- v1.2.2 已发布资产保留。

## 3. 台账

- R1~R21：**21/21 ✅**
- `PENDING §E-26`；`ENGINE §22.39`；`START-HERE` 已同步
- docs 待提交（本轮 ENGINE/PENDING/RESUME/INDEX/START-HERE）

## 4. 下一步

- 等用户明确发布指令；此前只做测试/回归。
- 后续 UI 验收必须加 computed bounding rect 非重叠断言（防再次“看起来修了”）。
