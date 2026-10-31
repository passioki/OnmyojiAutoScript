# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-ui-round6
checkpoint_seq: 34
updated_at: 2026-10-31T17:35:00+08:00
trigger: while/loop 最终语义已修；等用户验收
status: done
```

## 0. 当前状态

- R1~R21 ✅；U-01~U-29：主体完成；U-20 根级拖拽/多选整组拖动仍待补。
- 代码 `460ad32`；workspace **341 tests passed**。
- **未 tag/release**；版本仍 1.2.2；stage UI + exe 已同步测试构建。
- 未恢复用户删除的任务/素材。

## 1. 本轮最终语义

- `while`：**只有 cond + body，没有 max_iters**。
  - `cond` 为 bool：true 循环、false 不循环；
  - `cond` 为数值：0 不循环、非 0 循环；
  - 无用户迭代上限，但 runtime step budget 仍是硬保护。
- `loop`：`n <= 0` 不循环；`n > 0` 循环 n 次。
- builder：if/while 条件预设编辑器（素材出现/未出现、文字等于/不等于、自定义），条件选素材写 `cond` 不写 `sel`；while 表单无最大迭代字段；loop 字段文案「<=0 不循环；>0 循环次数」。
- normalize 清理 if/while/loop 的非法 `sel`/`max_iters`。

## 2. 发布规则

- 不自行 tag/release；只在用户明确说“发布”时发布；
- 平时只构建 release 测试；版本保持 1.2.2。

## 3. 下一步

- 等用户验收条件语义；
- 补 U-20 根级拖拽/多选整组拖动；
- 实机验证多行 OCR 资产；
- 发布时才 bump/tag/release。
