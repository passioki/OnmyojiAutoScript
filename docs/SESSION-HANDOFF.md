> ★★★ **新会话请先读 `docs/START-HERE.md`**（唯一入口 —— 它写死了"读什么/做什么/回报什么"）
# 会话交接单（SESSION HANDOFF）★ **一页纸，先看这个**

> ★★★ **本文件的目的**：解决两个已知问题
>
> 1. ★ **换新会话后交接不明朗** —— 新会话不知道"现在在哪、下一步干什么"
> 2. ★ **单一会话记忆压缩后开发逐渐走偏** —— 压缩会把结论磨成"我记得"
>
> ★ **规则**：★ **每轮对话结束时更新本文件**；★ **新会话第一件事就是读它**。
> ★ 本文件**只放"当前状态 + 下一步 + 活跃的坑"**，★ 不放历史（历史在 git log 与台账里）。

---

## ★ 0. 三十秒自检（★ 新会话必做）

```bat
cd /d D:\OAS-dev\backend

REM ① 代码是不是我以为的那一版
git log -1 --format="%h %ci %s"
git status --porcelain

REM ② 台账里"进行中/未开始"的有哪些
findstr /n /c:"🔄" /c:"⬜" /c:"⛔" docs\PENDING-LEDGER.md

REM ③ 强制跑守卫（★ 期望：全部 passed）
toolkit\python.exe -m pytest tests/test_comment_drift.py tests/test_task_flow_docs.py tests/module/config/test_standby_placeholder.py tests/module/config/test_entry_target_reached.py tests/module/server/test_help_texts_current_ui.py tests/module/server/test_profile_name_from_user.py tests/module/server/test_profile_transfer_keeps_enables.py tests/tasks/Component/SwitchSoul/test_switch_soul_validation.py tests/tasks/test_rest_random_minutes.py tests/module/config/test_loop_rounds.py -q
```

★ 三条都对得上 ⇒ ★ **可以开工**；★ 对不上 ⇒ ★ **先修对齐，别改代码**。

---

## ★ 1. 当前状态（★ 每次更新）

| 项 | 值 |
|---|---|
| ★ **日期** | 2026-10-14（★ 上轮 10-13）|
| ★ **开发工作区** | `D:\OAS-dev\`（`backend\` + `frontend\`，★ 各自是 git 仓库）|
| ★ **实机** | `D:\OAS-live\`（★ dev 的**拷贝**；端口 **22287**；开发用 **22288**）|
| ★ **后端分支/提交** | `main` · ★ **[本次提交后取 `git log -1`]**；★ ★ **远端 `dev` 已含本轮全部提交**（★ **`main` 远端未动** = `e28793ce`）|
| ★ **前端分支/提交** | `main` · ★ **`9c66064`**（★ 远端 `dev` 同）|
| ★ **恢复节点 tag** | 后端 `recovery-20261013-scheduler-audit` · 前端 `recovery-20261013-isolated-live` |
| ★★ **测试基线（★ 实测 [10-14]）** | 后端全量 = **49 failed / 1785 passed / 12 skipped**（★ 失败集**与基线逐条相同** ⇒ ★ **这 49 条是"已知环境类"**：★ 43 = 读 `D:/OAS-dev/OASX-src`（本机是 `frontend`）· ★ 4 = 缺 `module/config/i18n/zh-CN.json`（★ 前端推来的运行时产物）· ★ 2 = 读用户/实机状态 · ★ 1 = live 配置 · ★ 1 = 顺序 flaky）<br>★ 前端 = `flutter test` **158 passed** · `flutter analyze` **0 error**（4 条既有 info）|
| ★★ **`pwsh` 可用性** | ★★ **可用** ⇒ ★ 我能自己跑 pytest / flutter（★ 不必再让用户代跑）|
| ★ **实机是否在跑** | ★ 后端 `:22287`（`D:\OAS-live\backend`）|

## ★ 1b. ★★★ [10-14] 本轮做完的（★ 供交接，★ 不必重做）

```
★ 【10 条反馈：9 条已交付】
  N9-1 ★★P0  循环跑完报错 → 待命占位用大驼峰键 ⇒ KeyError ⇒ 调度循环死掉
             修：config.py 的 Function('restart')（小写键）+ 守卫 5 条（注入真红）
  N9-2       强制休息在跑吗 → ★ 实测三个配置 anti_ban.enable 全 False ⇒ 没在运行
  N9-3       休息 ±20% 随机 → 新增 randomized_rest_minutes()（均匀·整分钟·下限1）
             守 14 条（含"均值居中"）+ 注入 2/2 真红；★ 配置不被改写
  N9-4       新建页名字不生效 → 前端既不弹框也不传 name ⇒ 后端永远自动编号
             修：新增 _askProfileName()（与重命名同款）+ 传 name
  N9-5 🔄    逐任务流程图 → ★ 样板 docs/flows/RealmRaid.md + 55 任务登记台账
             + 守卫（新增任务漏登记必红）；★ 剩 54 张
  N9-6 🔄    annotator 新建任务 → ★★ 规格已定型（§1.16 NT1~NT7 + §1.17 NL1~NL7）
             ★ 卡在一个【架构选择】⇒ 见 §2 的第 1 项
  N9-7       周期任务无"运行中"tag → 三层真因（/run_list 只遍历 run_list +
             周期任务 entry_id=None + 前端只标那一行）⇒ 前端修（自动补齐行补 running）
  N9-8 ★★   复制执行顺序页多出自身周期任务 → ★ 已复现（A 开 orochi、B 开
             abyss_shadows ⇒ 转移后 B 变成 ['orochi']）⇒ 转移时剥掉 enable
  N9-9 ★★   御灵之境换御魂出错被跳过 → 出厂默认 '-1,-1' ⇒ get_group_assets(-1)
             抛 KeyError（非 ValueError）⇒ 旧 except 抓不住 ⇒ 整局任务被终结
             （★ 25+ 个任务通用）⇒ 修：先校验 + 响亮跳过
