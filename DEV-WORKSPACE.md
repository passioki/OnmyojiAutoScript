# 开发副本说明（`D:\OAS-dev\OnmyojiAutoScript-dev`）

> ★ 本文件**只属于开发副本**，不在实机仓库里。
> 目的：让新会话/新开发者一眼看懂"这个目录是什么、能不能动实机"。

---

## 一、这个目录是什么

| 项 | 值 |
|---|---|
| **用途** | ★ **调度架构（P-4）等开发工作** |
| **来源** | 从 `D:\OAS-dev\OnmyojiAutoScript` **拷贝**（2026-10-11，拷时 HEAD `48b2f7b5`）|
| **端口** | ★ **22289**（实机是 22288）—— `config/deploy.yaml` 的 `WebuiPort` |
| **`.git`** | ★ **没有**（拷贝时排除）—— 这里**不是** git 仓库，**不要**指望 `git commit` |
| **Python** | ★ **自己的** `toolkit\python.exe`（Python 3.10.11，`sys.prefix` 指向本目录）|
| **体积** | 约 1183 MB / 18295 文件（`log` 与 `.git` 已排除）|

## 二、★ 实机是哪个（**别动错**）

| 角色 | 路径 | 端口 | 说明 |
|---|---|---|---|
| ★ **实机（用户在跑）** | `D:\OAS-dev\OnmyojiAutoScript` | **22288** | ★ **只读参考，不要在里面开发** |
| ★ **开发副本（这里）** | `D:\OAS-dev\OnmyojiAutoScript-dev` | **22289** | 开发改这里 |
| 前端权威源码 | `D:\OASX-clean` | — | 可推送（分支 `oas-tasks-ui-s7`）|
| 前端运行产物 | `D:\OASX-app` | — | 实机跑的就是它 |

★ 启动器 `D:\OASX-app\启动OASX(含后端).cmd` 里写死
`ROOT=D:\OAS-dev\OnmyojiAutoScript` 并 `netstat` 查 `:22288`
—— 所以**它只会拉起实机后端，不会碰本副本**。

## 三、在本副本里怎么起后端

```powershell
cd /d D:\OAS-dev\OnmyojiAutoScript-dev
toolkit\python.exe server.py
# 或显式指定端口（覆盖 deploy.yaml）：
toolkit\python.exe server.py --port 22289
```

★ 起之前**确认实机后端在不在**（`netstat -ano | findstr :22288`）——
  两个后端**各读各的 `config/`**（本副本是拷贝时的快照），
  但同时跑会各自写自己的状态文件，**不会互相破坏**。

## 四、★★ 测试基线（本副本的，**与实机差别很大**）★★

`
★ 副本: 1699 passed / 39 failed / 10 skipped
★ 实机: 1745 passed /  5 failed /  4 skipped
`

### ★★ 那 39 个里，**32 个是副本没有前端仓库造成的**（不是回归）

