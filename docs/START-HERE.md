# 新会话入口（START HERE）★ **只要读这一个文件**

> ★★★ **给用户的一句话**（★ 新会话开场直接粘贴）：
>
> ```
> 先 skill session-memory，然后读 docs/START-HERE.md，严格按它执行，最后按它的模板回报。
> ```
>
> ★ **不需要再说别的** —— ★ 本文件把"读什么、做什么、回报什么"全写死了。

---

# §0 ★ 我是谁 / 这是什么项目

```
★ 项目：OAS（OnmyojiAutoScript）阴阳师自动化 + OASX（Flutter 前端）
★ 开发工作区：`D:\OAS-dev\`（`backend\` + `frontend\`，★ 各自是 git 仓库）
★ 实机：      `D:\OAS-live\`（★ dev 的**拷贝**；后端端口 **22287**；开发用 **22288**）
★ ★ **唯一真相 = git**：★★ **开发分支 = 后端 `dev` · 前端 `dev`**（★ 用户 [10-15] 原话：
   "**另一台可以拉dev啊，main是主要的稳定版本！**"）
   ⇒ ★ **`main` = 主要的稳定版本**（★ **冻结点，只在"判定稳定"时才前移**）
   ⇒ ★ ★ **本机本地分支名是 `main`，但推送目标必须是远端 `dev`**：
     ★ **`git push origin main:dev`** —— ★ ⚠ **绝不要 `main:main`**（★ 我 [10-15] 推错一次，已回退）
★ ★★ **不许在 `D:\OAS-live` 上做开发/测试**（★ 用户 [10-14] 原话：
   "**不要在实机跑，现有开发基于 dev 侧，实机是版本稳定后直接从 dev 拷贝过去**"）
   ⇒ ★ 新任务/新代码**一律先在 dev 做完并跑绿**，★ **稳定后**才整份拷到实机
   （★ 反面教材：我 [10-14] 曾把新建的 `FlowDemo` 直接装进实机 —— ★ 已还原，见坑 P14）
★ ★★★ **[10-15] 两台机器（★ 用户打算 · ★ 待裁定）**：★ 用户原话（逐字）——
   "**现在打算使用两台电脑，一台开发、测试稳定后，上传到github，另一台从git上更新，
     用于实机生产。本台电脑为实机生产用，所以需要你上传dev到git，
     确保另一台从git上取下来时可以无缝开发。**"
   ⇒ ★★ **交付通道 = GitHub 的 `dev` 分支**（★ 取代原来的"同一台机器上 robocopy"）：
     ★ 开发机 `git push origin main:dev` ⇒ 另一台 `git clone -b dev` / `git pull origin dev`
     ⇒ ★ 再按 `DEV-WORKFLOW.md §4` 拷到实机
     ⇒ ★★ **`main` 保持"主要的稳定版本"不动**（★ 用户 [10-15] 原话）
   ⇒ ★ [10-15] **曾经的失误（已回退）**：★ 我一度把 `main` 快进到 dev（后端 `2650b6d2` ·
     前端 `3978598`）⇒ ★ 用户纠正后已 **`--force-with-lease` 退回**：
     ★ 后端 `main` = **`e28793ce`**（10-13 15:44）· 前端 `main` = **`af10440`**（10-13 12:25）
     ⇒ ★ **恢复节点 tag 未动**（后端 `recovery-20261013-scheduler-audit` · 前端 `recovery-20261013-isolated-live`）
   ⇒ ★ ⚠ **用户原话里有一处矛盾**（"另一台…**用于实机生产**" vs "**本台电脑为实机生产用**"）
     ⇒ ★ 按"**另一台拉 `dev`**"推断：★ **本台 = 生产 · 另一台 = 开发**（★ 待你确认，见台账 §E-1）
   ⇒ ★ ⚠★ **git 只给到"源码级无缝"** —— ★ `toolkit\`（★ 实测 **17000 文件 / 1167.4 MB**）·
     `config/deploy.yaml` · ★★ **账号配置**（`恋鸟树.json`/`伴生树.json`）· `console.bat`
     **都不在 git** ⇒ ★ 完整清单见 `DEV-WORKFLOW.md §6` 与台账 **§E-1**（★ 7 项）
```

---

# §1 ★★★ 强制步骤（★ 顺序不许变，★ 少一步就算没开始）

## 1.1 加载 skill（★ 上下文压缩后必做）

```
★ 调用 `skill` 工具，name = `session-memory`
★ 理由：它的五条铁律（常驻区块 / 台账 / 逐步法 / 完成定义 / 双向读取）在压缩后会丢
```

