# 开发 / 测试 / 实机 工作流（★ 本文是**唯一**的流程依据）

> ★★★ **[2026-10-13] 用户裁定**：★★ "**规划下怎么开发和测试，我需要一个开发，
> 一个实机运行，考虑下只保留 dev 开发，实机用 dev 拷贝过去，前端也这样操作**"
>
> ★ 同日用户还裁定：★ "**全部删光吧，除了两份配置文件：伴生树、恋鳥樹**"

---

# §1 ★ 目录结构（唯一真相 = **git**）

```
D:\OAS-dev\                              ← ★★ **唯一开发工作区**
│
├── backend\                             ← 后端（git 仓库 · 分支 main）
│   ├── .git\                            ★ **只在这里改后端代码**
│   ├── script.py · server.py · module\ · tasks\ · tests\ · docs\
│   ├── config\
│   │   ├── template.json                （在 git）
│   │   ├── deploy.yaml                  ★★ **不在 git**（.gitignore 排除）
│   │   ├── 伴生树.json                   ★★ **你的账号配置**（不在 git）
│   │   └── 恋鸟树.json                   ★★ **你的账号配置**（不在 git）
│   ├── toolkit\                         ★★ **不在 git**（Python 运行时 + 依赖，1.1 GB）
│   └── console.bat                      ★★ **不在 git**（启动脚本）
│
└── frontend\                            ← 前端（git 仓库 · 分支 main）
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
| ★ 后端 `toolkit\` | ❌ | ★ 从 `OnmyojiAutoScript-easy-install.rar` 解压，或复制旧机器的 `toolkit\` |
| ★ 后端 `config\deploy.yaml` | ❌ | ★ **必须在每台机器上单独准备**（端口/模拟器等本机设置） |
| ★ 后端 `config\*.json`（账号配置）| ❌ | ★ **用户数据**，只能靠备份 |
| ★ 后端 `console.bat` | ❌ | ★ 见 §5 模板 |
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
cd /d D:\OAS-dev\backend
toolkit\python.exe server.py
REM ★ 默认监听 127.0.0.1:22288（见 config\deploy.yaml 的 WebuiPort）
```

```bat
REM ★ 前端（开发）—— 改完代码后重新编译
cd /d D:\OAS-dev\frontend
D:\flutter3271\bin\flutter.bat build windows --release
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
cd /d D:\OAS-dev\backend
toolkit\python.exe -m pytest tests/ -q
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
cd /d D:\OAS-dev\backend
toolkit\python.exe -m pytest tests/module/config/test_loop_rounds.py -q
toolkit\python.exe -m pytest tests/module/config/test_no_false_completion.py tests/tasks/test_effective_target.py -q
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
cd /d D:\OAS-dev\frontend
D:\flutter3271\bin\flutter.bat analyze lib     REM ★ 期望 0 error
D:\flutter3271\bin\flutter.bat test            REM ★ 单元测试
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

```
① 拉源码
   git clone -b main https://github.com/passioki/OnmyojiAutoScript.git backend
   git clone -b main https://github.com/passioki/OASX.git               frontend

② 补"不在 git"的运行时
   · 把 `toolkit\`（Python 运行时）放到 backend\toolkit\
       ★ 来源：另一台机器的 backend\toolkit\，或 OnmyojiAutoScript-easy-install.rar
   · 建 backend\config\deploy.yaml（★ 至少要有 WebuiPort）
   · 放 backend\console.bat（§5 模板）
   · 把账号配置（`伴生树.json` / `恋鸟树.json`）放进 backend\config\

③ 验后端
   cd backend
   toolkit\python.exe -m pytest tests/module/config/test_loop_rounds.py -q   REM ★ 期望 8 passed
   toolkit\python.exe server.py                                             REM ★ 端口起来

④ 编前端（★ 必须，因为 ephemeral/build 不在 git）
   cd frontend
   D:\flutter3271\bin\flutter.bat pub get
   D:\flutter3271\bin\flutter.bat build windows --release

⑤ 起实机（§4 的拷贝法）
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
