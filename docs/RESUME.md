# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round7
checkpoint_seq: 35
updated_at: 2026-10-31T18:05:00+08:00
trigger: 第六轮反馈 U-30~U-32 已审计；按 START-HERE 先报告等确认
status: in_progress
```

## 0. 当前状态

- 代码 `460ad32`；backend docs `6f349200`；两端 worktree 干净。
- workspace **341 passed / 0 failed**（本轮已实测）。
- 未 tag/release；版本 1.2.2；stage UI+exe 为上一轮同步（本轮未改代码）。
- 本轮没有改动代码/任务/素材；只做审计与台账。

## 1. 本轮需求（已审计，待确认）

| ID | 要求 | 现状 |
|---|---|---|
| U-30a | 工作台「任务」面板显示当前任务引用素材 | 🔄 `task-ref-assets` 只在素材面板；任务面板无 |
| U-30b | 素材行首列改识别区域缩略图（等比例） | ⬜ 当前纯蓝 button；无图片路由 |
| U-31a | 返回庭院修改 `not appear` 后能运行 | 🔄 根因：`町中` 是 OCR 资产，`appear()` 只支持模板；dry-run 已复现 `selector 町中 is not declared...` |
| U-31b | 条件素材输入显示所有匹配候选 | ⬜ 原生 datalist + change 事件，部分输入不提交 |
| U-32a | 素材位置属性（多帧 id） | ⬜ `AssetDecl` 无 positions |
| U-32b | 按帧批量 dry-run 测试 | ⬜ 无批量测试 API/UI |

详细设计草案与文件:行号证据：`docs/PENDING-LEDGER.md §E-32`。

## 2. 待用户确认

1. U-31：是否采用 **A = 扩展 `appear()` 支持 OCR 资产**（推荐；现有 `not appear('町中')` 直接可用），还是 B = 限制 `appear` 只选模板、OCR 改用 `ocr(...)`？
2. U-32：集合是否也要 `positions`？
3. U-32：删帧时已有位置 id 是**自动清理**还是**保留失效并提示**？

## 3. 下一步精确动作（确认后）

1. U-30a：新增 `#task-ref-assets-task`，与现有 `renderTaskReferencedAssets()` 共用；任务切换先 `loadTaskFlow` 再渲染。
2. U-30b：加 `GET /task/asset/image` + `GET /frames/image`；canvas 按 ROI 裁剪；`.asset-main` 改缩略图布局。
3. U-31a：按 A/B 修 runtime `appear` 或条件预设；补 runtime/flow tests。
4. U-31b：自定义过滤下拉（子串、键盘选择），替换条件素材 datalist。
5. U-32：`AssetDecl.positions` + UI 多帧位置 + `POST /task/assets/batch_test` + 结果表。
6. 每步 `cargo test` + stage 同步 + 断点；最后更新 ENGINE §22.39.4 / 台账。

## 4. 已验证事实

- `cargo test --workspace` = 341 passed（本轮实跑）。
- `dist/stage/tasks/回到庭院/flow.json` 当前语法正确：`while not appear('町中')`；dry-run 失败原因是 `appear` 不支持 OCR 资产。
- STAGE 任务 assets.json 为空；全局 assets 有 23 项（含 `町中`/`庭院` OCR、`返回庭院`/`返回上一级` 模板）。

## 5. 证据路径

- PENDING §E-32；stage logs `dist/stage/logs/editor.log`；dry-run 命令输出已记录在本轮回复。
- 未新增 `_verify/nNN` 目录（未改代码）。
