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

REM ③ 强制跑两组守卫（★ 任何改动之后都要跑）
toolkit\python.exe -m pytest tests/module/config/test_loop_rounds.py -q
toolkit\python.exe -m pytest tests/module/config/test_no_false_completion.py tests/tasks/test_effective_target.py -q
```

★ 三条都对得上 ⇒ ★ **可以开工**；★ 对不上 ⇒ ★ **先修对齐，别改代码**。

---

## ★ 1. 当前状态（★ 每次更新）

| 项 | 值 |
|---|---|
| ★ **日期** | 2026-10-14（★ 上轮 10-13）|
| ★ **开发工作区** | `D:\OAS-dev\`（`backend\` + `frontend\`，★ 各自是 git 仓库）|
| ★ **实机** | `D:\OAS-live\`（★ dev 的**拷贝**；端口 **22287**）|
| ★ **后端分支/提交** | `main` · ★ **`e28793ce`**（★ 已核实 = `origin/main`；★ 上轮写的 `787b489b` 已**落后 2 个文档提交**）|
| ★ **前端分支/提交** | `main` · `af10440`（★ 7 个 `generated_plugin*` 生成物被 `pub get` 改过 ⇒ **非源码**）|
| ★ **恢复节点 tag** | 后端 `recovery-20261013-scheduler-audit` · 前端 `recovery-20261013-isolated-live` |
| ★ **后端测试基线** | ★ **实测 [10-14]**：全量 = **49 failed / 1706 passed / 12 skipped**（★ 台账旧值 `35 failed` 实为**对不上**；★ 已归因：★ 大多数失败 = 测试去读 **`D:/OAS-dev/OASX-src`**（本机实际是 `frontend`）⇒ **"前端仓库不在本机"类**）；★ 守卫四文件 = **43 passed** |
| ★ **实机是否在跑** | ★ 后端 `:22287`（`D:\OAS-live\backend`）|
| ★★ **`pwsh` 可用性** | ★★ **已恢复（[10-14]）** ⇒ ★ `T14` 的"阻塞"理由**消失**；★ 我能自己跑 pytest |

## ★ 1b. ★★ [10-14] 本轮新增（★ 先看这里）

```
★ ① 收到 `D:\OAS-dev\记录\20261013-关于循环和周期任务.txt`
     （★ 10-13 实机日志 + **9 条用户反馈**）⇒ ★ 已**逐条代码核实**
     ⇒ ★ 见 `PENDING-LEDGER.md` **§C**
★ ② ★★ **P0 真 bug —— ✅ [10-14] 已修**（用户第 1 条"最后一个任务结束后报错"）：
     ★ `config.py` 用 `Function('Restart', …)` 造"待命占位"
     ⇒ ★ `ConfigModel.type()` 是拿**小写键**查 `__annotations__`
       （`config_model.py:314`）⇒ ★ **必抛 `KeyError: 'Restart'`**
     ⇒ ★ 被 `except` 吞成 warning ⇒ ★ 落到 `raise RequestHumanTakeover`
     ⇒ ★★ **整个调度循环死掉**（★ = 用户 10-12 报的"循环虚设"）
     ★ 修法（已落）：`'Restart'` ➜ **`'restart'`**（`config.py:4518`）
     ★ 守卫：`tests/module/config/test_standby_placeholder.py` **5 passed**
       ＋ ★★ 注入验证真红（改回 `'Restart'` ⇒ **3 failed**）
     ★ 规格：**新增 §1.5.x（SB1~SB5）** + `§4.5-㉑`
★ ③ ★ **N1 已完成**：新增 `tests/module/config/test_entry_target_reached.py`
     （★ 台账 `T10b` 的"零覆盖"）⇒ **11 passed** + ★★ **注入验证 3/3 真红**
★ ④ ★ 台账旧基线 `35 failed 更好` **被实测推翻** ⇒ ★ 已更正（见上表 + 台账 §C）
★ ⑤ ★★ **我自己踩的坑（已修）**：新测试文件 `os.chdir()` 不还原 ⇒
     污染共享测试进程的 `cwd` ⇒ ★ fixture 里补 `finally: os.chdir(cwd_before)`
★ ⑥ ★★★ **写守卫时连续空转两次（教训，★ 已写进 SPEC §1.5.x）**：
     ★ `get_next()` **第一行就 `self.update_scheduler()`**（`config.py:4351`）
     ⇒ ★ 在外部设 `pending_task` / `waiting_task` **会被重算覆盖**
     ⇒ ★ 必须 `monkeypatch` 打桩 `update_scheduler`；
     ★ 并且**模板里 `Restart` 默认 `enable=True`** ⇒ 实测
       `pending_task = ['Restart']` ⇒ ★ 不清空就走**出路①** ⇒ **空转**。
     ★ 判据：★ **"pass 但注入破坏后仍 pass" = 空转**（★ 必须做注入验证）
★ ⑦ ★ **N3 已完成**（★ 台账 `T21` 最后一项）：`loop_times` help 旧文案
     「跑空后 / 队列循环」在**界面上都不存在**（现行 = 「播放模式」+
     顺序/循环/乱序）⇒ ★ 已改，并新增守卫
     `tests/module/server/test_help_texts_current_ui.py`（4 条，注入验证真红）
