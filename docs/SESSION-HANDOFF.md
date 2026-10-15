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

REM ③ 强制跑守卫（★ 期望：全部 passed —— ★ [10-14] 第三轮 = 135 条）
toolkit\python.exe -m pytest tests/test_comment_drift.py tests/test_task_flow_docs.py tests/module/config/test_standby_placeholder.py tests/module/config/test_entry_target_reached.py tests/module/server/test_help_texts_current_ui.py tests/module/server/test_profile_name_from_user.py tests/module/server/test_profile_transfer_keeps_enables.py tests/tasks/Component/SwitchSoul/test_switch_soul_validation.py tests/tasks/test_rest_random_minutes.py tests/module/config/test_loop_rounds.py tests/tasks/test_no_ticket_is_success.py tests/module/flow/test_control_types.py tests/module/config/test_entry_custom_state.py -q
```

★ 三条都对得上 ⇒ ★ **可以开工**；★ 对不上 ⇒ ★ **先修对齐，别改代码**。

---

## ★ 1. 当前状态（★ 每次更新）

| 项 | 值 |
|---|---|
| ★ **日期** | ★ **2026-10-15**（★ 上轮 10-14）|
| ★ **开发工作区** | `D:\OAS-dev\`（`backend\` + `frontend\`，★ 各自是 git 仓库）★★ **[10-15] 用户打算把它挪到【另一台电脑】**（★ 见 §1i 与台账 §E）|
| ★ **实机** | `D:\OAS-live\`（★ dev 的**拷贝**；端口 **22287**；开发用 **22288**）★★ **不许在它上面做开发/测试**（★ 坑 P14）|
| ★ **后端分支/提交** | `main` · ★ **`2650b6d2`** · ★ **远端 `dev` = 同** · ★★ **远端 `main` = `2650b6d2`**（★ [10-15] **已快进** `e28793ce..2650b6d2`，纯快进 rc=0）|
| ★ **前端分支/提交** | `main` · ★ **`3978598`** · ★ **远端 `dev` = 同** · ★★ **远端 `main` = `3978598`**（★ [10-15] **已快进** `af10440..3978598`，纯快进 rc=0）|
| ★ **恢复节点 tag** | 后端 `recovery-20261013-scheduler-audit` · 前端 `recovery-20261013-isolated-live` |
| ★★ **测试基线（★ 实测 [10-14] 第五轮 · ★ 且 `tasks/FlowDemo` 已在库）** | ★ **守卫 = 166 passed**（★ 135 + 新增 31：`tests/module/test_task_factory.py`）<br>后端全量 = **49 failed / 1862 passed / 12 skipped**（★ **失败集与基线逐条一致** = 无回归）· ★ 前端 = `flutter test` **158 passed** · `flutter analyze` **0 error**（4 warning + 17 info）|
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

## ★ 1c. ★★ [10-14] 第二轮做完的（★ 交接用 · ★ **本轮只动文档，没动一行代码**）

```
★ 【入口自检】守卫 **98 passed** · 全量 **49 failed / 1785 passed / 12 skipped** · 前端 **0 error + 158 passed**
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
★ 【数字】★ 守卫 **106 passed** · 全量 **49 failed / 1793 passed / 12 skipped**
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
★ 【数字】★ 守卫 **135 passed**（106 + 29）· ★ 全量 **49 failed / 1826 passed / 12 skipped**
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
   ★ dev 侧已撤掉（★ 保持基线绿：49 failed / 1858 passed）
★ 【数字】★ 守卫 **166 passed** · ★ 全量 **49 failed / 1858 passed / 12 skipped**（★ 失败集逐条一致）
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
★ 【数字】★ 守卫 **166 passed** · ★ 全量 **49 failed / 1862 passed / 12 skipped**（★ 失败集逐条一致）
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

