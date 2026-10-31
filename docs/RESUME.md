# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-ui-round5
checkpoint_seq: 33
updated_at: 2026-10-31T17:28:00+08:00
trigger: while/if 条件 UI 优化完成；等用户验收
status: done
```

## 0. 当前状态

- R1~R21 ✅；U-01~U-28：主体完成；U-20 根级拖拽/多选整组拖动仍待补。
- 代码 `00ac85c`；workspace **339 tests passed**。
- **未 tag/release**；版本仍 1.2.2；stage UI + exe 已同步测试构建。
- 未恢复用户删除的任务/素材。

## 1. 本轮完成（U-28）

- 根因：builder 每个步骤顶部都有通用素材选择器，选择后直接写 `args.sel`；if/while 无 `sel` 字段，所以看起来“选了素材但条件还是 false/true 无关”。
- if/while 新增条件预设编辑器：
  - 素材出现时 → `appear('id')`
  - 素材未出现时 → `not appear('id')`
  - 文字等于 → `ocr('id') == 'text'`
  - 文字不等于 → `ocr('id') != 'text'`
  - 自定义表达式
- 条件素材选择直接写 `cond`，不写 `sel`；顶部通用素材选择器只对 appear/ocr/click/dismiss_popup/ocr_to_var 显示。
- normalize 删除 if/while/loop 的非法 `sel`；while 默认仍 `cond:true`, `max_iters:0`。
- CDP 验证：`not appear('保存测试')` 成功自动保存，flow 无 `sel`。

## 2. 发布规则

- 不自行 tag/release；只在用户明确说“发布”时发布；
- 平时只构建 release 测试；版本保持 1.2.2。

## 3. 下一步

- 等用户验收条件编辑器/旧任务清理；
- 补 U-20 根级拖拽/多选整组拖动；
- 实机验证多行 OCR 资产和工作台测试；
- 发布时才 bump/tag/release。
