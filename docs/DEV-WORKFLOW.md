# 开发 / 测试 / 实机 工作流（★ 本文是**唯一**的流程依据）

> ★★★ **[2026-10-13] 用户裁定**：★★ "**规划下怎么开发和测试，我需要一个开发，
> 一个实机运行，考虑下只保留 dev 开发，实机用 dev 拷贝过去，前端也这样操作**"
>
> ★ 同日用户还裁定：★ "**全部删光吧，除了两份配置文件：伴生树、恋鳥樹**"

---

# §0 ★★★ 会话协议（★ 解决"换会话交接不明朗 / 记忆压缩后走偏"）
> ★★★ **唯一入口 = `docs/START-HERE.md`** —— ★ 新会话只读它即可（它含强制步骤与回报模板）。

> ★★ **用户指出的两个问题**：
> > "**换新的会话后交接不明朗**"
> > "**单一会话记忆压缩导致开发执行逐渐走偏**"
>
> ★ **根因**：★ **记忆没有外置** —— ★ 一切靠"上下文里的记忆"⇒
>   ★ 换会话 = 记忆清零；★ 压缩 = 记忆被磨成"我记得…" ⇒ ★ **必然走偏**。
>
> ★ **对策**：★ **四层磁盘锚点 + 强制会话协议**（★ 全部在 git 里，可核查）。

## 0.1 ★ 四层记忆锚点

| 层 | 文件 | 放什么 | 更新时机 |
|---|---|---|---|
| **L1** | `docs/DESIGN-SPEC.md` | ★ **软件应该是怎样的**（设计 · 规则 · 分歧块 · `文件:行号`）| 设计变 / 实现变 |
| **L2** | `docs/PENDING-LEDGER.md` | ★ **未完成台账**（编号 · 依据 · 状态 · 验证方式）| ★ **每轮** |
| **L3** | ★ **`docs/SESSION-HANDOFF.md`** | ★ **一页交接**（当前状态 · 下一步 · 活跃的坑）| ★ **每轮** |
| **L4** | `docs/DEV-WORKFLOW.md` | ★ 怎么开发 / 测试 / 部署 | 流程变 |

## 0.2 ★★ 新会话开工协议（★ 强制，四步）

```
★ ① 读 `docs/SESSION-HANDOFF.md`      ← ★ **第一件事**（三十秒自检）
★ ② 读 `docs/PENDING-LEDGER.md`       ← 找 🔄 / ⬜ / ⛔
★ ③ ★ **用代码核实台账**（★ 不许信文档自述）：
     跑 `SESSION-HANDOFF.md §0` 里的三条命令
★ ④ 回报"我看到的 vs 台账写的"，★ 不一致就先对齐，★ **再动手改代码**
```

★ **禁止**：★ 凭"我记得规格是…"开工 —— ★ 必须**贴出文档引用 + 代码证据**。

## 0.3 ★★ 每轮结束协议（★ 强制，三步）

```
★ ① 更新 `docs/PENDING-LEDGER.md`（状态变了就改；★ "已完成"要有可核查证据）
★ ② 更新 `docs/SESSION-HANDOFF.md`（当前状态 / 下一步 / 新增的坑）
★ ③ ★ 有实质进展就 **commit + push**（★ git 是最可靠的锚点）
```

## 0.4 ★ 为什么这能治"压缩后走偏"

```
★ 压缩会丢的是【上下文】，★ 不会丢【磁盘】。
★ 所以：★ **任何结论一产生，立刻写进 L1/L2/L3** ⇒ ★ 压缩后从磁盘重建，而不是从记忆重建。
★ 配套：★ 文档里**标清"现行口径 / 已作废"**（★ 分歧块 + 正文同步改），
        ★ 否则压缩后的"我记得"会捡起**已作废的旧说法**。
```

## 0.5 ★ 文档权威顺序（★ 冲突时以此为准）

```
① DESIGN-SPEC §1~§3 正文（★ 用户的话 = 规格）
② DESIGN-SPEC §1.6.x / 分歧块
③ PENDING-LEDGER（状态与依据）
④ SESSION-HANDOFF（当前状态与下一步）
⑤ DEV-WORKFLOW（流程）
⑥ 代码 —— ★ 与 ①~⑤ 冲突 ⇒ ★ **以 ①~⑤ 为准**，并把冲突记进 SPEC §4
```

## 0.7 ★★★ [10-15] 两台机器**并发写 `dev`** 的规矩（★ 已真实撞上）

> ★ 实测：★ [10-15] 22:2x~22:5x，★ **实机侧与开发机侧同时在改 `docs/PENDING-LEDGER.md`**
> ⇒ ★ 两边的 `git push origin dev` **都被拒**（`! [rejected] … (fetch first)`）
> —— ★ 台账 **§E-7-b**（实机侧）· **§E-6-t**（开发机侧）