本副本是 **OAS 后端仓库**的拷贝 —— 它**没有前端源码**（lib/*.dart）。
这些测试**去读前端文件**，所以在副本里**必然失败**：

| 测试文件 | 个数 | 为什么失败 |
|---|---|---|
| 	est_window_editor_frontend.py | 13 | 读 lib/views/args/window_editor.dart 等 |
| 	est_queue_clear_and_settings.py::TestFrontendWiring | 5 | 读 lib/api/api_client.dart 等 |
| 	est_queue_entry_identity.py::TestFrontendCarriesEntryId | 4 | 读 lib/controller/.../task_list_controller.dart |
| 	est_queue_membership_and_category.py::TestFrontendCategoryVisuals | 4 | 读 lib/views/tasks/queue_panel.dart |
| 	est_category_label_consistency.py::TestFrontendUsesOneSourceOnly | 3 | 同上 |
| 	est_i18n_full_coverage.py | 2 | 读前端 i18n |
| **小计** | **31–32** | ★ **副本结构决定，与代码改动无关** |

### ★ 另外 7 个是环境/快照相关（实机也有类似的 5 个）

| 失败 | 为什么 |
|---|---|
| 	est_entry_id.py::test_pending_items_carry_entry_id | pending 项没有 entry_id |
| 	est_queue_clear_and_settings.py::test_disables_auto_queue_tasks | 没有 uto_queue 任务可停用 |
| 	est_task_catalog.py::test_interval_from_user_config | GoldYoukai.success_interval 为 None |
| 	est_task_report.py::test_task_row_keys / 	est_names_are_chinese | 没有运行记录（	asks 为空） |
| 	est_schema_router.py::test_at_least_one_task_outside_window | 没有任务在窗口外 |
| 	est_schema_router.py::TestOverviewSchedulingFields::test_effective_target_matches_count_when_no_override | RealmRaid: effective=50 count=30 |

### ★★ 开发时的规矩（修订版）

> **跑全部测试没有意义**（副本注定 39 个失败）。
> 只跑**你改的东西相关的那几个文件**，并对照**上面两张表**判断失败是不是已知的。

★ 判断是不是自己改坏的最可靠的办法（本会话用过多次）:
  **把改动暂存/还原，跑同一个测试，看结果是否相同**。

### ★ 想跑前端接线测试怎么办

把前端仓库放回**预期位置**（测试按固定路径找 lib/）。★ 具体路径见
那些测试文件里的 REPO/lib 解析（	ests/module/config/test_window_editor_frontend.py 开头）。
⚠ 本副本**没有** .git，所以无法靠 git 恢复；改动前请手动备份。

## 五、已知的坑（拷贝带来的）

| # | 坑 | 说明 |
|---|---|---|
| 1 | ★ **`config/` 是快照** | 实机后来改的配置、跑出来的状态，**本副本看不到**。需要同步就手动拷 `config/*.json` |
| 2 | ★ **任务状态文件可能不同** | `task_state.py` 的状态文件路径可能落在别处（见 `task_state._DEFAULT_STATE_FILE`）—— 两个环境各写各的 |
| 3 | ★ **ADB / 模拟器** | 本副本若真去跑任务，会和实机**抢同一个模拟器**。★ 开发时**不要**让它真跑任务 |
| 4 | ★ **没有 `.git`** | 改坏了没法 `git checkout` 还原。★ 重要改动前**手动备份**要改的文件 |

## 六、★★★ 探针/验证脚本的**铁律**（我违反过两次，代价很高）★★★

### 症状

★ 跑完自己的验证脚本后，**共享配置被改坏**：
```
★ config/恋鸟树.json 的 run_list 被我探针覆盖
  -> 它原本 ['RealmRaid','Rest','Rest']，变成 ['Orochi','Rest']
★ 于是【读共享配置的测试】开始失败：
  test_waiting_reason.py::test_reason_is_empty_for_open_full_day_tasks
  （RealmRaid 不在执行队列 -> reason='不在执行队列'）
★ 全量从 1700/38 退化到 1698/39，看起来像"我改坏了代码"，其实是**污染**
```

### ★ 为什么会发生

1. `mm.config_cache(name)` / `Config(name)` 会**加载并可能写回**配置；
2. 有些迁移/排期逻辑**在加载时就重写** `next_run`（实测：`Config()` 一加载，
   `next_run` 就从 `23:59:59` 变成现在）⇒ ★ **算"只读"也会改文件**；
3. 我为了造场景，对**临时配置名**写 `P.write_text(...)`，
   但**清理不够可靠**（有一次留下 `config/__dbg3__.json`）。

### ★★ 铁律

| # | 规矩 |
|---|---|
| 1 | ★ 造场景**只用临时配置名**（`__xxx__`），**绝不碰** `恋鸟树/伴生树/不存在的配置/template` |
| 2 | ★ **写完必须验证清理** —— 跑完立刻 `Get-ChildItem config -Filter '__*'`，**有残留就删** |
| 3 | ★ 验证脚本会**改共享配置**时，**先备份**到 `_dev_backup\` |
| 4 | ★ 跑全量测试**前后**都对比失败清单 —— 若出现**新**失败，**先怀疑污染**，再怀疑代码 |
| 5 | ★ 万一污染了：从 **`D:\OAS-dev\OnmyojiAutoScript\config\`**（实机仓库）恢复 |
| 6 | ★ 判断"是不是污染"的最快办法：**单独跑那个测试文件**（不与其他测试共享状态）|

### ★ 一次实际恢复（可作为模板）

```powershell
# 备份 -> 从实机恢复 -> 清临时 -> 复测
Copy-Item "$DEV\config\恋鸟树.json" "$DEV\_dev_backup\cfg_恋鸟树.json.bak" -Force
[IO.File]::WriteAllBytes("$DEV\config\恋鸟树.json",
                         [IO.File]::ReadAllBytes("$REL\config\恋鸟树.json"))
Remove-Item "$DEV\config\__*.json" -Force -ErrorAction SilentlyContinue
```
---

## ★★★★★ 铁律：**不许阴奉阳违**（用户 2026-10-12 亲令）★★★★★

> "**不许阴奉阳违！把这条写到文档里！！我前边几百轮的设计对话白说了！**"

★ **用户的设计就是规格（spec），不是"建议"。**

* ★ **禁止**把用户的设计降级成"在他现有代码上打补丁"。
* ★ **禁止**改完就说"已修好"，而实际**架构仍与设计不符**。
* ★ **动手前必须先出"设计要求 vs 当前代码"的逐条对照表**
  （符合 ✅ / 不符 ❌ + `文件:行号`），**不符项先报告、等方向**。
* ★ **报进度必须报"架构对齐度"**，不能只报"测试通过"。
* ★ 用户已裁定的事项**直接照做**；有障碍就**报告障碍**，不许自行换方案。

★ 完整设计要求与对齐表见 `DEV-SCHEDULER-UNIFY-PLAN.md` **最前面那一节**。
