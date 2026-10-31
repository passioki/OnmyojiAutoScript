# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round36
checkpoint_seq: 66
updated_at: 2026-11-01T01:25:00+08:00
trigger: 近一周对话回顾 + 代码审计 + 文档修正（U-56）
status: in_progress
```

## 0. 当前状态（磁盘实测）

- 引擎 `d360d05`，`main` 干净；workspace **350 passed / 0 failed**。
- 后端文档本轮提交后记录；此前 `4c066d17` 为本卡前版。
- 版本 **1.2.2**；v1.2.3 开发中，**未 tag/release**。
- stage 已重建/部署：8788 = HTTP 200。

## 1. 本轮完成（U-56）

### 对话覆盖

- 从 DSH 会话存储解压完整 `session.v4.jsonl`（91,633,434 bytes）→ `session-current-both.txt`（285 条，10-22~11-01 00:47）；
- 近一周 10-30~11-01：**163 条（U81/A82）**；
- 10-30 段 35 条、10-31 段 124 条、11-01 段 12 条；10-26~10-29 无记录；
- USER 发言全量已读；ASST 以设计文档/关键承诺落点核对（未声称逐条精读）；
- 之前“10-31 00:12~18:00 缺口”已解除（旧导出截断，完整存储已解压）。

### 代码审计发现 + 修复

- **旧资产迁移 bug**：`normalize_legacy_ocr_roi` 原 `roi:=ocr_source_roi`，会覆盖用户已调大的 ROI；改为 `union(roi, source)`，新增回归测试；
- 引擎 `d360d05`；350 tests；
- 其余 10-30 v1.1/v1.2 需求均有代码落点；U-20 多选整组拖动已由 `e73b408` 实现并收口；
- 未完成不是 v1.1/v1.2 需求，而是 U-32b 批量实帧验收、弱设备 WS 观察、发布前整体验收。

### 文档修正

- START-HERE：双 ROI → 单识别 ROI + 操作区域；测试基线 350；U-20 标注已实现；U-35~U-56；
- ENGINE R13/§22.38：改为 U-49 单 ROI 现行口径；新增分歧块 B8；§22.25 加“双 ROI 指识别+操作”提示；
- PENDING E-51d/E-52：死循环根因修正为“条件复用旧帧”（用户已确认修复）；
- E-48/E-40/E-41 加历史横幅；E-24 重启指针更新 seq65；U-20/U-32b/E-33e 收口；
- DESIGN-SPEC 顶部加范围提示（旧仓规格，现行以 ENGINE 为准）；
- DESIGN-SPEC-PROGRESS / SESSION-INDEX 追加 10-30~11-01 覆盖与缺口说明。

## 2. 下一步

1. 提交文档并更新本卡 hash；
2. U-32b 批量实帧验收；
3. 弱设备 WS 观察；
4. 发布前整体验收（仅用户明确“发布”才 tag/release）。

## 3. 证据

- PENDING §E-56；引擎 `d360d05`；350 tests；stage 8788=200；完整 transcript 285 条。