★ **固定动作（推之前，★ 一条都不许省）**：
```
git fetch origin                              # ★ 先看别人推了什么
git log --oneline dev..origin/dev             # ★ 有别人的提交 ⇒ 不许硬推
git pull --rebase origin dev                  # ★ 在最新之上**重做**（★ 不是合并覆盖）
git push origin dev
```
★ **铁律**：★ **绝不 `--force` / `--force-with-lease` 到共享分支**（★ 除非是"回退误推"那种**已裁定**的场景）。
★ ⚠ **`remote.origin.fetch` 必须是通配**：`+refs/heads/*:refs/remotes/origin/*`
  —— ★ 实测：**实机侧的 clone 只配了 `main`** ⇒ ★ `git fetch` **根本不更新 `origin/dev`**
  （★ 会看到**旧快照**、误判"远端被回退"）；★ **开发机侧实测是通配**（正常）。
  修：`git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'`
★ ★ **分工建议（防冲突）**：★ 台账/交接类文档**由一台机器主写**（★ 建议 = 开发机），
  另一台**只追加自己的小节**（★ 如实机侧的 `§E-7-*`），★ **别同时改同一张表**。

## 0.6 ★★ [10-15] **两台机器**（★ ★★ **角色已裁定：本机 = 开发机**）

> ★★ **用户原话（逐字）**：
> > "**现在打算使用两台电脑，一台开发、测试稳定后，上传到github，另一台从git上更新，
> >   用于实机生产。本台电脑为实机生产用，所以需要你上传dev到git，
> >   确保另一台从git上取下来时可以无缝开发。**"

| 机器 | ★ 角色（★ ★ **[10-15] 已裁定** · ★ 早先"按另一台拉 dev 推断"的说法**作废**）| 目录 |
|---|---|---|
| ★ **本台**（★ [10-15] 用户原话："**本机是开发机**"）| ★ ★ **开发 / 测试**（★ 现行）| `D:\OAS-dev\`（`backend\` + `frontend`）|
| ★ **另一台** | ★ **实机生产** | `D:\OAS-live\`（★ 本机**没有**这个目录 ⇒ 实机验收不在本机做）|

> ★ ⚠ **[10-15] 更正**：此前按"另一台拉 dev"**推断**成"本台 = 生产"，★ **该推断作废** ——
> ★ 用户 [10-15] 明说 **本机是开发机** ⇒ ★ 角色 = **本机开发 / 另一台实机生产**。

```
★★ 分支策略（★ [10-15] 用户裁定 · ★ 原话：
   "**另一台可以拉dev啊，main是主要的稳定版本！**"）：
   · `dev`  = ★ **开发分支**（★ 日常提交都到这里；★ 另一台电脑拉这个）
   · `main` = ★ **主要的稳定版本**（★ **冻结点**；★ 只在"判定稳定"时把 dev 快进过来）
   ★ ★ **[10-15] 本机（新开发机）两仓的本地分支名 = `dev`**（clone 时就是）⇒ ★ **一律 `git push origin dev`**
     ★ ⚠ **历史教训（旧开发机）**：★ 旧机本地分支叫 `main`，那时必须 `git push origin main:dev` ——
        ★ 我 [10-15] 曾误推 `main:main` ⇒ 已 `--force-with-lease` 回退
        （后端 main=e28793ce · 前端 main=af10440）
     ★ ⚠ **任何机器上都绝不把本地 `main` 推到远端 `main`**（★ `main` 只在"判定稳定"时前移）

★ 交付通道（★ 取代原来的"同一台机器上 robocopy"）：
   开发机（`D:\OAS-dev`）──git push origin dev──▶ GitHub(dev) ──git pull origin dev──▶ 生产机
          ──按 §4 拷贝──▶ D:\OAS-live（★ 本机没有这个目录）
★ ⚠★ **git 只给到"源码级无缝"** —— ★ toolkit\（1.17 GB）· deploy.yaml · 账号配置 · console.bat
   **都不在 git** ⇒ ★ 清单见台账 **§E-1** 与本文 **§6**。
★ ✅ ★★ **[10-15] 本机已按 §6 清单**补完**（★ 来源 = `C:\Users\passioki\Downloads`，★ 逐项实测：
   `toolkit\` **17000 文件 / 1167.4 MB** · `deploy.yaml` **6114 B**（`WebuiPort: 22288`）·
   `伴生树.json` 68437 B · `恋鸟树.json` 85570 B · `console.bat` 590 B）
★ ⚠ ★ **[10-15] 本机缺 C++ 工具链**（无 Visual Studio / Windows SDK）⇒ ★ `flutter build windows --release`
   **暂不可用**（★ 见 §7 坑 9）；★ `analyze` / `test` 不受影响。
```

---

# §1 ★ 目录结构（唯一真相 = **git**）

