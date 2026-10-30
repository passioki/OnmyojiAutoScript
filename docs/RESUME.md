# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-editor-v11
checkpoint_seq: 10
updated_at: 2026-10-30T21:45:00+08:00
trigger: phase-gate
status: done                # in_progress | blocked | done
```

## 0. 目标（一句话）

按用户确认的 v1.1 设计实现并发布：整屏 OCR 文字直点、素材 CRUD/区域/拟人拖动、任务工作台+完成条件、多页面（工作台/任务库/实例/调度/设置）、点击分布聚合+删除。

## 1. 验收清单（全部完成）

- [x] **P0**：`ocr_lines` 测试走 `/lines`；整屏 OCR 内联直点；`追加到流程` 中文；`logs/editor.log` — `4b9ee7c`
- [x] **P1**：素材 CRUD；`Locator::Region`；`Step::Drag`（方向必填/随机起终点/时长/方向校验）；flow 生成 — `fd005b0`
- [x] **P2**：任务工作台 ①~⑦；`meta.goal` battles 自动 loop；until_* 由 flow 判断 — `a62e803`
- [x] **P3**：顶部页面；任务库打开/删除/新建；实例读写 config；调度页；设置页 — `7551377`
- [x] **P4**：点击分布聚合（全部/最近10/最近1/按任务）+ 删除/清空到 `_trash` — `4a06d97`
- [x] **P5**：314 tests 全绿；release/实机回归；打包 v1.1.0；GitHub release — `f2c096c` / tag `v1.1.0`

## 2. 发布产物

- GitHub Release：`https://github.com/passioki/oas-core/releases/tag/v1.1.0`
- 包：`D:\OAS-dev\oas-core\dist\oasd-v1.1.0-win64.zip`（36,868,461 字节）
- SHA256：`140BB35BEF9CA7BD357A396CB101798C291A26E7208A58CA064141E0A82235BB`
- tag：`v1.1.0`；main：`f2c096c`
- 测试：`cargo test --workspace` = **314 passed / 0 failed**
- 包内冒烟：`oasd 1.1.0`；`task lint --all` 4 tasks/0 errors；serve `/state` captured 1280x720/OCR ready

## 3. 实机/回归证据

| 项 | 结果 |
|---|---|
| release 实机整屏 OCR 直点 | `clicked_target locator=ocr_text inline text="预设" score=1.000 point=(394,96)` → Done |
| dry-run 区域点击+拖动+loop | `region (1017,360)`；`drag direction=up from=(1027,635) to=(1027,496) ms=406`；`loop 2/2` → Done |
| P2 完成条件 | `loop n=param('max_battles')` 默认 2 → 两次日志 → Done；lint 通过 |
| 素材 CRUD | delete/rename/update threshold API 均 200；列表 count 6→5 |
| 点击分布 | 2 run 聚合 `runs=2 clicks=2 distinct=2`；删除移 `_trash` 成功 |
| 截图 | `_verify/n43/page_tasks2.png`、`page2_instances.png`、`page2_schedule.png`、`page3_settings.png`、`ui_p4.png` 等 |

## 4. 文档

- `docs/ENGINE-DESIGN.md §22.36` V1.1 交付记录（已追加）
- `docs/DELIVERY-PLAN.md §9` V1.1 交付结果（已追加）
- `_verify/n43/REPORT-V1.1.md`、`RELEASE-NOTES-v1.1.0.md`（工作区证据，不提交）
- 包内 `README-DEPLOY.md` 已更新 V1.1 新特性/工作台流程

## 5. 已知限制

- `until_resource/until_condition` 不做通用游戏语义，需 flow 用 while/识别/出现 判断；
- 拖动当前是直线 `adb input swipe`；曲线抖动待 minitouch/scrcpy 输入后端；
- v1.1 单进程单活动实例（实例配置可编辑，重启生效），多实例并行后续；
- APK/Android 引擎不在 v1.1.0；
- release 未签名（SmartScreen 可能提示）。

## 6. 阻塞 / 待用户裁定

- 无（v1.1 已完成并发布）

## 7. 证据索引

| 证据 | 路径 |
|---|---|
| 发布报告 | `_verify/n43/REPORT-V1.1.md` |
| 发布说明 | `_verify/n43/RELEASE-NOTES-v1.1.0.md` |
| 内联 OCR live | `_verify/n43/p5/live_ocr.clicks.jsonl` |
| 页面截图 | `_verify/n43/page*_*.png` / `ui_p4.png` |
| GitHub | `https://github.com/passioki/oas-core/releases/tag/v1.1.0` |

## 8. 坑

- PowerShell 默认 GBK：脚本/中文路径用绝对路径；.NET 相对路径不跟 `cd`；
- 运行中的 oasd.exe 锁 target；重建前停 serve；
- JS 无 node：用 headless Edge 截图 + 页面标题栏错误提示验页面；
- `loop` 的 body 是**顶层字段**，不是 `args.body`；`n` 是表达式字符串（如 `"2"`/`"param('max_battles')"`）。
