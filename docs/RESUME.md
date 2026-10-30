# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-r-audit
checkpoint_seq: 24
updated_at: 2026-10-31T01:30:00+08:00
trigger: 按新 skill 修 R6/R14/R19/R20；R9 真流程图仍待做
status: in_progress
```

## 0. 目标（一句话）

关闭 R1~R20 所有未完成项；当前只剩 **R9-a 真流程图**。

## 1. 本轮已完成（代码 `ed2ae6a`）

- **R6-a**：`app.js:907` 文案统一为「操作区域」；
- **R14-a**：`activatePage('builder')` 传入 workbench 当前任务；builder `activate(preferredTask)` 载入同一任务；浏览器实测 `builder=workbench=探索`；
- **R19-a**：素材行新增「点测 / 拖测 / 步骤」：
  - 点测 = dry-run，验证定位并显示目标点；
  - 拖测 = dry-run，显示方向/起终点 + drag JSON；
  - 步骤 = 生成 click_target 并复制到剪贴板；
  - 浏览器实测 3 个按钮、无 JS 错误；
- **R20-a**：builder 动作库增加「条件与取值」说明：出现=现在有没有 / 等到=一直等到有 / 识别=读出文字。

## 2. 台账状态

- R1~R20：**18 ✅ / 2 未完成（R9、R18）**；R18 只是 R9 的发布门禁；
- R9-a：真流程图仍为 DOM 缩进图（`builder.js:321-385`），无 SVG 边/汇合/回边/跳转/finish 出口；
- v1.2.2 仍标记“已发布但验收未闭合”，不可宣称完成；
- docs 待提交（本轮代码已 push `ed2ae6a`）。

## 3. 下一步精确动作

1. 重写 `builder.js` 图渲染：建图 IR（nodes/edges/ports）→ SVG `<path>` 边 + `<rect>` 节点；
2. 必须覆盖：开始、顺序边、if 条件+then/else 边+汇合、loop 回边、break/continue 跳转、每 finish 出口；
3. 点击节点选中联动属性；滚动；缩放可选；
4. CDP 验收：断言 SVG 节点/边连接关系与分支/回边，不只数 `.fg-*`；
5. R9 关闭后 v1.2.3 打包发布；R18 才能 ✅。

## 4. 已知事实

- v1.2.2 已发布：tag `v1.2.2` / `9debc0b` / SHA256 `B683343C…8994` / 330 tests
- 引擎 main `ed2ae6a`；本轮 UI 改动未重跑 cargo（无 Rust 改动）
- 新 skill：强制 7 需求覆盖审计 + 强制 8 压缩恢复门禁（`D:\tools\dsh-skills` commit `95425ce`）
