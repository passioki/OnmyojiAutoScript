# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round23
checkpoint_seq: 52
updated_at: 2026-10-31T22:25:00+08:00
trigger: 位置编辑搜索候选、U-20 整组拖动、WebSocket 实时预览完成
status: in_progress
```

## 0. 当前状态

- 引擎代码 `e73b408`；workspace **346 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步/重启 8788。

## 1. 本轮完成（U-44）

### U-44a 位置设置 modal

- `editAssetPositions` 不再用 prompt；
- 搜索+候选（分类 / #id 帧名），可删已选；
- 「保存位置」显式反馈，失败显示错误；
- 保存后刷新素材（分类继承位置帧）。

### U-44b U-20 多选整组拖动

- 勾选多个步骤后拖动任意已选行；
- `moveStepsGroup` 移动顶层勾选步骤到根级/容器；
- 自动排除被父级覆盖的子级；状态显示数量。

### U-44c WebSocket 实时

- `GET /ws/live`：树内 SHA1/base64 握手，后台线程推 PNG 二进制帧；
- UI 优先 WebSocket，失败回退 1.2s 轮询；
- 仍不入库；截图/选帧暂停。

## 2. 验证

- WS 连上并收到 binary PNG；UI ws readyState=1、无 JS 错误；
- modal 保存后 positions=[4]、category=庭院；测试后恢复；
- 多选拖动 before=5 after=5，状态“已移动 2 个勾选步骤到 根级”；
- 346 tests。

## 3. 仍待

1. U-32b 批量实帧验收（positions + 匹配帧）；
2. 实时 WebSocket 在弱设备上的帧率/断线重连观察；
3. 发布前整体验收。

## 4. 下一步

1. 用户验收位置编辑/U-20/WS；
2. 设置 positions 跑批量；
3. 发布时才 bump/tag/release。

## 5. 证据

- PENDING §E-44；代码 `e73b408`；346 tests；stage 8788。
