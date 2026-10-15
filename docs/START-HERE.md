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
★ ★★★ **[10-15] 本机 = 开发机**（★ 用户 [10-15] 原话："**本机是开发机**"）
★ 开发工作区：`D:\OAS-dev\`（`backend\` + `frontend\`，★ 各自是 git 仓库）
   ★ ★ **[10-15] 本机是新引导的开发机**：两仓都是 `git clone -b dev` 拉下来的
     ⇒ ★ **本地分支 = `dev`**（跟踪 `origin/dev`）· ★ 不是旧机的 `main`
   ★ ★ ✅ **[10-15] 路径与旧开发机【同名】**：★ 本机工作区也是 `D:\OAS-dev\`（★ 用户 [10-15] 提议
     "把开发路径移到 D 盘" ⇒ ★ 已整份搬到 D 盘）⇒ ★ 历史文档/历史证据里的 `D:\OAS-dev`
     **可以直接照做**（★ 差异只有"机器不同"：★ `D:\OAS-live` 在**另一台电脑**上）
★ 实机：      `D:\OAS-live\`（★ **在另一台电脑上**；★ dev 的**拷贝**；后端端口 **22287**；开发用 **22288**）
   ★ ⚠ 本机（开发机）**没有** `D:\OAS-live` ⇒ ★ **实机验收不在本机做**
★ ★ **唯一真相 = git**：★★ **开发分支 = 后端 `dev` · 前端 `dev`**（★ 用户 [10-15] 原话：
   "**另一台可以拉dev啊，main是主要的稳定版本！**"）
   ⇒ ★ **`main` = 主要的稳定版本**（★ **冻结点，只在"判定稳定"时才前移**）
   ⇒ ★ ★ **[10-15] 本机的本地分支名 = `dev`**（clone 时就是）⇒ ★ **推送一律 `git push origin dev`**
   ⇒ ★ ⚠ **历史教训（旧开发机）**：★ 旧机本地分支叫 `main`，那时必须 `git push origin main:dev`；
     ★ 我 [10-15] 曾误推 `main:main`（已 `--force-with-lease` 回退）⇒ ★ **本机不再有这个坑**，
     但**任何机器上都绝不许把本地 `main` 推到远端 `main`**（`main` 只在"判定稳定"时前移）
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
   ⇒ ✅ ★ **[10-15] 角色已由用户裁定 —— 本机 = 开发机**（★ 用户原话："**本机是开发机**"）
     ⇒ ★ **本机 = 开发 / 测试（`D:\OAS-dev`）· 另一台 = 实机生产（`D:\OAS-live`）**
     ⇒ ★ 此前"谁是谁"的口径矛盾**已消解**（旧推断"本台=生产"**作废**）· 见台账 **§E-1** / `DEV-WORKFLOW.md §0.6`
   ⇒ ★ ⚠★ **git 只给到"源码级无缝"** —— ★ `toolkit\`（★ 实测 **17000 文件 / 1167.4 MB**）·
     `config/deploy.yaml` · ★★ **账号配置**（`恋鸟树.json`/`伴生树.json`）· `console.bat`
     **都不在 git** ⇒ ★ 完整清单见 `DEV-WORKFLOW.md §6` 与台账 **§E-1**（★ 7 项）
   ⇒ ✅ ★★ **[10-15] 本机已按这条清单补完**（★ 来源 = `C:\Users\passioki\Downloads`）：
     `toolkit\`（★ 实测 **17000 文件 / 1167.4 MB**，与台账数字**一致**）· `deploy.yaml`（**6114 B** ·
     `WebuiPort: 22288`）· `伴生树.json`（68437 B）· `恋鸟树.json`（85570 B）· `console.bat`（590 B）
     ⇒ ★★ **四条基线已在本机跑绿**（★ 守卫 166 · 全量 15/1903/7 · 前端 0 error + 158 passed）—— 见 §1.3
   ⇒ ⚠ ★ **[10-15] 本机缺 C++ 工具链**（无 Visual Studio / Windows SDK）⇒ ★ `flutter build windows --release`
     **暂时不可用** ⇒ ★ 见坑 **P17**（★ 待用户裁定是否装 VS Build Tools）
```

---

# §1 ★★★ 强制步骤（★ 顺序不许变，★ 少一步就算没开始）

## 1.1 加载 skill（★ 上下文压缩后必做）

