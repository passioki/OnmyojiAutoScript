# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round9
checkpoint_seq: 38
updated_at: 2026-10-31T18:46:00+08:00
trigger: 素材条件逻辑运算符设计；等用户确认后实施
status: in_progress
```

## 0. 当前状态

- 引擎代码 `cdd9dde`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage 已同步/重启 8788。
- 本轮**未改代码**，只做审计与计划。

## 1. 本轮问题

“素材也应该支持逻辑运算符”。

现状：

- 后端表达式 parser 已支持 `and/or/not`、`&&/||/!`；
- 但 builder 条件预设只允许**单个素材**：
  - `parseConditionPreset()` 返回 `{asset}`：`builder.js:1089`
  - `condText()` 只生成一个 `appear('A')`：`:1102`
- 文字条件已能多个 `text_visible(...) or ...`，但和素材条件不是同一组件。

关键边界：

- 逻辑运算适用于**布尔条件**（appear/not appear/text_visible）。
- 不适用于 `click.sel`/`ocr.sel`（目标必须唯一）；点击“任一素材”用现有 `alts` / `click_target.find`。

## 2. 待确认

1. 多素材条件默认连接词：推荐每行可切 `且/或`，默认 `且`；
2. 组级“非”：推荐 `not (A and B)` 整体取反，而不是逐行取反；
3. click 是否要暴露“备选素材（alts）”多选 UI；
4. 文字多值默认 OR 保持不变。

## 3. 下一步（确认后）

1. 条件编辑器抽统一谓词行：素材/文字 + 出现/未出现 + 且/或 + 组非；
2. 生成 `appear(A) and not appear(B)` 等表达式，实时预览；
3. click 备选素材用 `alts`；OCR 保持单 ROI；
4. 旧 flow 条件保持语义；自定义表达式保留；
5. 测试 + stage + U-20 多选整组拖动。

## 4. 证据

- PENDING §E-34；ENGINE §22.39.4。
- `builder.js:1089/1102`；`oas-flow` logic tests；`alts` parser `:1152`。
