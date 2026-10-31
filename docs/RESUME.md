# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round34
checkpoint_seq: 63
updated_at: 2026-11-01T00:55:00+08:00
trigger: ScreenCache 截图抽象完成
status: in_progress
```

## 0. 当前状态

- 引擎代码 `e3721e6`；workspace **349 passed**。
- 版本 1.2.2，未 tag/release；需重新构建 stage（本轮代码尚未部署）。

## 1. 本轮完成（U-55）

用户要求把“读取帧”统一抽象，而不是每步单独改。

新增 `ScreenCache`：

```rust
pub struct ScreenCache {
    frame: Option<Frame>,
    matcher: Option<Matcher>,
    size: Option<(u32,u32)>,
    seq: u64,
}
```

Interpreter 只保留三个入口：

```rust
observe_screen()   // ensure：一次判断内共享同一帧
reobserve_screen() // refresh：条件/点击/OCR 开始新判断
invalidate_frame() // 输入动作后丢弃
```

- Interpreter 不再直接持有 frame/matcher/frame_size/frame_seq；
- 所有 selector/OCR/点击/拖拽/条件都通过缓存；
- 新增生命周期测试；
- 349 tests。

## 2. 设计要点

- 一次条件内的多个 `appear()` 共用同一帧（ensure）；
- 不同逻辑判断之间必须新帧（refresh）；
- 输入动作后只 invalidate，下一次读取时懒惰抓取；
- `frame_seq` 作为“是否抓了新帧”的可核查证据。

## 3. 下一步

1. 重新构建/部署 stage；
2. 跑「回到庭院」确认；
3. U-32b 批量实帧验收；
4. 发布前整体验收。

## 4. 证据

- PENDING §E-55；代码 `e3721e6`；349 tests；stage 待重建。
