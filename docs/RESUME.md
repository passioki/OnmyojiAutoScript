# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round19
checkpoint_seq: 48
updated_at: 2026-10-31T21:35:00+08:00
trigger: 编辑器/runtime 三条路径已同源；仅缺一致性守护测试
status: in_progress
```

## 0. 当前状态

- 引擎代码 `d049bfe`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步/重启 8788。
- U-32b 批量实帧验收仍待 positions。

## 1. 本轮完成（U-41c）

| 路径 | 统一 |
|---|---|
| 模板定位 | `oas_runtime::locate_template`：ROI mask 快路径 + 全帧兜底 |
| 编辑器 `/task/asset/match` | 同 helper |
| batch template | 同 helper |
| 编辑器 `/ocr`、`/lines` | 接受 task/id，应用 asset polygon mask |
| 素材行点击测试 | derived OCR 用 source ROI + `/lines`，带 task/id polygon |
| batch OCR 单行/derived | asset polygon mask + shared det+rec |
| collection 测试 | `/task/asset/collection/match`：runtime 同源最佳成员/threshold/action_roi |
| 集合 UI | 改用统一 endpoint |

代码：`cdf19d5`、`e953166`、`d049bfe`。

## 2. 仍待

1. 自动化“编辑器 vs runtime 同帧同 asset 结果一致”守卫；
2. U-32b 批量实帧验收（需用户给素材设置 positions）；
3. U-20 多选整组拖动。

## 3. 下一步

1. 加一致性守卫测试；
2. 用户设置 positions 后跑批量帧测试；
3. U-20；
4. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-41；stage 8788；344 tests。
- `/lines?task=回到庭院&id=庭院` 返回 `庭院 0.9668`（polygon 参数路径可用）。
