# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v122-backlog
checkpoint_seq: 17
updated_at: 2026-10-31T00:32:00+08:00
trigger: 用户「好的，继续」→ N44/N45 开工；用户选 C
status: in_progress          # N44 + N45-C done；N47/N49 待做
```

## 0. 目标（一句话）

继续处理 v1.2.1 后续缺口：**N44 帧持久化 ✅** → **N45-C 图片匹配结果支持识别/操作区域 ✅** → N47 builder 属性 / N49 工作台 flow DOM 清理 → N46/N48；完成后再决定发布版本（不提前跳版本）。

## 1. 完成清单

- [x] N44 帧磁盘持久化：`<frames-dir>/frames.json` + `frame-<id>.png`；元数据内存、当前帧像素懒加载；重启保留 name/category/order
- [x] `--frames-dir`（默认 `frames`）；start-editor/package 已接入
- [x] **N45-C**（用户 [10-31] 选 C）：图片匹配结果 → 「用匹配结果建素材」→ 识别区域=匹配框、template；可拖操作区域；保存写 `action_roi`
- [x] 测试：帧重启持久化测试；`cargo test --workspace` **328 passed / 0 failed**
- [x] 浏览器实测：匹配 roi=[1206,615,45,44] → save → `action_roi=[1190,600,80,70]`
- [ ] N47 builder 复杂动作结构化属性 / 变量持久化
- [ ] N49 工作台 flow 面板 DOM/JS 物理删除
- [ ] N46 旧 assets 清理 / N48 签名/APK

## 2. 关键事实

- 引擎：`a3d5dab`（N44）+ `d104277`（N45-C）· main 已 push · worktree 干净
- v1.2.1 仍为已发布版本：`4e50aea` / tag `v1.2.1`；**未 bump 到 v1.2.2，未发布**
- 帧数据：`frames/frames.json` + `frames/frame-<id>.png`；当前帧像素懒加载
- 图片匹配：`doMatch` 保存 `lastMatch`、显示匹配 bbox；「用匹配结果建素材」按钮设置 roi/assetKind=template；operation region 仍走 `action_roi`
- N45 不做：图片多候选/多选（用户选 C 明确单结果）

## 3. 下一步精确动作

1. N47：builder 的 `click_target` / `drag` 从纯 args JSON 改为结构化表单（保留高级 JSON 兜底）；
2. N49：物理删除工作台 `#panel-flow`，并把「追加到流程」入口迁到 builder 或改为复制步骤；
3. 全部做完后统一打包/评估版本（预计 v1.2.2），发布前再确认。

## 4. 证据

- 引擎 N44：`a3d5dab`；N45-C：`d104277`；测试 328 passed
- 浏览器 N45-C：`roi=[1206,615,45,44]` · saved `action_roi=[1190,600,80,70]`
- 设计/台账：`docs/ENGINE-DESIGN.md §22.39`（R17/B6）· `docs/PENDING-LEDGER.md §E-25`（N44/N45 已勾）
- 帧验证：`D:\OAS-dev\_verify\n43\migrate\frames\frames.json`（工作区临时）

## 5. 已知限制

- 帧持久化只存元数据/PNG；当前帧像素懒加载，不做全内存缓存。
- N45 只做单结果（C），不做图片多候选/多选。
- v1.2.1 发布说明里的“帧为 session 内存”已被 N44 取代，下一版发布说明需更新。