> ★★ **[10-15] 结构树与路径规约（R1~R5）已抽到 `docs/LAYOUT.md`** —— ★ **"路径该怎么写"一律看它**；
> ★ 本节只保留最小目录树与"哪些不进 git"的清单。★ 命令一律走**无盘符包装脚本**：
> `run-tests.bat` / `run-server.bat` / `dev_tools\flutter.bat`（★ 内部用 `%~dp0`，与 cwd 无关）。

```
D:\OAS-dev\                              ← ★★ **唯一开发工作区**
│
├── backend\                             ← 后端（git 仓库 · ★★ **本地分支 `dev`** ⇒ `git push origin dev`）
│   ├── .git\                            ★ **只在这里改后端代码**
│   ├── script.py · server.py · module\ · tasks\ · tests\ · docs\
│   ├── config\
│   │   ├── template.json                （在 git）
│   │   ├── deploy.yaml                  ★★ **不在 git**（.gitignore 排除）
│   │   ├── 伴生树.json                   ★★ **你的账号配置**（不在 git）
│   │   └── 恋鸟树.json                   ★★ **你的账号配置**（不在 git）
│   ├── toolkit\                         ★★ **不在 git**（Python 运行时 + 依赖，1.1 GB）
│   └── console.bat                      ★★ **不在 git**（★ [10-15] 实测：**上游的"调试控制台"** —— 开一个带 toolkit PATH 的交互 cmd，★ **不是**"启动 `server.py`"的启动器；见 §5）
│
└── frontend\                            ← 前端（git 仓库 · ★★ **本地分支 `dev`** ⇒ `git push origin dev`）
    ├── .git\                            ★ **只在这里改前端代码**
    ├── lib\ · windows\ · pubspec.yaml
    ├── windows\flutter\ephemeral\       ★ 由 `flutter pub get` 生成（不在 git）
    └── build\windows\x64\runner\Release\   ← ★ 构建产物
        └── oasx-live.exe                ★ 实机要用的就是它
```

## ★★ 关键认知：**有些东西不在 git 里**

| 路径 | 在 git？ | 丢了怎么办 |
|---|---|---|
| 后端源码（`script.py` / `module/` / `tasks/` / `tests/`）| ✅ | `git clone` 即可 |
| 后端 `config\template.json` | ✅ | 同上 |
| 后端 `docs\` | ✅ | 同上 |
| ★ 后端 `toolkit\` | ❌ | ★ 从 `OnmyojiAutoScript-easy-install.rar` 解压，或复制旧机器的 `toolkit\`；★ **[10-15] 本机来源 = `C:\Users\passioki\Downloads\toolkit\`**（★ 实测 **17000 文件 / 1167.4 MB**，与台账**一致**）|
| ★ 后端 `config\deploy.yaml` | ❌ | ★ **必须在每台机器上单独准备**（端口/模拟器等本机设置） |
| ★ 后端 `config\*.json`（账号配置）| ❌ | ★ **用户数据**，只能靠备份 |
| ★ 后端 `console.bat` | ❌ | ★ 实测**上游的调试控制台**（不是启动器）⇒ 想"一键起后端"就用 §5 的模板另存一份；★ 现网用的是上游那份 |
| ★ 前端 `windows\flutter\ephemeral\` | ❌ | ★ `flutter pub get` 自动重建 |
| ★ 前端 `build\` | ❌ | ★ `flutter build windows --release` 重建 |

⇒ ★★ **从零恢复一台机器的完整步骤见 §6。**

---

# §2 ★ 日常开发流程

## 2.1 只在一处改代码

```
★ 后端：★ 只在 `D:\OAS-dev\backend\` 改
★ 前端：★ 只在 `D:\OAS-dev\frontend\` 改
★ ⚠ **不要**在"实机目录"里改 —— ★ 实机是 dev 的**拷贝**，改了会被下次覆盖
```

## 2.2 起"开发"这一套

```bat
REM ★ 后端（开发）
REM ★ 去盘符：以下命令都在 backend\ 里跑（包装脚本内部用 %~dp0，与 cwd 无关）
run-server.bat
REM ★ 默认监听 127.0.0.1:22288（见 config\deploy.yaml 的 WebuiPort）
```

```bat
REM ★ 前端（开发）—— 改完代码后重新编译
REM ★ 去盘符：前端命令一律走 backend\dev_tools\flutter.bat（自动找 SDK）
dev_tools\flutter.bat build windows --release
build\windows\x64\runner\Release\oasx-live.exe
```

## 2.3 前端"改了却没生效"的三个常见原因

```
① ★ 忘了 `flutter build windows --release`（★ 源码改了但没重编译）
② ★ 起的是【旧目录】里的 exe（★ 必须起 `build\windows\x64\runner\Release\` 里那个）
③ ★ 后端没重启 ⇒ `/schema` 还是旧的（★ 前端界面由后端 schema 决定）
```

