# 逐任务流程图（索引）

> ★ **用户要求（[10-14] 记录第 5 条）**：
> > "**对每一个任务的代码逻辑，画出流程图，用于理解代码。**"
>
> ★ **目的**：★ 读代码时**先看骨架再看细节** ——
>   每张图都能对回 `文件:行号`，★ 不是"重写一遍代码"，而是
>   **决策链 + 与调度层的接口 + 已知坑**。

## ★ 每份流程图的固定结构（★ 新增时照这个写）

| 段 | 内容 |
|---|---|
| **一、总览** | ★ 从"被调度器派发"到"收尾"的主干（含换御魂 / 页面跳转 / 弹窗）|
| **二、主循环** | ★ ★ **全部决策** —— 每个判断都带 `文件:行号`，★ 并列出**每个出口的语义**（成功/失败/正常结束）|
| **三、子过程** | ★ 被主循环调用的函数（识别 / 点击 / 战斗 / 刷新 / 领奖）|
| **四、与调度层的接口** | ★★ 次数从哪来 · 本轮完成怎么上报 · 收尾怎么排下一次 · 暂停/切条怎么响应 |
| **五、已知坑** | ★ 改这个任务前**必读**的坑（历史踩过的）|

★ **行号口径（★ 血泪）**：★ 一律按 **UTF-8 文本行号**（即 read/grep 工具的口径）。
★ **不要用 `Get-Content` 核对行号** —— 它按 ANSI 解码，同一文件会**少数 10 行**
（实测：`tasks/Tako/script_task.py` 实际 **163** 行，`Get-Content` 只看到 **153** 行）。

## ★★ 已完成（8 张）

| 任务 | 中文名 | 文件 | 一句话看点 |
|---|---|---|---|
| `RealmRaid` | 个人突破 | [RealmRaid.md](RealmRaid.md) | ★ **样板**：含"退四打九 / 没券即本轮完成 / 时间上限"三条代表性分支 |
| `Tako` | 石距 | [Tako.md](Tako.md) | ★ **没有主循环**：单轮直线流程 + 组队开公开房；★ 所有出口都落 `exit_task()` |
| `Orochi` | 八岐大蛇 | [Orochi.md](Orochi.md) | ★ **组队**四角色分支（`run_leader`/`run_member`/`run_alone`/`run_wild`）+ `is_in_room()` 特殊收尾 |
| `RyouToppa` | 寮突破 | [RyouToppa.md](RyouToppa.md) | ★ 与 RealmRaid **同源**，但**"没票"的语义正好相反**（一个记成功、一个记失败）|
| `AreaBoss` | 地域鬼王 | [AreaBoss.md](AreaBoss.md) | ★ 难度/层数切换 + 热门/收藏/奖励三页 + 挑战次数 OCR |
| `DailyTrifles` | 每日琐事 | [DailyTrifles.md](DailyTrifles.md) | ★ 多子项串行（召唤/祈愿/寄语/友情/商店/买寿司），每个子项各自判"今天做过没" |
| `WeeklyTrifles` | 每周琐事 | [WeeklyTrifles.md](WeeklyTrifles.md) | ★ 每周周期 + 分享类子项（微信/收集/地域鬼王/秘闻）|
| `AutoCheckinBigGod` | 大神签到 | [AutoCheckinBigGod.md](AutoCheckinBigGod.md) | ★★ **不走素材识别**：frida 注入取 token → 签名 → HTTP 领奖（依赖 adb/frida/App 版本）|

## ★★ 待补台账（★ 全部任务的登记，一个不漏）

