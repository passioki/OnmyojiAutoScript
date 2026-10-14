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
★ ★ **唯一真相 = git**：后端 `main` · 前端 `main`
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
| **⑤** | 本文件 §3 的**活跃坑** | ★ 不要重复踩 | P1~P6 |

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

REM ③ ★★ 强制跑全部守卫（★ 一条命令，★ 期望 106 passed）
toolkit\python.exe -m pytest tests/test_comment_drift.py tests/test_task_flow_docs.py tests/module/config/test_standby_placeholder.py tests/module/config/test_entry_target_reached.py tests/module/server/test_help_texts_current_ui.py tests/module/server/test_profile_name_from_user.py tests/module/server/test_profile_transfer_keeps_enables.py tests/tasks/Component/SwitchSoul/test_switch_soul_validation.py tests/tasks/test_rest_random_minutes.py tests/module/config/test_loop_rounds.py tests/tasks/test_no_ticket_is_success.py -q

REM ④ ★ 全量基线（★ [10-14] 实测：49 failed / 1785 passed / 12 skipped）
REM   ★ 那 49 条是【已知环境类】，★ 不是回归：
REM     43 = 测试去读 D:/OAS-dev/OASX-src（本机是 frontend）· 4 = 缺
REM     module/config/i18n/zh-CN.json（前端推来的运行时产物）· 2 = 读用户/实机状态
REM     · 1 = live 配置 · 1 = 顺序 flaky
toolkit\python.exe -m pytest tests/ -q
```

★ 期望：★ **守卫 106 passed**（★ [10-14] 第二轮：98 + 新增 8 条 `test_no_ticket_is_success.py`）；★ 全量 **49 failed / 1793 passed**（★ 与基线一致 ⇒ 无回归）。

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

★ ⚠⚠ **[10-14] 换会话时最要紧的一件事**（★ 新会话请先看这条）：

> ★★ **`N9-6`（annotator 集成"新建任务" + 任务逻辑编辑器）卡在一个
> 【必须用户点头的架构选择】** —— ★ 见 `DESIGN-SPEC.md` **§1.17 一**：
> ★ **A 受控指令集（DSL，推荐）** vs ★ **B 直接编辑 Python**
> （★ 工具端点**无鉴权** ⇒ B 等价于"**远程代码执行**"）★ 或折中 **A+**。
> ★ **在这一条定下来之前，不要动 N9-6 的代码**（★ 免得白做）。

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