★ 【② 的实测】
  · ★ 远端 `dev` **本来就 = 本地 `main`**（后端 `2650b6d2` · 前端 `3978598`）⇒ ★ 只需**快进 `main`**
  · ★ 已推（★ 都 rc=0 · **纯快进**）：后端 `e28793ce..2650b6d2` · 前端 `af10440..3978598`
  · ★★ **但 git 只给"源码级无缝"**：`toolkit\`（★ 实测 **17000 文件 / 1167.4 MB**）·
    `config/deploy.yaml` · **账号配置**（`恋鸟树.json`/`伴生树.json`）· `console.bat`
    —— ★ **全都不在 git** ⇒ ★ 清单见台账 **§E-1**（7 项）

★ 【新坑 **P15**】本机 `git` 报 `dubious ownership`（★ 仓库属主 = `Administrators`，当前用户不同）
  ⇒ ✅ 已 `git config --global --add safe.directory <backend|frontend>` 修好
  ⇒ ★ 沙箱 `workspace-write` 下**改不了** `~/.gitconfig`（`could not lock config file`）

★ 【四条基线复核（★ 实测）】★ 守卫 **166 passed** · ★ 全量 **49 failed / 1862 passed / 12 skipped**
  · ★ 前端 `analyze` **0 error（4 warning + 17 info）** · `flutter test` **158 passed**
  ⇒ ★ 与 [10-14] 基线**逐数字一致**

★ 【⚠ 用户口径里有一处矛盾（★ 待裁定）】"另一台…用于实机生产" vs "本台电脑为实机生产用"
  ⇒ ★ 我按**后者**执行（★ 本台 = 生产，另一台 = 开发）；★ 见台账 **§E-1** / `DEV-WORKFLOW.md §0.6`
```

## ★ 2. ★★ 下一步（★ 按优先级）

