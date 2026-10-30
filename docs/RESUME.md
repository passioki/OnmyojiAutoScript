# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-builder-v12
checkpoint_seq: 12
updated_at: 2026-10-30T23:15:00+08:00
trigger: phase-gate
status: done                # in_progress | blocked | done
```

## 0. 目标（一句话）

v1.2：识别区域/操作区域统一、全局唯一命名、多选批量保存、操作区域可调；任务构建大页面（动作+值+实时流程图）；变量动作；回归/发布 v1.2.0。

## 1. 验收清单（全部完成）

- [x] **A**：`roi`=识别区域 + `action_roi`=操作区域（旧 roi_back alias）；`kind=region`；批量保存/全局唯一/冲突扫描；OCR 多选候选 + 操作区域画布调整
- [x] **B**：顶部「任务构建」（builder.js）：动作库/嵌套步骤树/动作值 inspector/实时流程图/保存/dry-run；工作台保留
- [x] **C**：`set_var/inc_var/ocr_to_var` + `var('name')`
- [x] **D**：326 tests 全绿；浏览器 CDP 回归；实机/dry-run；package；tag/release `v1.2.0`

## 2. 发布产物

- GitHub Release：`https://github.com/passioki/oas-core/releases/tag/v1.2.0`
- 引擎 tag `v1.2.0` / main `5d0f79c`
- 包：`D:\OAS-dev\oas-core\dist\oasd-v1.2.0-win64.zip`（36,895,821 字节）
- SHA256：`D31C500006643D318E16B3EDF23EC688BF6773D2886D4CAF1828F98C4CB035FC`
- 测试：`cargo test --workspace` = **326 passed / 0 failed**
- 包冒烟：`oasd 1.2.0`；lint 4 tasks/0 errors；serve `/state` captured/OCR ready；`/builder.js` 200；`/assets/conflicts` 旧任务 3 条重名

## 3. 回归证据

| 项 | 结果 |
|---|---|
| 浏览器候选/批量 | 整屏 OCR 25 候选；批量保存 25 个 V12UI 素材；操作区域绘制 `{5,5,194,94}`；无 JS 错误 |
| 任务构建页 | 20 动作；加载 t1；set_var/inc_var 保存 flow；实时图；截图 `_verify/n43/v12_builder.png` |
| 变量 dry-run | `set_var count=0` + loop 2：count 0→1→2，loop 2/2，Done |
| 区域/拖动 dry-run | region point (1025,385)；drag up (1073,619)->(1073,494) ms=426；Done |
| 实机 release | 内联 OCR「式神录」→ (1111,663) Done（`_verify/n43/v12release/live_ocr.clicks.jsonl`）|
| 旧冲突扫描 | `/assets/conflicts`：探索/个人突破 3 个同名素材（旧数据，不自动改名）|

## 4. 模型/实现事实

- `AssetDecl`：`roi`=识别区域；`action_roi`=操作区域（旧 `roi_back` 兼容）；`kind` 含 `region`（roi 即操作区域，无 file/threshold）
- 运行时：OCR 点击 action_roi（缺省=识别 ROI）；模板 action 跟随匹配平移；`Locator::RegionRef{sel}` 引用保存区域
- 批量保存：`POST /task/save_assets` 全有或全无；全局唯一 = 所有任务 + library；单存/改名同样校验；`GET /assets/conflicts`
- 变量：`set_var/inc_var/ocr_to_var` + `var('name')`；单次运行有效，不写 checkpoint
- 构建页：`apps/oasd/ui/builder.js`；静态路由 `/builder.js`；任务库「构建」

## 5. 已知限制

- 图片识别多选保存未做；图片资产已支持操作区域编辑
- builder 第一版复杂动作（click_target/drag）用 args JSON；实时流程图只读
- OCR 操作区域是保存的绝对坐标；模板跟随匹配框
- 旧探索/个人突破已有 3 个跨任务同名素材，需要手动改名才能继续新增同名对象
- 变量不持久化；release 未签名；APK 不在本版

## 6. 阻塞 / 待用户裁定

- 无（v1.2.0 已完成并发布）

## 7. 证据索引

| 证据 | 路径 |
|---|---|
| 发布说明 | `_verify/n43/RELEASE-NOTES-v1.2.0.md` |
| 交付报告 | `_verify/n43/REPORT-V1.2.md` |
| 构建页截图 | `_verify/n43/v12_builder.png` |
| 实机 clicks | `_verify/n43/v12release/live_ocr.clicks.jsonl` |
| GitHub | `https://github.com/passioki/oas-core/releases/tag/v1.2.0` |

## 8. 坑

- `action_roi` 是操作区域唯一字段；旧 `roi_back` 只在读取时兼容，新保存写 action_roi
- 批量保存回滚 assets.json 并清理新图片；全局唯一包含 task assets + library
- UI 无 node：headless Edge + CDP Runtime.evaluate 可做点击/画布/截图回归；错误看 `window.__oasErrors`
- `loop` body 顶层字段；builder 新增动作自动插到末尾 finish 之前
- 打包 serve 冒烟需要 `--ui ui`，否则会尝试读开发目录 `apps/oasd/ui`
