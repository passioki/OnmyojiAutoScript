# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round37
checkpoint_seq: 67
updated_at: 2026-11-01T02:00:00+08:00
trigger: v1.2.3 发布 + 远端任务迁移 batch1
status: in_progress
```

## 0. 当前状态（磁盘实测）

- oas-core `main` = `385d611`（v1.2.3 发布快照）· clean
- oas-core `dev` = `2416b18`（迁移 batch1 + Pets/TalismanPass 实机 Done + DailyTrifles 实机证据）· clean
- 迁移状态：**2 ✅ (Pets, TalismanPass 实机 Done) / 41 🔄 / 9 ⛔ / 8 ⬜**
- backend docs `dev` = 本卡提交（待记录）
- `cargo test --workspace` = **350 passed / 0 failed**
- `oasd task lint --tasks-dir tasks --all` = **57 tasks / 0 errors**
- stage 未启动（release 后曾停止；需要时启动）

## 1. 已完成

### v1.2.3 发布（main）

- tag `v1.2.3` / `385d611` / 350 tests
- GitHub Release：`https://github.com/passioki/oas-core/releases/tag/v1.2.3`
- 资产 zip SHA256 `F135922D762A28AE971377D744B4CB286AB9F21C708CD372CAB30EFE30F9C12E`
- U-32b 用户实帧日志 30/30 通过（已关闭）
- 迁移在 `dev`，**未合并 main**（main 作为恢复节点）

### 远端任务迁移 batch1（dev）

- 来源 `runhey/OnmyojiAutoScript@dev` @ `8b4dc669...`
- 61 目录 = 53 菜单任务 + 8 辅助目录（本机旧仓 64 的差异已记录）
- 53 个任务包 + 53 specs + 53 status
- 导入全局素材 2825；lint 57 tasks / 0 errors
- 状态：**0 ✅ / 44 🔄 / 9 ⛔ / 8 ⬜**（6 个未验证的 ✅ 已降级）
- 详见 `docs/MIGRATION-LEDGER.md` · `migration/TASK-LEDGER.md`

## 2. 关键决定

- 旧代码不直接移植；按逻辑抽象为 oas-flow；
- 模板导入 `roi=roiBack`、无 action_roi（点击匹配框）；
- 旧 RuleClick=region；OCR=ocr_lines；Swipe=FROM/TO region；
- 调度窗口/quota 不进 flow；
- 没有实机/replay 证据不得标 ✅。

## 3. 下一步（next loop）

1. 按 `migration/status/*.json` 的 gaps，先补 44 个 🔄 的缺口（战斗/组队/OCR 行框/长按/时钟）；
2. 9 个 ⛔ 等引擎原语或明确范围外；
3. 对可运行任务做实机/replay 验证，通过后才改 ✅；
4. 每批更新 migration ledger + commit/push dev；
5. 全部可完成项完成后，才考虑关机；未完成不要关。

## 4. 证据

- Release：tag `v1.2.3` / `385d611` / zip `F135922D…C12E`
- Migration：`dev 61b45e3`；`MIGRATION-LEDGER.md`
- Tests：350 passed；lint 57/0
