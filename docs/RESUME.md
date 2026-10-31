# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round32
checkpoint_seq: 61
updated_at: 2026-11-01T00:35:00+08:00
trigger: 撤销/重做 + while 实时帧完成
status: in_progress
```

## 0. 当前状态

- 引擎代码 `fb71014`；workspace **348 passed**。
- 版本 1.2.2，未 tag/release；stage 已部署/重启。

## 1. 本轮完成（U-53）

### 任务构建撤销/重做

- `返回/前进` 改为「↶ 撤销 / ↷ 重做」；
- 快照 flow 内容（最多 100），选择变化不产生历史；
- Ctrl+Z / Ctrl+Shift+Z（输入框内不拦截）；
- 实测增/撤/重做正确。

### while 实时帧

- 每次 while 条件求值前清缓存帧；
- `appear()` 重新抓 ADB 实时帧；
- `while_cond` 带 `frame_seq`；
- 编辑器运行输出 `appear_trace`：
  ```text
  appear_trace sel=召唤 -> true frame_seq=1
  while_cond iteration=0 value=Bool(true) truthy=true frame_seq=1
  ```
- 实测连续 frame_seq 递增。

## 2. 对用户问题的回答

运行时确实使用实时帧；之前存在复用缓存帧的风险。现在每次 while 条件强制新帧，并输出每个 appear 的结果。

如果仍死循环，看：
- `appear_trace ... -> false/ERROR`：哪个素材没识别；
- `frame_seq` 是否递增：是否真的抓了新帧；
- `/lines` 详细日志：OCR ROI/原始文本。

## 3. 仍待

1. 用户重跑「返回庭院」确认是否退出；
2. U-32b 批量；
3. 发布前整体验收。

## 4. 证据

- PENDING §E-53；代码 `fb71014`；348 tests；stage 8788。
