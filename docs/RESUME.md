# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round16
checkpoint_seq: 45
updated_at: 2026-10-31T21:00:00+08:00
trigger: 多行 OCR/旋转/单行路径彻查完成；等用户验收
status: in_progress
```

## 0. 当前状态

- 引擎代码 `0f0c293`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage 8788 运行。
- U-32b 批量实帧验收仍待 positions。

## 1. 本轮审计（U-40）

用户问：多行识别为什么旋转，是不是底层还是单行。

**结论：**

- 不是回退到单行 `/ocr`；`庭院` 走的是 **det + 逐行 rec**。
- 多行 OCR 的 rec 原语本来就是 line-level rec；det 确实执行了（1 个 box）。
- 旋转是**逐 box 方向纠正**：正立 rec 得 `"應" 0.217`，旋转后得 `"庭院" 0.9668`。
- 编辑器 `/lines` 早已有该兜底；runtime provider 缺失，所以“测试成功、运行失败”。已补同一套逻辑。

代码锚点：

- `apps/oasd/src/ocr.rs:52` recognize_lines
- `:59` det.detect
- `:66` 逐 box rec
- `:72` 90° 兜底
- `crates/oas-runtime/src/lib.rs:1226` derived OCR
- `:1228` 重新在 source ROI 调 recognize_lines
- `apps/oasd/src/serve.rs:1463/1535` 编辑器 /lines + 旋转

「庭院」资产：`kind=ocr_line, ocr_mode=lines, source=[999,219,111,87], ocr_text=庭院`；运行期确实走 derived det+rec，不是单行。

## 2. 下一步

1. 用户重跑「回到庭院」/「庭院」相关任务确认；
2. 设置 positions 跑批量帧测试，闭合 U-32b；
3. U-20 多选整组拖动；
4. 发布时才 bump/tag/release。

## 3. 证据

- PENDING §E-40；stage `_diag_ocr2`（已删）输出 `庭院` Done；344 tests。
