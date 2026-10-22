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
REM ★ 去盘符：以下命令都在 backend\ 里跑（包装脚本内部用 %~dp0，与 cwd 无关）

REM ① 代码是不是我以为的那一版
git log -1 --format="%h %ci %s"
git status --porcelain

REM ② 台账里"进行中/未开始"的有哪些
findstr /n /c:"🔄" /c:"⬜" /c:"⛔" docs\PENDING-LEDGER.md

REM ③ 强制跑守卫（★ 期望：全部 passed —— ★ [10-14] 第三轮 = 135 条）
run-tests.bat tests/test_comment_drift.py tests/test_task_flow_docs.py tests/module/config/test_standby_placeholder.py tests/module/config/test_entry_target_reached.py tests/module/server/test_help_texts_current_ui.py tests/module/server/test_profile_name_from_user.py tests/module/server/test_profile_transfer_keeps_enables.py tests/tasks/Component/SwitchSoul/test_switch_soul_validation.py tests/tasks/test_rest_random_minutes.py tests/module/config/test_loop_rounds.py tests/tasks/test_no_ticket_is_success.py tests/module/flow/test_control_types.py tests/module/config/test_entry_custom_state.py -q
```

★ 三条都对得上 ⇒ ★ **可以开工**；★ 对不上 ⇒ ★ **先修对齐，别改代码**。

---

## ★ 1. 当前状态（★ 每次更新）

| 项 | 值 |
|---|---|
| ★ **日期** | ★ **2026-10-15**（★ 上轮 10-14 · ★★ **[10-15] 本机换成了【新开发机 `D:\OAS-dev`】**）|
| ★ **开发工作区** | ★★ **[10-15] 本机 = 开发机** ⇒ **`D:\OAS-dev\`**（`backend\` + `frontend\`，★ 各自是 git 仓库 · ★ **两仓的本地分支都是 `dev`**）<br>★ **[10-15] 本机是【新引导的开发机】**：两仓 `git clone -b dev` ＋ `toolkit\`/`deploy.yaml`/两份账号配置/`console.bat` 从 `C:\Users\passioki\Downloads` 补齐（★ 详见 §1j）|
| ★ **实机** | `D:\OAS-live\`（★ **在【另一台电脑】上**；★ dev 的**拷贝**；端口 **22287**；开发用 **22288**）★★ **不许在它上面做开发/测试**（★ 坑 P14）<br>★ ⚠ **[10-15] 本机没有 `D:\OAS-live`** ⇒ ★ 实机验收不在本机做 |
| ★ **后端分支/提交** | ★★ **[10-15] 开发机（`passioki` / `D:\OAS-dev\backend`）实测**：★ 本地 **`dev` = 见 §1 末「本轮入口实测」** · ★★ 远端 `dev` **与本地同 hash**（★ **开发分支** —— ★ 另一台拉这个）· ★★ **远端 `main` = `e28793ce`**（10-13 15:44 · ★ **主要的稳定版本 · 未动**）<br>★ ⚠★ **一律 `git push origin dev`**（★ 本机本地分支就叫 `dev` —— ★ **不是**旧机的 `main`）；★ 旧机那种"本地 `main`"的机器才要 `git push origin main:dev`，★ **绝不 `main:main`**（★ [10-15] 误推过一次 ⇒ 已 `--force-with-lease` 回退）|
| ★ **前端分支/提交** | ★★ **[10-15] 开发机（`D:\OAS-dev\frontend`）实测**：★ 本地 **`dev` = 见 §1 末「本轮入口实测」** · ★★ 远端 `dev` **与本地同 hash** · ★★ **远端 `main` = `af10440`**（10-13 12:25 · ★ **恢复节点 / 稳定版本 · 未动**）|
| ★ **恢复节点 tag** | 后端 `recovery-20261013-scheduler-audit` · 前端 `recovery-20261013-isolated-live` |
| ★★ **测试基线（★★ [10-15] 开发机 `D:\OAS-dev` 实测复现）** | ★ **守卫 = 170 passed**（**15 个文件** —— ★ [10-15] 把 `test_no_hardcoded_paths.py` 并进清单 · 5.03s）<br>后端全量 = **14 failed / 1904 passed / 7 skipped**（85.80s · ★ **14 条 = 已知环境/用户状态类**：**9** 缺 `module/config/i18n/zh-CN.json`（★ 前端**运行后**经 `/chinese_translate` 推来的运行时产物）＋ **2** 用户/实机状态（`test_task_report`）＋ **1** 窗口外任务（`test_schema_router`）＋ **1** 用户配置（`test_task_catalog`）＋ **1** live 配置（`test_queue_clear_and_settings`）⇒ ★★ **真漂移已修**，那 1 条不再红）<br>★ 前端 = `flutter analyze` **0 error（4 warning + 17 info）** · `flutter test` **160 passed**（★ [10-15] 新增 2 条 F9 可达性守卫）<br>★★ **与台账 §E-6-o 的旧口径差异只在于"真漂移已修 + F9 守卫 +2"** ⇒ ★ 这台开发机**可以开工** |
| ★★ **`pwsh` 可用性** | ★★ **[10-15] 可用**（★ 但本会话开场时**整段不可用**：每条命令返回 `exit code 3221225794` = `0xC0000142`，★ 续跑后自行恢复 ⇒ ★ 见 §3 坑 **P7**）⇒ ★ 我能自己跑 pytest / flutter（★ 不必再让用户代跑）|
| ★ **实机是否在跑** | ★ ⚠ **[10-15] 与开发机无关**（实机在另一台电脑上）· ★ 开发机实测：**`:22287`/`:22288` 都没有监听**；★ `E:\MuMuPlayer` 已安装但**模拟器未运行**（`16384` 未监听）|

### ★★★ 本轮（[10-15] 第二次开工）的提交 —— ★ 下一会话从这里开始

```
★ 开发机（passioki）· D:\OAS-dev
【入口实测（本轮开工那一刻）】★ 留作对照，**不是**现在的 HEAD
  后端：本地 dev = 7459e1ad = 远端 dev · 远端 main = e28793ce（未动）
  前端：本地 dev = 1a31709  = 远端 dev · 远端 main = af10440（未动）
  守卫（15 文件）= 170 passed · 全量 = 14 failed / 1904 passed / 7 skipped
  前端 = analyze 0 error（4w+17i）· test = 160 passed
【★★ 本轮结束已推送（★ 以 `git log -1` 为准）】
  后端：本地 dev = 7948e768 = 远端 dev（★ 7459e1ad → caa11b3a → 7948e768）
  前端：本地 dev = 8da0f2a = 远端 dev（★ 1a31709 → 8da0f2a）
  ★ 两仓 worktree 均**干净** · ★ 推送全程 `dev..origin/dev` **为空** ⇒ 无需 rebase · ★ **没有 force**
  ★ 本轮动了代码（F9 + 真漂移收敛 + .bat/.py 工具）⇒ ★ 下一会话的守卫/全量基线不变：
    ★ 守卫 **170** · 全量 **14 / 1904 / 7** · 前端 **0 error + 160 passed** · ★ `build windows --release` **可用**
```

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

## ★ 1c. ★★ [10-14] 第二轮做完的（★ 交接用 · ★ **本轮只动文档，没动一行代码**）

```
★ 【入口自检】守卫 **98 passed** · 全量 **15 failed / 1785 passed / 12 skipped** · 前端 **0 error + 158 passed**
   ⇒ ★ 与 [10-14] 基线**逐数字一致**
★ 【订正】4 处实测不符的数字（★ 你已授权"确认事实就订正"）：
   ① 本文件 §一「35 failed / 1696 passed」→ **49 / 1785**（旧值）
   ② 本文件 §1 + START-HERE §1.3 + 前端台账 F8 的「4 条既有 info」→ **4 warning + 17 info**
   ③ 前端台账 F8 的「157 passed」→ **158 passed**
★ 【交付 N9-5】逐任务流程图 **7 张**（`Tako` 石距 · `Orochi` · `RyouToppa` 寮突破 · `AreaBoss` ·
   `DailyTrifles` · `WeeklyTrifles` · `AutoCheckinBigGod`）+ README 登记表（★ 8 张 ✅ + 补链接）
   + ★ **任务中文名按 `meta.py` 订正 18 处**（如「章鱼」→「石距」、「突破」→「寮突破」）
   ⇒ ★ 守卫 `tests/test_task_flow_docs.py` = **4 passed**
★ 【规格】★ 新增 **§1.18「接口模块化」**（★ 用户第 1 项需求：把接口抽成模块 ⇒ 任何流程图都能落到代码上）
   + §4.5-**㉛** 登记 ⇒ ★ **方案待你点头：M1 只做原语层 / M2 原语层 + 解释器（我推荐 M2）**
★ 【台账】★ 新增 **§D.3**（本轮交付）· **§D.4**（`FL-1`~`FL-10` 新发现，★ 全部带 `文件:行号`）
★ ⚠★ 【数字口径】★ 守卫里有 **2 条会自己变红/绿**：`test_standby_placeholder` 的 ④⑤
   （★ 用例内跑**真调度** ⇒ 依赖实时状态）⇒ ★ 同一天 **22:55 = 98 passed**、**23:01 = 96 passed / 2 failed**，
   而两次之间**只有文档改动**（`git status` 只列 `docs/**`）⇒ ★ **不是代码回归** ⇒ 见 §D.4 的 `FL-9`
★ 【新坑】**P11** 沙箱 `workspace-write` 假红（125 errors）· **P12** 原生命令**别接管道** ·
   **P13** 核对行号**别用 `Get-Content`**（少算 10 行 ⇒ 行号错位）
```

## ★ 1d. ★★★ [10-14] 第二轮**用户裁定后的修复**（★ 有代码改动 + 守卫）

```
★ 【裁定】★ 用户 [10-14]：①**M2**（= §1.17 的 A/A+ 受控指令集；★ annotator **可以深度拆解**进任务实现器）
   ②**没票算成功**（"本来就是清票，票没有了就不用清了"）③④ `FL-6`/`FL-8` **待定**（后续可能重构）
   ⑤ `FL-9` **查清原因解决就行**
★ 【修 1｜㉜】`RyouToppa`（寮突破）"没票"不再记失败 —— `success = False` ➜ **不改 success** +
   `mark_entry_completed('没票了（本轮结束）')` + 中文日志（★ 与样板 `RealmRaid:180-200` 对齐）
   ⇒ ★ 新增守卫 `tests/tasks/test_no_ticket_is_success.py`（**8 条 · AST 级**，覆盖 `RyouToppa` + `RealmRaid`）
   ⇒ **8 passed** · ★★ **注入验证 2/2 真红** + 还原后逐字节一致
