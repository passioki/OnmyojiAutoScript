# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round8
checkpoint_seq: 37
updated_at: 2026-10-31T18:44:00+08:00
trigger: 逻辑运算符审计 + U-32b/根级拖拽补完；等用户验收
status: in_progress
```

## 0. 当前状态

- 引擎代码 `cdd9dde`；workspace **344 passed / 0 failed**。
- 版本 **1.2.2**，未 tag/release；stage UI + OCR exe 已同步并重启 8788。
- 未恢复用户删除的任务/素材。

## 1. 本轮完成（U-33）

- **逻辑运算符审计**：
  - `and/or/not` + `&&/||/!` 在 `parse_expr` 中均支持；
  - 表达式字段：`if.cond`、`while.cond`、`wait_until.cond`、`loop.n`、`log.text`、`set_var.value`、`inc_var.by`、`click_point.x/y`；
  - `click_point x/y` UI 从 number 改为表达式输入；
  - 这些字段统一显示逻辑运算符提示；
  - 文字出现/未出现用 `text_visible('a') or text_visible('b')` / `not (...)`；
  - 字面量数字/结构字段（wait.seconds、timeout、swipe/drag 坐标、stable_frames）不强行表达式化。
- **U-32b 补完**：batch_test 对 derived `ocr_line` 用 source ROI det+rec 比对 `ocr_text`。
- **U-20**：新增「拖到根级」drop 区，单步可从容器拖回根级；**多选整组拖动仍未做**。

## 2. 下一步

1. 等用户验收逻辑运算符和批量帧测试；
2. U-20 多选整组拖动（剩余唯一明确未完成项）；
3. 实机验证「回到庭院」（dry-run 不点击会跑到预算耗尽，属预期）。
4. 发布时才 bump/tag/release。

## 3. 证据

- PENDING §E-32 / §E-33；ENGINE §22.39.4。
- CDP stage：任务面板 3 个引用素材；23 个缩略图；14 个位置帧选项。
- release dry-run：`appear('町中')` 不再报 selector 未声明；进入 while/if/click。
- tests 344 passed。
