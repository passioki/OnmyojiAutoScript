# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-builder-v121
checkpoint_seq: 13
updated_at: 2026-10-31T00:10:00+08:00
trigger: phase-gate
status: done                # in_progress | blocked | done
```

## 0. 目标（一句话）

v1.2.1：统一全局素材库、OCR 多行来源一致、批量素材可见、builder 素材/布局/真流程图、帧管理、工作台流程收口；全做完后发布。

## 1. 验收清单（全部完成）

- [x] OCR 来源一致：`ocr_mode/ocr_source_roi/ocr_text` + 运行时原 det+rec + 操作区域平移
- [x] 批量保存素材可见：active task 统一
- [x] builder 素材选择器/布局/真控制流图（if 分支、loop 回边）
- [x] 帧重命名、去 20 上限、拖动排序、自由文本分类
- [x] 全局素材库统一（`assets/`）+ 迁移自动后缀 + 按任务重写 flow
- [x] 工作台流程入口移除，流程编辑统一到任务构建
- [x] 327 tests 全绿；浏览器/迁移/运行验证；发布 v1.2.1

## 2. 发布产物

- GitHub Release：`https://github.com/passioki/oas-core/releases/tag/v1.2.1`
- tag `v1.2.1`；main `4e50aea`
- 包：`D:\OAS-dev\oas-core\dist\oasd-v1.2.1-win64.zip`（37,148,195 字节）
- SHA256：`E4E4E94DDBF86CBB6D3D7A831BFD7E8940DA6DCAD823B0432A4FD55843C99AC1`
- 测试：**327 passed / 0 failed**
- 包内：assets 26 / tasks 4 / migration 3 flows rewritten / lint 4 ok

## 3. 关键实现事实

- 全局库 `assets/assets.json + images/`；`oasd assets migrate`，`/assets/migrate`；启动脚本 `--assets-dir assets`
- 迁移：重名自动 `_2/_3`；每个任务独立 old→new 映射重写 flow；失败回滚 flows；报告 `assets/migration-report.json`
- 运行时：`RunOptions.assets`；存在全局库时优先；`task lint` 支持全局 id
- OCR derived line：`AssetSet.derived_ocr`；`ocr_read` 原 source ROI det+rec；`last_ocr_rect` 平移 action_roi
- builder：`builder.js`、三栏布局、`fg-control-box/fg-backedge` 真流程图
- 帧：`SessionFrame{name,category}`、`/frames/rename|category|reorder`；内存 session，无 20 上限
- 工作台 flow rail 移除；`#panel-flow` 仅隐藏保留兼容 JS（用户不可见）

## 4. 验证摘要

- 浏览器 CDP：taskName=select=任务1；全局素材 26；批量保存 39 个；`V121UI0` provenance 字段正确；builder 可用素材 26、控制图 3/回边 2；帧 24；无 JS 错误
- 迁移：26 assets / 4 tasks / 3 flows / 3 renames；lint 4/4 ok
- 全局运行：`assets=global` 23 runtime assets；派生 OCR click `(158,16)` Done
- 删除/改名全局素材被 task flow 引用时拒绝并列出任务

## 5. 已知限制

- 帧为 serve session 内存数据，重启不保留（仅去上限+管理）
- 图片识别多选保存未做；OCR 行多选已完成
- 旧任务目录 assets/images 迁移后保留未删除（编辑器/运行只读全局库）
- builder 复杂动作 args JSON；变量不持久化
- release 未签名；APK 不在本版

## 6. 阻塞 / 待用户裁定

- 无（v1.2.1 已完成并发布）

## 7. 证据索引

| 证据 | 路径 |
|---|---|
| 发布说明 | `_verify/n43/RELEASE-NOTES-v1.2.1.md` |
| 交付报告 | `_verify/n43/REPORT-V1.2.1.md` |
| GitHub | `https://github.com/passioki/oas-core/releases/tag/v1.2.1` |

## 8. 坑

- 打包 serve 冒烟要 `--ui ui`；包脚本迁移需要 stage 目录无运行中的 exe 锁
- 迁移会 rewrite flow；保留 task assets 作备份但不再读取
- 全局模板允许 roi=None（旧 library 模板全屏搜索）
- builder 新增动作自动插在末尾 finish 前；流程图节点路径与步骤树共用
- 帧拖动顺序 UI：拖到分组头改分类，拖到行前排序
