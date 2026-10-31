# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-adb-assets
checkpoint_seq: 30
updated_at: 2026-10-31T13:48:00+08:00
trigger: ADB 多实例/测试运行/删除保护/素材集合 完成；等待用户验收
status: done
```

## 0. 当前状态

- R1~R21 ✅；v1.2.3 验收 U-01~U-10 全部完成/裁定。
- 代码 `4480d05`；workspace **336 tests passed**。
- **未 tag/release**；版本仍 1.2.2。
- stage `dist\stage` 的 UI + 带 OCR 的 exe 已同步测试构建；阶段服务器测试端口 8798。

## 1. 本轮完成

### ADB/多实例（U-05）
- `Device` 保留 `aliases`（同物理设备的 `127.0.0.1:port` + `emulator-xxxx`）。
- `Adb::resolve_device`：配置 serial 匹配任意 alias；TCP endpoint 缺失时自动 `adb connect` 后重试。
- `main/run/serve` 统一使用 resolve_device。
- `config.adb_path` 相对路径按包根/config 目录解析（stage `config/live.json` + `adb/adb.exe`）。
- 新增 `GET /instance/devices`；实例页下拉显示 label + serial pair，自动匹配配置。
- 实机验证：断开 127.0.0.1:16384 后 probe 自动连接成功；输出 aliases 两个。

### 运行入口（U-06）
- 删除 `⑥ 测试运行` 死按钮与 handler；单一 `运行任务`；dry-run 勾选时文案变“测试运行（dry-run，不点击设备）”。

### 删除保护（U-07）
- 素材/集合被 flow 引用时 400 阻止，返回引用任务/集合列表；UI alert + 结果区 + 日志明确提示。
- 集合成员：被引用集合至少保留 1 个成员；未被引用可删到 0 并自动移除集合。

### 素材集合（U-08）
- `AssetsFile.collections: Vec<AssetCollection>`；`kind=template_set`，成员为 template asset ids。
- flow **只引用集合 id**；oas-task `load_flow` 将 `click`/`click_target` 展开为成员；runtime `AssetSet` 也支持集合（最佳成员匹配，使用命中成员 action_roi）。
- UI：素材行勾选模板 →「新建集合」；集合行「测集合/删」；builder 素材下拉包含集合。
- 删除规则、成员保留规则、重复成员 id 拒绝、集合被引用阻止；测试覆盖。
- 未自动合并相似图片：集合负责多图检索；重复图片由用户决定（U-10 设计选择）。

### 操作区域归素材（U-09）
- 决策改为 asset-owned：`roi`=识别区域，`action_roi`=操作区域；flow 只保存 sel；集合命中成员 action_roi 生效。
- 旧 R3 的 click/drag offset 规则保留；文档 B7 记录改判。

## 2. 发布规则

- 不自行 tag/release；只在用户明确说“发布”时发布；
- 平时只构建 release 测试；版本保持 1.2.2。

## 3. 下一步

- 等用户验收；若要发布，再 bump 版本/tag/release。
- 已知边界：`appear('集合')` 条件表达式尚未做 OR 展开；集合目前主要覆盖 click/click_target。
