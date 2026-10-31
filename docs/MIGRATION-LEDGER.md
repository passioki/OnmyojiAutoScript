# OAS TASK MIGRATION LEDGER（远端 → oas-core）

> 来源：`https://github.com/runhey/OnmyojiAutoScript` `dev` @ `8b4dc669b47838f42d283f14aa394844c1963c86`
> 本机只读检出：`D:\OAS-dev\_verify\remote-oas`
> 迁移分支：`oas-core` **dev**（不合并 main；main = 发布恢复节点）

## 1. 总量与结构

| 项 | 值 |
|---|---:|
| 远端 `tasks/` 目录 | 61 |
| 菜单任务 | 53 |
| 辅助目录（Component/General/GameUi/GlobalGame/GotoMain/Restart/Script/Utils） | 8 |
| 任务包（meta/flow/migration/README） | 53 |
| 迁移规格 `migration/specs/*.md` | 53 |
| 状态文件 `migration/status/*.json` | 53 |
| 导入全局素材 | 2825（23 core + 2802 legacy/component） |
| `oasd task lint --tasks-dir tasks --all` | **57 tasks / 0 errors** |
| `cargo test --workspace` | **350 passed / 0 failed** |

> 远端当前是 61 个任务目录、53 个菜单任务，不是本机旧仓的 64；差异（辅助目录/旧版数量）已在本表记录，不冒充 64。

## 2. 状态定义与当前计数

| 状态 | 含义 | 数量 |
|---|---|---:|
| ✅ | 行为等价 + lint + **实机/回放证据** | **1 (Pets)** |
| 🔄 | 已抽象/实现主链，但有明确未覆盖项或未做实机验证 | 43 |
| ⛔ | 当前 DSL/架构无法表达（记录具体原语缺口） | 9 |
| ⬜ | 辅助目录/未开始 | 8 |

> ★ 重要：Pets 已实机 Done（入口→宠物小屋→喂养/已投喂判定→退出重试→庭院）；其余 42 个 🔄 仍无实机等价证据，不冒充完成。

## 3. 本批交付（oas-core dev）

| commit | 内容 |
|---|---|
| `63b95ef` | 远端盘点、旧 assets 导入（res/assets.py/Component）、迁移 README/inventory |
| `bb29e18` | 清理 packaged legacy backup |
| `06b275c` | 53 个任务包 + 53 specs + 53 status（主批） |
| `59219de` | shipped-task lint gate 改用全局素材（测试修正） |
| `61b45e3` | 未验证 ✅ 降级、台账刷新 |
| `83cc114` | 旧 `res/*.png` 实为 JPEG 的图片转真 PNG；否则 runtime 加载失败 |
| `c2c28e1` | 记录 Pets 实机验证失败证据；状态保持 🔄 |
| `afbdeee` | polish2：12 个任务的不可达分支/守卫/无操作退出修复 |
| `a08d9b7` | 主界面旧阈值 0.75；Talisman 奖励红点误匹配临时 disabled |
| `2bae63f` | polish3：12 个任务的死出口/不可达分支/战斗等待/守卫修复 |
| `1016f95` | polish3 后 ledger 刷新 |

## 3.1 实机验证（非全量）

- **Pets ✅**：实机 Done。
- **TalismanPass 🔄**：no-op 路径实机 Done；但 polish 后奖励分支因 `I_RED_POINT_LEVEL` 误匹配已临时 disabled（cond=false），需重采入口；因此整体降回 🔄。
- **DailyTrifles 🔄**：friend_love 回归实机 Done；store_sign no-op 回归 Done；luck_msg 实机 OCR 0.856 低于旧 0.9，已移除 requires 并加 threshold .8，待重测；召唤/买体力未复测。
- **GoryouRealm 🔄**：导航修通；账号卡片显示 40 级/御灵等级门槛，疑似未解锁。
- 其余 41 个任务尚无实机/回放验证。

## 4. 已实现的通用抽象

- 旧 `RuleImage` → 新 `template`：`roi=roiBack` 搜索区，**不写 action_roi**，点击落匹配模板 bbox（旧行为）；
- 旧 `RuleClick` → `region`，精确操作区；
- 旧 `RuleOcr` → `ocr_lines`（无 `ocr_text`）；
- `RuleSwipe` → `_FROM/_TO` 两个 region；
- 旧 `Component/*` → `legacy_Component_<Module>_<const>`；
- 通用战斗样板：`prepare → battle_info → win/false/reward → task page`；
- 旧 Timer/while-true 改为有界 loop + `wait_until(timeout)+retry`；
- 调度窗口/quota 不进 flow（遵循 ENGINE §22.34 三层分离）。

## 5. 架构阻塞（已逐任务记录）

1. 多行 OCR 逐行数值/行框点击（`ocr_nth_number` / OCR 行框点击）；
2. 时长解析 / 流程内时钟 / `set_next_run`；
3. 跨任务调度依赖；
4. 长按原语（`long_press`）；
5. 组队事件机（建房/邀请/接受/等待/退出）；
6. 动态扫描/几何/状态机（Dokan 双馆主、KekkaiUtilize 蹭卡等）；
7. 图像相似/亮度色值判定；
8. 外部题库/字符串处理（Quiz）；
9. ONNX 目标检测/窗口控制（Hyakkiyakou）；
10. ADB 通知/外部 App API（AutoCheckinBigGod/FindJade）。

## 6. 未完成项（下一批）

- 44 个 🔄：补齐各自 `migration.json.gaps` / spec TODO；
- 9 个 ⛔：引擎补原语后再实现，或明确范围外；
- 全部任务：需实机/回放证据才允许改 ✅；
- U-32b 已由用户 30/30 日志关闭（独立复跑未做）。

## 7. 发布节点

- v1.2.3：main `385d611`，tag `v1.2.3`，Release `https://github.com/passioki/oas-core/releases/tag/v1.2.3`，zip SHA256 `F135922D…C12E`；350 tests。
- 迁移只在 `oas-core dev`；main 保持发布快照。
