# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round11
checkpoint_seq: 40
updated_at: 2026-10-31T19:15:00+08:00
trigger: 修复 workbench run 未传 OCR models；等用户复测
status: in_progress
```

## 0. 当前状态

- 引擎代码 `3f341a4`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage exe/UI 已同步并重启 8788。
- U-32b 批量实帧验收仍未闭合（需 positions + 匹配帧）。

## 1. 本轮关键修复（U-35）

用户日志：

```text
OCR is not available for appear(町中): no OCR provider attached
```

根因：

- `/state` 显示 `ocr:true det:true`；
- 但 workbench `POST /task/run` 构造 `RunOptions` 时没有传 `opts.model`/`opts.det_model`；
- 编辑器 OCR 引擎与 run executor 是两套加载，run 侧 provider=None。

修复：

- `Server` 保存 `--model`/`--det-model` 路径；
- `/task/run` 设置 `opts.model`/`opts.det_model`；
- 临时 serve 验证日志：`ocr=on model=... det=...`，`appear('町中')` 正常求值。

## 2. 用户确认的逻辑

`not(A and B)` = 排除 A、B 同时存在；A only / B only / neither 均满足；等价 De Morgan。

## 3. 下一步

1. 重启 stage 8788 后重跑「回到庭院」；若仍报 no OCR provider，检查启动参数/构建。
2. 给 stage 素材设置 positions，跑批量帧测试闭合 U-32b。
3. U-20 多选整组拖动仍待补。
4. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-35；ENGINE §22.39.4。
- `3f341a4` diff；临时 serve `/task/run` 日志 `ocr=on`。
- tests 344 passed。