## 1.2 读这 5 份文档（★ 按顺序，★ 全部在 `D:\OAS-dev\backend\docs\`）

| 序 | 文件 | 读它为了什么 | ★ 必须读到 |
|---|---|---|---|
| **①** | `SESSION-HANDOFF.md` | ★ **当前在哪、下一步干什么、有哪些坑** | 全文（5 KB）|
| **②** | `PENDING-LEDGER.md` | ★ **未完成台账**（🔄/⬜/⛔）| 全文（24 KB）|
| **③** | `DEV-WORKFLOW.md` | ★ 怎么开发/测试/部署 + **§0 会话协议** | ★ **§0 必读**，其余按需 |
| **④** | `DESIGN-SPEC.md` | ★ **软件应该是怎样的** | ★ **只读本轮相关的 §**（如改调度读 §1，改前端读 §3）|
| **⑤** | 本文件 §3 的**活跃坑** | ★ 不要重复踩 | P1~P7 ＋ **P15**（★ [10-15] 新增 · ★ 详见 `SESSION-HANDOFF.md §3` 的 P1~P15）|

★ **禁止**：★ 凭"我记得规格是…"开工 —— ★ 必须**贴出文档引用（§/行号）+ 代码证据**。

## 1.3 ★★ 用代码核实台账（★ 不许信文档自述）

★ 在 `D:\OAS-dev\backend\` 下跑：

```bat
REM ① 代码是不是台账以为的那一版
git log -1 --format="%h %ci %s"
git status --porcelain

REM ② 台账里"进行中/未开始"的
REM   ⚠ 不要用 findstr 查 emoji（GBK 下匹配不到，会静默输出空）——
REM     用 PowerShell 的 Select-String（本机 pwsh 可用）
powershell -NoProfile -Command "Select-String -Path docs\PENDING-LEDGER.md -Pattern '🔄','⬜','⛔' | Select-Object LineNumber,Line"

REM ③ ★★ 强制跑全部守卫（★ 一条命令，★ 期望 166 passed）
toolkit\python.exe -m pytest tests/test_comment_drift.py tests/test_task_flow_docs.py tests/module/config/test_standby_placeholder.py tests/module/config/test_entry_target_reached.py tests/module/server/test_help_texts_current_ui.py tests/module/server/test_profile_name_from_user.py tests/module/server/test_profile_transfer_keeps_enables.py tests/tasks/Component/SwitchSoul/test_switch_soul_validation.py tests/tasks/test_rest_random_minutes.py tests/module/config/test_loop_rounds.py tests/tasks/test_no_ticket_is_success.py tests/module/flow/test_control_types.py tests/module/config/test_entry_custom_state.py tests/module/test_task_factory.py -q

