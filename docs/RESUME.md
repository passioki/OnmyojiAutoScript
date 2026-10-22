# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `SESSION-HANDOFF.md` / `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-live-v1
checkpoint_seq: 2
updated_at: 2026-10-23T02:15:00+08:00
trigger: plan-milestone
status: in_progress        # in_progress | blocked | done
```

## 0. 目标（一句话）

从当前引擎做到 **V1.0：实机上能创建任务、手动运行、并由调度器自动运行**（交付路线 `docs/DELIVERY-PLAN.md` M0~M5）。

## 1. 验收清单（全部 ☑ 才算 V1.0；每项带证据）

- [ ] **M0/N36** 统一任务模板：meta 契约 + `param()` 注入 + `task lint` + 旧任务零破坏 — `cargo test --workspace` / lint 输出
- [ ] **M1/N38** 任务创建闭环：`POST /task/create` + 「新建任务」UI + 骨架 + 保存 lint + 编辑器「运行任务」 — 新建→运行 Done 证据
- [ ] **M2/N37** 调度 v3：periodic + temp（B：每轮跑一次、执行前后重置）+ reset-memory + 面板 — replay 端到端 + 截图
- [ ] **M3/N39** 实机包：release + `config/live.json` + `--serial` + package.ps1 + 启停/升级脚本 — 干净目录启动包
- [ ] **M4/N40** 实机 gate：V0.9 手动运行 Done；V1.0 调度 2 轮 + 重启恢复；24h 长跑 — 实机日志/截图/report
- [ ] **M5** 收尾：DoD D1~D9 全勾；台账/文档/v1.0 tag — 提交 hash

## 2. 当前进度

- 当前阶段：**M0 未开始**（计划/设计已完成；引擎实现未动）
- 上一步已完成：调度 v3 + 统一任务模板设计（§22.34）；到实机交付路线 `DELIVERY-PLAN.md`（M0~M5）
- **下一步精确动作（可直接执行）**：

```bash
cd D:\OAS-dev\oas-core
git log -1 --format="%h %s"        # 期望 8b252a6（实现未动）
cargo test --workspace             # 期望 213 passed / 0 failed
# M0：crates/oas-task/src/lib.rs 加 meta 可选契约字段（params/exits/entry/capabilities）
#      oas-flow: 新增 param('key') 注入 + 出口收集；先写单测再实现
# M1（依赖 M0）：apps/oasd/src/serve.rs + /task/create；ui 新建任务对话框；
#      /task/run 后台执行 + /task/run/status；保存 flow 前 lint
```

## 3. 已验证事实（带时间/命令输出）

- oas-core：本地 `main` = `8b252a6`（2026-10-23 00:36）；worktree 干净；无远端
- 引擎测试：`cargo test --workspace` = **213 passed / 0 failed**（2026-10-23 00:36 实测）
- 文档仓：backend `dev` = `5ab0e2a7`（已 push）→ 本轮将提交 DELIVERY-PLAN/N38~N40/RESUME seq2
- 编辑器：serve 8787（带 `--features ocr`）；改 Rust 后须先停 8787 再 build
- 任务现状：`tasks/S1切预设`、`tasks/任务1`；**无创建 API/UI、无模板 lint**（差距见 DELIVERY-PLAN §1）
- 实机：另一台 PC，本机无法直连；交付/操作需用户配合

## 4. 在途改动（未提交）

| 文件 | 改了什么 | 状态 |
|---|---|---|
| `backend/docs/DELIVERY-PLAN.md` | 新增：到实机可用的 M0~M5 计划/部署/风险/DoD | 本轮提交 |

## 5. 本轮新裁定 / 约束（只记与下一步相关的）

- ★ 终点 = **实机 V1.0**（创建任务 + 手动运行 + 调度自动运行），交付包与部署方案见 DELIVERY-PLAN
- ★ 顺序：**N36 → N38 → N39 →（实机手动 gate）→ N37 →（实机自动 gate）→ N40**；V0.9 与 V1.0 两个 gate
- ★ 实机目录 `D:\OAS-live\oas-core\`，端口 8788，与旧 OAS 22287 并存；同一模拟器只允许一个自动化进程
- ★ 设备必须显式 serial/config，禁止"第一个设备"隐式选择；release 包冻结模型/adb 版本
- ★ 调度/模板语义沿用 §22.34（temp B、无 one_shot/continue、重置记忆清两者）

## 6. 阻塞 / 待用户裁定（只写真正需要外部输入的）

- **交付通道待定**（不阻塞 M0~M3）：实机 zip 用 GitHub Release / 局域网共享 / U 盘？首次实机验收需要用户操作并回传证据。
- 实机旧 OAS 与新引擎共用模拟器的停机窗口（M4 前确认）。

## 7. 证据索引（可跳转）

| 证据 | 路径 |
|---|---|
| 交付路线 M0~M5 | `docs/DELIVERY-PLAN.md` |
| 调度 v3 + 模板设计 | `docs/ENGINE-DESIGN.md §22.34` |
| 任务模板差距/代码证据 | `docs/DELIVERY-PLAN.md §1` |
| 设计流程图 | `D:\OAS-dev\_verify\n38\` |

## 8. 坑（本任务新发现、必须带走的）

- serve 重建前必须停 8787；OCR 必须 `--features ocr`
- 中文文档只用 read/edit/write 工具改，不用 PowerShell 管道重写 UTF-8
- 测试数以实测为准（现 213）
- 实机验收证据必须回传（截图/log/report zip），不能"口头完成"
