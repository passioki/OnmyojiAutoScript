# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v122-backlog
checkpoint_seq: 16
updated_at: 2026-10-31T00:35:00+08:00
trigger: 用户「好的，继续」→ 按 N44~N49 优先级开工
status: in_progress          # N44 done；N45/N47/N49 待做
```

## 0. 目标（一句话）

按用户确认的优先级处理 v1.2.1 后续缺口：**N44 帧持久化 ✅** → N45 图片多选 / N47 builder 属性 / N49 工作台 flow DOM 清理 → N46/N48；完成后再决定发布版本（不提前跳版本）。

## 1. 完成清单

- [x] N44 帧磁盘持久化：`<frames-dir>/frames.json` + `frame-<id>.png`；元数据内存、当前帧像素懒加载；重启保留 name/category/order
- [x] `--frames-dir`（默认 `frames`）；start-editor/package 已接入
- [x] 测试：新增重启持久化测试；`cargo test --workspace` **328 passed / 0 failed**
- [x] 实机/进程验证：25+ 帧上传 → 重启 → 27/28 帧仍在；rename/category/reorder 持久化
- [ ] N45 图片识别多选（需先明确“多选”的候选来源/交互；当前 `/match` 只返回最佳单结果）
- [ ] N47 builder 复杂动作结构化属性 / 变量持久化
- [ ] N49 工作台 flow 面板 DOM/JS 物理删除（当前仅隐藏，需同时处理“追加到流程”入口）
- [ ] N46 旧 assets 清理 / N48 签名/APK

## 2. 关键事实

- 引擎：`a3d5dab`（N44）· main 已 push · worktree 干净
- v1.2.1 仍为已发布版本：`4e50aea` / tag `v1.2.1`；**未 bump 到 v1.2.2，未发布**
- 新 frames 数据：`frames/frames.json` + `frames/frame-<id>.png`；当前帧像素在 `State.png`
- 帧 manifest 结构：`next_id/current_id/frames[{id,name,category,file,width,height,source,ts_ms}]`
- 启动加载：`Server::with_frames_dir()` 读取 manifest；当前帧文件懒解码

## 3. 下一步精确动作

1. 和用户确认 N45“图片识别多选”的语义（是“同一模板多处匹配”还是“多个模板资产候选”？）——**不要凭猜测实现**；
2. 若 N45 暂缓，先做 N47（builder 的 click_target/drag 结构化表单）或 N49（删除 flow 面板）；
3. 全部做完后统一打包/发下一版本；发布前重新评估 version（用户此前要求不要提前跳版本）。

## 4. 证据

- 引擎 N44：commit `a3d5dab`；测试 328 passed
- 进程验证：`D:\OAS-dev\_verify\n43\migrate\frames\frames.json`（工作区临时）
- 设计/台账：`docs/ENGINE-DESIGN.md §22.39` · `docs/PENDING-LEDGER.md §E-25`（N44 已勾）

## 5. 已知限制

- N44 只持久化元数据/顺序/分类和帧 PNG；当前帧像素懒加载，非全内存。
- N45/N47/N49 未做；v1.2.1 发布说明中的“帧为 session 内存”已被 N44 取代，但下一版发布说明需更新。
