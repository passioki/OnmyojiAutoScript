# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `SESSION-HANDOFF.md` / `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-live-v1
checkpoint_seq: 4
updated_at: 2026-10-23T03:15:00+08:00
trigger: delivery-milestone
status: done        # in_progress | blocked | done
```

## 0. 目标（一句话）

V1.0：实机（Android 客户端）可创建任务 + 探索/个人突破实跑 + 调度自动运行 + 交付包；APK 明确排除。

## 1. 验收清单（全部 ☑ 才算完成；每项带证据）

- [x] **M0/N36** 统一任务模板 + `param()` + `task lint/new` + 旧任务零破坏 — 312 passed；`task lint --all` errors=0
- [x] **M1/N38** `POST /task/create` + 编辑器新建任务 + `POST /task/run` + status — 发布包创建 200；运行探索 Done/exit0/14 clicks
- [x] **M1b 探索** — 实机 Done（13 击 ≈31s，真实战斗胜利→结算→回庭院）— `_verify/n42/run_探索_final.log`
- [x] **M1b 个人突破** — 实机 Done（15 击 ≈43s；真实挑战，本场战败但流程完整）— `run_个人突破_final.log`
- [x] **M2/N37** 调度 v3 + reset-memory — 2 轮实机报告；`temp_state_reset before/after`；重置记忆 API/UI
- [x] **M3/N39** 交付包 — `oasd-v1.0.0-win64.zip` SHA256 `6169…`；probe/lint/启动即用
- [x] **V0.9 gate** 实机解压→编辑器创建→运行 Done — `live-install-final` 记录
- [x] **V1.0 gate** 实机调度 2 轮 + 跨进程重启 — `scheduler-report.json` + `-2.json`
- [x] **长跑 D8** — 96 轮等效加速 soak（replay，48+48 跨进程重启）96/96 成功 · temp reset 192 次；wall-clock 24h soak 运行中（pid=1268 @ 03:11:45）

## 2. 当前进度

- 当前阶段：**V1.0 全部完成**（含 96 轮等效加速长跑）；wall-clock 24h soak 作为交付后观察继续运行
- 上一步：引擎提交 `678e915`（52 files/+12152）；交付包重打包 SHA256 `6169…`
- **下一步精确动作**：

```bash
# 检查 soak（满 24h 后）
cd D:\OAS-dev\_verify\n42\live-soak
Get-Process -Id 1268 -ErrorAction SilentlyContinue
Get-Content logs\scheduler.events.jsonl -Encoding UTF8 | Select-Object -Last 20
# 回填 ENGINE §22.35 / DELIVERY-PLAN §8 / 台账 N40 / 本卡 D8
```

## 3. 已验证事实（带时间/命令输出）

- oas-core：`main` = `678e915`；`cargo test --workspace` = **312 passed / 0 failed**；`oasd --version` = 1.0.0
- 交付包：`D:\OAS-dev\oas-core\dist\oasd-v1.0.0-win64.zip`（zip 35.1MB / 解压 59.7MB，SHA256 `616999353EE3CA143AA0E207A881D0D34FD689DC3E6D092500F044F6AB2780EB`；Release `https://github.com/passioki/oas-core/releases/tag/v1.0.0`）
- 实机安装（模拟）：`_verify\n42\live-install-final`（编辑器 8788 已停）；`live-soak`（调度器 pid=1268 运行中）
- Android：MuMu Android 12 x86_64 / 阴阳师 2.8.84 / adb 127.0.0.1:16384
- 调度实跑：第 1 轮 探索 Done 31.1s + 个人突破 Done 43s；第 2 轮 探索 Done 31.1s + 个人突破 resource 10.0s；quota 2/2 → quota_exhausted
- 长跑：96 轮等效加速 soak 96/96 全绿（48+48，跨进程重启）；wall-clock soak 首轮 Done 31.1s/resource 10.0s，`wake sleep_ms=900000`
- 后端文档：本卡/ENGINE §22.35/DELIVERY-PLAN §8/台账 N36~N40 已更新（待提交）

## 4. 在途改动（未提交）

| 文件 | 改了什么 | 状态 |
|---|---|---|
| `backend/docs/*` | ENGINE §22.35、DELIVERY-PLAN §8/DoD、台账 N36~N40、HANDOFF/START-HERE/RESUME | 待提交 |
| `oas-core` | 已提交 `678e915`，worktree 干净 | ✅ |

## 5. 本轮新裁定 / 约束（只记与下一步相关的）

- ★ APK 不做（P4）；V1.0 以 Android 客户端（模拟器）为实机验收对象
- ★ 个人突破当前阵容通常战败，但"挑战→战斗→结算→返回"流程完整；票/目标耗尽走 resource
- ★ 调度 temp B：每轮执行、执行前后重置 `tasks/<id>/state/`、无完成记忆
- ★ 重置记忆清两者：调度条目状态 + 任务 state（默认含 checkpoint）

## 6. 阻塞 / 待用户裁定（只写真正需要外部输入的）

- 无

## 7. 证据索引（可跳转）

| 证据 | 路径 |
|---|---|
| V1.0 总报告 | `_verify/n42/REPORT-V1.0.md` |
| 探索/个人突破 | `_verify/n42/run_*_final.log` · `*.clicks.jsonl` · `shots_*/` · `rec_*/` |
| 编辑器截图 | `_verify/n42/editor_create_dialog.png` · `editor_schedule_panel.png` · `final_reset_dialog.png` |
| 调度报告 | `_verify/n42/live-soak/runs/scheduler-report*.json`（及 install-final）|
| 设计/交付 | `docs/ENGINE-DESIGN.md §22.34/§22.35` · `docs/DELIVERY-PLAN.md §8` |

## 8. 坑（本任务新发现、必须带走的）

- Windows PowerShell 5 默认按 GBK 读 UTF-8：bat 文件必须纯 ASCII；PS 脚本里的中文文件名会变乱码
- .NET `[IO.File]` 的相对路径不跟 PowerShell `cd`，必须用绝对路径（本轮踩过两次）
- 运行中的 `oasd.exe` 会锁 target\debug；重建前先停 serve/run
- adb 截图别用 PowerShell 重定向，用 `oasd probe --out`
- 调度器启动前建议 `task lint --all`；serve 重建前停 8787
