# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-builder-v12
checkpoint_seq: 11
updated_at: 2026-10-30T23:05:00+08:00
trigger: phase-gate
status: in_progress        # in_progress | blocked | done
```

## 0. 目标（一句话）

v1.2：统一「识别区域 + 操作区域」对象模型（含纯操作区域 region）、全局唯一命名、识别结果多选批量保存、操作区域可调；新增任务构建大页面（动作库+值+实时流程图）；补齐变量动作；测试/实机/发布 v1.2。

## 1. 验收清单

- [x] **A 统一对象模型**：`action_roi` 取代旧 `roi_back`（serde alias 兼容）；`kind=region`；批量保存 `/task/save_assets`；全局唯一（单存/批量/改名）+ `/assets/conflicts`；识别多选候选（名称/勾选/操作区域调整）— 引擎 `1e119c3`
- [x] **B 任务构建页**：新顶部「任务构建」（builder.js）；动作库/嵌套步骤树/动作值 inspector（素材/区域/数字/表达式/高级 JSON）/实时流程图/保存/dry-run；任务库「构建」入口
- [x] **C 变量动作**：`set_var`/`inc_var`/`ocr_to_var` + `var('name')` 表达式；builder/flow_model 支持
- [ ] **D 回归/发布**：全量测试、实机/浏览器回归、README/docs、v1.2.0 zip + GitHub release

## 2. 当前进度

- 引擎 main = `1e119c3`（已 push）；v1.1 release `f2c096c` 不变
- 测试：最近一轮全量绿：flow 46 / runtime 89 / task 43 / oasd 113（待最终汇总）
- 浏览器回归（CDP + headless Edge）已验证：
  - 整屏 OCR → 25 个候选；名称/勾选/操作区域绘制；批量保存 25 个到 t1（`V12UI0..`）
  - 操作区域 canvas 绘制更新候选 `action={5,5,194,94}`
  - 任务构建页加载 t1、动作库 20 项、嵌套步骤/实时图；新增 set_var/inc_var 并保存 flow.json
  - 页面无 JS 错误
- **下一步 D**：
  1. 补单测/回归：变量 flow dry-run、batch rollback、region/action_roi 点击；全量 cargo test
  2. 实机安全回归（dry-run + release 包冒烟）；截图证据
  3. 版本 1.2.0、README/docs、package、tag `v1.2.0`、GitHub release

## 3. 已实现模型/事实（v1.2）

- `AssetDecl`：`id/kind`（template|ocr_line|ocr_lines|region）+ `roi`（识别区域）+ `action_roi`（操作区域，旧 `roi_back` alias）+ file/threshold/polygon/rev
- `kind=region`：`roi` 即操作区域；无识别、无 file/threshold；runtime `AssetSet::insert_region`
- OCR 资产点击用 `action_roi`（缺省=识别 ROI）；模板点击操作区域继续按匹配位置平移
- `Locator::RegionRef{sel}`：流程引用保存的纯操作区域
- 批量保存：`POST /task/save_assets {task,assets:[...]}`，任务内全有或全无；全局唯一扫描所有 tasks + library；UI 多选候选
- 全局冲突扫描：`GET /assets/conflicts`
- 变量：`set_var/inc_var/ocr_to_var` + `var('name')`；变量单次运行内有效，不写 checkpoint
- 任务构建页文件：`apps/oasd/ui/builder.js`（新增）；静态路由 `/builder.js`

## 4. 在途/未提交

| 文件 | 内容 | 状态 |
|---|---|---|
| oas-core | `1e119c3` 已提交/推送（A/B/C） | committed |
| backend/docs | 本卡/索引待提交 | 待提交 |

## 5. 已知限制/待做

- 图片识别目前是单次“测试匹配”；多图/多次匹配结果的多选保存尚未做（OCR 行多选已做）
- 操作区域跟随：模板跟随匹配框；OCR 资产目前按保存的绝对坐标（ROI 固定）
- builder 第一版：高级动作（click_target/drag）用 args JSON；流程图只读查看
- 变量不持久化，checkpoint 不保存变量
- release 未签名；v1.1 的 until_* 完成条件仍由 flow 判断

## 6. 阻塞 / 待用户裁定

- 无（继续 D）

## 7. 证据索引

| 证据 | 路径 |
|---|---|
| v1.2 浏览器候选/批量保存 | CDP 实测（t1，25 候选，V12UI0..）|
| builder 截图 | `_verify/n43/v12_builder.png` |
| A/B/C 提交 | `1e119c3` |
| v1.1 发布 | `_verify/n43/REPORT-V1.1.md`；release v1.1.0 |

## 8. 坑

- `loop` body 是顶层字段；`n` 是表达式字符串；builder 新增动作会自动插到末尾 finish 之前
- `action_roi` 与旧 `roi_back` 兼容；不要在 assets.json 里再写 roi_back（新保存统一 action_roi）
- 全局唯一范围 = 所有任务 assets + 全局 library；旧数据冲突用 `/assets/conflicts` 查，不自动改名
- 批量保存 rollback 会恢复 assets.json 并清理本轮新建图片
- UI 无 node：headless Edge + CDP Runtime.evaluate 可做点击/画布自动化；页面错误看 `window.__oasErrors`
