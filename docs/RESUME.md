# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-r-audit
checkpoint_seq: 22
updated_at: 2026-10-31T01:12:00+08:00
trigger: 用户追问“真流程图”的理解与现有实现
status: in_progress
```

## 0. 目标（一句话）

把“真流程图”按 10-30 助手承诺/用户要求补齐：SVG 控制流图（节点+边），不是 DOM 步骤缩进图。

## 1. 本轮结论（双向重核后）

**R1~R18 实核：14 ✅ / 4 🔄（R6/R9/R14/R18）**

- **R2 ✅（按当期口径）**：助手 10-30 20:17 明确 until 模式“记录目标，由 flow 自己判断”，用户 20:21“好的，确认”；不是缺口。
- **R9-a 真流程图 ❌**：当前 `builder.js:321-385` 是 DOM 缩进节点 + `↓`/`↺` 文字；没有 SVG 边/正交路由；if 没有真实分支边+汇合节点；loop 没有实际回边线；break/continue 没跳转边；多个 finish 被压成一个“流程出口”。助手 10-30 23:37 承诺的是 SVG 控制流图。
- **R6-a 文案残留**：`app.js:907` “实际点击/拖动区域”。
- **R14-a active task**：workbench 已同步；builder 独立 `B.task`，未接 workbench。
- **R18-a**：v1.2.2 已发布，但 R6/R9/R14 未闭合，发布门槛重开。

## 2. 真流程图理解（现行口径）

- 节点 = 动作/控制；边 = 执行流；
- if：分支节点 + then/else 两条有向边 + 汇合节点；
- loop/while：循环头 + 循环体子图 + 真实回边；
- break/continue：跳到循环出口/下一迭代的边；
- finish：按路径连到终止节点（不能压成一个出口）；
- 节点显示动作+关键值，点击选中属性；SVG 连线/箭头/正交路由；支持滚动/缩放；
- 流程图只表达控制流，不复述完整步骤文本。

## 3. 下一步精确动作

1. `builder.js` 建图 IR：把 flow steps 转成 `nodes[]` + `edges[]`（含 if/loop/break/continue/finish 端口）；
2. SVG 渲染：节点矩形/菱形，边 path + marker，if 分支/汇合、loop 回边、finish 出口；
3. 保留点击选中、滚动；缩放可选；
4. CDP 回归：断言 `svg path/line` 数量/连接关系，不只数 `.fg-*`；
5. 修 R6-a 文案、R14-a builder active task；
6. 全部关闭后 v1.2.3。

## 4. 已知事实

- v1.2.2 已发布：tag `v1.2.2` / `9debc0b` / SHA256 `B683343C…8994` / 330 tests
- 引擎 worktree 干净；本轮未改代码
- 上一版 §E-26 全 ✅ 错误；本轮已按 USER+ASST 重核并补 R9-a
