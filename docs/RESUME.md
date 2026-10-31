# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round31
checkpoint_seq: 60
updated_at: 2026-11-01T00:15:00+08:00
trigger: while 条件逻辑确认 + 每次迭代日志
status: in_progress
```

## 0. 当前状态

- 引擎代码 `a4ebbfd`；workspace **348 passed**。
- 版本 1.2.2，未 tag/release；stage 已部署/重启。

## 1. 逻辑确认（U-52）

```text
while not appear(町中) and not appear(召唤)
= not (appear(町中) or appear(召唤))
```

- 任一出现 → false → 退出；
- 都不出现 → true → 继续。
- 用户预期正确。

如果没退出，说明该次 `appear('町中')` 和 `appear('召唤')` 都返回 false；不是 `not/and` 解析错误。

## 2. 新日志

每次 while 迭代：

```text
step seq=... depth=1 op=while_cond result=ok detail=iteration=N value=Bool(true) truthy=true cond=...
```

- value=true → 继续；
- value=false → 退出；
- 配合 `/lines` 的详细日志和 `__oasLogs` 定位哪个 appear 没命中。

## 3. 下一步

1. 用户重跑「回到庭院」，看 `while_cond` 值；
2. 若 value=true 且屏幕已有町中/召唤，用素材行识别检查 OCR ROI/文本；
3. 若确认业务上“应退出但 OCR 失败”，调整素材 ROI；
4. 发布前验收。

## 4. 证据

- PENDING §E-52；代码 `a4ebbfd`；348 tests；stage 8788。