---

# §3 ★ 测试

## 3.1 后端自动化测试

```bat
REM ★ 去盘符：以下命令都在 backend\ 里跑（包装脚本内部用 %~dp0，与 cwd 无关）
run-tests.bat tests/ -q
```

★ **已知的非本次失败**（★ 与改动无关，读它们是"前端仓库不在本机"）：
```
★ `tests/module/config/test_window_editor_frontend.py`
★ `tests/module/config/test_queue_*.py`
★ `tests/module/server/test_category_label_consistency.py`
★ `tests/module/config/test_i18n_full_coverage.py`
★ （这些用例会去读 OASX 源码目录；★ 路径不含本机布局时会红）
```

## 3.2 ★★ 改"调度/计数/循环"时**必须**跑的两组守卫

```bat
REM ★ 去盘符：以下命令都在 backend\ 里跑（包装脚本内部用 %~dp0，与 cwd 无关）
run-tests.bat tests/module/config/test_loop_rounds.py -q
run-tests.bat tests/module/config/test_no_false_completion.py tests/tasks/test_effective_target.py -q
```

| 测试文件 | 守什么 |
|---|---|
| `tests/module/config/test_loop_rounds.py` | ★ 队列循环**轮数会递增**（修过"只计数到 1"）· 枚举取 `.value` · 停止判据 · 重置 |
| `tests/module/config/test_no_false_completion.py` | ★ 「**已完成后按时间戳过期**」· 无基准 ⇒ 按未完成 |
| `tests/tasks/test_effective_target.py` | ★ `bind_counter` **不读盘**（从 0 起算）· `commit_count` **不写盘** |

## 3.3 ★ 守卫必须是"真会红"的（★ 防"空转守卫"）

> ★ 教训：2026-10-13 审计发现，有的守卫**恒真**（守着的目录里根本没有它要查的东西）。
> 所以新增守卫后，**必须做一次"注入验证"**：

```bat
REM ① 故意把代码改坏（例如把取 .value 改回裸枚举）
REM ② 跑守卫 —— ★ 必须变红
REM ③ 还原   —— ★ 必须回绿
```

★ 例（`test_loop_rounds.py` 已做过）：
```
注入"裸枚举比较"        ⇒ 1 failed   ✓ 守卫抓住
注入"bump 不递增"       ⇒ 5 failed   ✓ 守卫抓住
还原                    ⇒ 8 passed   ✓ 回绿
```

## 3.4 前端

```bat
REM ★ 去盘符：前端命令一律走 backend\dev_tools\flutter.bat（自动找 SDK）
dev_tools\flutter.bat analyze lib     REM ★ 期望 0 error（★ [10-15] 本机实测：0 error / 4 warning / 17 info）
dev_tools\flutter.bat test            REM ★ 单元测试（★ [10-15] 本机实测：158 passed）
REM ★ ⚠ **必须带 `--no-version-check`** —— 否则 flutter 对 SDK 仓库跑 `git fetch --tags`
REM   （611285 个对象）⇒ 在当前网络下**挂死**（★ §7 坑 9）
REM ★ ⚠ 本机**无 Visual Studio / Windows SDK** ⇒ `build windows --release` 暂不可用（★ §7 坑 10）
```

## 3.5 ★ 实机人工验收（★ 唯一不能自动化的部分）

```
★ 后端起来后，看日志里有没有：
   · `[TaskState] 本次启动时间已记录: …`      ← ★ 时间戳机制生效
   · `战斗计数: 本轮从 0 开始`                 ← ★ 不读旧计数
★ 前端里看「全局设置」的**那个下拉**：
   · ★ 选项必须是 **顺序 / 循环 / 乱序**（★ 不要出现"关闭游戏"）
★ 任务队列：★ 跑完一轮后，★ 轮数**必须递增**（不是停在 1）
```

---

# §4 ★ 实机部署（★ 拷贝法）

> ★ 用户裁定：★ "**实机用 dev 拷贝过去，前端也这样操作**"

```powershell
# ---------- ★ 后端：把 dev 拷贝成实机 ----------
# ⚠ 先停掉正在跑的实机后端（否则文件被占用）
robocopy D:\OAS-dev\backend D:\OAS-live\backend /E /MT:16 `
    /XD .git __pycache__ .pytest_cache .mypy_cache log
# ★ 保留实机自己的运行时状态目录：
#   log\（运行日志）—— 上面的 /XD log 就是"不覆盖"；首次部署需手动建

# ---------- ★ 前端：把构建产物拷过去 ----------
robocopy D:\OAS-dev\frontend\build\windows\x64\runner\Release `
         D:\OAS-live\frontend /E /MT:16
```