REM ④ ★ 全量基线（★ [10-14] 实测：49 failed / 1862 passed / 12 skipped）
REM   ★ 那 49 条是【已知环境类】，★ 不是回归：
REM     43 = 测试去读 D:/OAS-dev/OASX-src（本机是 frontend）· 4 = 缺
REM     module/config/i18n/zh-CN.json（前端推来的运行时产物）· 2 = 读用户/实机状态
REM     · 1 = live 配置 · 1 = 顺序 flaky
toolkit\python.exe -m pytest tests/ -q
```

★ 期望：★ **守卫 166 passed**（★ [10-14] 第四轮：135 + 新增 31 条 `tests/module/test_task_factory.py`）；★ 全量 **49 failed / 1862 passed**（★ 失败集与基线**逐条一致** ⇒ 无回归）。

```bat
REM ⑤ ★ 前端（★ 也要核）
cd /d D:\OAS-dev\frontend
D:\flutter3271\bin\flutter.bat analyze lib
D:\flutter3271\bin\flutter.bat test
REM   ★ [10-14] 实测：analyze 0 error（4 warning + 17 info）· test 158 passed
```

## 1.4 ★★★ 先回报，再动手（★ 这一步不许省）

★ **读完、核实完，必须先把 §2 的回报模板发给用户**，
★ 并**等用户确认方向**，★ **然后才允许改代码**。

★ ⚠⚠ **[10-14] 换会话时最要紧的三件事**（★ 新会话请先看这三条）：

> ★ **① 架构早已定案，别再问** —— ★ 用户 [10-14] 裁定 **`M2`**（= `DESIGN-SPEC.md` §1.17 的
>   **A/A+ 受控指令集**，★ **不用 `eval`**）★ ＋ ★ **annotator 允许"深度拆解"进任务实现器**
>   （★ §1.18-八 `AN1`~`AN4`）。★ **P0 已落地**（`module/flow/` + `entry_state`，见 §4.5-㉞）。
>   ⇒ ★ **下一步是 `P1`**（§1.18-六）：★ 补 5 个空缺原语（**返回键/键盘/文本/滚动/拖拽**）
>   ＋ ★ 把 `LoopBudget/StuckGuard/RetryPolicy` 提到 `module/action/`。
>
> ★★ **② "新建任务"已经能跑通了（`N9-11`）** —— ★ `module/task_factory.py`（原子创建 +
>   回滚 + 命名校验 + 自动登记 + 示例识别骨架）★ ＋ `tasks/FlowDemo/`（**已在 dev**）★
>   ＋ 守卫 `tests/module/test_task_factory.py`（31 条，★ 注入验证 3/3 真红）。
>   ★★ **新建任务的"完整合同" = 6 类**（★ 见 §1.16-五 `NT8`；★ 实测一次创建撞红 **14 条**守卫）——
>   ★ 谁要再建任务，**先读 NT8**，★ 别以为"写 4 个文件就完了"。
>
> ★★ **③ 开发只在 dev；实机是"稳定后的拷贝"** —— ★ 用户 [10-14] 原话：
>   "**不要在实机跑，现有开发基于dev侧，实机是版本稳定后直接从dev拷贝过去**"
>   ⇒ ★ 见 §0 与坑 **P14**（★ 我[10-14]曾把 `FlowDemo` 装进实机 ⇒ **已还原**）。
>   ★ **待你裁定的一件事**：★ dev 侧把「流程示例」**真跑一次**怎么做（★ dev 的 `恋鸟树` 与实机
>     **同一个模拟器** `127.0.0.1:16384`）⇒ ★ **A** 先停实机 `:22287` · **B** 给 dev 换设备 ·
>     **C** 等稳定后拷到实机再跑。
>
> ★★ **④ [10-15] 新增：两件"待裁定" + 一件"建议立刻修"** ——
>   ★ ① **两台机器的角色**（★ 用户原话自相矛盾：★ "另一台…用于实机生产" vs "本台电脑为实机生产用"）
>     ⇒ ★ 台账 **§E-1** · `DEV-WORKFLOW.md §0.6`
>   ★ ② **非 git 的运行时怎么传给另一台**（★ `toolkit\` = **17000 文件 / 1167.4 MB** ·
>     `deploy.yaml` · ★★ **账号配置** · `console.bat`）⇒ ★ 台账 **§E-1**（★ 7 项实测清单）
>     —— ★★ **光"上传 dev 到 git"不足以让另一台无缝开发**
>   ★ ③ ★★ **前端 `F9`（★ 建议立刻修）**：★ `queue_panel.dart:1042-1058` 是**多余分支**
>     （★ 与 `:1059` 的 `else if` **条件逐字相同** ⇒ 死代码）⇒ ★ **`[⏸] 暂停调度` 永远不显示** ——
>     ★ 这正是用户 [10-15] 报的"**恢复调度按钮缺少了暂停调度**"（★ 前端台账 `F9`）

---

# §2 ★★ 回报模板（★ 逐项填，★ 不许省略）

```
📖 已看过 design_spec 文档 · §<相关小节> · 规则 <编号> · 修复进度 <§4.5-N>

【1. 我已加载】
   skill `session-memory`：✅/❌
   读过的文档：SESSION-HANDOFF ✅ · PENDING-LEDGER ✅ · DEV-WORKFLOW §0 ✅ · DESIGN-SPEC §__ ✅

【2. 代码与我核实的台账】
   后端 commit = <hash> · 分支 = <branch> · worktree 干净 = 是/否
   前端 commit = <hash> · 分支 = <branch>
   ★ 守卫（§1.3 的第 ③ 条那一条命令）= __ passed（★ [10-14] 基线 = 98）
   ★ 全量 = __ failed / __ passed（★ [10-14] 基线 = 49 / 1785，★ 49 条是已知环境类）
   ★ 前端 = flutter analyze __ error · flutter test __ passed（★ [10-14] 基线 = 0 / 158）

【3. 差异（★ 文档说 A、代码是 B 的地方）】
   | 台账/文档说 | 我看到的 | 差异 |

【4. 下一步（按台账优先级 + 我的判断）】
   1. …   2. …   3. …
   ★ 我建议先做：… 因为 …

【5. 未完成台账】（★ 全表贴出，★ 见 PENDING-LEDGER.md）

【6. 需要你裁定的事】
   …

【7. 本轮"完成定义"（★ 说完成前必须勾完）】
   ☐ …  ☐ …  ☐ …
