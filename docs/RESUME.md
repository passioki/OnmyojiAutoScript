# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-r-audit
checkpoint_seq: 20
updated_at: 2026-10-31T01:00:00+08:00
trigger: 用户指出 §E-26 全 ✅ 不可信 → 逐条复核 R1~R18
status: in_progress
```

## 0. 目标（一句话）

纠正“把映射当验收”的错误：逐条核 R1~R18，未完成项写进台账；关闭 R2/R6/R14/R18 后再谈发布。

## 1. 本轮审计结论

- **R1~R18 实核：14 ✅ / 4 🔄**（不是全部完成）
- **R2**：完成条件归属已定，`battles` 可执行；`until_resource/until_condition` 只写入 meta、engine 不执行（`meta.rs:190-196`、`app.js:511-515`）→ **R2-a 口径待确认**
- **R6**：功能已统一「操作区域」，UI 仍有一处 `实际点击/拖动区域`（`app.js:907`）→ **R6-a 文案**
- **R14**：workbench 的 taskName/taskSelect 已同步；builder 用独立 `B.task`，未接同一 active task（`builder.js:722/798-800`）→ **R14-a 功能缺口**
- **R18**：v1.2.2 在 R2/R6/R14 未闭合时发布 → **R18-a 发布门槛重开**；v1.2.2 已发布，不能静默改写

## 2. 台账状态

- `PENDING §E-26` 已纠正：R2/R6/R14/R18 标 🔄，新增 R2-a/R6-a/R14-a/R18-a
- 上一版“全 ✅”错误已记录；**不建议整段 revert** `ff8e8e50`（会丢 R17 引用纠正与 SESSION-INDEX 拆行）；当前用正向纠正 commit
- 若用户要求完全回退：仅 revert docs commit `ff8e8e50`，引擎/发布不受影响

## 3. 下一步精确动作

1. **R14-a**：进入 builder 时传入 workbench 当前任务（或抽全局 activeTask），浏览器验证 builder 素材/flow 与 workbench 一致；
2. **R6-a**：把 `app.js:907` 文案改为“操作区域”；
3. **R2-a**：请用户二选一——① 仍是“flow 自己判断”，关账；② v1.2.3 实现 until 自动执行；
4. **R18-a**：三项关闭后打包 v1.2.3；在此之前不再宣称“台账全部完成”。

## 4. 关键事实

- v1.2.2 已发布：tag `v1.2.2` / `9debc0b` / SHA256 `B683343C…8994` / 330 tests
- 引擎 worktree 干净；本轮只改文档，未改代码
- §E-26 位置：`docs/PENDING-LEDGER.md`（用户指出“看不到”的那张 R 台账）
- R17 图片多选已撤回：用户原话是“图片识别也同理…识别/操作区域”，10-31 只回复 C（助手选项）；图片多选不是用户要求

## 5. 阻塞/待用户裁定

- R2-a：until 完成条件是否需要 engine 自动执行？
- R18-a：v1.2.2 保留为“部分验收”并出 v1.2.3，还是撤回发布？建议保留已发布资产，补 v1.2.3，不删除历史 release。