> ★ ⚠★ **[10-15] 重要变化：现在开发机与实机是【两台电脑】** ⇒ ★ 上面这两条 `robocopy`
> **不能直接跨机跑**（`D:\OAS-live` 在另一台上）。★ 两条可行路径：
> ★ **① 推荐**：★ 生产机 `git pull origin dev` 拿源码 ⇒ ★ 在生产机上跑 `flutter build` ⇒
>   把产物放进 `D:\OAS-live\frontend`（★ 源码同步交给 git，★ 只手动搬"不在 git 的运行时"）
> ★ **②**：★ 开发机产出后，用共享目录 / 移动盘把 `backend`（去掉 `.git`）与前端 `Release` 目录搬过去
> ★ ★ 无论哪条：★ **`toolkit\` / `deploy.yaml` / 两份账号配置 / `console.bat` 都要在生产机上单独准备**（§6-②）
> ★★ **[10-15] 实机【不带前端源码】、也【不跑 pytest】** —— ★ 用户："**不参与运行的不应该存在**"
>   ⇒ ★ 实机上只有"后端拷贝 + `oasx-live.exe`"；★ **跨仓契约测试（需要前端源码）只在开发机跑**
>   （★ 这本来就是坑 **P14**"不许在实机做开发/测试"的口径）。

## ★ 实机与开发**必须区分开**的 4 处

| 项 | 开发（dev）| 实机（live）| 为什么 |
|---|---|---|---|
| ★ 后端目录 | `D:\OAS-dev\backend` | `D:\OAS-live\backend` | ★ 拷贝后互不影响 |
| ★ 前端目录 | `D:\OAS-dev\frontend\build\...\Release` | `D:\OAS-live\frontend` | ★ 同上 |
| ★ **端口** | **22288** | ★ **22287**（★ 建议）| ★ 同时跑时不撞（见 `config\deploy.yaml` 的 `WebuiPort`）|
| ★ **本地存储** | `Documents\GetStorage-live.gs` | ★ **同一个**（★ 当前实现如此）| ⚠ **见下方警告** |

## ⚠⚠ 已知限制：前后端**共用**本地存储

```
★ 现在 exe 里的 appId 是 `com.oas.live` ⇒ ★ 存储 = `Documents\GetStorage-live.gs`
★ ⇒ ★ **dev 前端与实机前端共用同一份配置**（★ 包括"后端地址"那一项）
★ ⇒ ★ 若两个前端同时开，★ 会互相覆盖"服务地址"等设置
★ ⇒ ★ **建议：同一时间只开一个前端**；★ 或改 `lib\main.dart` 的
   `GetStorage.init('…')` 容器名，各用一个容器
```

## ★ 实机入口

```
★ 后端：双击 `D:\OAS-live\backend\console.bat`
★ 前端：双击 `D:\OAS-live\frontend\oasx-live.exe`
★ ⚠ 双击打不开时见 §7（`PassGuard` 保护区问题）
```

---

# §5 ★ `console.bat` 模板（★ 不在 git，丢了用这个）

> ★ ⚠ **[10-15] 实测口径更正**：现网（旧机与 `C:\Users\passioki\Downloads`）里的 `console.bat` **不是**
> 下面这份模板 —— 它是**上游的"调试控制台"**：设好 `toolkit\alias`/`command`/`Git`/`adb` 的 PATH 后
> `cmd /Q /K` 开一个交互 shell（用来手敲 `adb devices` / `git log` / `python -V`）。
> ★ 它的第 23 行有一个**孤立的 `)`** —— ★ 实测 **cmd 容忍它，rc=0，无害**（★ 别去"修"它）。
> ★ 想"双击即起后端"就用下面这份模板（★ 另存为 `console-serve.bat` 更不易混淆）。

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 启动 OAS 后端 ...
"%~dp0toolkit\python.exe" "%~dp0server.py"
pause
```

---

# §6 ★ 从零恢复一台机器（★ 完整步骤）

> ★★ **[10-15] 分发通道 = GitHub 的 `dev` 分支**（★ 两台机器模型见 §0.6 · ★ 用户裁定：
> "**另一台可以拉dev啊，main是主要的稳定版本！**"）：
> ★ 开发机（★ **[10-15] 本机 = `D:\OAS-dev`**）`git push origin dev` ⇒ 另一台 `git clone -b dev` / `git pull origin dev`
> ★ ★ `main` = **主要的稳定版本**，★ **保持不动**；★ 只有判定稳定时才把 `dev` 快进到 `main`

