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
| ★ **日期** | 2026-10-13 |
| ★ **开发工作区** | `D:\OAS-dev\`（`backend\` + `frontend\`，★ 各自是 git 仓库）|
| ★ **实机** | `D:\OAS-live\`（★ dev 的**拷贝**；端口 **22287**）|
| ★ **后端分支/提交** | `main` · ★ **`787b489b`**（文档）/ `b858496c`（代码）|
| ★ **前端分支/提交** | `main` · `af10440` |
| ★ **恢复节点 tag** | 后端 `recovery-20261013-scheduler-audit` · 前端 `recovery-20261013-isolated-live` |
| ★ **后端测试基线** | ★ `test_loop_rounds.py` **8 passed**；★ 全量：失败项**只应**是"前端仓库不在本机"类 |
| ★ **实机是否在跑** | ★ 后端 `:22287`（`D:\OAS-live\backend`）|

## ★ 2. ★★ 下一步（★ 按优先级）

| # | 事项 | 依据 | 状态 |
|---|---|---|---|
| **N1** | ★ `entry_target_reached()` 补测试（**唯一还缺的守卫**）| 台账 `T10b` | ⬜ |
| **N2** | ★ `.py` 里 **7 处注释漂移**改齐 | 台账 `T18` · SPEC §6.6 | ⬜ |
| **N3** | ★ `loop_times` 的 help 文案改"播放模式"口径（现仍写「跑空后/队列循环」）| 台账 `T21` · `schema_router.py:467` | ⬜ |
| **N4** | ★ §4.2-C 小标题仍写"未废弃"（正文已改 ✅）| SPEC §6.6 | ⬜ |
| **N5** | ★ 前端：`D:\OAS-dev\frontend` 也建 `PENDING-LEDGER.md`（现在只后端有）| 本文件 §3 | ⬜ |

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