★ 【修 2｜㉝】`FL-9` 守卫"时红时绿" —— ★★ **根因（实测）**：`Restart` 的窗口 = **12:00-14:00 / 20:00-22:00**，
   `update_scheduler()`（`config.py:1946-1949`）在**窗口外**把"next_run 已过"的任务放进 **`waiting_task`**
   ⇒ 用例读 `pending_task` 就空（★ 同日 22:55 绿 / 23:01 红，期间**只有文档改动**）
   ⇒ ★ 修法：素材取 `pending or waiting` + ★ **加"哨兵 `entry_id`"**
   —— ⚠ ★ **原断言只比 `command`，而唯一默认任务是 `Restart`、占位也叫 `Restart` ⇒ 空转**（注入后照样绿！）
   ⇒ **注入验证 2/2 真红**（破坏 waiting / pending 分支各 1 failed）+ 还原 SHA 一致
★ 【查清·不修】`FL-2`（"满票被误判成没票"）★ **是误报**：`sub_ocr.py:166` 的 `DigitCounter` 返回
   `(current, total - current, total)` ⇒ ★ `cu + res == total` **恒真** ⇒ 条件等价于 `cu == 0`；
   ★ 而 `cu` = **可用票数**（佐证：`RealmRaid:378` 用 `cu < base` 判"票不够基准"）
★ 【顺手抓到】★ 新写的 `docs/flows/Tako.md` 提了**已删符号** ⇒ 触发 `test_docs_no_dead_refs`
   ⇒ ★ 已改写（★ 现行文档不许提已删符号 —— 这是**真守卫**，不是噪音）
★ 【数字】★ 守卫 **106 passed** · 全量 **15 failed / 1793 passed / 12 skipped**
```

## ★ 1e. ★★★ [10-14] 第三轮：**流程控制抽象**（★ 用户提问 → SPEC §1.19 · ★ 只动文档）

```
★ 【问题】用户看完 8 张流程图后问："实现这些流程，需要哪些抽象层面的控制"，
   并给了 4 条自认"太宽泛"的分类（是否该执行 / 成功失败 / 初始化 / 如何执行）
