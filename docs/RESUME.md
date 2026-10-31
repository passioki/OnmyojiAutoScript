# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round17
checkpoint_seq: 46
updated_at: 2026-10-31T21:08:00+08:00
trigger: 跨路径一致性审计；OCR 已统一，模板/polygon/集合测试待统一
status: in_progress
```

## 0. 当前状态

- 引擎代码 `70df254`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步/重启 8788。
- U-32b 批量实帧验收仍待 positions。

## 1. 本轮完成（U-41）

- 抽取 `apps/oasd/src/ocr.rs::recognize_lines_impl`：
  - crop → det → 每 box rec → 低分 90° cw/ccw → score>=0.5 过滤 → 绝对坐标；
- 三处共用：
  - runtime `OnnxOcr::recognize_lines`
  - 编辑器 `GET /lines`（vertical 参数保留，输出转回 ROI-local）
  - batch_test derived OCR
- 修复了同类“编辑器成功、runtime 失败”的 90° 漂移。
- stage 验证：`_diag_ocr3` `appear('庭院')` → true，Done（临时任务已删）。

## 2. 仍待统一（见 §E-41）

1. 模板测试 `/task/asset/match` + batch template 只跑全帧匹配；runtime 是 ROI mask 快路径 + 全帧兜底 → 带 polygon 模板可能两边不一致。
2. 单行 `/ocr` 编辑器测试不做 asset polygon mask；runtime 会 mask。
3. 集合测试逐成员 `/task/asset/match`，未完全复用 runtime collection 逻辑。
4. 尚未加“编辑器 vs runtime 同帧同 asset 结果一致”守卫。

## 3. 下一步

1. 用户验收当前 UI/OCR；
2. 继续抽 runtime `locate_template` 公共 helper，统一模板/polygon 测试；
3. 设置 positions 跑批量帧测试，闭合 U-32b；
4. U-20 多选整组拖动；
5. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-41；代码 `70df254`；tests 344。
- stage `_diag_ocr3` cond true → Done。
