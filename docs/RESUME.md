# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-acceptance
checkpoint_seq: 28
updated_at: 2026-10-31T02:25:00+08:00
trigger: v1.2.3 验收 U-01~U-04；U-02/U-03/U-04 已修，U-01 待裁定
status: in_progress
```

## 0. 当前状态

- **R1~R21 全部关闭**（台账 ✅）。
- **U-02/U-03/U-04 已修**（engine `cbfbab4`，stage UI 已同步测试）。
- **U-01 子流程/任务调用待用户裁定 A/B**；未自行发布，版本 1.2.2。

## 1. 本轮完成（验收 U-02/U-03/U-04）

### U-02 素材保存统一入口 + 全选
- 移除独立的 `btn-batch-save`；
- 右侧统一按钮「保存素材（当前框选 / 选中识别行）」：有 OCR 候选走批量，无候选走单素材；
- 候选列表新增全选 checkbox（全选/半选/全不选）；
- CDP 实测：全选→two true；全不选→two false；旧批量按钮不存在。

### U-03 任务构建布局（stage）
- 根因：全局 `aside{width:320px}` 覆盖 builder grid 轨道（palette 320px，center x=244 → 重叠 90px）；
- 修复：grid 轨道 + `.builder-main > aside { width:auto; flex:none }`；
- 新增左右 splitter 可拖拽，`localStorage` 记忆（`oas.builder.layout.v1`）；
- repo + `dist/stage`（8788）实测：palette=220、center.x=260、splitters=2、SVG 存在；拖到 240 后刷新仍 240；无 JS 错误。
- **stage UI 已同步**（仅测试；未 bump 版本、未 tag/release）。

### U-04 流程控制子动作
- `renderForm` 子动作从硬编码 `log` 改为 **动作选择器**（任意 op）加入 then/else/body；
- 选中 if/loop 容器后，动作库按钮直接加入容器（if→then，loop→body）；
- CDP 实测：选 if → `.builder-child-add` 出现；选择 `click_point` 加入 then；动作库点击 `点击坐标` 也加入；无 JS 错误。

## 2. U-01 待裁定

用户原话：“应当可以调用已有任务作为当前任务的一部分。这是否属于函数调用？”

结论：**是子流程/任务调用（subflow call），不是纯函数**；任务有设备副作用/屏幕状态/共享素材，必须定义输入/输出/exit/嵌套上限/失败传播。
两条实现路线：

- **A. 构建时展开/内联**：复制目标任务 steps，简单，不能动态同步；
- **B. 运行时 `call_task`**：运行时加载目标 flow，函数式边界，需 runtime/flow parser 改动；
- 推荐 **B 最小版**（无参数、单 exit、禁止递归、深度上限 1），等用户确认。

## 3. 发布规则

- 不自行 tag/release；只在用户明确说“发布”时发布；
- 平时只构建 release 测试；版本保持 1.2.2。

## 4. 下一步

1. 用户裁定 U-01 A/B；若 B，先改 `oas-flow` op schema + `oas-runtime` 解释器 + builder 表单；
2. 之后跑 testing/release 测试构建；
3. 每次 UI 验收加 computed rect/真实交互断言（skill 强制 7）。
