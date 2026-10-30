# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-acceptance
checkpoint_seq: 29
updated_at: 2026-10-31T03:05:00+08:00
trigger: v1.2.3 验收 U-01~U-04 全部完成；准备关机
status: done
```

## 0. 当前状态

- **R1~R21 全部关闭**（台账 21/21）。
- **v1.2.3 验收 U-01~U-04 全部完成**（4/4）。
- **未自行发布**；版本仍 1.2.2。
- stage `dist\stage` 的 UI 与 `oasd.exe` 已同步最新测试构建（OCR feature 开启），未打 tag/release。

## 1. 本轮完成

### U-01 任务调用 A/B（`1ee41d0`）
- A：builder `inlineCallTask` 读取目标任务 flow → 复制 steps → 去掉目标 `finish` → 替换当前 call_task 步骤；
- B：flow DSL 新增 `call_task`；`oas-task::TaskBundle::load_flow` 在加载时递归展开目标 flow（cycle 检测、深度上限 8、目标 `finish` 视为返回）；
- builder「调用已有任务」表单：任务选择 + 方式 A/B；
- 测试：`load_flow_expands_call_task_and_strips_target_finish`；workspace **331 passed**；
- stage(8796) 表单实测 task=子任务、mode=run；repo 实测 A 内联生效、B 保存 raw call_task。

### U-02 素材保存统一 + 全选（`cbfbab4`）
- 删除独立批量保存按钮；统一「保存素材（当前框选/选中识别行）」；
- 多行候选全选 checkbox（全选/半选/全不选）；CDP 验证。

### U-03 布局/记忆（`d455f6e` + `cbfbab4`）
- 根因全局 `aside width 320` 覆盖 grid；修复后三栏不重叠；
- 左右 splitter 可拖拽，localStorage 记忆；repo + stage 验证；
- stage UI 已同步。

### U-04 if/loop 子动作（`cbfbab4`）
- 属性面板子动作选择器（任意 op 加入 then/else/body），不再硬编码 log；
- 选中 if 后动作库点击动作加入 then；CDP 验证。

## 2. 发布规则

- 不自行 tag/release；只在用户明确说“发布”时发布；
- 平时只构建 release 测试；版本保持 1.2.2。

## 3. 下一步

- 用户要求：**完成后关闭电脑**（本轮结束执行 shutdown）。
- 下次启动：读本卡；继续等用户发布指令；若需发布再 bump 版本并走 release。