```
★ 调用 `skill` 工具，name = `session-memory`
★ 理由：它的五条铁律（常驻区块 / 台账 / 逐步法 / 完成定义 / 双向读取）在压缩后会丢
★ ⚠ ★★ **[10-15] 若技能目录里没有 `session-memory`**（★ 它是**用户级技能**，不在项目仓库里）：
  ⇒ ★ **装它**（★ 一次性，之后 `git pull` 即同步；★ **不需要重启 DSH**，会热加载）：
     ```
     ① 克隆技能仓库（★ 路径随你）：git clone https://github.com/passioki/dsh-skills.git <位置>\dsh-skills
     ② 确认 DSH 配置根：echo $env:DSH_HOME        （★ 本机 = C:\Users\passioki\.dsh）
     ③ 一键安装（★ 建 Junction，**不需要管理员**）：cd <位置>\dsh-skills  ⇒  .\install.bat
     ④ 自检：python verify.py                     （★ 期望 ALL CHECKS PASSED）
     ```
     ★ 装完技能扫描目录里会出现：`%DSH_HOME%\skills\session-memory\SKILL.md`
     ★ ⚠ 别把它拷进 `backend\` / `frontend\`（★ DSH **不扫描**项目目录）。
  ⇒ ★ **实在装不上时才跳过**（★ 不要卡住）：直接读本文件 + `SESSION-HANDOFF.md` + `docs/LAYOUT.md`，
    这三份已把要读什么/做什么/回报什么写死在磁盘上。
★ ⚠ **[10-15] 新会话请把工作目录设成 `D:\OAS-dev`**（★ 项目在 D 盘；★ 上轮会话的 workspace
  `E:\OAS-dev` 已清空）—— ★ 否则各工具的**相对路径**会落到空目录上。
```

## 1.2 读这 5 份文档（★ 按顺序，★ 全部在 `D:\OAS-dev\backend\docs\`）

| 序 | 文件 | 读它为了什么 | ★ 必须读到 |
|---|---|---|---|
| **①** | `SESSION-HANDOFF.md` | ★ **当前在哪、下一步干什么、有哪些坑** | 全文（5 KB）|
| **②** | `PENDING-LEDGER.md` | ★ **未完成台账**（🔄/⬜/⛔）| 全文（24 KB）|
| **③** | `DEV-WORKFLOW.md` | ★ 怎么开发/测试/部署 + **§0 会话协议** | ★ **§0 必读**，其余按需 |
| **④** | `DESIGN-SPEC.md` | ★ **软件应该是怎样的** | ★ **只读本轮相关的 §**（如改调度读 §1，改前端读 §3）|
| **⑤** | ★ **[10-15] `LAYOUT.md`** | ★ **存放结构树 + 路径规约 R1~R5**（"路径该怎么写"的唯一入口）| ★ 改任何命令/路径前必读 |
| **⑥** | 本文件 §3 的**活跃坑** | ★ 不要重复踩 | P1~P7 ＋ **P15~P18**（★ [10-15] 新增 · ★ 详见 `SESSION-HANDOFF.md §3` 的 P1~P18）|

★ **禁止**：★ 凭"我记得规格是…"开工 —— ★ 必须**贴出文档引用（§/行号）+ 代码证据**。

## 1.3 ★★ 用代码核实台账（★ 不许信文档自述）

★ 在**后端仓库**里跑（★ **去盘符**：见 `docs/LAYOUT.md`；★ 下面用到的 `run-tests.bat` 是**仓库内包装脚本** —— 与 cwd 无关，内部用 `%~dp0`）：

```bat
REM ① 代码是不是台账以为的那一版
git log -1 --format="%h %ci %s"
git status --porcelain

REM ② 台账里"进行中/未开始"的
REM   ⚠ 不要用 findstr 查 emoji（GBK 下匹配不到，会静默输出空）——
REM     用 PowerShell 的 Select-String（本机 pwsh 可用）
powershell -NoProfile -Command "Select-String -Path docs\PENDING-LEDGER.md -Pattern '🔄','⬜','⛔' | Select-Object LineNumber,Line"

REM ③ ★★ 强制跑全部守卫（★ 一条命令，★ 期望 166 passed）
run-tests.bat tests/test_comment_drift.py tests/test_task_flow_docs.py tests/module/config/test_standby_placeholder.py tests/module/config/test_entry_target_reached.py tests/module/server/test_help_texts_current_ui.py tests/module/server/test_profile_name_from_user.py tests/module/server/test_profile_transfer_keeps_enables.py tests/tasks/Component/SwitchSoul/test_switch_soul_validation.py tests/tasks/test_rest_random_minutes.py tests/module/config/test_loop_rounds.py tests/tasks/test_no_ticket_is_success.py tests/module/flow/test_control_types.py tests/module/config/test_entry_custom_state.py tests/module/test_task_factory.py -q

REM ④ ★ 全量基线（★ **[10-15] 相对路径改造后实测：15 failed / 1903 passed / 7 skipped**）
REM   ★ 那 15 条是【已知环境类】，★ 不是回归：
REM     9 = 缺 module/config/i18n/zh-CN.json（★ 它是**前端运行后**经 /home/chinese_translate
REM         推来的运行时产物 ⇒ 没起前端就没有）· 2 = 读用户/实机状态（test_task_report）
REM     · 1 = test_schema_router（窗口外任务）· 1 = test_task_catalog（用户配置）
REM     · 1 = live 配置（test_queue_clear_and_settings）· ★ 1 = **真漂移**（见下）
REM   ★★ 原来那 43 条"测试硬编码读 `…\OASX-src`"已**根治**（[10-15] 改走 `dev_tools/paths.py`）
REM   ★ ★ **真漂移那 1 条**：tests/module/config/test_linkage_unification.py::test_pause_reports_requeue
REM     期望前端 run_control_bar.dart 里有 `pauseScriptDetailed`，★ 而前端 v2 已只剩「启动/停止脚本」
REM     ⇒ ★ 这是**跨仓契约不一致**（★ 已记台账 §E-6-n · ★ 与前端 F9 同源），★ 不是环境问题
run-tests.bat
```

