# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round27
checkpoint_seq: 56
updated_at: 2026-10-31T23:00:00+08:00
trigger: 同 ROI 手动 vs 素材识别差异已定位并修复（双 ROI + 拆分行合并）
status: in_progress
```

## 0. 当前状态

- 引擎代码 `efe2b1d`；workspace **348 passed**。
- 版本 1.2.2，未 tag/release；stage 已同步。

## 1. 本轮修复（U-48）

用户质疑：同 ROI 手动多行能识别，素材行不能；要求不对症就回退。

事实：
- 手动测试用画布 **行 ROI**（1050,156,101,115）；
- 素材旧逻辑只用 **多行来源 ROI**（1032,145,133,125）；
- 帧 #4：来源 ROI 只出 `唤`；行 ROI 出 `召`+`唤`；手动看到“召唤”，素材只查来源 → 失败；
- 帧 #52：来源 ROI 出 `召喚`（繁体）；U-47 变体匹配能过，但用户当前帧 #4 不适用。
- det 会把竖排两字拆成两行，逐行匹配永远对不上 `召唤`。

修复：
1. 素材测试同时测 source ROI + 行 ROI，显示各自匹配状态；
2. `match_ocr_line` / `matchedOcrLine` 合并拆分 CJK 行（召+唤）再匹配；
3. 运行期 derived OCR 先 source、失败回退行 ROI，并用合并行；
4. 保留简繁/异体单字容忍；
5. 结果标注当前分析帧。

实测帧 #4「召唤」：来源未匹配、行 ROI 匹配，显示 `1. 召唤 (0.969)`；348 tests。

## 2. 仍待

1. U-32b 批量实帧验收；
2. 实时 WS 弱设备观察；
3. 发布前整体验收。

## 3. 下一步

1. 用户重试素材行识别（选中相应帧）；
2. 批量；
3. 发布时才 bump/tag/release。

## 4. 证据

- PENDING §E-48；代码 `efe2b1d`；348 tests；stage UI 验证。
