# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round29
checkpoint_seq: 58
updated_at: 2026-10-31T23:30:00+08:00
trigger: 详细日志标准已落地
status: in_progress
```

## 0. 当前状态

- 引擎代码 `bdfe3c3`；workspace **348 passed**。
- 版本 1.2.2，未 tag/release；stage 已部署/重启。

## 1. 本轮完成（U-50）

用户要求：简繁容忍不回退，但所有日志详细化。

前端 `log`：

```text
[HH:MM:SS.mmm] [LEVEL] message | {json}
```

- 支持 level + 结构化 detail；
- `window.__oasLogs` 保留 2000 条。

OCR 测试详细记录：

- asset/kind/mode/task；
- 当前帧 #id/name 或 live；
- roi/action_roi/expected；
- `/lines` 原始 lines(text/score/box)、count/elapsed；
- 匹配模式 exact/normalized/fuzzy、distance、score；
- 全屏回退 reason/full_roi/count/lines；
- 失败/异常 ERROR。

服务端 `logs/editor.log`：

- `/lines` OK/FAIL：roi/task/id/vertical/count/elapsed/lines；
- `/ocr` OK/FAIL：roi/task/id/text/score/elapsed/polygon；
- asset_match：score/threshold/point/pass/elapsed；
- collection_match：member/score/threshold/pass；
- 失败同样带 ROI/task/id/error。

## 2. 实测

前端：

```text
[23:19:06.671] [INFO] OCR 测试匹配 asset=召唤 | {"expected":"召唤","actual":"召喚","mode":"fuzzy","distance":1,...}
```

服务端：

```text
[1793459946668] lines OK roi=Rect { x: 1032, y: 145, w: 133, h: 125 } task=回到庭院 id=召唤 vertical=false count=2 elapsed_ms=205.4 lines=["召喚"(0.826), "UP"(0.999)]
```

348 tests。

## 3. 仍待

1. U-32b 批量实帧验收；
2. 实时 WS 弱设备观察；
3. 其他日志按同一标准逐步覆盖。

## 4. 证据

- PENDING §E-50；代码 `bdfe3c3`；348 tests；stage 8788。