| # | 事项 | 依据 | 状态 |
|---|---|---|---|
| **★0** | ★★★ **[10-15] 待你裁定：两台机器的角色** —— ★ 你原话里"**另一台…用于实机生产**"与"**本台电脑为实机生产用**"**互相矛盾**；★ 我按后者执行（★ 本台 = 生产 · 另一台 = 开发）| **台账 §E-1** · **`DEV-WORKFLOW.md §0.6`** | ⬜ **等你一句话** |
| **★0b** | ★★ **[10-15] 待你定：非 git 的运行时怎么传给另一台** —— `toolkit\`（**17000 文件 / 1167.4 MB**）· `config/deploy.yaml` · ★ **账号配置**（`恋鸟树`/`伴生树`）· `console.bat` ★★ **光 git 不足以"无缝开发"** | **台账 §E-1**（★ 7 项实测清单）| ⬜ **等你选方式**（★ U 盘 / 网盘 / 私密仓库 / 打包）|
| **★0c** | ★★★ **[10-15] `F9`：删掉 `queue_panel.dart:1042-1058` 的多余分支** ⇒ 让 `[⏸] 暂停调度` 可达（★ 真因 = 与 `:1059` **条件逐字相同** ⇒ 死代码）。★ 用户本轮只要求"**先记台账**" | **前端台账 `F9`** · **SPEC §3.6 现行口径 · §3.4-L3 · §1.4-Z3** | ⬜ **建议立刻做**（★ 删 1 段 + 1 条"可达性"守卫 + 注入验证）|
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
| **P7** | ★ **`pwsh -replace` 注入会静默不生效**（正则 + `$` 展开）| ★ **注入一律用 Python `str.replace`** + 打印"是否生效" + 还原比 SHA256 |
| **P8** | ★ **`git commit -m` 带中文引号/反引号会被 PowerShell 吞** | ★ **用 `git commit -F <文件>`**（★ 文件放**仓库外**，否则会误提交）|
| **P9** | ★ **`/tool/annotator` 的写端点【无鉴权】**（`tool_router.py` 无 `Depends`；`app.py:112` 的 `-k/--key` **从未被使用**）| ★ 这直接决定了 N9-6 的架构选择（见 §2-★1）|
| **P10** | ★ **测试去读 `D:/OAS-dev/OASX-src`**（本机没有；真实前端在 `frontend`）| 那 43 条失败是**环境类**，不是回归 |
| **P11** | ★★ **DSH 沙箱（`workspace-write`）会把 125 条测试打成"假红"** | `script_process.py:30` 的 `multiprocessing.Pipe`（**命名管道**）被沙箱拒 ⇒ `PermissionError [WinError 5]`：★ 受约束 = **141 failed / 1570 passed / 125 errors**，★ 放开 = **49 / 1785** ⇒ ★ **跑 pytest 必须放开沙箱** |
| **P12** | ★ **沙箱下原生命令接 PowerShell 管道 = `Access is denied`** | 如 `python.exe … \| Select-Object` / `git … \| Select-String` ⇒ ★ **别接管道**（看工具自动截尾，或 `Select-String` 只读文件）|
| **P13** | ★★ **核对行号不要用 `Get-Content`** | 它按 **ANSI** 解码 ⇒ 同一文件**少算行**（实测 `tasks/Tako/script_task.py` = **163** 行，`Get-Content` 只看到 **153** 行 ⇒ 行号**整体错位**）★ 用 **read/grep 工具**（与 `Select-String` 口径一致）|
| **P14** | ★★ **不要把开发中的东西写进实机 `D:\OAS-live`** | ★ 用户原话："**不要在实机跑，现有开发基于 dev 侧，实机是版本稳定后直接从 dev 拷贝过去**"（★ `START-HERE.md` §0 已写死：★ **实机 = dev 的拷贝**）⇒ ★ 我 [10-14] 曾把新建的 `FlowDemo` 装进实机（**已还原**：删目录 + 重生成 catalog + 新进程复验 55 个任务）|
| **P15** | ★★ **本机 `git` 报 `dubious ownership`**（★ `fatal: detected dubious ownership in repository at 'D:/OAS-dev/backend'` ⇒ **`git log`/`status`/`push` 全被拒**）| ★ 真因：仓库属主 = **`S-1-5-32-544`（Administrators）**，★ 当前用户 = `S-1-5-21-…-1000` ⇒ ★ git 2.35+ 的安全闸。★ **修**：`git config --global --add safe.directory D:/OAS-dev/backend`（★ 前端同理）；★ ⚠ **沙箱 `workspace-write` 下改不了** `~/.gitconfig`（`could not lock config file … Permission denied`）⇒ ★ **修这条必须先放开沙箱**（★ [10-15] 已修）|

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

## ★ 6. ★★ 交接模板（★ [10-15] 已按当前状态填好 —— ★ 可直接粘给新会话）

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
     `main` 快进到 dev 最新并推上 GitHub**（后端 e28793ce..2650b6d2 · 前端 af10440..3978598，
     都是纯快进）★ ＋ ★ **实测出"无缝开发"缺口清单**（toolkit 17000 文件/1167.4MB 等 7 项
     都不在 git，台账 §E-1）★ ＋ ★ 新坑 **P15**（本机 git dubious ownership 已修）
  ⑪ ★★★ [10-15]【前端 F9】用户报"恢复调度按钮缺少了暂停调度" ⇒ ★ **查出真因 = 死代码**：
     `queue_panel.dart:1042` 与 `:1059` 的 `else if` 条件**逐字相同** ⇒ ★ `[⏸] 暂停调度`
     **永不显示**（全仓 `pause_circle_filled` 只 1 处、`_pauseSchedule` 只 1 处）
     ⇒ ★ **已记进前端台账 F9**（★ 用户只要求记台账 ⇒ **未改代码**）
【当前代码状态】
  ★ 后端 main = 2650b6d2 · 远端 dev = 同 · ★★ 远端 main = **2650b6d2**（[10-15] 已快进推上）
  ★ 前端 main = 3978598 · 远端 dev = 同 · ★★ 远端 main = **3978598**（[10-15] 已快进推上）
  ★ 守卫 = 166 passed · 全量 = 49 failed / 1862 passed / 12 skipped（★ 失败集逐条一致 = 无回归）
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
  ① ★ [10-15] 两台机器的**角色**（★ 你原话自相矛盾 → 台账 §E-1 / DEV-WORKFLOW §0.6）
  ② ★ [10-15] 非 git 运行时**传递方式**（U 盘 / 网盘 / 私密仓库 / 打包）
  ③ ★ dev 侧"运行"怎么跑（A/B/C，见上第 1 条）
  ④ ⏸ 三红灯 + FL-6/FL-8（★ 用户已说"待定，后期可能重构，暂不处理"）
  ⑤ ⚠ 建议（非阻塞）：把"库存快照"类守卫改成读实际清单（台账 §D.9 的 B 方案）
```

---

