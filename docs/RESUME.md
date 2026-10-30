# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-r-audit
checkpoint_seq: 21
updated_at: 2026-10-31T01:05:00+08:00
trigger: 用户指出未读 ASST 对话；重新按 USER+ASST 双向核对 R1~R18
status: in_progress
```

## 0. 目标（一句话）

按 skill 铁律 **双向读取** 重新核对 R1~R18；把真正未闭合项写进台账，不把“映射”当验收。

## 1. 双向核对后的结论

**R1~R18 实核：15 ✅ / 3 🔄（R6/R14/R18）**

- **R2 ✅（按当期口径）**：助手 10-30 20:17 明确“完成条件先做计数型；until_resource/until_condition 记录目标，由 flow 自己用 while/识别/出现 判断”；用户 20:21“好的，确认”。之后 v1.1 P2/发布说明也重复该口径。**不是缺口**；若现在要求 engine 自动执行 until，属新需求 R2-b。
- **R14-a 真缺口**：助手 10-30 23:37/23:44 明确承诺“引入唯一 activeTaskId，taskName/taskSelect/批量保存/素材列表/builder 全部只读它”；实际 workbench 已同步（`app.js:2759-2797`），builder 仍用独立 `B.task`（`builder.js:722/798-800`）。
- **R6-a 文案残留**：助手 10-30 22:31 承诺“用户界面只出现 识别区域/操作区域”；`app.js:907` 仍有“实际点击/拖动区域”。
- **R18-a 发布门槛重开**：v1.2.2 在 R6/R14 未闭合时发布；已发布不可静默改写，需 v1.2.3 或标注部分验收。

## 2. 我上一轮错在哪

- 我**读了** ASST 正文（extract.py 输出 USER/ASST），但做 §E-26 审计时**只拿用户原话 + 版本摘要**当依据，没有把 ASST 里定下的范围/承诺纳入；违反 skill 第 2 条“必须双向读取”。
- 因此把 R2 误判为缺口，又把 §E-26 全标 ✅；两次都不可信。已改为按“用户原话 + 助手当期口径/承诺 + 代码实核”三方对照。

## 3. 台账状态

- `PENDING §E-26`：R2 ✅（带口径说明）；R6/R14/R18 🔄；新增 R6-a/R14-a/R18-a
- `ENGINE §22.39` 注：R6/R14/R18 未闭合；R2 不是缺口
- `START-HERE` v1.2.2 交付行：验收未闭合
- docs commit `a9715908` 之后又修正 R2（待提交）

## 4. 下一步精确动作

1. 修 **R14-a**：进入 builder 时传入 workbench 当前任务（或抽全局 activeTask）；
2. 修 **R6-a**：`app.js:907` 文案统一为“操作区域”；
3. 浏览器回归 R6/R14；
4. 关闭后发 v1.2.3；R2 不写代码，除非用户明确要 until 自动执行（新需求）。
