# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round18
checkpoint_seq: 47
updated_at: 2026-10-31T21:20:00+08:00
trigger: 模板 locate 已统一；剩余单行 polygon/集合测试待统一
status: in_progress
```

## 0. 当前状态

- 引擎代码 `cdf19d5`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步/重启 8788。
- U-32b 批量实帧验收仍待 positions。

## 1. 本轮完成（U-41 第 2 部分）

抽 `oas_runtime::locate_template` + `template_polygon_mask`：

- interpreter `locate_one` 使用；
- 编辑器 `/task/asset/match` 使用；
- batch_test template 使用。

统一语义：

```text
ROI 快路径（有 polygon 则 masked NCC）
  → score>=0.95 直接返回
  → 否则全帧金字塔兜底
  → 取最高分
```

代码 `cdf19d5`；stage 已部署；344 tests。

## 2. 仍待统一（§E-41）

1. 单行 `/ocr` 编辑器测试不做 asset polygon mask；runtime `ocr_read` 会 mask；
2. collection 测试逐成员 `/task/asset/match`，未完全复用 runtime 的 collection 展开/threshold/action_roi；
3. 未加“编辑器 vs runtime 同帧同 asset 结果一致”守护测试。

## 3. 下一步

1. 编辑器 OCR 测试按 asset id 走统一入口（应用 polygon）；
2. collection 测试复用 runtime collection 选择；
3. 一致性守卫测试；
4. U-32b positions 批量验收；U-20 多选整组拖动；
5. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-41；代码 `cdf19d5`；stage 8788；344 tests。
