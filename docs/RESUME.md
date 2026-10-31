# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round36
checkpoint_seq: 65
updated_at: 2026-11-01T01:10:00+08:00
trigger: 近一周对话回顾 + 代码审计 + 文档修正（U-56）
status: in_progress
```

## 0. 当前状态（磁盘实测）

- 引擎 `d360d05`，`main` 干净；workspace **350 passed / 0 failed**。
- 后端文档 `109cd436`（U-56 审计文档 + U-20 收口）已提交并推送 `dev`。
- 版本 **1.2.2**；v1.2.3 开发中，**未 tag/release**。
- stage 已重建/部署：8788 = HTTP 200。

## 1. 本轮完成（U-56）

### 对话覆盖

- 导出 transcript `_verify/n44/_both_ab9eff.txt`：10-30 19:34~10-31 00:12，**35 段（U16/A19）** 双向全文已读；
- 当前活动会话 10-31 23:16~11-01 01:05（U-50~U-56）从压缩上下文 + 文档/提交事实补读；
- **缺口**：10-31 00:12~18:00 无导出 transcript，明确标记，不声称逐条读过；
- 复核发现此前“37 条（17/20）”与实际导出 35 段不符，已在覆盖台账修正。

### 代码审计发现 + 修复

- **旧资产迁移 bug**：`normalize_legacy_ocr_roi` 原来 `roi:=ocr_source_roi`，会覆盖用户已调大的 ROI；改为 `union(roi, source)`，新增回归测试；
- 引擎 `d360d05`；350 tests。
- 其余 10-30 v1.1/v1.2 需求均有代码落点；U-49~U-55 已在 e3721e6~d360d05；
- 未完成不是 v1.1/v1.2 需求，而是 U-32b 批量实帧验收、弱设备 WS 观察、发布前整体验收。

### 文档修正

- START-HERE：双 ROI → 单识别 ROI + 操作区域；测试基线 350；U-20 标注已实现；
- ENGINE R13/§22.38：改为 U-49 单 ROI 现行口径；新增分歧块 B8；§22.25 加“双 ROI 指识别+操作”提示；
- PENDING E-51d/E-52：把死循环根因修正为“条件复用旧帧”，用户已确认修复；
- E-48 加“已被 U-49 取代”横幅；E-24 重启指针更新 seq64；
- DESIGN-SPEC 顶部加范围提示（旧仓规格，现行以 ENGINE 为准）；
- DESIGN-SPEC-PROGRESS / SESSION-INDEX 追加 10-30~11-01 覆盖与缺口。

## 2. 下一步

1. 提交文档并更新 RESUME/INDEX 终态 hash；
2. U-32b 批量实帧验收；
3. 弱设备 WS 观察；
4. 发布前整体验收（仅用户明确“发布”才 tag/release）。

## 3. 证据

- PENDING §E-56；引擎 `d360d05`；350 tests；stage 8788=200。