★ 期望：★ **守卫 166 passed**（★ 14 个文件 · [10-15] 实测 3.36s）；★ 全量 **15 failed / 1903 passed / 7 skipped**（★ 15 条 = 9 缺前端推来的 `zh-CN.json` + 5 用户/实机状态 + **1 真漂移**）。
★★ **[10-15] 相对路径改造后的实测（本机 = 开发机）**：★ 守卫 **166 passed** · ★ 全量 **15 / 1903 / 7** · ★ 前端 `analyze` **0 error（4w+17i）** · `test` **158 passed**
★ **改造前 = 49 failed / 1862 passed / 12 skipped**（★ 那 43 条"硬编码读 `…\OASX-src`"⇒ **已根治**；★ 覆盖反而变强：这些测试**现在真的在读前端源码**）。

```bat
REM ⑤ ★ 前端（★ 也要核）——★ **无盘符包装**：自动找 SDK + 自动补 --no-version-check（坑 P16）
dev_tools\flutter.bat analyze lib
dev_tools\flutter.bat test
REM   ★ [10-14] 实测：analyze 0 error（4 warning + 17 info）· test 158 passed
REM   ★ ★ [10-15] 本机复现：analyze 0 error（4 warning + 17 info）· test 158 passed
REM   ★ ⚠ **必须带 `--no-version-check`**：否则 flutter 会对 SDK 仓库跑
REM     `git fetch --tags`（要拉 611285 个对象）⇒ 在当前网络下**挂死**（★ 坑 P16）
REM   ★ ⚠ 本机**无 Visual Studio / Windows SDK** ⇒ `build windows --release` 暂不可用（★ 坑 P17）
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
>
> ★★ **⑤ [10-15] 本机已换成新开发机（`D:\OAS-dev`）—— 环境已引导完毕** ——
>   ★ 两仓 = `git clone -b dev`（★ 本地分支 `dev`）· ★ `toolkit\` / `deploy.yaml` / 两份账号配置 /
>   `console.bat` 已从 `C:\Users\passioki\Downloads` 补齐 · ★ Flutter 3.27.1 装在 `D:\flutter3271`
>   （★ **必须带 `--no-version-check`**，见坑 P16）· ★★ **四条基线已实测复现**
>   （守卫 **166 passed** · 全量 **15/1903/7** · 前端 **0 error + 158 passed**）
>   ★ ⚠ **本机缺 Visual Studio / Windows SDK** ⇒ `flutter build windows --release` **暂时不可用**
>   （★ 见坑 P17 · ★ **待用户裁定是否安装 VS Build Tools**）

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
| **P7** | ★★ **`pwsh` 工具整段不可用（★ 两种症状）** | ★ ① `spawn … ENOENT`（旧）· ★★ ② **[10-15] 每条命令都返回 `exit code 3221225794`（= `0xC0000142` STATUS_DLL_INIT_FAILED）且零输出**（★ 连 `echo hi` 都失败）⇒ ★ **两种都靠"续跑/重启 DSH 会话"解决**（★ 不是重启电脑；★ [10-15] 实测下一轮自行恢复）· ★ 也可用 `pwsh -Command` 之外的原生手段（`read`/`grep`/`glob` 工具）先取证 |
| **P15** | ★★ **[10-15] 旧开发机的 `git` 报 `dubious ownership`**（★ `git log`/`status`/`push` **全被拒**）| ★ 真因：仓库属主 = `Administrators` ≠ 当前用户 ⇒ ★ 修：`git config --global --add safe.directory D:/OAS-dev/backend`（★ 前端同理）；★ ⚠ **沙箱下改不了** `~/.gitconfig` ⇒ ★ **必须先放开沙箱**（★ [10-15] 已修 · 详见 `SESSION-HANDOFF.md §3`）★ ★ **[10-15] 本机（`D:\OAS-dev`）实测没有这个问题**（仓库属主正常，`git log`/`status` 直接可用）⇒ ★ 若将来出现，`safe.directory` 要写 **`D:/OAS-dev/backend`**（不是 `D:/…`）|
| **P16** | ★★ **[10-15] `flutter` 的"版本检查"会跑 `git fetch --tags`（★ 611285 个对象）⇒ 在新网络上**挂死** | ★ 症状：`flutter --version`（或任何不带开关的命令）卡 10+ 分钟，后台常驻 `git fetch --tags` + `git index-pack`（★ 实测 `git remote-https origin https://github.com/flutter/flutter.git`）⇒ ★ **正解：命令一律加 `--no-version-check`**；★ 并把包/引擎源换成国内镜像：`PUB_HOSTED_URL=https://pub.flutter-io.cn` · `FLUTTER_STORAGE_BASE_URL=https://storage.flutter-io.cn`（★ 实测 Google 源 **~170 KB/s** vs 国内镜像 **3.5 MB/s**，997 MB 的 SDK 包 5 分钟下完且**字节数精确一致**）|
| **P17** | ★★ **[10-15] 本机缺 C++ 工具链 ⇒ `flutter build windows --release` 不可用** | ★ 实测：**无 `vswhere`** · 无 `Microsoft Visual Studio` 目录 · 无 `Windows Kits\10\bin` · 无 `cmake`/`ninja` · **无 `winget`** ⇒ ★ `analyze`/`test` **不受影响**（已跑绿），★ **只有构建 exe 需要** Visual Studio Build Tools（`Microsoft.VisualStudio.Workload.VCTools` + Win10/11 SDK）⇒ ★ **待用户裁定是否安装**（★ 见台账 §E-6）|
| **P18** | ★ **[10-15] `test_task_factory` / `test_task_flow_docs` 会重写 `docs/flows/README.md` 的行尾** | ★ 实测**可复现**：跑完这两个测试后 `git status` 显示 ` M docs/flows/README.md`，但 `git diff --numstat` **为空** · `git diff --ignore-cr-at-eol` **0 行** ⇒ ★ 纯 LF/CRLF 幻影（`core.autocrlf=true`），★ **内容没变** ⇒ ★ 处置：`git checkout -- docs/flows/README.md` 还原；★ 根因在 `module/task_factory.py:40/403` 用 Python 默认换行写回（★ 根治建议未做：写入时保留原行尾）|

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
★ ③ ★ 有实质进展就 **commit + push**（★ **[10-15] 本机两仓的本地分支 = `dev`** ⇒ **`git push origin dev`**；★ 旧机"本地 `main`"的写法只适用于本地分支叫 `main` 的机器 —— 那种机器必须 `git push origin main:dev`；★ **绝不 `main:main`**；★ **`main` 只在"判定稳定"时前移**）
```

---

# §6 ★ 常用命令速查

```bat
REM ---------- 开发（★ **去盘符**：一律用仓库内包装脚本，★ 与 cwd 无关）----------
REM   ★ 工作区根 = <WORKSPACE>（里面并排 backend\ 与 frontend\；★ 见 docs/LAYOUT.md）
backend\run-server.bat                          REM ★ 开发后端 :22288（端口取自 config\deploy.yaml）
backend\run-tests.bat                           REM ★ 全量测试
backend\dev_tools\flutter.bat analyze lib       REM ★ 期望 0 error（4 warning + 17 info）
backend\dev_tools\flutter.bat test              REM ★ 期望 158 passed
backend\dev_tools\flutter.bat build windows --release
REM   ★ ⚠ build 需要 Visual Studio（★ 本机暂无 ⇒ 见坑 P17）
frontend\build\windows\x64\runner\Release\oasx-live.exe   REM ★ 开发前端
REM   ★ **自查锚点**：backend\toolkit\python.exe -m dev_tools.paths

REM ---------- 实机（★ 在【另一台电脑】上 · 本机没有）----------
REM   实机工作区根记作 <LIVE>（★ 生产机上的工作区；本机不存在）
REM   <LIVE>\backend\console.bat         REM ★ 实机后端 :22287
REM   <LIVE>\frontend\oasx-live.exe      REM ★ 实机前端
REM   ★ ⚠ console.bat 实测是**上游的调试控制台**（开一个带 toolkit PATH 的交互 cmd），
REM     不是"启动 server.py"的启动器 —— ★ `DEV-WORKFLOW.md §5` 给的是另一份模板

REM ---------- 从零恢复一台机器 ----------
REM ★ 见 DEV-WORKFLOW.md §6
```
