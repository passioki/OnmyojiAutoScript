# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round15
checkpoint_seq: 44
updated_at: 2026-10-31T20:50:00+08:00
trigger: 第五轮 UI/OCR 反馈已修；等用户验收
status: in_progress
```

## 0. 当前状态

- 引擎代码 `0f0c293`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步并重启 8788。
- U-32b 批量实帧验收仍待用户实际设置 positions 后闭合。

## 1. 本轮完成（U-39）

| ID | 结果 |
|---|---|
| U-39a | 任务引用素材只放「任务」页；素材页删除该块 |
| U-39b | 素材位置：分类下拉 + 帧下拉 + 添加位置列表（可多位置） |
| U-39c | builder `← 返回 / 前进 →` 选中步骤历史 |
| U-39d | 父级拖入自身子级被拒绝，带 snapshot 回滚；不再双消失 |
| U-39e | 运行期 OCR provider 补 90° 旋转兜底；竖排「庭院」可识别；诊断输出 found lines |

## 2. 关键证据

- CDP stage：任务页 5 个引用素材；素材页无引用块；位置分类 7/帧 14；返回/前进工作。
- stage `_diag_ocr2`：`ocr=on`，`庭院` 识别成功，Done（临时任务已删）。
- OCR 根因：运行期 `recognize_lines` 缺 90° fallback，正立识别得到 `"應"(0.217)`；编辑器 `/lines` 有 fallback。
- 测试 344 passed。

## 3. 下一步

1. 用户重跑「回到庭院」；条件建议：
   - 直到任一出现：`not (appear('町中') or appear('召唤'))`
   - 排除同时存在：`not (appear('町中') and appear('召唤'))`
2. 设置 positions 跑批量帧测试，闭合 U-32b。
3. U-20 多选整组拖动仍待补。
4. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-39；ENGINE §22.39.4。
- 代码 `0f0c293`；stage 8788。
