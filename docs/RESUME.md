# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-editor-v11
checkpoint_seq: 6
updated_at: 2026-10-30T20:48:00+08:00
trigger: phase-gate
status: in_progress        # in_progress | blocked | done
```

## 0. 目标（一句话）

按用户确认的 v1.1 设计实现：整屏 OCR 文字直点、素材 CRUD/区域/拟人拖动、任务工作台+完成条件、多页面（工作台/任务库/实例/调度/设置）、点击分布聚合+删除，验收后发布。

## 1. 验收清单

- [x] **P0**：`ocr_lines` 测试走 `/lines`；整屏 OCR 内联直点；`追加到流程` 中文；`logs/editor.log` — `4b9ee7c`
- [x] **P1**：素材 CRUD（delete/rename/update meta）；独立区域 `Locator::Region`；`Step::Drag`（方向必填、随机起终点/时长、方向校验）；flow 生成 — `fd005b0`
- [ ] **P2**：任务工作台（①~⑦一条龙）；任务级完成条件（打 N 场/资源耗尽/出现 X），与调度 quota 分离
- [ ] **P3**：顶部页面（工作台/任务库/实例/调度/设置）；实例配置 CRUD + 活动实例（单进程单设备）
- [ ] **P4**：点击分布聚合（本次/最近/全部/按任务）+ 删除/清空（_trash）
- [ ] **P5**：单测/回放/实机回归；文档；v1.1 打包发布

## 2. 当前进度

- 当前阶段：**P2 未开始**（P1 完成并推送 `fd005b0`）
- P1 验证：`cargo test --workspace` 全绿；asset delete/rename/update API 实测 200；`/task/assets` 结果正确；UI 页面加载正常（`_verify/n43/ui_p1.png`）
- **下一步精确动作（P2）**：
  1. `meta.goal`：`{mode:"battles|until", count|exit}`；任务创建模板/UI 完成条件字段；生成 flow `loop n=param('max_battles')` 或 `while`
  2. 任务工作台：任务面板按 ①基础 ②画面素材 ③操作 ④流程 ⑤完成条件 ⑥测试运行 ⑦保存/加入调度 引导
  3. 完成条件与调度 quota 分开展示；P2 验收：不写 JSON 建完整任务

## 3. 已验证事实

- 引擎 `main` = `fd005b0`；remote `https://github.com/passioki/oas-core`（main 已推；v1.0.0 tag/release 保留）
- 测试：`cargo test --workspace` 全绿
- P1 API：delete `预设ocr` 200；rename `预设`→`预设2` 200；update template threshold 0.85→0.9 200；`task/assets` count 6→5
- P0/P1 编辑器：`logs/editor.log` 记录 asset 操作；`flow_model.js` 增加 drag 中文项
- 用户 release 测试：`C:\Users\passioki\Downloads\test`（整屏 OCR 任务、逐 run clicks）

## 4. 在途改动

| 文件 | 改了什么 | 状态 |
|---|---|---|
| oas-core | P1 已提交 `fd005b0` 并 push | committed |
| backend/docs | 本卡/索引待提交 | 待提交 |

## 5. v1.1 设计约束（已确认）

- ★ 整屏 OCR 每行直接点击：flow `ocr_text` 内联 `roi+text`，无需素材
- ★ 素材操作参数只存 flow；素材 CRUD 只管理 id/kind/ROI/图/阈值
- ★ 无 offset；独立区域操作（随机点点击/拖动）
- ★ 拖动方向必填；起点/终点随机、时长/速度随机；当前 PC adapter 为直线 swipe（曲线抖动待 minitouch/scrcpy）
- ★ 完成条件归任务；调度器 quota=每天跑几次
- ★ 点击分布保留逐 run JSONL，聚合视图 + 删除（默认 _trash）
- ★ 多实例 v1.1 只做实例配置+活动实例

## 6. 阻塞 / 待用户裁定

- 无

## 7. 证据索引

| 证据 | 路径 |
|---|---|
| P0 内联 OCR | `_verify/n43/inline/clicks.jsonl` |
| P1 CRUD/UI | `_verify/n43/crud/` · `_verify/n43/ui_p1.png` |
| 用户 release 测试 | `C:\Users\passioki\Downloads\test` |

## 8. 坑

- Windows PowerShell 5 默认 GBK：bat 纯 ASCII；.NET 相对路径 CWD 不跟随 `cd`，用绝对路径
- 运行中的 oasd.exe 锁 target；重建前停 serve
- 无 node：JS 用 headless Edge 截图验页面；`node --check` 不可用
- 内联 OCR 需要 det+rec；单行 `/ocr` 仅用于 ocr_line