> ★ **规则**（★ 由 `tests/test_task_flow_docs.py` 强制）：
> ★ 每个 `tasks/<Name>/` 必须在**下表**里出现 ⇒
>   ★ **要么已有流程图**（状态 ✅ 且 `flows/<Name>.md` 存在），
>   ★ **要么在待补表里**（状态 ⬜ + **一句为什么**）。
> ★ ★ **新增任务时忘了登记 ⇒ 守卫变红**（这才是这条守卫的价值）。
>
> ★ ⚠ **[10-14] 中文名已按 `tasks/<Name>/meta.py` 的 `name_zh` 逐条订正**
>   （★ 旧版有 18 处与代码不符：如 `Tako` 被写成"章鱼"实为「**石距**」、
>   `RyouToppa` 被写成"突破"实为「**寮突破**」、`MetaDemon` 被写成"鬼王"实为「**超鬼王**」）。

| 任务（中文名）| 状态 | 图纸 / 待补理由 |
|---|---|---|
| **`RealmRaid`**（个人突破）| ✅ **已完成** | ★ **样板** → [RealmRaid.md](RealmRaid.md)（退四打九 / 没券即本轮完成 / 时间上限）|
| **`Exploration`**（探索）| ⬜ **优先 1** | ★ 历史上"跑完又跑"的**热循环**就在它身上（SPEC §2.7 / §7.6）|
| **`Orochi`**（八岐大蛇）| ✅ **已完成** | [Orochi.md](Orochi.md)（组队四角色 + `is_in_room()` 特殊收尾）|
| **`Rest`**（休息）| ⬜ **优先 3** | ★ 最简单，但它是**阻塞队列**的载体（`rest_until`）+ 刚加了 ±20% 随机（§1.14.x）|
| **`GeneralBattle`**（公共战斗循环）| ⬜ **优先 4** | ★ **被 20+ 任务共用** ⇒ ★ 一张图顶很多张（不在 `tasks/` 顶层，属 `Component`）|
| `AbyssShadows`（狭间暗域）| ⬜ 待补 | 普通战斗任务（模式与 RealmRaid 相近）|
| `ActivityShikigami`（当期爬塔）| ⬜ 待补 | 爬塔 + 两套御魂配置 |
| `AreaBoss`（地域鬼王）| ✅ **已完成** | [AreaBoss.md](AreaBoss.md) |
| `AutoCheckinBigGod`（大神签到）| ✅ **已完成** | [AutoCheckinBigGod.md](AutoCheckinBigGod.md)（frida + adb + HTTP）|
| `BondlingFairyland`（契灵之境）| ⬜ 待补 | ★ **最复杂**（多模式 + 御魂搜索 + 状态机）—— 建议**最后**做 |
| `BudokaiTournament`（武道大会）| ⬜ 待补 | 状态机 + 分段阵容 |
| `CollectiveMissions`（集体任务）| ⬜ 待补 | 轻量流程 |
| `DailyTrifles`（每日琐事）| ✅ **已完成** | [DailyTrifles.md](DailyTrifles.md)（多子项串行）|
| `Delegation`（式神委派）| ⬜ 待补 | 纯 UI 流程 |
| `DemonEncounter`（逢魔之时）| ⬜ 待补 | ★ 有**窗口**（17:00-23:00）⇒ 值得一张图 |
| `DemonRetreat`（首领退治）| ⬜ 待补 | 普通战斗任务 |
| `Dokan`（道馆）| ⬜ 待补 | ★ 有**场景检测**（`DokanSceneDetector`）|
| `Duel`（斗技）| ⬜ 待补 | 战斗 + 阵容切换 |
| `DyeTrials`（灵染试炼）| ⬜ 待补 | 普通战斗任务 |
| `EternitySea`（永生之海）| ⬜ 待补 | 两套御魂配置 |
| `EvoZone`（觉醒副本）| ⬜ 待补 | 普通战斗任务 |
| `ExperienceYoukai`（经验妖怪）| ⬜ 待补 | 普通战斗任务 |
| `FallenSun`（日轮之陨）| ⬜ 待补 | ★ 御魂"双层身份"（`fallen_sun` + `fallen_sun_2`）|
| `FindJade`（寻找协作任务）| ⬜ 待补 | 轻量流程 |
| `FloatParade`（花车巡游）| ⬜ 待补 | 轻量流程 |
| `FrogBoss`（对弈竞猜）| ⬜ 待补 | 普通战斗任务 |
| `GoryouRealm`（御灵之境）| ⬜ 待补 | ★ 刚修了"换御魂非法配置"（§1.5.y）—— 值得一张图 |
| `GotoMain`（回到庭院）| ⬜ 待补 | ★ 极简（但它是"停"的落点）|
| `GoldYoukai`（金币妖怪）| ⬜ 待补 | ★ 与 Ark/`charge` 遗留字段有关（`charge` 已删，图里要说明现状）|
| `GuildActivityMonitor`（寮活动监控）| ⬜ 待补 | 监控型（少操作）|
| `GuildBanquet`（寮宴会）| ⬜ 待补 | ★ 有**动态窗口**（`guild_banquet_time.day_N`）|
| `HeroTest`（英杰试炼）| ⬜ 待补 | 战斗 + 技能回退 |
| `Hunt`（狩猎战）| ⬜ 待补 | ★ 两套配置（麒麟 / 阴界）|
| `Hyakkiyakou`（百鬼夜行）| ⬜ 待补 | 特殊玩法（撒豆）|
| `KekkaiActivation`（结界挂卡）| ⬜ 待补 | 轻量流程 |
| `KekkaiUtilize`（结界蹭卡）| ⬜ 待补 | 轻量流程 |
| `KittyShop`（猫咪铺子）| ⬜ 待补 | 纯 UI 流程 |
| `MemoryScrolls`（绘卷）| ⬜ 待补 | ★ 有专门契约测试（`test_window_ui_contract`）|
| `MetaDemon`（超鬼王）| ⬜ 待补 | 普通战斗任务 |
| `MysteryShop`（神秘商店）| ⬜ 待补 | 纯 UI 流程 |
| `Nian`（年兽）| ⬜ 待补 | 普通战斗任务 |
| `OtherWorldTwilight`（彼世逢魔）| ⬜ 待补 | 普通战斗任务 |
| `Pets`（小猫咪）| ⬜ 待补 | 纯 UI 流程 |
| `Quiz`（智力竞赛）| ⬜ 待补 | 纯 UI 流程 |
| `Restart`（重启）| ⬜ 待补 | ★ 与**调度器待命**有关（它被当成待命占位，见 §1.5.x-SB3）|
| `RichMan`（大富翁）| ⬜ 待补 | 特殊玩法 |
| `RyouToppa`（寮突破）| ✅ **已完成** | [RyouToppa.md](RyouToppa.md)（与 RealmRaid 同源但语义相反）|
| `Secret`（秘闻副本）| ⬜ 待补 | ★ 有**窗口**（★ 每日 **07:00** 起开放；★ 旧写法提的 `success_interval` **已删除**，别再照抄）|
| `SixRealms`（六道之门）| ⬜ 待补 | 普通战斗任务 |
| `Sougenbi`（业原火）| ⬜ 待补 | 普通战斗任务 |
| `SoulsTidy`（御魂整理）| ⬜ 待补 | ★ 纯 UI + 规则判定（无战斗）|
| `Tako`（石距）| ✅ **已完成** | [Tako.md](Tako.md)（单轮直线 · 无主循环 · 公开房组队）|
| `TalismanPass`（花合战）| ⬜ 待补 | 纯 UI 流程 |
| `TrueOrochi`（真八岐大蛇）| ⬜ 待补 | 与 Orochi 相近 |
| `WantedQuests`（悬赏封印）| ⬜ 待补 | 轻量流程 |
| `WeeklyTrifles`（每周琐事）| ✅ **已完成** | [WeeklyTrifles.md](WeeklyTrifles.md)（每周周期 + 分享子项）|
| `FlowDemo`（流程示例）| ⬜ **新建任务待补** | ★ [10-14] 由「新建任务」创建 ⇒ ★ 流程图待补（★ 先看 `RealmRaid.md` 样板：五段结构 + 每个判断带 `文件:行号`）|
