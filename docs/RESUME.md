# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round24
checkpoint_seq: 53
updated_at: 2026-10-31T22:35:00+08:00
trigger: 选中帧被实时帧覆盖已修复
status: in_progress
```

## 0. 当前状态

- 引擎代码 `958b868`；workspace **346 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步/重启 8788。

## 1. 本轮修复（U-45）

问题：选中图片后测试识别仍用实时帧。

根因：实时 WS/抓帧直接写 `State.frame/png`，会覆盖选中帧。

修复：

- `State` 拆分：
  - `frame/png` = 分析帧（选中图片 / 显式截图）；
  - `live_frame/live_png` = 实时预览。
- WS 与 `/frame.png?live=1` 只更新 live 字段；
- 仅当 `current_frame_id=None`（没有选中帧）时才同步分析帧，保证启动即可实时识别；
- `/frame.png?live=1` 返回 live；普通 `/frame.png` 返回选中帧。

验证：选 #4 → live → 普通 `/frame.png` SHA256 不变；UI WS 正常；346 tests。

## 2. 仍待

1. U-32b 批量实帧验收；
2. 实时 WS 弱设备重连/帧率观察；
3. 发布前整体验收。

## 3. 下一步

1. 用户重试“选中图片 → 测试识别”；
2. positions 批量；
3. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-45；代码 `958b868`；346 tests；stage 8788。
