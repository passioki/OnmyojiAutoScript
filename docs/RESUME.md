# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `SESSION-HANDOFF.md` / `ENGINE-DESIGN.md`，这里只放恢复必需。

```yaml
task_id: scheduler-v3-task-template
checkpoint_seq: 1
updated_at: 2026-10-23T02:05:00+08:00
trigger: manual
status: in_progress        # in_progress | blocked | done
```

## 0. 目标（一句话）

实现「统一任务模板 + 调度 v3（periodic + temp B 语义 + 重置记忆）」P0~P4 全绿并交付。

## 1. 验收清单（全部 ☑ 才算完成；每项带证据）

- [ ] **A1 / P0 统一任务模板**：`meta.json` 契约字段 + `oasd task lint` + `task new` + `param('key')` 注入；现有任务零改动通过 — 证据：`cargo test --workspace`、`oasd task lint --all`（待实现）
- [ ] **A2 / P1 调度纯函数**：Calendar/Window/Quota/Pass/WakePlanner；无 IO；无游戏常量 — 证据：单测清单（待实现）
- [ ] **A3 / P2 调度器 v3**：pass 循环 + temp 每轮跑一次 + 执行前后重置 + 状态/锁/恢复 + `reset-memory` CLI；替换 v1 `every_s` — 证据：replay 端到端 + 杀进程恢复（待实现）
- [ ] **A4 / P3 serve 面板**：今日清单/下次唤醒/临时任务/**重置记忆多选（全选/反选）** — 证据：headless 截图（待实现）
- [ ] **A5 / P4 验收收尾**：v1 plan 迁移 + replay 长跑 + 文档（§22.34 状态、N36/N37 ✅、handoff） — 证据：`_verify/nNN/` + 提交 hash（待实现）

## 2. 当前进度

- 当前阶段：**P0 未开始**（设计已定稿，实现代码未动）
- 上一步已完成：调度 v3 + 统一任务模板设计定稿；START-HERE 重写；文档提交 `backend 309a4a89`
- **下一步精确动作（可直接执行）**：

```bash
cd D:\OAS-dev\oas-core
git log -1 --format="%h %s"        # 期望 8b252a6
cargo test --workspace             # 期望 213 passed / 0 failed
# 然后按 ENGINE-DESIGN.md §22.34.6 的 P0：
#   crates/oas-task/src/lib.rs —— meta.json 模板字段（params/exits/entry/capabilities/schedule_hint，全部可选）
#   先写单测：缺字段默认值、非法 exit、未声明 param、旧任务通过
```

## 3. 已验证事实（带时间/命令输出）

- oas-core：本地 `main` = `8b252a6`（2026-10-23 00:36）；worktree 干净；无远端
- 引擎测试：`cargo test --workspace` = **213 passed / 0 failed**（2026-10-23 00:36 实测）
- 文档仓：backend `dev` = `309a4a89`（已 push `origin/dev`）；worktree 干净
- 设计权威：`docs/ENGINE-DESIGN.md §22.34`；入口：`docs/START-HERE.md`；台账 N36/N37 = ⬜
- 编辑器：serve 8787（最近一次启动带 `--features ocr`；改 Rust 后需先停 8787 再 build）

## 4. 在途改动（未提交）

| 文件 | 改了什么 | 状态 |
|---|---|---|
| — | 无 | — |

## 5. 本轮新裁定 / 约束（只记与下一步相关的）

- ★ **放弃旧仓 `period=none` 的"完成标记/继续"记忆**：临时任务每次启动全新执行，执行前/后各重置一次状态；"完成"= 门票耗尽/次数达标 ⇒ `EXITS` 只保留 success/resource/blocked/retryable/fatal（**无 continue/stop**）
- ★ **删除 `one_shot`**；临时任务 = `temp` 生命周期，**B 触发**：可放进 `entries`，每轮按数组顺序跑一次；loop 每轮再跑（无资源就快速结束）
- ★ **重置记忆**清两者：调度器条目状态 + `tasks/<id>/state/`（checkpoint/计数）；UI 弹任务多选框，**全选/反选**
- ★ 调度器/任务模板**零游戏常量**：重置时间/窗口/维护/作息/清单全部来自玩家 `scheduler.json`
- ★ v1 `oasd schedule`（`every_s`）是原型，P2 时替换，不做兼容包袱（迁移工具另做）

## 6. 阻塞 / 待用户裁定（只写真正需要外部输入的）

- 无（设计已全部确认；实现阶段无需再问）

## 7. 证据索引（可跳转）

| 证据 | 路径 |
|---|---|
| 设计定稿 | `docs/ENGINE-DESIGN.md §22.34` · backend `309a4a89` |
| START-HERE（引擎版） | `docs/START-HERE.md` · backend `309a4a89` |
| 设计与流程图 | `D:\OAS-dev\_verify\n38\`（scheduler_v2_flow.png / task_template_scheduler_arch.png / player_day_timeline.png）|

## 8. 坑（本任务新发现、必须带走的）

- serve 重建前必须停 8787 占用；OCR 必须 `--features ocr`，否则识别 501
- 中文文档只用 read/edit/write 工具改，不用 PowerShell 管道重写 UTF-8
- 测试数以实测为准（现 213），不要硬编码"永远 213"
