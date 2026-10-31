# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round7
checkpoint_seq: 36
updated_at: 2026-10-31T18:36:00+08:00
trigger: U-30~U-32 第六轮实现；等用户验收
status: in_progress
```

## 0. 当前状态

- 引擎代码 `af66179`；workspace **344 passed / 0 failed**。
- 版本 **1.2.2**，未 tag/release；stage UI + OCR exe 已同步并重启 8788。
- 未恢复用户删除的任务/素材。

## 1. 本轮完成

| ID | 结果 |
|---|---|
| U-30a | 任务面板新增当前任务引用素材；修复 `loadTaskFlow` 依赖已删除 `flowJson` 导致引用永远为空；用 raw flow 扫描引用 |
| U-30b | 素材行首列缩略图（模板图 / 帧+ROI canvas 裁剪等比例）；新增 `/task/asset/image`、`/frames/image` |
| U-31a | `appear()` 覆盖所有素材（OCR 资产文本/行非空；derived 不匹配=false）；新增 `text_visible()` 全屏 det+rec；条件预设改为素材出现/未出现（所有素材）+ 文字出现/未出现（全屏，不绑素材） |
| U-31b | 条件素材输入改自定义子串过滤下拉（候选含 kind） |
| U-32a | `AssetDecl.positions: Vec<u64>`；保存必选位置帧；素材行「帧」可改多帧；帧被位置引用时删帧 400；集合保存后自动把任务 flow 成员引用改写为集合 id；集合不加位置 |
| U-32b | 🔄 部分：`POST /task/assets/batch_test` + UI「批量帧测试」；template/region/OCR 单行已实现；derived OCR det-lines 待补；stage 素材尚未设置 positions |

## 2. 关键语义（用户 10-31）

- “出现素材” = **所有素材 kind** 都支持；OCR 资产按文字是否可读判断。
- 文字等于/不等于 = **全屏多行识别搜索文字**，与资产无关；多个文字用 `or`。
- 集合不添加位置；加入集合会改写**所有引用该素材的任务 flow** 到集合 id。
- 添加素材必须带位置帧（可多选）；删帧前必须先删除/修改引用该位置的素材。
- while 只 cond（0=false/非 0=true，无 max_iters）；loop `<=0` 不循环、`>0` 次数。

## 3. 下一步

1. 补 U-32b 的 derived OCR（det+rec）批量分支；
2. 给 stage 素材补 positions 后实测批量帧测试；
3. 用实机验证「回到庭院」（`not appear('町中')` 现在可运行；dry-run 不点击会跑到预算耗尽，属预期）；
4. U-20 根级拖拽/多选整组拖动仍待补。

## 4. 证据

- PENDING §E-32；ENGINE §22.39.4。
- CDP stage：任务面板 3 个引用素材；23 个缩略图；14 个位置帧选项。
- dry-run release：`appear('町中')` 不再报 selector 未声明；实际进入 while/if/click（dry-run 不点击）。
- 测试 344 passed。
