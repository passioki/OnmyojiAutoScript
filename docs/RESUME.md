# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v122
checkpoint_seq: 18
updated_at: 2026-10-31T00:45:00+08:00
trigger: 用户「台账全部完成再发布，继续完成」
status: done
```

## 0. 目标（一句话）

完成台账 N44~N49 全部项后发布 v1.2.2；不得跳版本、不得带缺口发布。

## 1. 验收清单（全部完成）

- [x] N44 帧磁盘持久化（manifest + PNG + 懒加载；--frames-dir）
- [x] N45-C 图片匹配结果支持识别/操作区域（用户选 C；不做图片多选）
- [x] N46 旧任务 assets 清理（`assets cleanup-legacy`，dry-run/apply，归档 `_legacy-backup`）
- [x] N47 builder `click_target`/`drag` 结构化表单 + 变量 checkpoint 持久化/恢复
- [x] N48 范围关闭：Windows 包 unsigned + SHA256；APK/Android 不在 oas-core 仓库
- [x] N49 工作台 `#panel-flow` 从 DOM 删除；生成/追加改复制到剪贴板
- [x] `cargo test --workspace` = **330 passed / 0 failed**
- [x] 浏览器/包冒烟；v1.2.2 已发布

## 2. 发布产物

- GitHub Release：`https://github.com/passioki/oas-core/releases/tag/v1.2.2`
- tag `v1.2.2`；引擎 `9debc0b`
- 包：`D:\OAS-dev\oas-core\dist\oasd-v1.2.2-win64.zip`（37,179,387 字节）
- SHA256：`B683343C24504CF5053196A2845079454BACD4BD0D316EBD524E97A8C48D8994`
- 包内：4 tasks / 26 global assets / lint 4 ok / legacy assets 已清理

## 3. 关键实现事实

- 帧：`frames/frames.json` + `frame-<id>.png`；重启保留 name/category/order；当前帧像素懒加载
- 图匹配：`lastMatch` →「用匹配结果建素材」→ roi/action_roi；单结果（C）
- builder：`click_target` 定位方式/素材/OCR 文本结构化；`drag` 方向/区域/距离/时长/margin；高级 JSON 保留
- 变量：`Checkpoint.vars` + `ProgressSink::vars_changed` + `Interpreter::with_vars`；`--resume` 恢复
- 清理：`oasd assets cleanup-legacy --apply` 移动旧 task assets/images 到 `assets/_legacy-backup/<ts>/`
- 工作台 flow：DOM 删除；`appendStepToFlow` 在无 flowJson 时复制 JSON 到剪贴板

## 4. 验证摘要

- 330 tests 全绿；新增帧重启、checkpoint vars roundtrip、run --resume vars restore
- 浏览器：无 `#panel-flow`/`flow-json`/flow rail；无 JS 错误；builder 结构化子表单；复制步骤 fallback
- 包内：`oasd 1.2.2`；lint 4/4；`/task/assets` 26；`/frames` 正常；builder.js 200
- 迁移/清理：4 tasks / 3 renames；legacy cleanup 4 tasks 归档

## 5. 已知限制

- 图片识别仍单结果（用户选 C），不做多候选/图片多选；
- 变量只在单次运行/checkpoint 内有效，不跨任务持久化；
- 旧 assets 归档不自动删除；release unsigned；APK 不在本版；
- 帧数据本机 serve 本地，不随任务包同步。

## 6. 下一步

- 若继续：图片多候选（需新设计）或 Authenticode/APK 另立项；
- 否则本版完成，维护台账/RESUME。