```
⓪ ★★ [10-15] **装用户级技能 `session-memory`**（★ 它**不在任何项目仓库里**，`git clone` 带不过来）
   · 仓库：`https://github.com/passioki/dsh-skills` ⇒ 克隆到任意位置（★ 本机 = `D:\tools\dsh-skills`）
   · 安装：`cd <位置>\dsh-skills` ⇒ `.\install.bat`（★ 建 **Junction**，**不需要管理员**；
     ★ 直接跑 `install.ps1` 会报 "not digitally signed" —— 那是执行策略，用 `.bat` 或 `-ExecutionPolicy Bypass`）
   · 自检：`python verify.py`（★ 期望 **ALL CHECKS PASSED**）
   · 目标：`%DSH_HOME%\skills\session-memory\SKILL.md`（★ 本机 `DSH_HOME = C:\Users\passioki\.dsh`）
   · ★ 之后同步只需 `git pull`（★ Junction 模式立即生效，不用重装）
   · ⚠ ★ **别把技能拷进 `backend\` / `frontend\`** —— DSH 只扫描 `%DSH_HOME%\skills\` 与 `~\.agents\skills\`

① 拉源码（★ 唯一真相 = git · ★★ **拉 `dev`**）
   git clone -b dev https://github.com/passioki/OnmyojiAutoScript.git backend
   git clone -b dev https://github.com/passioki/OASX.git               frontend

② 补"不在 git"的运行时（★ [10-15] 逐项实测，★ 一个都不能少）
   · ★★ 把 `toolkit\`（Python 运行时）放到 backend\toolkit\
       ★ 实测本机 = **17000 文件 / 1167.4 MB**（★ `.gitignore:18`）
       ★ 来源：★ **[10-15] 本机实测 = `C:\Users\passioki\Downloads\toolkit\`**（★ 17000/1167.4 MB，
         **与台账一致**）；★ 另有 `OnmyojiAutoScript-easy-install.rar` 内的 `toolkit\`
         （★ 实测 **21350 文件 / 743.7 MB**，★ **与旧机的不是同一份** ⇒ 优先用前者）
   · ★ 建 backend\config\deploy.yaml（★ 至少要有 WebuiPort；★ 实测 6114 B）
       ★ dev 机 = **22288** · live 机 = **22287**（★ 两台机器上各建一份）
       ★ [10-15] 本机实测：`WebuiPort: 22288` · `PythonExecutable: ./toolkit/python.exe` ·
         `AdbExecutable: ./toolkit/Lib/site-packages/adbutils/binaries/adb.exe` · `ReplaceAdb: true` · `Branch: dev`
   · ★ 放 backend\console.bat（★ 实测用的是**上游调试控制台**那份；★ 想一键起后端见 §5 模板）
   · ★★ 把账号配置（`伴生树.json` / `恋鸟树.json`）放进 backend\config\
       ★ 实测 68437 B / **85570 B**（★ 台账里的旧值是 86062 B —— ★ 用户 [10-15] 又更新过）；
       ★ **是用户数据，git 里永远不会有** ⇒ ★ 必须单独传
   · ★ [10-15] Flutter SDK（★ 见步骤 ④ 的工具链要求）

③ 验后端
   cd backend
   run-tests.bat tests/module/config/test_loop_rounds.py -q   REM ★ 期望 8 passed
   run-server.bat                                             REM ★ 端口起来

④ 编前端（★ 必须，因为 ephemeral/build 不在 git）
   cd frontend
   dev_tools\flutter.bat pub get
   dev_tools\flutter.bat build windows --release
   ★ [10-15] Flutter 3.27.1 SDK 获取（★ 本机实录）：
       · 包 = `flutter_windows_3.27.1-stable.zip`（**1045850748 B**，解压后 **2466 MB**）
       · ★ 用**国内镜像**下（`https://storage.flutter-io.cn/...`）：★ 实测 **3.5 MB/s**
         vs Google 源 **~170 KB/s**，★ 且字节数与 Google 的 `Content-Length` **精确一致**
       · 解压到 **`D:\flutter3271`**（★ 文档里所有 `D:\flutter3271\bin\flutter.bat` 都指它）
       · ★★ 设两个环境变量（`setx`）：`PUB_HOSTED_URL=https://pub.flutter-io.cn` ·
         `FLUTTER_STORAGE_BASE_URL=https://storage.flutter-io.cn`
       · ★★ **所有 flutter 命令都要带 `--no-version-check`**（★ 否则 `git fetch --tags` 挂死，§7 坑 9）
   ★ ⚠★ **`build windows --release` 需要 Visual Studio**（Desktop C++ + Win10/11 SDK）：
       ★ [10-15] 本机实测**没有**（无 `vswhere` / VS 目录 / Windows SDK / cmake / ninja / winget）
       ⇒ ★ **本机目前只能 `analyze` + `test`，不能 build**（★ §7 坑 10）

