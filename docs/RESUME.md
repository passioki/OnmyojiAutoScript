# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-editor-v11
checkpoint_seq: 5
updated_at: 2026-10-30T20:35:00+08:00
trigger: phase-gate
status: in_progress        # in_progress | blocked | done
```

## 0. 目标（一句话）

按用户确认的 v1.1 设计实现：整屏 OCR 文字直点、素材 CRUD/区域/拟人拖动、任务工作台+完成条件、多页面（工作台/任务库/实例/调度/设置）、点击分布聚合+删除，验收后发布。

## 1. 验收清单

- [x] **P0**：`ocr_lines` 测试走 `/lines`；整屏 OCR 内联直点（no asset）；`追加到流程` 中文；`logs/editor.log` — 引擎 `4b9ee7c`
- [ ] **P1**：素材 CRUD（增删改查）；独立区域操作（点击/拖动随机点）；拟人拖动（方向+随机起终点+随机速度）；生成流程步骤
- [ ] **P2**：任务工作台（①~⑦一条龙）；任务级完成条件（打 N 场/资源耗尽/出现 X），与调度 quota 分离
- [ ] **P3**：顶部页面（工作台/任务库/实例/调度/设置）；实例配置 CRUD + 活动实例（单进程单设备）
- [ ] **P4**：点击分布聚合（本次/最近/全部/按任务）+ 删除选中/清空（_trash）
- [ ] **P5**：单测/回放/实机回归；文档；v1.1 打包发布

## 2. 当前进度

- 当前阶段：**P1 未开始**（P0 完成并提交 `4b9ee7c`）
- P0 验证：`cargo test --workspace` 全绿；内联 OCR dry-run 实测 `clicked_target locator=ocr_text inline text="预设" point=(370,96)`（`_verify/n43/inline/clicks.jsonl`）；编辑器页面加载正常（`_verify/n43/ui_assets.png`）
- **下一步精确动作**：
  1. `oas-task` 增加 `delete_asset/rename_asset/update_asset_meta`（安全校验：flow 引用中不可删/需同步替换）
  2. `oas-flow` 新增 `region` 区域目标 + `drag` op（方向/随机起终点/随机时长）；`oas-runtime` 实现并测
  3. serve 路由 `/task/asset/delete|rename|update`；UI 素材行增加删除/重命名/编辑 + 区域操作生成步骤

## 3. 已验证事实

- 引擎 `main` = `4b9ee7c`（P0）；本机 remote `origin=https://github.com/passioki/oas-core`（v1.0.0 tag/release 已发布）
- 测试：`cargo test --workspace` 全绿（P0 后）
- 编辑器：`logs/editor.log` 记录 `/ocr`、`/lines`、`/task/*` 等请求；`apps/oasd/logs/` 已 gitignore
- 用户 release 测试目录：`C:\Users\passioki\Downloads\test`（含 `新建任务测试-个人突破`、整屏 OCR 素材、逐 run clicks JSONL）
- 实机验收：MuMu Android 12 / 阴阳师 2.8.84 / adb 127.0.0.1:16384；当前画面=式神录/队伍预设

## 4. 在途改动

| 文件 | 改了什么 | 状态 |
|---|---|---|
| oas-core | P0 已提交 `4b9ee7c`；`dist/` 未重建 | committed |
| backend/docs | 本卡/索引待提交 | 待提交 |

## 5. 本轮新裁定（v1.1）

- ★ 整屏 OCR 每行可直接点击：flow `ocr_text` 支持**内联 roi+text**，不强制逐行素材
- ★ 素材操作参数**只存 flow**；素材本身不存 offset/操作默认值
- ★ 删除“偏移”概念；改用**独立区域操作**（区域框选后随机点点击/拖动）
- ★ 拖动拟人：方向必填 + 起点/终点在区域内随机 + 时长/速度随机 + 曲线抖动（引擎能力允许时）
- ★ 完成条件归**任务**；调度器 quota=每天跑几次
- ★ 点击分布保留每次运行 JSONL，聚合视图 + 删除（默认移 `_trash`）
- ★ 多实例：v1.1 做实例配置+活动实例（单进程单设备），真正并行后续

## 6. 阻塞 / 待用户裁定

- 无（用户已确认）

## 7. 证据索引

| 证据 | 路径 |
|---|---|
| P0 内联 OCR dry-run | `_verify/n43/inline/clicks.jsonl` |
| P0 UI 截图 | `_verify/n43/ui_assets.png` |
| 用户 release 测试 | `C:\Users\passioki\Downloads\test` |
| 设计 | 对话 v1.1 设计 + `_verify/n42/REPORT-V1.0.md` |

## 8. 坑

- Windows PowerShell 5 默认 GBK：bat 纯 ASCII；PS 中文文件名/路径用绝对路径（.NET CWD 不跟 cd）
- 运行中的 oasd.exe 锁 target；重建前停 serve
- JS 无 node 可用：用 headless Edge 截图验页面加载，`node --check` 不可用
- 文字行内联 OCR 走 det+rec（`/lines`），单行 `/ocr` 仅用于 ocr_line
