# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `SESSION-HANDOFF.md` / `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-live-v1
checkpoint_seq: 3
updated_at: 2026-10-23T02:35:00+08:00
trigger: plan-milestone
status: in_progress        # in_progress | blocked | done
```

## 0. 目标（一句话）

V1.0：实机上能创建任务、任务含 **探索 + 个人突破** 并在 **Android 客户端（MuMu Android 12 / 阴阳师 2.8.84）** 跑通；调度器自动运行；release 包/配置/启停升级齐全。（**APK 引擎 = P4，本次明确不做**，用户已同意按原计划。）

## 1. 验收清单（全部 ☑ 才算 V1.0；每项带证据）

- [ ] **M0/N36** 统一任务模板：meta 契约 + `param()` 注入 + `task lint` + 旧任务零破坏 — `cargo test --workspace`
- [ ] **M1/N38** 创建闭环：`POST /task/create` + 「新建任务」UI + 骨架 + lint + 编辑器「运行任务」 — 新建→运行 Done
- [ ] **M1b** 任务 `探索`（Exploration）在 Android 客户端跑通 Done + 点击审计
- [ ] **M1b** 任务 `个人突破`（RealmRaid）在 Android 客户端跑通 Done + 点击审计
- [ ] **M2/N37** 调度 v3：periodic + temp B + 重置记忆（多选/全选/反选）+ 面板 — replay/live 端到端
- [ ] **M3/N39** 实机包：release + `config/live.json` + `--serial` + package + 启停/升级 — 干净目录启动
- [ ] **M4/N40** E2E：Android 客户端新建任务→运行→调度 2 轮→重启恢复；24h 长跑启动/记录 — 证据
- [ ] **M5** DoD 全勾；台账/文档/v1.0 收尾

## 2. 当前进度

- 当前阶段：**M0 未开始**（本轮开工）
- 上一步已完成：计划/设计定稿（DELIVERY-PLAN e085d726）；范围确认：探索+个人突破 + Android 客户端；APK 不做
- **下一步精确动作**：实现 M0（模板契约/lint/param/CLI）→ M1（创建/运行 API+UI）→ M1b（两个任务）→ M2 → M3 → M4
- 团队分工（如启用）：template-core / serve-create / game-tasks / scheduler-v3；Lead 负责集成/M3/验收/文档

## 3. 已验证事实（带时间/命令输出）

- oas-core：`main` = `8b252a6`；worktree 干净；`cargo test --workspace` = **213 passed**
- backend docs `dev` = `e085d726`（push 完成）
- 模拟器：MuMu `vmindex=0`，Android **12** x86_64，`127.0.0.1:16384`；阴阳师 `versionName 2.8.84`；当前画面=庭院
- 控制：`E:\MuMuPlayer\nx_main\mumu-cli.exe control --vmindex 0 launch/shutdown/restart` 可用；adb 可点击/截图
- serve 8787 在跑（带 OCR）；改 Rust 后先停 8787 再 build
- 旧仓参考任务：`backend/tasks/Exploration`（探索）、`backend/tasks/RealmRaid`（个人突破）

## 4. 在途改动（未提交）

| 文件 | 改了什么 | 状态 |
|---|---|---|
| — | 本轮开工前无 | — |

## 5. 本轮新裁定 / 约束（只记与下一步相关的）

- ★ **APK 引擎不在本次范围**：用户原话"我要的是apk，不过既然做不到那就按原有计划进行" ⇒ V1.0 仍按 Android 客户端（模拟器）验收；APK 归 ENGINE P4
- ★ 任务必须包含 **探索 + 个人突破**（旧仓 `Exploration` / `RealmRaid` 为参考）
- ★ Android 构建/测试证据：Android 12 / x86_64 / 阴阳师 2.8.84 写入交付报告
- ★ 全程不向用户提问；不可恢复故障才停；每里程碑更新本卡 + 索引

## 6. 阻塞 / 待用户裁定（只写真正需要外部输入的）

- 无（用户已授权；APK 明确排除）

## 7. 证据索引（可跳转）

| 证据 | 路径 |
|---|---|
| 交付路线 | `docs/DELIVERY-PLAN.md` |
| 设计权威 | `docs/ENGINE-DESIGN.md §22.34` |
| 当前屏幕/环境 | `D:\OAS-dev\_verify\n41\now2.png` |
| 旧任务参考 | `backend/tasks/Exploration`, `backend/tasks/RealmRaid` |

## 8. 坑（本任务新发现、必须带走的）

- serve 重建前停 8787；OCR 构建 `--features ocr`
- adb 截图别用 PowerShell 重定向（会损坏 PNG），用 `oasd probe --out`
- 中文文档只用 read/edit/write 工具改
- 测试数以实测为准（现 213）