```

## ★ 2. ★★ 下一步（★ 按优先级）

| # | 事项 | 依据 | 状态 |
|---|---|---|---|
| **N9-9** | ★ 御灵之境**更换御魂出错被静默跳过**（★ 疑 `switch_parser` 失败被 `return` 吞）| 台账 §C.1 · `SwitchSoul/switch_soul.py:90-95` | ⬜ |
| **N9-4** | ★ 新建配置页时"填的名称不生效"（要靠重命名）| 台账 §C.1 · `schema_router.py:2102-2161` | ⬜ |
| **N9-7** | ★ 周期任务运行时**没有"正在运行" tag** | 台账 §C.1 · `schema_router.py:1240-1284` | ⬜ |
| **N9-8** | ★ 复制执行顺序页后**多出自身周期任务** | 台账 §C.1 · `schema_router.py:2125-2151` | ⬜ |
| **N9-2** | ★ 核 `script.anti_ban.enable`：机上的**强制休息（2:00–8:00）到底开没开** | 台账 §C.1 | ⬜ |
| **N9-3** | ★ 休息时间**范围内随机 ±20%**（新功能，需先立 SPEC）| 台账 §C.1 | ⬜ |
| **N9-5** | ★ 逐任务**流程图**（文档）| 台账 §C.1 | ⬜ |
| **N9-6** | ★★ **annotator 集成"新建任务"**（需求级：设计 → 前后端 → 新建周期/临时任务跑通验收 → 统一管理全部周期任务）| 台账 §C.1 | ⬜ **需先写 SPEC** |
| **N2** | ★ `.py` 里 **7 处注释漂移**改齐 | 台账 `T18` · SPEC §6.6 | ⬜ |
| **N5** | ★ 前端：`D:\OAS-dev\frontend` 也建 `PENDING-LEDGER.md`（现在只后端有）| 本文件 §3 | ⬜ |
| ~~**N9-1**~~ | ~~P0 待命占位 `KeyError`~~ | 台账 §C | ✅ **已完成（[10-14]）** |
| ~~**N3**~~ | ~~`loop_times` help 旧文案~~ | 台账 `T21` | ✅ **已完成（[10-14]）** |
| ~~**N4**~~ | ~~§4.2-C 小标题仍写"未废弃"~~ | ★ **实测已完成**（`DESIGN-SPEC.md:1641` 已写"三函数已删"）| ✅ **关闭** |

## ★ 3. ★ 活跃的坑（★ 别再踩）

| # | 坑 | 一句话 |
|---|---|---|
| **P1** | ★ **`"播放模式"` 这个标题是用户要求删掉的** ⇒ ★ 前端该处**只有下拉**（顺序/循环/乱序），★ **不要"修复"成带标题** | 用户明令 |
| **P2** | ★ **前端不能放 `D:\MuMuPlayer\OAS\` 下** | 内核驱动 `PassGuard_x64.sys` 打了保护标记 ⇒ 双击打不开 |
| **P3** | ★ **守卫必须做"注入验证"** | 否则可能是恒真空转（审计已发现过 2 处）|
| **P4** | ★ **`toolkit\` / `config\deploy.yaml` / 账号配置 / `console.bat` 不在 git** | 清理目录前必须先抢救（见 `DEV-WORKFLOW.md` §1）|
| **P5** | ★ **删目录前逐个核对完整路径** | 已因"删+建同名前缀混用"误删过 `D:\OASX-Live` |
| **P6** | ★ **删含 `adb.exe` 的目录前先 `adb kill-server`** | 否则删不净 |

## ★ 4. ★ 文档权威顺序（★ 冲突时）

```
① docs/DESIGN-SPEC.md  §1~§3 正文（★ 用户的话 = 规格）
② docs/DESIGN-SPEC.md  §1.6.x / 分歧块
③ docs/PENDING-LEDGER.md（状态与依据）
④ 本文件 SESSION-HANDOFF.md（当前状态与下一步）
⑤ docs/DEV-WORKFLOW.md（流程）
⑥ 代码（★ 与 ①~⑤ 冲突 ⇒ ★ **以 ①~⑤ 为准**，并把冲突记进 SPEC §4）
```

## ★ 5. ★ 本轮（10-13）做完的事（★ 供交接，不必重做）

```
★ 判定机制：计数器 → 【时间戳】（session_start ↔ completed_session）
★ 本轮进度：不落盘（bind_counter 不读 / commit_count 不写）
★ 判定语义：计数≥target → 【临时任务跑完即完成】
★ script.py 收尾：删 _bound 死分支 / set_entry_runs 覆写 / "0 场补记 1 场"
★ 修复队列循环"轮数只到 1"（枚举取 .value）+ ★ 新增 8 条守卫（含注入验证）
★ 修 config.py 的 NameError（补 from pathlib import Path）
★ 文档收敛：SPEC §1.6.x / 分歧块⑪ / §6.6 / §4.1 重判 / Q5Q6 定案
★ 环境重建：单一工作区 D:\OAS-dev（backend + frontend）+ 实机 D:\OAS-live
★ 新增 docs/DEV-WORKFLOW.md（开发/测试/实机工作流）
```

---

## ★ 6. ★ 交接模板（★ 换会话时，把这段填好发给新会话）

```
【本次会话做了什么】
…
【当前代码状态】
后端 <commit> · 前端 <commit> · 测试 <结果>
【下一步（按优先级）】
1. …  2. …  3. …
【已知坑 / 不要做的事】
…
【需要用户裁定的事】
…
```
