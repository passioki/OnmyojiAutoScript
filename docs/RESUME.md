# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round28
checkpoint_seq: 57
updated_at: 2026-10-31T23:10:00+08:00
trigger: OCR 单识别 ROI 已统一；双 ROI/行合并已移除
status: in_progress
```

## 0. 当前状态

- 引擎代码 `8cab6ab`；workspace **348 passed**。
- 版本 1.2.2，未 tag/release；stage 已部署/重启。

## 1. 本轮完成（U-49）

用户指出双 ROI/手动合并是补丁，要求舍弃统一。

统一后的模型：

- **一个识别 ROI**：`roi`；
- **一个点击 ROI**：`action_roi`，不参与识别；
- 不再保留 `ocr_source_roi` 作为第二识别区域。

实现：

1. 旧资产加载时迁移：
   - `ocr_source_roi` → `roi`；
   - 清除 source；下一次保存写回统一形状。
2. 新保存：
   - 多行来源素材 `roi` = 用户实际测试/调大的多行 ROI；
   - action_roi = 行点击框；
   - 不写 `ocr_source_roi`。
3. 运行期：
   - derived OCR 只对 `roi` det+rec + 匹配 `ocr_text`；
   - 删除 source/行 ROI fallback 和 CJK 行合并。
4. 编辑器测试/批量测试：
   - 只使用 `roi`；
   - 无双 ROI。

## 2. 验证

- 旧资产 `/task/assets` 的 `召唤`：`roi=[1032,145,133,125]`，无 `ocr_source_roi`；
- 帧 #52 测试：2 行，`召喚(0.826)`/`UP(0.999)`，期望 `召唤` → 匹配；
- 迁移测试覆盖 source→roi 和 runtime derived；
- 348 tests。

## 3. 注意

- 统一后若某素材 ROI 不够大，只能**重新调大 ROI 并重存**；不再靠换 source/拼行兜底。
- 旧资产迁移在加载时完成，磁盘在下次保存时更新。

## 4. 仍待

1. U-32b 批量实帧验收；
2. 实时 WS 弱设备观察；
3. 发布前整体验收。

## 5. 证据

- PENDING §E-49；代码 `8cab6ab`；348 tests；stage 8788。