⑤ ★★ 验"无缝"（★ [10-15] 的四条基线，★ 逐数字对得上才算真的能开发）
   cd backend
   run-tests.bat tests/test_comment_drift.py tests/test_task_flow_docs.py ^
       tests/module/config/test_standby_placeholder.py tests/module/config/test_entry_target_reached.py ^
       tests/module/server/test_help_texts_current_ui.py tests/module/server/test_profile_name_from_user.py ^
       tests/module/server/test_profile_transfer_keeps_enables.py ^
       tests/tasks/Component/SwitchSoul/test_switch_soul_validation.py ^
       tests/tasks/test_rest_random_minutes.py tests/module/config/test_loop_rounds.py ^
       tests/tasks/test_no_ticket_is_success.py tests/module/flow/test_control_types.py ^
       tests/module/config/test_entry_custom_state.py tests/module/test_task_factory.py -q
       REM ★ 期望 **166 passed**（★ 且必须先放开沙箱，否则见坑 P11）
   ★★ **[10-15] 本机（新开发机 `D:\OAS-dev`）实测 = 逐数字一致**：
       守卫 **166 passed**（4.48s）· 全量 **15 failed / 1903 passed / 7 skipped**（91.02s）
       · 前端 `analyze` **0 error（4 warning + 17 info）** · `flutter test` **158 passed**
   ★ ⚠★ 跑完 `test_task_factory` / `test_task_flow_docs` 后 `docs/flows/README.md` 会**幻影变脏**
       （★ 纯 LF/CRLF，内容不变）⇒ ★ `git checkout -- docs/flows/README.md` 还原（★ §7 坑 11）
   ★ ⚠ 前端那 7 个 `generated_plugin*` 每次 `pub get`/`test` 后也会幻影变脏（★ F7）⇒ 同样 `git checkout --` 还原

⑥ 起实机（§4 的拷贝法 · ★ **[10-15] 实机在另一台电脑上**）

⑦ ★★ 装 DSH 技能（★ [10-15] 新增 —— ★ **技能不在项目仓库里，必须单独拉**）
   git clone https://github.com/passioki/dsh-skills.git <任意位置>\dsh-skills
   cd /d <那个位置>\dsh-skills
   install.bat                      REM ★ 默认 Junction：以后 git pull 即同步
                                    REM ★ 想要独立副本 ⇒ install.bat -Copy
                                    REM ★ 干跑看看 ⇒ install.bat -WhatIf
   REM ★ 原理：技能放在 %DSH_HOME%\skills\ 下（空则默认 %USERPROFILE%\.dsh\skills\）
   REM ★ 放进去即生效，**不用重启 DSH**（DSH 热加载技能目录）
   REM ★ 台账依据：§E-7-a（★ 含三条实测坑：UTF-8 BOM / 执行策略 / rmdir 删联接）
