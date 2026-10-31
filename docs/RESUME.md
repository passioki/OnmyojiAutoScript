# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round33
checkpoint_seq: 62
updated_at: 2026-11-01T00:45:00+08:00
trigger: 缓存帧全面审计完成
status: in_progress
```

## 0. 当前状态

- 引擎代码 `0594ceb`；workspace **348 passed**。
- 版本 1.2.2，未 tag/release；stage 已部署/重启。

## 1. 本轮完成（U-54）

用户确认 while 实时帧修复后任务成功，要求举一反三。

所有“读当前屏幕”的入口统一刷新：

- `while` / `if` 条件求值前；
- `wait` 结束后；
- `wait_until` 每轮求值前；
- `dismiss_popup` 每轮检测前；
- `appear` / `ocr` 步骤；
- `click` / `click_point` / `click_target` 定位前；
- `drag` 取源区域前；
- `swipe` 执行后（原有）；
- `verify_expect` 每轮（原有）。

服务端/UI：
- `/lines` `/ocr` `/match` 用当前分析帧；
- 实时预览只更新 live，不覆盖选中图片；
- 编辑器测试/批量帧测试使用同一分析帧。

## 2. 证据

- while `frame_seq` 逐轮递增；
- `appear_trace` 显示每个 appear 结果；
- 348 tests；stage 已部署。

## 3. 仍待

1. U-32b 批量实帧验收；
2. 发布前整体验收。

## 4. 证据

- PENDING §E-54；代码 `0594ceb`；348 tests；stage 8788。
