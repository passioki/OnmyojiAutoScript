# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-r-audit
checkpoint_seq: 25
updated_at: 2026-10-31T01:38:00+08:00
trigger: 用户取消 R18a 发布门禁；改为只在用户明确要求时发布
status: in_progress
```

## 0. 目标（一句话）

关闭 R1~R20 最后一个未完成项 **R9-a 真流程图**；不自行发布。

## 1. 发布规则（[10-31] 用户新裁定）

- **取消 R18-a 发布门禁**，不单独做发布项；
- **只在用户明确说“发布”时才 tag/release，任何情况下不自行发布**；
- 平时只构建 **release 构建用于测试**，**版本号保持 1.2.2 不变**；
- v1.2.2 已发布资产保留，不因 R9 未完成而改写/删除。

## 2. 当前台账

- R1~R20：**19 ✅ / 1 未完成（仅 R9 真流程图）**
- R9-a：`builder.js:321-385` 仍是 DOM 缩进节点 + `↓`/`↺` 文字；无 SVG 边/汇合/回边/跳转/finish 出口。
- R6/R14/R19/R20 已在 `ed2ae6a` 修复并浏览器验证。
- R18 状态改为“按新口径调整 ✅”，R18-a 已删除。

## 3. 下一步精确动作

1. 重写 `builder.js` 图渲染：建图 IR（nodes/edges/ports）→ SVG 节点/边；
2. 覆盖：开始、顺序边、if 条件+then/else+汇合、loop 回边、break/continue 跳转、每 finish 出口；
3. 点击节点联动属性；滚动；缩放可选；
4. CDP 验收：断言 SVG `path` 连接关系，不只数 `.fg-*`；
5. R9 关闭后按用户指令决定是否发布；不得自行 tag/release。

## 4. 已知事实

- v1.2.2 已发布：tag `v1.2.2` / `9debc0b` / SHA256 `B683343C…8994` / 330 tests
- 引擎 main `ed2ae6a`；worktree 干净
- 新 skill：强制 7 需求覆盖审计 + 强制 8 压缩恢复门禁（`D:\tools\dsh-skills` commit `95425ce`）
