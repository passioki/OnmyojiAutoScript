# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round10
checkpoint_seq: 39
updated_at: 2026-10-31T19:02:00+08:00
trigger: U-34 素材条件逻辑实现；等用户验收
status: in_progress
```

## 0. 当前状态

- 引擎代码 `c2de9c6`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage UI 已同步（exe `cdd9dde`）并重启 8788。
- U-32b 代码完成，**批量实帧验收仍未闭合**（assets 无 positions；临时帧测试未命中期望文字）。

## 1. 本轮完成（U-34）

- 条件编辑器统一为谓词行：
  - 行类型：素材 / 文字（全屏）；
  - 每行「未出现」；
  - 行间「且/或」；
  - 组级「非（整组取反）」；
  - 实时表达式预览；
  - 自定义表达式仍保留。
- 素材行默认 AND；文字多值默认 OR。
- click 属性新增「备选素材（任一命中）」多选，写入 `args.alts`；`sel` 仍单目标。
- `not(A and B)` 语义 = 排除同时存在；A only/B only/neither 均满足（De Morgan）。

## 2. 用户确认

- #1 多行条件默认且 ✅
- #2 `not(A and B)` 布尔代数 ✅
- #3 click 备选素材暴露 alts ✅
- #4 文字多值默认 OR ✅

## 3. 下一步

1. 给 stage 素材设置 positions，跑批量帧测试并取得通过证据；
2. U-20 多选整组拖动（唯一明确未完成项）；
3. 实机验证「回到庭院」（dry-run 不点击会跑到预算耗尽，属预期）。
4. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-32 / §E-33 / §E-34；ENGINE §22.39.4。
- CDP 条件行测试：2 行 + 组非生成 `not (not (appear('保存测试')) and appear('位置测试'))`。
- tests 344 passed。