★ 【交付】SPEC **§1.19**：★ 把 4 条粗分类拆成 **9 个控制面 + 2 个支撑面**
   C1 准入（7 个调度门 + 任务内前置 · ★ 缺"推迟到某时刻"这一态）
   C2 准备（环境级/界面级/配置级 · ★ 缺 prepare() 契约）
   C3 骨架（★ 实测 5 种形状 · ★ 没有抽象）
   C4 判断（★ 返回 bool/tuple/int 三种混用）
   C5 动作（★ 5 个空缺 + 26 组重复）
   C6 出口（★ 8 类具名出口 · ★ 现在没有枚举）
   C7 结果（★ 三态：DONE/FAILED/**EXHAUSTED(=DONE)** + 2 上报对象 + 2 排期基准）
   C8 收尾（★ 与 C2 不对称）
   C9 容错 · C10 记忆（★ 缺"任务自定义状态"入口）· C11 接管（★ 三套失败语义）
   ★ 另附 **API 草案** + ★ **与 M2/DSL 的映射** + ★ **落地顺序（接 §1.18 的 P0~P3）**
★ 【实测矩阵】8 任务 × 12 控制点（★ 脚本统计 `script_task.py`，可复现）
★ 【三个红灯（★ 待你裁定）】
   ① 出口语义靠自觉（★ `AreaBoss` 出口 True/False/None 混用）
   ② 收尾与准备不对称（★ `AreaBoss`/`AutoCheckin` 不回庭院；★ `AutoCheckin` 失败路径不清理）
   ③ 暂停检查点只有一半任务有（★ `Tako`/`AreaBoss`/`DailyTrifles`/`WeeklyTrifles` 全 0
      ⇒ ★ 框架兜底只在 `PAUSE_BATTLE` 生效 ⇒ **`PAUSE_ROUND` 对它们 ≈ 不生效**）
★ 【台账】新增 **§D.6**（`N9-10` / `N9-10-a` / `N9-10-b`）
```

## ★ 1f. ★★★ [10-14] 第四轮：**P0 落地**（★ 用户"开工"裁定 · ★ 有代码 · ★ 零改行为）

```
★★ 用户裁定：①三个红灯"待定、记录下、后期可能重构暂不处理" ②"开工吧，先做最小代码验证，跑通整个流程"
★ 【交付】★ 新增 `module/flow/`（★ 4 个控制面里的 3 个文件）
   · `outcome.py`  = ★ C6 `Exit`（**8 类具名出口**）+ C7 `Outcome`（**三态** DONE/FAILED/EXHAUSTED）
                     + ★★ `finish()` = **唯一映射点**（★ 改语义只改这里）
   · `precondition.py` = ★ C1 `Verdict`（★ **三态：跑 / 跳过 / `defer_until`**）+ `Precondition` 协议
   · `match.py`    = ★ C4 `Match`（ok/score/roi/text —— ★ 终结 bool/tuple/int 混用）
   · `__init__.py` = 统一出口
★ 【交付】★ `module/config/task_state.py` 新增 **C10 任务自定义状态**（约 170 行）
   `get_state/set_state` + `get/set_entry_state` + `get/set_task_state`
   ★ **两级**（★ 周期任务 `entry_id=None` ⇒ 必须能按任务名存）· ★ 建在**既有落盘 + 锁**上
★ 【方法】★ 按 START-HERE：★ 先出「设计 vs 现状」→ ★ 逐步（先 types，再 state）→
   每步立刻 `pytest` → ★★ **注入验证**（2/2 真红）→ 更新台账/交接 → commit + push
★ 【数字】★ 守卫 **135 passed**（106 + 29）· ★ 全量 **15 failed / 1826 passed / 12 skipped**
   （★ 失败集与基线**逐条一致** ⇒ 无回归）· ★★ **零改行为**（★ 没动任何任务的 `run()`）
★ 【下一轮】★ **P1**：★ C5 补 5 个空缺（返回键/键盘/文本/滚动/拖拽）+ C9 的
   `LoopBudget/StuckGuard/RetryPolicy` 提到 `module/action/`
★ ⚠ 【仍待办】★ 三个红灯 ⏸ 待定（★ 等重构）· ★ `N9-5` 流程图 47 张 · ★ `N9-6` P1 后端
```

## ★ 1g. ★★★ [10-14] 第五轮：**「新建任务 → 测试」跑通**（★ 用户澄清后的正解 · ★ 有代码）

```
★★ 用户澄清："我说的最小代码跑通整个流程是指，**跑通新建任务、测试、运行这个流程**"
   ⇒ ★ 用户选定：★ "**只做到『测试』为止，运行由你在实机界面点**"
★ 【交付】★ 新增 `module/task_factory.py` —— ★ **新建任务工厂**（SPEC §1.16 NT1~NT4）
   · ★ 原子创建（临时目录 ⇒ `ast.parse` 自检 ⇒ `os.replace` ⇒ 失败 `rmtree` 回滚）
   · ★ 命名校验 `[A-Z][A-Za-z0-9]*` + 保留名 + 大小写不敏感查重（★ 路径穿越不可能）
   · ★ 安全空壳 + ★ **示例识别**（用全局素材 `I_UI_BACK_RED` ⇒ 开箱可跑）
   · ★ **自动登记** `docs/flows/README.md`（★ 否则流程图守卫变红）
   · ★ 自动 `window`（全天）+ 自动唯一 `list_pos`（★ 都是被守卫逼出来的合同）
★ 【交付】★ 守卫 `tests/module/test_task_factory.py`（**31 条**）⇒ 166 passed
   ★★ 注入验证 **3/3 真红**（关命名校验 ⇒ 10 failed；去回滚 ⇒ 1 failed；假装登记成功 ⇒ 2 failed）
★ 【跑通】★ 探针在**真 `tasks/`** 下建了又删；★ 实证：`task_catalog` 认到 · `ConfigBase` 子类在 ·
   `ScriptTask.run` 可调用 · ★ **新进程**里 `_CONFIG_CLASSES = ['flow_demo']` · `all_tasks()` 含它
★ 【修 bug】★ 工厂第一版只清 `reload_specs()` ⇒ ★ `all_tasks()`（走 JSON+合并缓存）**看不到新任务**
   ⇒ ★ **单跑测试绿、放进完整守卫链才红** ⇒ 已改成两个缓存都清
★★ 【最重要的发现】★ **"新建任务"远不止写 4 个文件** —— ★ 实测一次创建撞红 **14 条**项目级守卫，
   分 **6 类合同**（★ 明细见 SPEC **§1.16-五 NT8** 与台账 **§D.8-b**）：
   ① `window` 必须显式声明 ② `list_pos` 必须唯一 ③ 流程图台账必须登记
   ④ 必须重生成 `task_catalog_data.json` ⑤ 必须重生成 i18n（★ 且 `gen_i18n.py` **要前端仓库路径**，
      本机未配置 ⇒ 实测报"找不到 OASX 仓库"）⑥ ★ **"库存快照"类守卫**（★ `test_counts_are_15_and_40`
      写死 15/40 等）⇒ ★ 每加一个任务必红 ⇒ ★ **待你裁定**（台账 §D.9）
★ 【实机就绪】★ `D:\OAS-live\backend\tasks\FlowDemo\` 已装（4 文件）+ ★ 实机 `task_catalog_data.json` 已重生成
   + ★ **实机新进程验证通过** ⇒ ★ **你重启实机后端 + 在界面"添加任务"里加 `FlowDemo`（流程示例）即可跑**
   ★ dev 侧已撤掉（★ 保持基线绿：15 failed / 1858 passed）
★ 【数字】★ 守卫 **166 passed** · ★ 全量 **15 failed / 1858 passed / 12 skipped**（★ 失败集逐条一致）
```

## ★ 1h. ★★★ [10-14] 第六轮：**按你的纠正回退实机 + 在 dev 侧跑通"新建 → 测试"**

```
★★ 用户纠正（原话）："**不要在实机跑，现有开发基于dev侧，实机是版本稳定后直接从dev拷贝过去，
   请仔细阅读 D:\OAS-dev\backend\docs\START-HERE.md**"
★ 【纠错】★ 我上轮**错把新建的 `FlowDemo` 装进了实机**（`D:\OAS-live`）—— ★ 违反 START-HERE §0
   （★ 实机 = dev 的**拷贝**）⇒ ★ **已还原**：★ 删实机里的 `tasks/FlowDemo` + ★ 重生成实机
   `task_catalog_data.json` + ★ **实机新进程复验**：`get_spec('FlowDemo') = None`、**55** 个任务、
   `ConfigModel` 无 `flow` 命中
★ 【留在 dev】★ `tasks/FlowDemo/`（流程示例 · TIMED · NONE · 全天窗口）★ **就放在 dev** ——
   ★ 符合"**dev 开发 → 稳定后整份拷到实机**"的模型
★ 【修 bug】★ 工厂模板原写 `auto_queue=False` ⇒ ★ **违反项目不变量 `auto_queue == NOT countable`**
   （"次数任务不自动进队列，定时任务自动进"）⇒ ★ 改 `True`（★ 安全性由 `scheduler.enable=False`
   + 分组 `enable=False` 保证）⇒ ★ 2 条守卫转绿
★ 【补合同】★ 跑 `$env:OASX_REPO=D:\OAS-dev\frontend` + `python dev_tools/gen_i18n.py` ⇒ i18n 2 条转绿
   （★ 同时改了**前端 2 个 dart** ⇒ 一起提交）
★ 【同步盘点】★ "库存快照"类守卫 **6 处**按**项目既有先例**改数字并写明来历
   （★ 先例就在守卫自己的 docstring："14+40 ⇒ 新增 Rest 后 15+40"）
★ 【数字】★ 守卫 **166 passed** · ★ 全量 **15 failed / 1903 passed / 7 skipped**（★ 失败集逐条一致）
   · ★ 前端 **158 passed / 0 error**（★ 生成器改过 dart，也复跑过）
★ 【新坑】★ **P14**：★ **不许在 `D:\OAS-live` 上做开发/测试**（★ 已写进 START-HERE §0 + §3）
   ★ 顺带把 START-HERE §1.3④ 的**旧数字**（1785）改成实测值（1862）
★ 【下一步】★ **dev 侧"运行"** ⬜ 待你定：★ 起 dev 后端 `:22288` + dev 前端 ⇒ 打开「流程示例」开关
   + 加入执行队列 + 点 ▶ ★ ⚠ dev 的 `恋鸟树` 与实机**同一个模拟器**（`127.0.0.1:16384`）
   ⇒ ★ 要么先停实机后端 `:22287`，★ 要么给 dev 换设备
```

## ★ 1i. ★★★ [10-15] 第七轮：**两台机器分工 + dev 已推上 git + `F9`（暂停调度按钮缺失）**

```
★ 【用户两项指令（★ 逐字见台账 §E 与前端台账 F9）】
  ① "恢复调度按钮缺少了暂停调度，请添加到台账"
  ② "现在打算使用两台电脑，一台开发、测试稳定后，上传到github，另一台从git上更新，
     用于实机生产。本台电脑为实机生产用，所以需要你上传dev到git，
     确保另一台从git上取下来时可以无缝开发。"

★ 【① 的真因 = ★★ 死代码（★ 不是"忘了做"）】
  `frontend/lib/views/tasks/queue_panel.dart` 的两个 `else if` 条件【逐字相同】：
     `:1042`  `else if (isTask && e['running'] == true)`  → `[▶]` 恢复调度
     `:1059`  `else if (isTask && e['running'] == true)`  → `[⏸]` 暂停调度   ← ★ **永不执行**
  ⇒ ★ 佐证：全仓 `pause_circle_filled` **只 1 处**（`:1072`）· `_pauseSchedule` **只 1 处**（`:1071`）
  ⇒ ★ **界面上根本没有"暂停调度"入口**（★ 用户看到的正是"只有恢复、没有暂停"）
  ⇒ ★ 与 SPEC **§3.6 现行口径**不符（★ 设计只有三条：暂停中 `[▶]` / 运行中 `[⏸]` / 未运行 `[▶]` 描边）
  ⇒ ★ 修法 = **删掉 `:1042-1058` 这个多余分支**（★ `:1059` 自然可达）
  ⇒ ★★ **本轮按用户要求：只记进台账（前端 `F9`），未改代码**

★ 【② 的实测 + ★ 一次走偏与回退】
  · ★ 远端 `dev` **本来就 = 本地 `main`**（后端 `2650b6d2` · 前端 `3978598`）⇒ ★ **`dev` 无需再推**
  · ★★ **我走偏的一步**：★ 我**顺手把 `main` 也快进**到 dev（后端 `2650b6d2` · 前端 `3978598`）
    —— ★ **理由是"另一台 clone 默认拿 main"** ⇒ ★★ **但用户 [10-15] 纠正**：
    "**另一台可以拉dev啊，main是主要的稳定版本！**"
  · ✅ **已回退**（`--force-with-lease`）：★ 后端 `main` = `e28793ce`（10-13 15:44）·
    前端 `main` = `af10440`（10-13 12:25）⇒ ★ **`main` 回到"主要的稳定版本"**
  · ★ **现行分支策略**：★ `dev` = 开发分支（★ **另一台拉这个**）· ★ `main` = **稳定版本**（★ 冻结点）
    · ★ 本机本地分支名是 `main` ⇒ ★ **推送一律 `git push origin main:dev`**（★ 绝不 `main:main`）
  · ★★ **但 git 只给"源码级无缝"**：`toolkit\`（★ 实测 **17000 文件 / 1167.4 MB**）·
    `config/deploy.yaml` · **账号配置**（`恋鸟树.json`/`伴生树.json`）· `console.bat`
    —— ★ **全都不在 git** ⇒ ★ 清单见台账 **§E-1**（7 项）

★ 【新坑 **P15**】本机 `git` 报 `dubious ownership`（★ 仓库属主 = `Administrators`，当前用户不同）
  ⇒ ✅ 已 `git config --global --add safe.directory <backend|frontend>` 修好
  ⇒ ★ 沙箱 `workspace-write` 下**改不了** `~/.gitconfig`（`could not lock config file`）

★ 【四条基线复核（★ 实测）】★ 守卫 **166 passed** · ★ 全量 **15 failed / 1903 passed / 7 skipped**
  · ★ 前端 `analyze` **0 error（4 warning + 17 info）** · `flutter test` **158 passed**
  ⇒ ★ 与 [10-14] 基线**逐数字一致**

★ 【⚠ 用户口径里有一处矛盾（★ 待裁定）】"另一台…用于实机生产" vs "本台电脑为实机生产用"
  ⇒ ★ 我按**后者**执行（★ 本台 = 生产，另一台 = 开发）；★ 见台账 **§E-1** / `DEV-WORKFLOW.md §0.6`
```

## ★ 1j. ★★★ [10-15] 引导轮：本机（新开发机 `D:\OAS-dev`）从零到**四条基线全绿**

```
★ 【前提】★ 用户 [10-15] 明说"**本机是开发机**" ⇒ ★ 角色裁定：**本机 = 开发 / 另一台 = 实机生产**
   （★ 旧推断"本台=生产"**作废**；★ §0.6 与台账 §E-1 已同步）
★ 【① 源码】两仓 = `git clone -b dev`（★ 本地分支 `dev`，跟踪 `origin/dev`）
     · 后端 OnmyojiAutoScript → `D:\OAS-dev\backend`（★ `93f7a4db`）
     · 前端 OASX            → `D:\OAS-dev\frontend`（★ `ae1065b`）
     · ★ 本机 git = `C:\Program Files\Git\cmd\git.exe` **2.55.0** · ★ **没有** P15 的 dubious ownership
★ 【② 不在 git 的运行时】★ 来源 = `C:\Users\passioki\Downloads`
     · `toolkit\` → `backend\toolkit`（robocopy：★ **17000 文件 / 1167.4 MB**，与台账**一致**；rc=1=成功）
     · `deploy.yaml`（**6114 B** · `WebuiPort: 22288`）· `伴生树.json`（68437 B）· `恋鸟树.json`（85570 B）
       · `console.bat`（590 B）⇒ 分别落到 `backend\config\` 与 `backend\`
     · ★ 实测工具链：`toolkit\python.exe` = **Python 3.10.11** · `pytest 9.1.1` · adb.exe 在 toolkit 里
★ 【③ Flutter】★ 本机**原本没有** Flutter ⇒ ★ 装了 **Flutter 3.27.1**（Dart 3.6.0 · 引擎 `cb4b5fff73`）
     · 官方包 `flutter_windows_3.27.1-stable.zip` = **1045850748 B** ⇒ 解压 **`D:\flutter3271`**（2466 MB）
     · ★ 用**国内镜像** `storage.flutter-io.cn`（★ 实测 **3.5 MB/s**；Google 源仅 **~170 KB/s**）
     · ★ 已 `setx PUB_HOSTED_URL` / `FLUTTER_STORAGE_BASE_URL` 指向 `*.flutter-io.cn`
     · ★ ⚠ `flutter --version` 会对 SDK 仓库 `git fetch --tags`（★ **611285 个对象**）**挂死**
       ⇒ ★ **所有 flutter 命令一律加 `--no-version-check`**（★ 坑 P16；★ 已卡的进程要
       `Stop-Process git,dart` + 删 `bin\cache\lockfile`）
★ 【④ 四条基线 —— ★★ 逐数字实测复现】
     · 守卫链（14 个文件）= **166 passed**（4.48s）
     · 全量 `pytest tests/ -q` = **15 failed / 1903 passed / 7 skipped**（91.02s）
       ★ 11 个失败文件 · 主导是 `FileNotFoundError`（测试硬编码读 `D:\OAS-dev\OASX-src`）
     · 前端 `analyze lib` = **0 error / 4 warning / 17 info**（★ rc=1 是因为有 info，不是 error）
     · 前端 `test` = **158 passed**
★ 【⑤ 收尾】★ `pub get` / `test` 之后那 7 个 `generated_plugin*` ＋ `docs/flows/README.md` 是**幻影脏**
     （★ 纯 LF/CRLF，`git diff --numstat` 为空）⇒ ★ 已 `git checkout --` 还原 ⇒ ★ **两仓工作区干净**
★ 【⑥ 缺口（★ 待裁定）】★ 本机**没有 Visual Studio / Windows SDK / cmake / ninja / winget**
     ⇒ ★ `flutter build windows --release` **暂时不可用**（★ `analyze`/`test` 不受影响）
     ⇒ ★ 见 §2 的 **★0d** 与坑 **P17**
★ 【⑦ 一个真发现】★ `test_task_factory` / `test_task_flow_docs` 会把 `docs/flows/README.md`
     **重写成 LF**（★ 内容不变）⇒ ★ 每次跑完测试工作区都显示脏 ⇒ ★ 坑 **P18**
★ 【⑧ [10-15] 工作区搬家】★ 先在 `E:\OAS-dev` 引导成功 ⇒ ★ 按用户提议**整份搬到 `D:\OAS-dev`**
     （★ `robocopy /E` = **22085 文件 / 1.363 GB** · rc=1）⇒ ★ 理由：① 与历史文档的 `D:\OAS-dev`
     口径一致 ② ★★ **43 条硬编码测试只在 D 盘下才可能对齐** ③ D 盘空闲 47 GB 且 `D:\flutter3271` 同盘
     ⇒ ★ **搬完复验**：守卫 **166 passed** · 全量 **15 / 1903 / 7** · 前端 **0 error + 158 passed**
```

## ★ 1k. ★★★ [10-15] 相对路径轮（★ 用户裁定"全改相对路径 + 彻底去盘符"）

```
★★ 用户 [10-15] 三句裁定（逐字）：
   "**要不全改成相对路径，先设计好存放的结构树，然后改成相对引用**"
   "**彻底去盘符**"
   "**前端仓库要存在**"

★ 【S1 解析器去盘符】dev_tools/paths.py
   · 候选由**绝对**改**相对**：★ 新增 **`..\frontend`**（现行工作区布局，**首选**）
   · 新增 `workspace_root()` · `frontend_root()` · **`flutter_root()` / `require_flutter()`**
   · 新增 `dev_tools/paths.local.json.example`（★ 模板在 git；真文件 `.gitignore:280`）
   · ★ 实测 `python -m dev_tools.paths`：工作区根 = 本机 `D:\OAS-dev` · 前端 = **自动探测到 `frontend`**
     · Flutter = **来自 paths.local.json**（★ 本机 Flutter 不在工作区里）
★ 【S2 9 个测试文件】硬编码常量 → `require_oasx()`
   · ★ 其中 `test_linkage_unification` 的 2 处 `pytest.skip('OASX 源码不在预期位置')` → **`assert`**
     （★ 依"前端仓库要存在"：★ **缺前端就响亮失败，绝不跳过**）
   · ★ 效果：这些测试**第一次真的在读前端源码**（不是"因为路径不存在而红"）
★ 【S3 守卫范围加 tests/】`test_no_hardcoded_paths.py` 的 `_py_files()` 增 `tests`
   · ★ 扩范围后**一次通过**（说明 9 处已全清）；★ 注入探针 ⇒ 必须红（已验）
★ 【S4 结构树文档 + 无盘符包装】
   · 新增 **`docs/LAYOUT.md`**（结构树 + R1~R5 + 唯一允许绝对路径的两个文件 + 包装脚本 + 豁免表 + 历史沿革）
   · 新增 `run-tests.bat` · `run-server.bat` · `dev_tools\flutter.bat`（+ `run_flutter.py`）
   · ★ 实测：从 `C:\` 跑 `run-tests.bat …` = **4 passed**；`dev_tools\flutter.bat analyze lib` = **21 issues**
     （0 error / 4 warning / 17 info）；`dev_tools\flutter.bat test` = **158 passed**
★ 【S5 文档】现行文档命令块全改包装脚本；★ 基线数字更新（见下）；★ 台账 §E-6-l~p

★★ 【真 bug（本轮抓到并修）】`_resolved_cache` **把"找不到"也缓存** ⇒ 全量跑时 3 条跨仓测试
   被污染的 `None` 卡红（★ 单跑却绿）⇒ 改成**不缓存找不到** ＋ 守卫
   `test_negative_result_is_never_cached`（★ 注入验证 1 failed）
★★ 【★ 真漂移（新发现 · 待裁定）】`test_linkage_unification::test_pause_reports_requeue`
   期望前端 `run_control_bar.dart` 有 `pauseScriptDetailed` —— ★ **前端 v2 已只剩「启动/停止脚本」**
   ⇒ ★ 与前端 **F9**（`queue_panel.dart:1042-1058` 死代码 ⇒ 暂停入口消失）**同源**（★ 台账 §E-6-n）

★★ 【新基线（★ 旧数字作废）】
   · 全量 = **15 failed / 1903 passed / 7 skipped**（★ 改前 = 49 / 1862 / 12）
   · 守卫链 = **166 passed** · 前端 = **analyze 0 error（4w+17i）** · **test 158 passed**
   · ★ 15 条归因 = 9 缺 `zh-CN.json` ＋ 2 用户/实机状态 ＋ 1 窗口外任务 ＋ 1 用户配置 ＋ 1 live 配置
     ＋ ★ 1 真漂移（§E-6-n）
```

## ★ 1l. ★★★ [10-22 02:0x] **新引擎主线：N1 + N3 + N5 完成（交接用）**

```
【新引擎位置】★ D:\OAS-dev\oas-core（独立 git 仓 · 本地 main · 无远端）
  ★ [10-22] 引擎提交 = 42ecd2d（N1 click_point + N3 TaskBundle/编辑器 API + N5 S1 样板/`oasd run`）
  ★ 文档依据 = backend\docs\ENGINE-DESIGN.md §19/§20/§22（旧仓 backend/frontend 冻结，只作资产/知识源）

【入口核对（本轮实测）】
  后端 dev = 1258c400（干净）· 前端 dev = 8da0f2a（干净）· oas-core = 1a0ae8c -> 42ecd2d（干净）
  守卫链（15 文件） = 171 passed（7s）
  后端全量 = 1935 passed / 0 failed / 18 skipped（102s）  ★ 旧 14 failed 已被 §E-13 收敛
  前端 = analyze 0 error（4w+17i）· test 160 passed
  引擎 = cargo test --workspace = 103 passed / 0 failed（default 与 --features oasd/ocr 都是 103）
  新引擎 **编译基线已修**：无 ocr feature 时默认 `cargo build/test --workspace` 原本失败（已修）

【N1 判据（注入验证真红）】越界 click_point => Failed 且不下发点击；删 CP3 => 越界点击被当 Done（红）；
  删 click 后 invalidate_frame => 第二击仍用旧帧 target=(12,10) 期望 (40,20)（红）
【N3 判据】中文 id + 序号文件名 aNNN.png（id 不落地成路径）；重复 id => 400「nothing written」；
  flow 拼错引用 => 400；两文件 SHA256 不变；编辑器 UI 有 任务名/保存素材到任务/保存 flow（校验引用）
【N5 判据】真机 outcome=Done（7 点 + 1 滑，设备回庭院）；回放同 seed outcome=Done，
  clicks 与逐步 detail 逐字相同（结构 diff=0）· 证据 _verify/n5/N5_EVIDENCE.md
  ★ 「识别分组2」= 编辑器 /lines（9 行 ≥0.9994）→ 框中心表达式 "1131 + 69 / 2" 写进 click_point
  ★ 新增 swipe 指令（列表默认停底部，必须滚到顶才看得到分组2）

【下一步（引擎主线）】
  1. N2 编辑器「生成点击指令」（选中识别块 => 直接出 click_point 步骤）
  2. N4 编辑器内嵌点击分布视图 + oasd run 落 CD2 点击 JSONL（现在是步日志 JSONL）
  3. 解释器 ocr() 接线（真正 in-flow 识别；本轮 S1 的识别在编辑器侧）
  4. 弹窗原语（真机出现过「悬赏封印」弹窗，手动关掉）

【常用命令（新引擎）】
  ★ 起编辑器/OCR 服务（本会话已起在 8787，restart 时用）：
    cd oas-core
    $env:ADB_PATH='D:\OAS-dev\backend\toolkit\Lib\site-packages\adbutils\binaries\adb.exe'
    .\target\debug\oasd.exe serve --port 8787 --tasks-dir tasks `
      --model D:\OAS-dev\backend\toolkit\Lib\site-packages\rapidocr\models\PP-OCRv6_rec_small.onnx `
      --det-model D:\OAS-dev\backend\toolkit\Lib\site-packages\rapidocr\models\PP-OCRv6_det_small.onnx
  ★ 跑任务（真机 / 回放；seed 必看打印值）：
    .\target\debug\oasd.exe run --task tasks\S1切预设 --seed 12345 --record _verify\n5\rec --events-out _verify\n5\live.jsonl
    .\target\debug\oasd.exe run --task tasks\S1切预设 --replay _verify\n5\rec --seed 12345 --events-out _verify\n5\replay.jsonl
```

---

## ★ 1m. ★★★ [10-22 02:1x] **新引擎第二轮 N2 + N4 完成 —— 下一个会话从这里开始**

```
【引擎位置/提交】★ D:\OAS-dev\oas-core（独立 git 仓 · 本地 main · 无远端）
  42ecd2d = N1 click_point + N3 TaskBundle/编辑器落盘 + N5 S1 样板
  0e61999 = N2 生成点击指令 + N4 点击分布（CD2 JSONL）+ runs/ 忽略
  文档：backend docs（§22.3/§22.4/§E-15/§E-16）已 push origin/dev

【本轮实测基线（★ 不是抄文档）】
  oas-core: cargo test --workspace = 117 passed / 0 failed（default 与 --features oasd/ocr 各 117）
  旧仓（本轮未动代码）：守卫 171 passed · 全量 1935 passed / 0 failed / 18 skipped · 前端 0 error + 160 passed

【编辑器闭环（已全部落地）】
  截图 → /lines 识别 → 点区块 →「生成点击指令」（或 /task/save_asset 存素材）
       → flow.json 保存（保存即校验引用）→ oasd run（--record/--replay/--seed/--clicks-out）
       → 编辑器「点击分布」叠加看实际落点（clicks=N distinct=K）
  常用：oasd run --task tasks\S1切预设 --seed 12345 --record ..\_verify\n5\rec --events-out ...
        oasd run --task ... --replay ... --seed 12345 --clicks-out runs\s1-replay.clicks.jsonl

【环境（本机 = 开发机）】
  MuMu adb = 127.0.0.1:16384（1280x720）· adb.exe 在 backend\toolkit\Lib\site-packages\adbutils\binaries\
  oasd serve 建议常驻 :8787：--tasks-dir tasks --runs-dir runs + OCR 模型（完整命令见 §1l）
  ⚠ serve 会锁 target\debug\oasd.exe：要 rebuild 先停 serve，build 完再起
  ⚠ headless Edge 截图必须用**新的 --user-data-dir**（否则偶发 0 字节；后备 = 自写 CDP 脚本）
  ⚠ 本机没有 node/npm（UI 校验用 headless Edge/CDP）

【下一个会话从这里开始（按建议顺序）】
  1. ★★ 解释器 ocr() 接线（最大一块；ENGINE-DESIGN §22.4 下一步 1）
     · EvalContext 已在；给 Interpreter 注入 OcrProvider（trait + onnx feature 门控）
     · 验收（不碰设备）：用 _verify/n5/s1_recording2 回放跑含 ocr()/wait_until(ocr(...)) 的 flow，
       文字/分数与真机一致（P1-c 已有真机基线：默认分组 0.9987 / 分组2 0.9912）
  2. ★ 弹窗原语（真机 S1 曾出现「悬赏封印」弹窗；建议 dismiss_popup / on_interrupt 钩子）
  3. ★ 点击分布 base 帧（跨屏 run 目前只能叠当前帧）
  4. ★ 旧仓台账中与本主线无关的项**不动**（引擎线以 ENGINE-DESIGN 为准）

【证据（都在磁盘，不进 git）】
  _verify/n5/N5_EVIDENCE.md · _verify/n5/s1_recording2/（真机 8 帧 + meta）
  _verify/n4/ui_n4_deeplink.png（N4 编辑器实拍）· _verify/n4/n2-flow.png（N2）
  _verify/n4/s1_clicks_heatmap.png（click_heatmap.py 兼容）· _verify/n4/（N4 截图/日志）

【不要做】
  · 不要把 _verify/ 里的大文件（录制帧）提交进 git
  · 不要把旧仓 pytest 基线当引擎验收
  · oasd run 真机会点游戏（S1 可逆）⇒ 跑前确认设备在**庭院**；跑后设备应自动回庭院
```

---

## ★ 1n. ★★★ [10-22 12:40] **新引擎 N6：解释器 `ocr()` 接线完成 —— 下一个会话从这里开始**

```
【引擎位置/提交】★ D:\OAS-dev\oas-core（独立 git 仓 · 本地 main · 无远端）
  42ecd2d = N1 + N3 + N5 · 0e61999 = N2 + N4 · ★ 05e497f = **N6 ocr() 接线**
  ★ 8558ac3 = **N6b 素材更新（rev+1）** + **N7 10k 点击模拟工具**
  ★ 598d4c5 = **N6c det+rec 纠正（ocr_lines）** + **N7b 整任务 1000 次模拟**
  ★ f671bfa = **N8 点击人类化 v2：钟形（对齐旧仓库）+ HB7 手误**
  ★ 3404fec = **回退 HB7：去掉手误，只保留钟形**（用户 [10-22 18:4x] 裁定）
  ★ 1954d19 = **N9 点击分布 v3：30/20/50 混合 + 彗星（手侧）+ 1~3% 手误**（用户 [10-22 19:0x] spec）
  ★ 21d0218 = **N9b 彗星修订：头在中心 + 径向指数衰减，手侧尾巴**（用户 [10-22 19:1x] 追问的判定）
  ★ bdf5b56 = **N9c 混合权重 20/5/75**（用户 [10-22 19:3x] 指定）
  ★ bb770e1 = **N10 多边形框选一期**（点击区 = 多边形最大内接矩形 LAAR；编辑器多边形模式）
  ★ 6abb816 = **N11 定位冗余链一期**（click_target：图片 > 文字 > 坐标记忆 + state/coords.json + locator 审计）
  ★ 3d705c7 = **N12 点击后验证**（expect：appear/vanish/ocr_text，轮询超时=步失败）
  ★ bf44bbe = **N16 页面守卫**（requires：点击前校验，不满足=零点击失败）+ oas-flow 注释乱码修复 + S1 加 requires
  ★ c3c4237 = **N17 多模板变体**（click.alts：主图失败逐张试变体，审计命中变体 id）
  ★ 11ae6b2 = **N18 点击审计**（CD2 match 字段 + --shots-dir 失败截图）
  ★ 1cb7397 = **N20 弹窗/中断处理**（interrupts 自动消弹 + dismiss_popup；纵向第①项）
  ★ 4ced23b = **N20b 弹窗"接受"动作**（detect + action 双模板；悬赏封印邀请等）
  ★ cafe5f0 = **N21 步级重试与退避**（retry:{times,delay_ms,backoff}；纵向第②项上半）
  ★ 61bb19c = **N21b 断线重连 + 检查点恢复**（ProgressSink/--resume + OAS_ADB_RECONNECT_ENDPOINTS；纵向②完成）
  ★ 174800f = **N22 多任务调度/supervisor**（`oasd queue`：串行任务队列/重试/轮次/JSON 报告；纵向③）
  ★ 449a6e5 = **N23 可视化流程编辑器**（/task/flow + flow_model.js + 步骤/参数/弹窗规则可视化；纵向④）
  ★ e7a5b11 = **N24 运行统计与告警**（oasd stats + HTML 仪表盘 + ALERT + /stats 编辑器面板；纵向⑤）
  ★ d919e13 = **N25 整帧模板搜索 + 图识别试匹配 + 点击区改匹配外接矩形**（用户三项裁决；§22.10 修订 / §22.20 / §22.21）
  ★ [10-22 23:1x] OCR 501 事故修复：serve 必须 `cargo build -p oasd --features ocr` 且带 --model/--det-model；`/state` 现返回 ocr/det 能力位；编辑器状态栏显示 OCR=on/off
  ★ [10-22 23:1x] 用户裁决：点击区=bbox；OCR 区域=bbox+多边形掩膜；匹配=掩膜 NCC；LAAR 废弃（裁字风险）。N10b 子项=掩膜 NCC/OCR 掩膜/自交/顶点编辑
  ★ [10-22 23:1x] 用户提出**全局素材库**（跨任务调用素材用于匹配等用途）→ ENGINE §22.22 设计已记录，台账 N26 待开工（一期模板库 ~1 天）
  ★ 4cd84a5 = **N10b 二期完成**（匹配掩膜 NCC / OCR 掩膜 bbox+fill / 自交检测 / 顶点拖动+双击删除 / 界面中文化；198 passed）
  ★ ca01cae = **N26 全局素材库一期**（library/ + `lib:<id>` 引用 + run `--library` + serve `/library` + `/match?lib=` + 编辑器素材库面板；201 passed）
  ★ 4ba650e = **N27 编辑器分页**（编辑页瘦身 + 新调试面板 `/dashboard.html`：画面/点击分布/长跑统计/日志；`?run=` 深链）
  ★ ce2de42 = **N28 三栏 IDE 布局 + 双 ROI**（参考旧 OAS annotator：rail 面板 素材/任务/流程、画布下输出、识别框/点击框 roi_back；205 passed）
  ★ [10-24 00:0x] **N29 会话图片列表（多帧）**：`/frames` 系列接口 + 编辑器「图片」面板（capture 入列/上传/选择/删除/清空）；供 H4 多帧投票与离线素材调试（206 passed）
  ★ [10-24 00:2x] **N30 标题行结果/日志抽屉 + 素材行内测试 + 导航调整**：header 抽屉、rail「点击分布」、任务素材分组/搜索/测试按钮、`/task/asset/match`（206 passed）
  ★ [10-24 00:5x] **N31 H4 多帧投票**：`click.stable_frames`（1..=10，连续 N 帧同位置 ±4px 才点，失败不点）；flow 33 / runtime 77 / 208 passed
  ★ [10-24 00:5x] **N32 标题行常驻结果/日志窗口 + 点击分布并入 rail**（五 tab 行为统一；/dashboard 保留）；208 passed
  ★ [10-24 01:0x] **N33 H5 OCR+模板互证**（ocr_text.require_template，行周边 16px 模板校验；210 passed）
  ★ [10-24 01:0x] **N34 结果/日志窗口移到截图上方、rail 左侧**（headless 截图 n36/editor_windows_left.png）
  ★ 素材库用法：编辑器选 ROI → 填库素材 id →「保存到素材库」；flow/素材写 `lib:<id>`（click/appear/click_target/requires/expect/interrupts 均可）；`oasd run`/`serve` 默认读 `library/`；`GET /match?lib=<id>` 或编辑器「用库素材试匹配」可测
  ★ [10-22 23:3x] 界面中文化：试识别/多行识别/试匹配/得分/耗时/状态栏能力位/flow op 下拉均为中文；多边形模式提示"点击区=匹配外接矩形"
  ★ 实机验收 [10-22 21:0x]：S1 连续 4 跑全 Done（7 击/跑、miss 0）；实机录制同 seed 回放 7/7 逐点一致；`expect appear(预设)` 真机 verified=true ⇒ 下一步**页面守卫**（S1 起始页是"探索/御魂"，不是庭院）
  文档：backend docs（§22.5 / §E-17 / §1n）已 push origin/dev

【本轮实测基线（★ 不是抄文档）】
  oas-core: cargo test --workspace = 135 passed / 0 failed（default）
            cargo test -p oasd --features ocr = 22 passed · cargo build -p oasd --features ocr 绿
  旧仓（★ 已冻结为资源库 · 本轮未动代码）：守卫 171 · 全量 0/1935/18 · 前端 0 error + 160 passed

【N6 落地了什么（详情见 ENGINE-DESIGN §22.5）】
  ★ flow 里可以用 wait_until(ocr('分组2') == '分组2') / ocr_digit(...)
  ★ OcrProvider trait 在 oas-runtime（运行时不含 ort）；oasd 侧 OnnxOcr 适配器 + run --model/--det-model
  ★ ocr_line = rec 快路径；ocr_lines = det+rec（ENGINE §17.1 现行 · 缺 det 响亮失败）
  ★ 空文本 => Null；无 provider / 未声明 / 模板资产 => 响亮失败
  ★ 素材更新：同名 id 再存 = 覆盖并 rev+1（旧图删除；UI 弹确认；失败 nothing written）
  ★ 点击模拟：cargo run -p oas-runtime --example click_sim -- rect 10000 12345 330 69 95 55 out.jsonl
  ★ 点击分布：HB1 = **20% 钟形 / 5% 完全随机 / 75% 彗星（头在中心、概率随离中心距离指数下降、手侧方向衰减更慢）**；HB7 = **每 100 次 1~3 次手误**（框外 ≤12px，日志/JSONL 带 miss）
  ★ 待实现：点击定位冗余链（图片>文字>坐标记忆 + 10 条补充层）→ ENGINE §22.11，待裁定；建议先于多边形
  ★ 定位链一期已完成（6abb816：click_target + coords.json + locator 审计，离线 replay 验收）；补充层/模糊匹配/过期策略待排期
  ★ 点击后验证已完成（3d705c7：expect appear/vanish/ocr_text；轮询超时=步失败；3 帧 replay 验收 verified=true）；剩余补充层：多模板/相对锚点/无障碍/取色/多帧投票/OCR+模板互证
  ★ 页面守卫已完成（bf44bbe：requires；实机庭院起跑零误点失败、探索页起跑 guard=true 全流程）；S1 flow 第一次 click 已带 requires
  ★ 多模板变体已完成（c3c4237：click.alts；离线 replay 主模板噪声→variant 命中）；剩余补充层：相对锚点/无障碍/取色断言/多帧投票/OCR+模板互证
  ★ 点击审计已完成（11ae6b2：每次点击 CD2 带 match=图片/文字/坐标证据；失败自动截图 --shots-dir）；相对锚点（§22.14）待裁定
  ★ 用户裁定 [10-22 21:4x]：**继续纵向开发**；横向补充（相对锚点/无障碍/取色/多帧投票/OCR+模板互证）只登记为待开发记录（台账 §E-23）
  ★ 纵向第①项已完成（1cb7397 弹窗/中断处理）；下一项建议 ② 步级重试与失败恢复
  ★ 纵向第②项上半已完成（cafe5f0 步级重试+退避）；剩余：断线重连/检查点恢复（N21b）→ 再做 ③ 多任务调度
  ★ 纵向第②项已完成（61bb19c 断线重连+检查点恢复）；下一步 ③ 多任务调度/supervisor
  ★ 纵向第③项已完成（174800f `oasd queue`：串行队列/重试/轮次/报告）；下一步 ④ 任务编排/流程编辑器 或 ⑤ 运行统计与告警
  ★ 纵向第④项已完成（449a6e5 可视化流程编辑器）；下一步 ⑤ 运行统计与告警（长跑报表）
  ★ 纵向第⑤项已完成（e7a5b11 stats/HTML 仪表盘/ALERT/编辑器面板）；纵向 ①~⑤ 全部完成，剩余为横向 H1~H5 待开发记录
  ★ [10-22 23:0x] 用户三项裁决已实现（d919e13）：搜索窗=整页截图（§22.20 金字塔全帧搜索，平移容忍）；编辑器补图识别试匹配（/match + 按钮）；点击区=匹配外接矩形（§22.10 修订，LAAR 不再参与 click）。H1 相对锚点降级（平移已被全帧搜索覆盖）；H3 取色暂缓（场景窄/精度一般，遇实例再启）
  ★ 多边形一期已完成（bb770e1：编辑器多边形框选 + 点击区=LAAR，匹配/OCR 仍外接矩形）；二期掩膜/自交/顶点编辑待排
  ★ 证据 _verify/n6/N6_EVIDENCE.md · _verify/n8/N8_EVIDENCE.md · _verify/n9/N9_EVIDENCE.md · _verify/n11/ · _verify/n12/ · _verify/n13/（v3.1 指数修订）
  ★ 对比分析：旧仓 RuleClickExclude（安全随机点击）vs 手误 → ENGINE §22.8；可移植 click_safe/等待随机滑动（待裁定）

【下一个会话从这里开始（按建议顺序）】
  1. ★★ 弹窗原语（真机 S1 曾出现「悬赏封印」弹窗）：dismiss_popup(sel|ocr_text) 或 on_interrupt 钩子
  2. ★ 点击分布 base 帧（跨屏 run 现在只能叠当前帧）
  3. ★ find_text_in_list（列表内按文字找项并点击，§14.2；det 结果已可用）
  4. ★ 旧仓台账中与本主线无关的项**不动**（旧仓已冻结，只作资源库）

【不要做】
  · 不要把 _verify/ 里的大文件（录制帧）提交进 git
  · 不要把旧仓 pytest 基线当引擎验收
  · 无 --features ocr 的 oasd 不接受 --model（会响亮拒绝，这是预期）
```

---

## ★ 2. ★★ 下一步（★ 按优先级）

| # | 事项 | 依据 | 状态 |
|---|---|---|---|
| **★0** | ★★ **[10-15] 分支策略 —— ✅ 已裁定**：★ `dev` = **开发分支**（★ **另一台拉这个**）· ★ `main` = **主要的稳定版本**（★ 用户原话："**另一台可以拉dev啊，main是主要的稳定版本！**"）⇒ ★ 我一度误把 `main` 快进到 dev，**已 `--force-with-lease` 回退**（★ 后端 `main` = `e28793ce` · 前端 `main` = `af10440`）<br>★★ **[10-15] 角色也已定案（★ 用户原话："对了。"）**：★ **实机（`Win~Win~Win~`）= 生产** · ★ **开发机（`passioki`）= 开发** ⇒ ★ 台账 **§E-7-0** 消歧义（★ **禁止裸用"本机"**）| **台账 §E-2 / §E-5 / §E-7-0** · **`DEV-WORKFLOW.md §0.6`** | ✅ **已裁定并落地** |
| **★0b** | ★★ **[10-15] 待你定：非 git 的运行时怎么传给另一台** —— `toolkit\`（**17000 文件 / 1167.4 MB**）· `config/deploy.yaml` · ★ **账号配置**（`恋鸟树`/`伴生树`）· `console.bat` ★★ **光 git 不足以"无缝开发"** | **台账 §E-1**（★ 7 项实测清单）| ⬜ **等你选方式**（★ U 盘 / 网盘 / 私密仓库 / 打包）|
| **★0c** | ★★★ **[10-15] `F9`（前端「暂停调度」按钮缺失）⇒ 🔄 已移交开发机**（★ 用户原话："**这个交给开发机。**"）—— ★ 真因 = `queue_panel.dart:1042-1058` 与 `:1059` **条件逐字相同** ⇒ `[⏸]` 死代码。★ 修法 = 删那 1 段 + 1 条"可达性"守卫 | **前端台账 `F9`** · **SPEC §3.6 现行口径 · §3.4-L3 · §1.4-Z3** · **台账 §E-6-n**（★ 与后端一条真漂移同源）| ✅ **已完成**（前端 `8da0f2a`：删死分支 + 2 条可达性守卫）|
| **★0f** | ⬜ **[10-15] 后续项：把 `session-memory` 迁移成「通用技能」**（★ 用户意向："后期可能会把该技能迁移成通用技能"）—— ★ 实测**要改 4 处**：`seg.ps1:14` 的默认 `-File`（唯一写死盘符处）· `index_gen.py:24/26/27` 的项目专属关键词 · `SKILL.md` 写死的 4 个文档名 · `README.md` 的项目工作流 | **台账 §E-7-a-8**（★ 含逐处实测清单）| ⬜ **未开始（等指令）** |
| **★0d** | ★★ **[10-15] 待你裁定：装不装 C++ 工具链** —— ★ 本机缺 Visual Studio / Windows SDK ⇒ ★ `flutter build windows --release` **不可用**（★ `analyze`/`test` 已跑绿）· ★ 本机**也没有 `winget`** ⇒ ★ 要用官方 `vs_BuildTools.exe` ＋ `Microsoft.VisualStudio.Workload.VCTools`（★ 约 2~6 GB）| **§1j-⑥** · **DEV-WORKFLOW §7 坑 10** · **START-HERE P17** | ✅ **已装（[10-15]）**：VS 2022 Build Tools `17.14.37806.7` + Windows SDK `10.0.26100.0` ⇒ `flutter build windows --release` 可用 |
| **★0e** | ★★★ **[10-15] 待你裁定：真漂移** —— `tests/module/config/test_linkage_unification.py::test_pause_reports_requeue` 期望前端 `run_control_bar.dart` 有 `pauseScriptDetailed`，★ **而前端 v2 已只剩「启动/停止脚本」**（★ 改走解析器后**第一次真的读到前端源码**才暴露出来）⇒ ★ 与前端 **F9**（`queue_panel.dart:1042-1058` 死代码 ⇒ 暂停入口消失）**同源** | **台账 §E-6-n** · **前端台账 F9** · **SPEC §3.6** | ✅ **已修**（按现行口径改成 `test_pause_entry_lives_on_the_queue_row`，16 passed）|
| **★1** | ★★★ **接口模块化的方案已定案（[10-14] 用户）**：★ **`M2`**（= §1.17 的 **A/A+ 受控指令集**，**不用 `eval`**）＋ ★ **annotator 可以"深度拆解"进任务实现器** | **SPEC §1.17 一（分歧块⑫）· §1.18-五/八** | ✅ **已定案 ⇒ 可开工** |
| **★1b** | ★ **[10-14] `FL-*` 新发现的处置**：★ `FL-1` ✅ **已修**（㉜）· ★ `FL-9` ✅ **已修**（㉝）· ★ `FL-2` ✅ **查清 = 误报** · ★ `FL-6`/`FL-8` ⏸ **用户裁定"待定"**（★ 原话："待定，后续可能会重构代码"）| 台账 **§D.4** · SPEC **㉜/㉝** | ✅ / ⏸ |
| **★1c** | ★★ **`P0` 已落地**（★ 见 §1f）：★ `module/flow/`（C1/C4/C6/C7）+ ★ C10 状态入口；★ 守卫 29 条 + ★★ 注入验证 2/2 | **SPEC §1.19-七 · 台账 §D.7** | ✅ **已完成** |
| **★1d** | ★★ **`N9-11`「新建任务」工厂已落地**（★ 见 §1g/§1h）：★ `module/task_factory.py`（原子 + 回滚 + 命名校验 + 自动登记 + 示例识别）+ ★ **`tasks/FlowDemo/` 已在 dev** + 守卫 31 条（★ 注入 3/3 真红）+ ★★ **完整合同 = §1.16-五 `NT8`（6 类）** | **SPEC §1.16 · 台账 §D.8/§D.10** | ✅ **已完成** |
| **★1e** | ★★ **待你裁定：dev 侧把「流程示例」真跑一次怎么跑** —— ★ dev 的 `恋鸟树` 与实机**同一台模拟器**（`127.0.0.1:16384`）⇒ ★ **A** 先停实机 `:22287` · **B** 给 dev 换设备 · **C** 等稳定后拷实机再跑 | **台账 §D.10-g · HANDOFF §1h** | ⬜ **等你一句话** |
| **★1f** | ★★ **P1 开工项**：★ C5 补 5 个空缺（**返回键/键盘/文本/滚动/拖拽**，★ 现状：`atom/scroll.py:11` 空壳 · `scrcpy/control.py:48/62/100/123` **零调用** · `Control.drag`(`control.py:239`) 零调用且缺 2 分支/读错配置字段）+ ★ C9 的 `LoopBudget/StuckGuard/RetryPolicy` 提到 `module/action/` | **SPEC §1.18-三/六 · §1.19-C5/C9** | ⬜ **下一轮（推荐）** |
| **★2** | ★ **N9-6 P1 剩下的部分**：★ 后端 `tasks/create` **已由工厂完成**（NT1~NT4 + 示例识别）⇒ ★ 只剩 ★ `flow.json` **解释器**（NL1/NL2）+ ★ **立即运行**（NL3）+ ★ **结构化日志**（NL4）| **SPEC §1.17** | ⬜ 待启动（★ 依赖 P1 的原语）|
| **★3** | ★ **N9-6 P2**：★ 前端「任务编排」面板（★ 指令增删改 · 素材下拉 · 立即运行 · 实时日志）| SPEC §1.17 三 | ⬜ |
| **★4** | ★ **N9-6 P3 验收**：★ **新建一个周期任务 + 一个临时任务并跑通**（★ 用户原验收定义；★ 临时任务那半 ≈ `FlowDemo`）| SPEC §1.16-NT6 | ⬜ |
| **★5** | ★ **N9-5 续**：★ 流程图**剩 47 张**（★ 已完成 8 张：`RealmRaid`/`Tako`/`Orochi`/`RyouToppa`/`AreaBoss`/`DailyTrifles`/`WeeklyTrifles`/`AutoCheckinBigGod`；★ 建议下一批 `Exploration` → `Rest` → `GeneralBattle`，★ 登记台账已就绪 ⇒ **只写不改**）| `docs/flows/README.md` | 🔄 进行中（8/55）|
| **★6** | ★ **前端 F5~F8**（★ 见 `frontend/docs/PENDING-LEDGER.md`）：★ 自动补齐行是否也该显示"已运行 N 次" · `zh-CN.json` 推送时机 · `generated_plugin*` 反复变脏 · 测试基线 | 前端台账 §一 | ⬜ |
| **★7** | ★ **实机验收**（★ 用户 [10-14]："**不要在实机跑**…实机是**版本稳定后直接从 dev 拷贝过去**"）⇒ ★ **等版本稳定**；★ 拷贝时记得 `flutter build windows --release` + 跑 §6 的从零恢复清单 | 台账 §C · SPEC §0 | ⬜ **等"稳定"指令** |
| **★8** | ★ **旧账未动**：`S3b`（门④临时任务队列过滤）· `D7.4` · `D43` · `D45` · `F4` · `DOC4` · `DOC5` · `O1` · `O2` · `T9/T11/T14` | 台账 §一~§六 | ⬜ |
| **★9** | ★ **两条"待定"（用户已明示暂不处理）**：★ 三个红灯（出口语义/收尾对称/暂停检查点）· ★ `FL-6`/`FL-8` | SPEC §1.19-四 · 台账 §D.4/§D.6 | ⏸ 等重构 |

## ★ 3. ★ 活跃的坑（★ 别再踩）

| # | 坑 | 一句话 |
|---|---|---|
| **P1** | ★ **`"播放模式"` 这个标题是用户要求删掉的** ⇒ ★ 前端该处**只有下拉**（顺序/循环/乱序），★ **不要"修复"成带标题** | 用户明令 |
| **P2** | ★ **前端不能放 `D:\MuMuPlayer\OAS\` 下** | 内核驱动 `PassGuard_x64.sys` 打了保护标记 ⇒ 双击打不开 |
| **P3** | ★★ **守卫必须"真会红"** ⇒ ★ **每个新守卫都要做注入验证**（★ 本轮抓到 **4 次空转**）| 台账 §C.3 |
| **P4** | ★ **`toolkit\` / `config\deploy.yaml` / 账号配置 / `console.bat` 不在 git** | 清理目录前必须先抢救（`DEV-WORKFLOW.md` §1）|
| **P5** | ★ **删目录前逐个核对完整路径** | 已因"删+建同名前缀混用"误删过 `D:\OASX-Live` |
| **P6** | ★ **删含 `adb.exe` 的目录前先 `adb kill-server`** | 否则删不净 |
| **P7** | ★★ **`pwsh` 工具相关两个坑**：★ ① `pwsh -replace` 注入会**静默不生效**（正则 + `$` 展开）· ★★ ② **[10-15] `pwsh` 整段不可用** —— 每条命令都返回 `exit code 3221225794`（= `0xC0000142` STATUS_DLL_INIT_FAILED）且**零输出**（连 `echo hi` 都失败）| ★ ① **注入一律用 Python `str.replace`** + 打印"是否生效" + 还原比 SHA256 · ★ ② **续跑/重启 DSH 会话**（★ 不是重启电脑；★ [10-15] 实测下一轮自行恢复），期间用 `read`/`grep`/`glob` 工具继续取证 |
| **P8** | ★ **`git commit -m` 带中文引号/反引号会被 PowerShell 吞** | ★ **用 `git commit -F <文件>`**（★ 文件放**仓库外**，否则会误提交）|
| **P9** | ★ **`/tool/annotator` 的写端点【无鉴权】**（`tool_router.py` 无 `Depends`；`app.py:112` 的 `-k/--key` **从未被使用**）| ★ 这直接决定了 N9-6 的架构选择（见 §2-★1）|
| **P10** | ★ **测试去读 `D:/OAS-dev/OASX-src`**（本机没有；真实前端在 `frontend`）| 那 43 条失败是**环境类**，不是回归 |
| **P11** | ★★ **DSH 沙箱（`workspace-write`）会把 125 条测试打成"假红"** | `script_process.py:30` 的 `multiprocessing.Pipe`（**命名管道**）被沙箱拒 ⇒ `PermissionError [WinError 5]`：★ 受约束 = **141 failed / 1570 passed / 125 errors**，★ 放开 = **49 / 1785** ⇒ ★ **跑 pytest 必须放开沙箱** |
| **P12** | ★ **沙箱下原生命令接 PowerShell 管道 = `Access is denied`** | 如 `python.exe … \| Select-Object` / `git … \| Select-String` ⇒ ★ **别接管道**（看工具自动截尾，或 `Select-String` 只读文件）|
| **P13** | ★★ **核对行号不要用 `Get-Content`** | 它按 **ANSI** 解码 ⇒ 同一文件**少算行**（实测 `tasks/Tako/script_task.py` = **163** 行，`Get-Content` 只看到 **153** 行 ⇒ 行号**整体错位**）★ 用 **read/grep 工具**（与 `Select-String` 口径一致）|
| **P14** | ★★ **不要把开发中的东西写进实机 `D:\OAS-live`** | ★ 用户原话："**不要在实机跑，现有开发基于 dev 侧，实机是版本稳定后直接从 dev 拷贝过去**"（★ `START-HERE.md` §0 已写死：★ **实机 = dev 的拷贝**）⇒ ★ 我 [10-14] 曾把新建的 `FlowDemo` 装进实机（**已还原**：删目录 + 重生成 catalog + 新进程复验 55 个任务）|
| **P15** | ★★ **本机 `git` 报 `dubious ownership`**（★ `fatal: detected dubious ownership in repository at 'D:/OAS-dev/backend'` ⇒ **`git log`/`status`/`push` 全被拒**）| ★ 真因：仓库属主 = **`S-1-5-32-544`（Administrators）**，★ 当前用户 = `S-1-5-21-…-1000` ⇒ ★ git 2.35+ 的安全闸。★ **修**：`git config --global --add safe.directory D:/OAS-dev/backend`（★ 前端同理）；★ ⚠ **沙箱 `workspace-write` 下改不了** `~/.gitconfig`（`could not lock config file … Permission denied`）⇒ ★ **修这条必须先放开沙箱**（★ [10-15] 已修）★ ★ **[10-15] 本机（`D:\OAS-dev`）实测没有这个问题**（属主正常）⇒ ★ 若将来出现，写 **`D:/OAS-dev/backend`**|
| **P16** | ★★ **[10-15] `flutter` 的"版本检查"会跑 `git fetch --tags`（★ 611285 个对象）⇒ 在当前网络上**挂死** | ★ 症状：`flutter --version`（或任何不带开关的命令）卡 10+ 分钟 · 后台常驻 `git fetch --tags` + `git index-pack`（★ 实测 `git remote-https origin https://github.com/flutter/flutter.git`）⇒ ★ **正解：命令一律加 `--no-version-check`** ＋ `PUB_HOSTED_URL=https://pub.flutter-io.cn` / `FLUTTER_STORAGE_BASE_URL=https://storage.flutter-io.cn`（★ 实测 Google 源 **~170 KB/s** vs 国内镜像 **3.5 MB/s**）；★ 已卡的进程要 `Stop-Process git,dart` ＋ 删 `D:\flutter3271\bin\cache\lockfile` |
| **P17** | ★★ **[10-15] 本机缺 C++ 工具链 ⇒ `flutter build windows --release` 不可用** | ★ 实测：**无 `vswhere`** · 无 `Microsoft Visual Studio` 目录 · 无 `Windows Kits\10\bin` · 无 `cmake`/`ninja` · **无 `winget`** ⇒ ★ `analyze`/`test` **不受影响**（已跑绿）· ★ 只有构建 exe 需要 VS Build Tools（`Microsoft.VisualStudio.Workload.VCTools` + Win10/11 SDK）⇒ ★ **待裁定**（★ §2 的 ★0d）|
| **P18** | ★ **[10-15] `test_task_factory` / `test_task_flow_docs` 会重写 `docs/flows/README.md` 的行尾** | ★ 实测**可复现**：跑完测试后 `git status` 显示 ` M docs/flows/README.md`，但 `git diff --numstat` **为空** · `git diff --ignore-cr-at-eol` **0 行** ⇒ ★ 纯 LF/CRLF 幻影（`core.autocrlf=true`），★ **内容没变** ⇒ ★ `git checkout -- docs/flows/README.md` 还原；★ 根因 `module/task_factory.py:40/403` 用 Python 默认换行写回 |

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

## ★ 6b. ★★★ [10-15] 本机引导轮交接（★ **新会话优先读这一节**）

```
【本机身份】★ **开发机**（★ 用户 [10-15]："本机是开发机"）⇒ ★ 开发 = 本机 · 实机生产 = 另一台
【★★ 新会话第一步】★ **工作目录设成 `D:\OAS-dev`**（★ 项目在 D 盘；★ 上轮会话的 workspace
   `E:\OAS-dev` **已清空**）—— ★ 否则各工具的**相对路径**会落到空目录
   ★ ✅ **[10-15] `session-memory` 已装好**（★ 它是**用户级技能**，不在项目仓库里）：
   `%DSH_HOME%\skills\session-memory` → **Junction** → `D:\tools\dsh-skills`（★ 仓库 `passioki/dsh-skills`）
   ⇒ ★ **新会话直接 `skill session-memory`** 即可（★ DSH 会热加载）；★ 同步 = `cd D:\tools\dsh-skills; git pull`
   ★ 换机器要重装（★ 步骤见 `START-HERE §1.1` / `DEV-WORKFLOW §6`-⓪）
【工作区】`D:\OAS-dev\`（`backend` + `frontend` · ★ 两仓本地分支都是 **`dev`**）
   · 后端 = **`fe2bbd67`**（= 远端 `dev`）· 远端 `main` = `e28793ce`（★ 稳定 · 未动）
   · 前端 = **`daf493c`**（= 远端 `dev`）· 远端 `main` = `af10440`（★ 稳定 · 未动）
【★★ 怎么跑 —— 一律【无盘符包装脚本】】
   · 后端全量：`backend\run-tests.bat`      · 起开发后端：`backend\run-server.bat`（`:22288`）
   · 前端：`backend\dev_tools\flutter.bat {analyze lib|test|build windows --release}`
     （★ 自动找 SDK + 自动补 `--no-version-check` · ★ 坑 P16）
   · ★ **自查锚点**：`backend\toolkit\python.exe -m dev_tools.paths`（★ 四行都要指对）
【四条基线（★ [10-15] 相对路径改造后 · 本机实测）】
   ★ 守卫链 = **166 passed**（★ 14 文件的完整命令见 `START-HERE §1.3③`）
   ★ 全量 = **15 failed / 1903 passed / 7 skipped**（★★ 旧的 49/1862/12 **已作废**）
   ★ 前端 = `analyze` **0 error（4 warning + 17 info）** · `test` **158 passed**
   ★ 15 条归因：**9** 缺 `zh-CN.json`（★ 前端**运行后**才推来的运行时产物）· **2** 用户/实机状态
     · **1** 窗口外任务 · **1** 用户配置 · **1** live 配置 · ★ **1 真漂移**（见下）
【★ 路径规约（必读）】`docs/LAYOUT.md`（R1~R5）：仓库内相对仓库根 · 跨仓走 `dev_tools/paths.py`
   · 绝对路径**只允许**在 `config\deploy.yaml` 与 `dev_tools\paths.local.json`（★ 都不进 git）
   · 守卫 `test_no_hardcoded_paths` 的扫描范围**含 `tests/`**
【推送】★ **`git push origin dev`**（★ 本机本地分支就叫 `dev`；★ **绝不 `main:main`**）
【不要做】★ 实机（在另一台）不许开发/测试（P14）· ★ **实机不带前端源码、也不跑 pytest**
   （★ 用户："不参与运行的不应该存在" ⇒ ★ 跨仓测试只在开发机跑 · ★ 台账 §E-6-q）
   · ★ 跑完测试 `git checkout --` 还原幻影脏（`docs/flows/README.md` ＋ 7 个 `generated_plugin*`）
【待你裁定（★ 新会话开头就问这三条）】
   ① ★★ **真漂移怎么修**：`tests/module/config/test_linkage_unification.py::test_pause_reports_requeue`
      期望前端 `run_control_bar.dart` 有 `pauseScriptDetailed`，★ 而前端 v2 已只剩「启动/停止脚本」
      ⇒ ★ **A** 前端恢复「暂停调度」路径（SPEC §3.6）· **B** 改测试期望（★ 台账 §E-6-n）
   ② ★ **装不装 VS Build Tools**（★ 没它就不能 `build windows` · ★ 坑 P17 · ★ 台账 §E-6-f）
   ③ ★ **下一步做什么**：★ `F9`（删 `queue_panel.dart:1042-1058` 死代码 ＋ 可达性守卫 ＋ 注入验证，
      ★ 与①**同源**）还是 ★ `P1`（C5 五个原语 ＋ C9 的 `LoopBudget/StuckGuard/RetryPolicy`）
```

---

## ★ 6. ★★ 交接模板（★ [10-15] **旧开发机版** · ★ **已被 §6b 取代** —— ★ 留作历史）

```
【本次会话（10-14 ~ 10-15）做了什么】
  ① 入口核实：守卫 98 → 全量 49/1785 → 与基线逐数字一致（★ 顺带订正 4 处过期数字）
  ② N9-5 流程图：1 → 8 张（+ Tako/Orochi/RyouToppa/AreaBoss/DailyTrifles/WeeklyTrifles/
     AutoCheckinBigGod；★ 每张五段结构 + 每个判断带 文件:行号）+ 登记表 18 处中文名订正
  ③ N9-6 架构：定案 M2（= A/A+ 受控指令集，不用 eval）+ annotator 允许深度拆解（AN1~AN4）
  ④ §1.19「流程控制抽象」：9 控制面 + 11 支撑面 + 8 任务控制点实测矩阵 + ★ 三个红灯
  ⑤ P0 落地：module/flow/（Exit 8 类 / Outcome 三态 / finish 唯一映射点 / Verdict 三态 /
     Match）+ C10 entry_state；守卫 29 条 + 注入 2/2 真红
  ⑥ N9-11「新建任务」工厂：module/task_factory.py（原子 + 回滚 + NT2 命名校验 + 自动登记 +
     示例识别骨架）+ tasks/FlowDemo（★ 在 dev）+ 守卫 31 条 + 注入 3/3 真红
  ⑦ ★ 实测出「新建任务的完整合同」= 6 类（SPEC §1.16-五 NT8）：建一个任务会撞红 14 条守卫
  ⑧ FL-1（RyouToppa 没票记失败）已修 + FL-9（守卫时红时绿）已查清并修 + FL-2 = 误报
  ⑨ 纠错：曾把 FlowDemo 装进实机 ⇒ 按用户要求【已还原】+ 新增坑 P14
  ⑩ ★★★ [10-15]【两台机器分工】用户打算"一台开发 / 另一台实机生产" ⇒ ★ **已把两仓
     `dev` 推到最新**（后端 `5243cb19` · 前端 `ae1065b`）★ ＋ ★ **实测出"无缝开发"缺口清单**
     （toolkit 17000 文件/1167.4MB 等 7 项都不在 git，台账 §E-1）★ ＋ ★ 新坑 **P15**
     （本机 git dubious ownership 已修）
  ⑩b ★★★ [10-15]【★ 一次走偏与回退】我**顺手把 `main` 也快进**到 dev ⇒ ★ 用户纠正
     "**另一台可以拉dev啊，main是主要的稳定版本！**" ⇒ ✅ **已 `--force-with-lease` 回退**
     （后端 `main` = `e28793ce` · 前端 `main` = `af10440`）★ ⇒ ★ 现行：`dev` = 开发（另一台拉）
     · `main` = **主要的稳定版本** · ★ 推送一律 **`git push origin main:dev`**（绝不 `main:main`）
  ⑪ ★★★ [10-15]【前端 F9】用户报"恢复调度按钮缺少了暂停调度" ⇒ ★ **查出真因 = 死代码**：
     `queue_panel.dart:1042` 与 `:1059` 的 `else if` 条件**逐字相同** ⇒ ★ `[⏸] 暂停调度`
     **永不显示**（全仓 `pause_circle_filled` 只 1 处、`_pauseSchedule` 只 1 处）
     ⇒ ★ **已记进前端台账 F9**（★ 用户只要求记台账 ⇒ **未改代码**）
【当前代码状态】
  ★ 后端：本地 main = 5243cb19 · ★★ 远端 dev = 5243cb19（开发分支）· ★★ 远端 main = e28793ce
    （★ 10-13 15:44 · **主要的稳定版本 · 未动**）
  ★ 前端：本地 main = ae1065b · ★★ 远端 dev = ae1065b · ★★ 远端 main = af10440
    （★ 10-13 12:25 · 恢复节点 / 稳定版本 · 未动）
  ★★ 分支策略：dev = 开发（另一台拉这个）· main = 主要的稳定版本
     ★ ⚠ 本机本地分支名是 main ⇒ **推送一律 `git push origin main:dev`；绝不 `main:main`**
  ★ 守卫 = 166 passed · 全量 = 15 failed / 1903 passed / 7 skipped（★ 失败集逐条一致 = 无回归）
  ★ 前端 = analyze 0 error（4 warning + 17 info）· flutter test 158 passed
  ★ 两个仓库工作区都干净（★ 前端那 7 个 generated_plugin* 是 F7 老现象，已按惯例还原）
【下一步（按优先级）】
  0. ★★ 【等你两句话】① 两台机器的**角色**（台账 §E-1：你原话自相矛盾）② 非 git 运行时
     （toolkit 1.17GB / deploy.yaml / 账号配置 / console.bat）**怎么传给另一台**
  0b. ★★★ 【建议立刻做】前端 F9：删掉 queue_panel.dart:1042-1058 的多余分支 ⇒ 让
     `[⏸] 暂停调度` 可达（★ 1 段删除 + 1 条"可达性"守卫 + 注入验证）
  1. ★★ 【等用户一句话】dev 侧把「流程示例（FlowDemo）」真跑一次：A 先停实机 :22287 /
     B 给 dev 换设备 / C 等稳定后拷实机再跑（★ dev 与实机是同一台模拟器 127.0.0.1:16384）
  2. ★★ P1（推荐开工）：C5 补 5 个空缺原语（返回键/键盘/文本/滚动/拖拽）+ C9 的
     LoopBudget/StuckGuard/RetryPolicy 提到 module/action/（★ 每步 1~2 边界 + 注入验证）
  3. ★ N9-6 P1 剩下的：flow.json 解释器（NL1/NL2）+ 立即运行（NL3）+ 结构化日志（NL4）
  4. ★ N9-6 P2 前端编排面板 → 5. ★ N9-6 P3 端到端验收（新建周期 + 临时任务并跑通）
  6. ★ N9-5 剩余 47 张流程图（★ 登记台账已就绪，只写不改）
  7. ★ 前端 F5~F8 · 8. ★ 旧账 S3b/D7.4/D43/D45/F4/DOC4/DOC5/O1/O2/T9/T11/T14
【已知坑 / 不要做的事】
  ★★ 实机（D:\OAS-live）**不许开发/测试**（P14；★ 它是 dev 稳定后的拷贝）
  ★★ [10-15] 本机 git 若报 dubious ownership ⇒ `git config --global --add safe.directory …`
     （P15；★ **必须先放开沙箱**，否则改不了 ~/.gitconfig）
  ★ 核对行号别用 Get-Content（P13，少算 10 行）· 注入验证一律用 Python（P7）
  ★ 提交信息走 git commit -F 文件（P8）· 沙箱 workspace-write 会把测试打成假红（P11）
     （★ [10-15] 实测：同一条守卫链在沙箱内 = 10 failed / 156 passed，放开 = 166 passed）
  ★ 原生命令别接 PowerShell 管道（P12）· 不要给"播放模式"加标题（P1）
  ★ annotator 写端点无鉴权（P9）—— ★ 深度拆解前必须先加鉴权
  ★ 守卫必须做注入验证（P3）· 新建任务前先读 SPEC §1.16-五 NT8（6 类合同）
【需要用户裁定的事】
  ① ★ [10-15] **角色确认**（★ 分支策略已定：dev 开发 / main 稳定）—— ★ "另一台拉 dev" ⇒
     我推断 **本台 = 生产 · 另一台 = 开发**，★ 若相反说一声
  ② ★ [10-15] 非 git 运行时**传递方式**（U 盘 / 网盘 / 私密仓库 / 打包）—— toolkit 1.17GB 等 4 样
  ③ ★ [10-15] **前端 F9 现在修吗**（删 queue_panel.dart:1042-1058 的多余分支）
  ④ ★ dev 侧"运行"怎么跑（A/B/C，见上第 1 条）
  ⑤ ⏸ 三红灯 + FL-6/FL-8（★ 用户已说"待定，后期可能重构，暂不处理"）
  ⑥ ⚠ 建议（非阻塞）：把"库存快照"类守卫改成读实际清单（台账 §D.9 的 B 方案）
```

---