```

★ **恢复节点 tag**（★ 出问题回这里）：
```
★ 后端：`recovery-20261013-scheduler-audit`（★ 时间戳判定 + 循环轮数守卫）
★ 前端：`recovery-20261013-isolated-live`（★ 隔离构建身份）
★ 回退：git checkout <tag>
```

---

# §7 ★ 踩过的坑（★ 别再踩）

| # | 坑 | 症状 | 正解 |
|---|---|---|---|
| **1** | ★ **前端放在 `D:\MuMuPlayer\OAS\` 下** | ★ **双击打不开** | ★ 那个目录被内核驱动 `PassGuard_x64.sys` 打了保护标记（含非标准 SID `S-1-4-225551088-58158104` + `Everyone Deny DeleteSubdirectoriesAndFiles`）⇒ ★ **前端不要放那里** |
| **2** | ★ 用 `robocopy` 拷前端源码树 | ★ `flutter build` 报 `Cannot create link … errno = 183` | ★ 删掉 `windows\linux\macos\flutter\ephemeral` + `.dart_tool` + `build` ⇒ 再 `pub get` + build |
| **3** | ★ 改了源码没重编译 | ★ 界面还是旧的 | ★ `flutter build windows --release` |
| **4** | ★ 后端没重启 | ★ `/schema` 还是旧的 ⇒ 界面选项不变 | ★ 重启后端 |
| **5** | ★ 起错目录的 exe | ★ 界面是旧版的 | ★ 只起 `build\windows\x64\runner\Release\oasx-live.exe` |
| **6** | ★ 用"删+建同名前缀目录"混在一次清理里 | ★ 误删了实机目录 | ★ 删前**逐个核对完整路径**；★ 先建新的、验完再删旧的 |
| **7** | ★ 清理时忘了 `adb.exe` 被 adb server 占用 | ★ 目录删不净 | ★ 先 `adb kill-server`（或结束 adb 进程）再删 |
| **8** | ★ `pip install -r requirements.txt` 报 `UnicodeDecodeError: 'gbk'` | ★ 装依赖失败 | ★ `requirements.txt` **必须纯 ASCII**（中文注释移到 `requirements-notes.txt`）|
| **9** | ★★ **[10-15] `flutter` 的"版本检查"跑 `git fetch --tags`（611285 个对象）** | ★ `flutter --version` 或任何不带开关的命令**卡 10+ 分钟**；后台常驻 `git fetch --tags` + `git index-pack`（★ `git remote-https origin https://github.com/flutter/flutter.git`）| ★ **命令一律加 `--no-version-check`**；★ 并设 `PUB_HOSTED_URL` / `FLUTTER_STORAGE_BASE_URL` 为国内镜像；★ 已卡的进程要 `Stop-Process git,dart` + 删 `bin\cache\lockfile` 才能重来 |
| **10** | ★★ **[10-15] 本机没有 C++ 工具链** | ★ `flutter build windows --release` 报找不到 Visual Studio | ★ 装 **VS 2022 Build Tools**（`Microsoft.VisualStudio.Workload.VCTools` + Win10/11 SDK）；★ 本机**也没有 `winget`** ⇒ 要用官方 `vs_BuildTools.exe`；★ `analyze` / `test` 不需要它 |
| **11** | ✅ **[10-15] 跑测试后 `docs/flows/README.md` 幻影变脏 —— ★ 已根治（T0-1）** | ★ `git status` 显示 ` M`，但 `git diff --numstat` **为空** · `--ignore-cr-at-eol` **0 行** | ★★ **真因两处**：① `task_factory._register_in_flow_index()` 用 `read_text()`（universal newlines ⇒ CRLF→LF）读 + `newline=''` 写 ② ★★ **`tests/module/test_task_factory.py` 的 `probe` fixture** 用 `read_text()` 备份、收尾 `write()` 写回 ⇒ 收尾把整份台账还原成 LF（★ 主因）。★ **已修**：读 `newline=''` + 按原行尾拼回；fixture 改 `read_bytes()`/`write_bytes()`。★ 判据：跑两守卫后该文件 **字节 + SHA256 均不变** ⇒ `git status` 干净 |
| **12** | ★★ **[10-15] `pwsh` 工具整个会话不可用** | ★ 每条命令都返回 `exit code 3221225794`（= `0xC0000142` STATUS_DLL_INIT_FAILED）且**零输出**（★ 连 `echo hi` 都失败）| ★ **续跑/重启 DSH 会话**（★ 不是重启电脑）；★ 期间用 `read`/`grep`/`glob` 工具继续取证 |
| **13** | ★★ **[10-15] `.bat` 里写中文 ⇒ cmd 把 REM 行**误解析成命令**** | ★ 每条命令都多出**假报错**（`'去盘符：靠' is not recognized` · `'sts.bat' is not recognized`），★ 且 `cmd /c` 的**退出码被污染成 1**（★ 明明 `16 passed`）| ★ **`run-tests.bat` / `run-server.bat` / `dev_tools\flutter.bat` 一律【纯 ASCII】**（★ 与 `session-memory` 技能同一条教训：★ **通用脚本 = 纯 ASCII**，不是"记得加 BOM"）；★ [10-15] 已全部改写并复验 |
| **14** | ★★ **[10-15] `__pycache__` 残留**旧盘符路径** ⇒ 测试输出路径是错的** | ★ 换机器/换盘（`robocopy`）会把 `__pycache__` 一起搬 ⇒ `.pyc` 里 `co_filename` 仍是旧盘符 ⇒ ★ pytest 的 SKIPPED/FAILED 行显示 `E:\OAS-dev\backend\tests\…`（★ 会让人**误判"测试不是在 D 盘跑的"**）| ★ **换机器/换盘后清一遍 `__pycache__`**（★ [10-15] 实测清掉 **342** 个）；★ 判据：输出路径必须与 `%~dp0` **一致** |
| **15** | ★ **[10-15] Python 在 GBK 控制台 print 中文会**乱码** | ★ `dev_tools\flutter.bat` 的输出里 `★ Flutter SDK :` 全成 `��` ⇒ ★ **会让人看漏真正的报错** | ★ 工具里 ① `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` ② **提示语只用 ASCII**（★ `dev_tools/run_flutter.py` 已按此改）|

---

# §8 ★ 文档纪律（★ 用户明令）

```
★ ① `docs/DESIGN-SPEC.md`  —— 软件**应该是怎样的**（设计 + 论断 + 分歧块）
     ★ 不是流水账；★ 每条要有 `文件:行号` 证据
★ ② `docs/PENDING-LEDGER.md` —— **未完成台账**
     ★ 每条：编号 · 事项 · 依据 · 状态（⬜/🔄/✅/⛔）· 验证方式
     ★ "已完成"必须有**可核查证据**（测试输出 / 日志 / diff）
★ ③ ★ **不许阴奉阴违**：
     ★ 用户的话 = 规格；★ 不许降级成"打补丁"；★ 规格与代码冲突时**以规格为准**并记进对照表
★ ④ ★ **逐步法**：★ 一次只改 1~2 个边界 ⇒ 立刻测 ⇒ 再做下一步
★ ⑤ ★ **完成定义**：★ 说"完成"前先列勾选清单；★ 没勾完不许说完成
```