```

★ **没有这个回报 ⇒ ★ 本轮不算开始**（★ 这是防"压缩后走偏"的第一道闸）。

---

# §3 ★ 活跃的坑（★ 别再踩）

| # | 坑 | 一句话 |
|---|---|---|
| **P1** | ★ **`"播放模式"` 这个标题是用户要求删掉的** | ★ 前端该处**只有下拉**（顺序/循环/乱序）—— ★ **不要"修复"成带标题** |
| **P2** | ★ **前端不能放 `D:\MuMuPlayer\OAS\` 下** | 内核驱动 `PassGuard_x64.sys` 打了保护标记 ⇒ 双击打不开 |
| **P3** | ★ **守卫必须做"注入验证"** | 否则可能是恒真空转（审计已发现过 2 处）|
| **P4** | ★ **`toolkit\` / `config\deploy.yaml` / 账号配置 / `console.bat` 不在 git** | ★ 清理目录前必须先抢救（`DEV-WORKFLOW.md` §1 有清单）|
| **P5** | ★ **删目录前逐个核对完整路径** | 已因"删+建同名前缀混用"误删过 `D:\OASX-Live` |
| **P6** | ★ **删含 `adb.exe` 的目录前先 `adb kill-server`** | 否则删不净 |
| **P7** | ★ **powershell.exe 曾整段不可用（ENOENT）** | 若 `pwsh` 工具报 `spawn … ENOENT`：★ **重启 DSH 会话**（不是重启电脑）|
| **P15** | ★★ **[10-15] 本机 `git` 报 `dubious ownership`**（★ `git log`/`status`/`push` **全被拒**）| ★ 真因：仓库属主 = `Administrators` ≠ 当前用户 ⇒ ★ 修：`git config --global --add safe.directory D:/OAS-dev/backend`（★ 前端同理）；★ ⚠ **沙箱下改不了** `~/.gitconfig` ⇒ ★ **必须先放开沙箱**（★ [10-15] 已修 · 详见 `SESSION-HANDOFF.md §3`）|

---

# §4 ★★ 铁律（★ 来自 `session-memory` skill + 用户明令）

```
★ ① ★ 用户的话 = **规格**，不是建议 ⇒ ★ 不许降级成"打补丁"
★ ② ★ **读写双向**：★ 不只看用户说了什么，★ 还要看我提了什么选项、用户裁的是哪个
★ ③ ★ **禁止**拿"首行预览 / Select -First N 截断"当读过 —— ★ 必须读正文
★ ④ ★ **边读边写**（防上下文压缩丢失）；★ **不攒到最后**
★ ⑤ ★ 动手改代码前 ⇒ ★ 必须先出「**设计 vs 现状**」对照（符合 ✅ / 不符 ❌ + `文件:行号`）
★ ⑥ ★ **逐步法**：★ 一次只改 **1~2 个边界** ⇒ 立刻 `test` ⇒ 再做下一步
★ ⑦ ★ **完成定义**：★ 说"完成"前先列勾选清单；★ **没勾完不许说完成**
★ ⑧ ★ **台账**：★ 每条回复**必须**先更新台账文件、★ 并把全表贴进回复
★ ⑨ ★ **不许阴奉阳违**（★ 用户原话，已写进文档）
★ ⑩ ★ 文档**不是流水账** —— ★ 是围绕设计 / 实现 / 经验教训的**有逻辑的集合体**
```

---

# §5 ★ 每轮结束（★ 三步，★ 强制）

```
★ ① 更新 `docs/PENDING-LEDGER.md`（★ 状态变了就改；★ "已完成"要有可核查证据）
★ ② 更新 `docs/SESSION-HANDOFF.md`（当前状态 / 下一步 / 新增的坑）
★ ③ ★ 有实质进展就 **commit + push**（★ 后端 `main`；★ 前端 `main`）
```

---

# §6 ★ 常用命令速查

```bat
REM ---------- 开发 ----------
cd /d D:\OAS-dev\backend
toolkit\python.exe server.py                    REM ★ 开发后端 :22288
toolkit\python.exe -m pytest tests/ -q          REM ★ 全量测试

cd /d D:\OAS-dev\frontend
D:\flutter3271\bin\flutter.bat build windows --release
build\windows\x64\runner\Release\oasx-live.exe  REM ★ 开发前端

REM ---------- 实机 ----------
D:\OAS-live\backend\console.bat                 REM ★ 实机后端 :22287
D:\OAS-live\frontend\oasx-live.exe              REM ★ 实机前端

REM ---------- 从零恢复一台机器 ----------
REM ★ 见 DEV-WORKFLOW.md §6
```