★ 【用户没点名、我自己抓出来的】：N2 注释漂移 3 处 · N5 前端台账 · N4（文档已改）
★ 【产出】规格书新增 6 个小节 + §4.5-㉑~㉚ · 后端 17 提交 · 前端 3 提交（都在 dev）
★ 【方法论】★ 空转守卫抓到 4 次 ⇒ 铁律："注入破坏后仍 pass ⇒ 守卫作废、必须重写"
   ① update_scheduler() 会覆盖外部设定（要 monkeypatch 打桩）
   ② 模板里 Restart 默认启用 ⇒ 走"出路①"不到被测分支（要同时清 pending+waiting）
   ③ 源码级"比行序"的守卫是空转的（要运行时断言）
   ④ 关键词在"别处"命中 ⇒ 假通过（判据要限定范围：开头 N 行 / 窗口）
   ★ 附：pwsh 的 -replace 是正则且 $ 展开、-m 里中文引号会被吞
     ⇒ 注入与提交信息一律走 Python str.replace / git commit -F 文件
```

## ★ 2. ★★ 下一步（★ 按优先级）

| # | 事项 | 依据 | 状态 |
|---|---|---|---|
| **★1** | ★★★ **等你点头：N9-6 的架构选择** —— ★ **A 受控指令集（DSL，我推荐）** vs ★ **B 直接编辑 Python**（★ 工具端点**无鉴权** ⇒ B = **远程代码执行**）★ 或折中 **A+**（指令集 + **解析式表达式**，不用 `eval`）| **SPEC §1.17 一** | ⬜ **阻塞（★ 等用户一句话）** |
| **★2** | ★ **N9-6 P1**（★ 架构定了就开工）：★ 后端 `tasks/create`（NT1~NT4：★ **原子创建 + 回滚** + **命名校验前置** + **示例识别骨架**）+ ★ `flow.json` **解释器**（NL1/NL2）+ ★ **立即运行**（NL3）+ ★ **结构化日志**（NL4）| **SPEC §1.16 + §1.17** | ⬜ 待启动 |
| **★3** | ★ **N9-6 P2**：★ 前端「任务编排」面板（★ 指令增删改 · 素材下拉 · 立即运行 · 实时日志）| SPEC §1.17 三 | ⬜ |
| **★4** | ★ **N9-6 P3 验收**：★ **新建一个周期任务 + 一个临时任务并跑通**（★ 用户原验收定义）| SPEC §1.16-NT6 | ⬜ |
| **★5** | ★ **N9-5 续**：★ 流程图**剩 54 张**（★ 建议顺序 `Exploration` → `Orochi` → `Rest` → `GeneralBattle`，★ 登记台账已就绪 ⇒ **只写不改**）| `docs/flows/README.md` | 🔄 进行中 |
| **★6** | ★ **前端 F5~F8**（★ 见 `frontend/docs/PENDING-LEDGER.md`）：★ 自动补齐行是否也该显示"已运行 N 次" · `zh-CN.json` 推送时机 · `generated_plugin*` 反复变脏 · 测试基线 | 前端台账 §一 | ⬜ |
| **★7** | ★ **实机验收**（★ 用户明令"**暂不验收，继续做**"⇒ 等指令）⇒ ★ 把 dev 拷到 `D:\OAS-live`；★ **N9-7/N9-4 需先** `flutter build windows --release` | 台账 §C | ⬜ **等指令** |
| **★8** | ★ **旧账未动**：`S3b`（门④临时任务队列过滤）· `D7.4` · `D43` · `D45` · `F4` · `DOC4` · `DOC5` · `O1` · `O2` · `T9/T11/T14` | 台账 §一~§六 | ⬜ |

## ★ 3. ★ 活跃的坑（★ 别再踩）

| # | 坑 | 一句话 |
|---|---|---|
| **P1** | ★ **`"播放模式"` 这个标题是用户要求删掉的** ⇒ ★ 前端该处**只有下拉**（顺序/循环/乱序），★ **不要"修复"成带标题** | 用户明令 |
| **P2** | ★ **前端不能放 `D:\MuMuPlayer\OAS\` 下** | 内核驱动 `PassGuard_x64.sys` 打了保护标记 ⇒ 双击打不开 |
| **P3** | ★★ **守卫必须"真会红"** ⇒ ★ **每个新守卫都要做注入验证**（★ 本轮抓到 **4 次空转**）| 台账 §C.3 |
| **P4** | ★ **`toolkit\` / `config\deploy.yaml` / 账号配置 / `console.bat` 不在 git** | 清理目录前必须先抢救（`DEV-WORKFLOW.md` §1）|
| **P5** | ★ **删目录前逐个核对完整路径** | 已因"删+建同名前缀混用"误删过 `D:\OASX-Live` |
| **P6** | ★ **删含 `adb.exe` 的目录前先 `adb kill-server`** | 否则删不净 |
| **P7** | ★ **`pwsh -replace` 注入会静默不生效**（正则 + `$` 展开）| ★ **注入一律用 Python `str.replace`** + 打印"是否生效" + 还原比 SHA256 |
| **P8** | ★ **`git commit -m` 带中文引号/反引号会被 PowerShell 吞** | ★ **用 `git commit -F <文件>`**（★ 文件放**仓库外**，否则会误提交）|
| **P9** | ★ **`/tool/annotator` 的写端点【无鉴权】**（`tool_router.py` 无 `Depends`；`app.py:112` 的 `-k/--key` **从未被使用**）| ★ 这直接决定了 N9-6 的架构选择（见 §2-★1）|
| **P10** | ★ **测试去读 `D:/OAS-dev/OASX-src`**（本机没有；真实前端在 `frontend`）| 那 43 条失败是**环境类**，不是回归 |

## ★ 4. ★ 文档权威顺序（★ 冲突时）

```
① docs/DESIGN-SPEC.md  §1~§3 正文（★ 用户的话 = 规格）
② docs/DESIGN-SPEC.md  §1.6.x / §1.14.x / §1.15 / §1.16 / §1.17 / 分歧块
③ docs/PENDING-LEDGER.md（状态与依据）
④ 本文件 SESSION-HANDOFF.md（当前状态与下一步）
⑤ docs/DEV-WORKFLOW.md（流程）
⑥ 代码（★ 与 ①~⑤ 冲突 ⇒ ★ **以 ①~⑤ 为准**，并把冲突记进 SPEC §4）
```

## ★ 5. ★ 文档地图（★ 新会话找东西用）

| 想看什么 | 去哪 |
|---|---|
| ★ 软件**应该是怎样** | `docs/DESIGN-SPEC.md`（★ 2246+ 行，★ 按 § 找）|
| ★ **还没做完的** | `docs/PENDING-LEDGER.md`（★ 后端）· `frontend/docs/PENDING-LEDGER.md`（★ 前端）|
| ★ 怎么开发/测试/部署 | `docs/DEV-WORKFLOW.md` |
| ★ 逐任务流程 | `docs/flows/README.md`（索引）· `docs/flows/RealmRaid.md`（样板）|
| ★ 调度器架构 | `docs/scheduler-architecture.md` |
| ★ 会话整理产物 | `docs/SESSION-INDEX.md` · `docs/DESIGN-SPEC-PROGRESS.md` |
| ★ annotator 调研结论 | ★ 台账 §C.1 的 `N9-6` 行 + **SPEC §1.16**（★ 契约 4 文件 + 现状缺口）|

## ★ 6. ★ 交接模板（★ 换会话时，把这段填好发给新会话）

```
【本次会话做了什么】
  10-14：修 9 条反馈中的 9 条 + 2 项遗留（N2 注释/N5 前端台账）；
  规格书新增 §1.14.x（休息随机）/§1.15 /§1.16（新建任务）/§1.17（任务逻辑编辑器）
  /§3.9.7~3.9.9 + §4.5-㉑~㉚；后端 17 提交 + 前端 3 提交，全部推 dev
【当前代码状态】
  后端 main（本地领先远端 main 17 提交，★ 远端 dev 已同步）· 前端 main 9c66064
  后端全量 49 failed / 1785 passed（49 条是已知环境类）· 前端 158 passed
【下一步（按优先级）】
  1. ★ 等用户点头 N9-6 的架构选择（A 指令集 / B 直接 Python / A+ 折中）
  2. ★ N9-6 P1 后端（创建 + 示例骨架 + 解释器 + 立即运行 + 日志）
  3. ★ N9-6 P2 前端编排面板 → 4. P3 端到端验收
  5. ★ N9-5 剩余 54 张流程图（★ 登记台账已就绪，只写不改）
  6. ★ 前端 F5~F8
【已知坑 / 不要做的事】
  P1 不要给"播放模式"加标题 · P3 守卫必须做注入验证 ·
  P7 注入用 Python 不用 pwsh · P8 提交信息走 -F 文件 · P9 annotator 写端点无鉴权
【需要用户裁定的事】
  ★ N9-6 的架构选择（见 SPEC §1.17 一）
```
