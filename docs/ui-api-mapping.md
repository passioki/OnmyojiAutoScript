# 界面设计 ↔ 后端接口 对照表

> 用途：把**已确认的设计稿**（`docs/task-list-prototype.html`）里的每个控件，
> 映射到**具体接口与字段**。做前端前先对一遍，避免两种返工：
>   1. 做完才发现原型里某控件**后端没支持**
>   2. 前端**自己硬编码**了本该由接口提供的东西

---

## 0. 三个数据源分工

| 接口 | 性质 | 内容 | 界面用它做什么 |
|---|---|---|---|
| `GET /{script}/schema` | **静态**，与账号无关 | 任务名/类别/资源规则/可配字段 | 渲染**结构**（有哪些任务、哪些可设次数） |
| `GET /{script}/overview` | **动态**，一次取全 | 每任务 `can_run`/`reason`/`charges`/`next_run` | 渲染**列表与总览** |
| `GET/PUT /{script}/run_control` | 动态 | 暂停/休息/延后状态 | 渲染**顶部控制条** |
| `PUT /{script}/{task}/{group}/{arg}/value` | 写入 | 改任意配置值 | **所有**编辑操作 |
| `GET /capabilities` | 静态 | 平台能力 | 非 Windows 上灰掉不可用控件 |

★ **写入统一走既有的通用配置接口**，不为每个控件新开端点。

---

## 1. 任务总览页（原型 tab `overview`）

### 1.1 表格列 → 字段映射

| 原型列 | 接口字段 | 说明 |
|---|---|---|
| 任务 | `overview.tasks[].name_zh` | 中文名；`name` 是下划线键 |
| 类型 | `overview.tasks[].category_label` | **接口已给中文标签**，前端不必自建映射 |
| 状态 | `can_run` + `slot` + `reason` | 见下方状态语义表 |
| 目标次数 | `count` | 仅 `countable=true` 时显示；`null` = 用默认值 |
| 进度 / 存量 | `charges` 或 `count` + `schema.count_default` | 见下方进度语义表 |
| 下次运行 | `next_run` | 字符串时间 |
| 对方 | `overview.teams[]` | 组队协同；见 §1.3 |
| 在列表 | `in_list` + `list_pos` | `in_list=false` 表示未被编排 |

### 1.2 状态语义（`can_run` / `slot` / `reason`）

| `slot` | `can_run` | `reason` | 界面显示 |
|---|---|---|---|
| `pending` | `true` | `''` | 🟢 可执行 |
| `waiting` | `false` | `'等待到点'` | ⚪ 等待 |
| 任意 | `false` | `'未启用'` | ⚫ 已停用 |
| 任意 | `false` | `'不在开放时段（…）'` | 🕐 时段未到（`in_window=false`）|
| `''` | `false` | 其它 | ⚠️ 显示 `reason` 原文 |

★ **设计约束（已确认）**：总览页**不放单个任务的启停开关** ——
只有一个开关（任务列表页），但总览页**不隐藏**状态：行尾显示 `⚠ 配置中已停用`。

### 1.3 "对方"列（组队协同）

`overview.teams[]` = `[{config, online, ...}]`

| 场景 | 显示 |
|---|---|
| 无队友配置 | 留空（多数任务不需要） |
| 有队友且在线 | 🟢 队友名 |
| 有队友但离线 | ⚪ 队友名（灰） |

★ 注意：`teams` 目前是**账号级**的（哪些账号在线），
而不是"这个任务的队友"。若原型要求"每行显示该任务的队友"，
需要后端补 —— **这是待确认项，见 §5**。

### 1.4 批量操作条

| 原型控件 | 实现方式 | 后端支持 |
|---|---|---|
| `bulk('all')` 全选 | 前端本地选择 | ✅ 无需后端 |
| `bulk('none')` 全不选 | 前端本地 | ✅ |
| `bulk('invert')` 反选 | 前端本地 | ✅ |
| `bulk('listonly')` 只选在列表的 | 前端按 `in_list` 过滤 | ✅ |
| 批量启用/停用 | 循环 `PUT .../scheduler/enable/value` | ✅ 既有接口 |
| `#onlyon` 只看启用 | 前端按 `enable` 过滤 | ✅ |
| `#onlyfixed` 只看固定任务 | 前端按 `category` 过滤 | ✅ |
| `#q` 搜索 | 前端按 `name_zh`/`name` 过滤 | ✅ |

★ **批量操作是前端行为**，但每次写入都是一次 HTTP 请求。
若一次勾 50 个任务，会有 50 次请求 —— **需要后端提供批量写入端点**（见 §5）。

---

## 2. 任务列表页（原型 tab `list`）

### 2.1 执行顺序 = **固定任务 + 休息**

★ **v2 最大变化**：把**固定任务**与**定时任务**分开管理。
列表里**只有固定任务**（+ 休息）；定时任务由定时调度器管
（见 `docs/architecture.md` §5.4 与本文件 §2.6）。

| 条目 | 界面名称 | 效果 | 阻塞列表 |
|---|---|---|---|
| `task` | 任务 | 跑一个**固定任务** | ❌ 不阻塞（未就绪就跳过）|
| `rest` | **休息** | **去庭院待着** N 分钟 | ✅ |

★ v1 的 `delay`（"只停列表"）**已作废** —— 固定与定时分开管理后，
"只停列表" 不再有意义（想只停列表就关掉定时任务总开关）。
旧配置里的 `delay` 条目会被**跳过**，不会让整份配置加载失败。

★ **只有固定任务能进列表**：判定用 `run_list.is_list_task(task)`；
`from_list()` 默认校验，定时任务会被跳过并记录。

#### 读

```
GET /{script}/run_list
→ {entries: [...], task_order: [...], blocking: {...}|null, count: N}
```

#### 写（整体替换 —— 界面拖拽走这条）

```
PUT /{script}/run_list        body: [{"kind":"task","task":"A"}, {"kind":"rest","minutes":30}]
```

★ 为什么**整体替换**而不是逐条增删：界面拖拽后拿到的是**完整清单**
（含控制条目的位置），整体写入最简单可靠，也不会出现"拖到一半只写了一半"。

#### 单条增删（可选，用于"＋ 添加"按钮）

```
POST   /{script}/run_list/entry?index=2   body: {"kind":"rest","minutes":30}
DELETE /{script}/run_list/entry?index=2
```

★ `index=-1`（默认）表示追加到末尾。**能插到任意位置**才是模型 B 的意义 ——
原型说的"都可插入到任意位置"就是这个。

#### 预期执行流程

```
GET /{script}/run_list/preview
→ {flow: [{at, kind, text, note}], disclaimer: "推算, 不是保证…"}
```

★ 必须向用户显示 `disclaimer` —— 实际还受体力/网络/开放时段影响。

#### 同时必须设置调度模式

```
PUT /{script}/script/optimization/schedule_rule/value?types=string&value=List
```

★ `schema.list.mode_value` 就是 `'List'`。

#### ★ 前端不该硬编码的东西

`schema.list` 已给出：

| 字段 | 用途 |
|---|---|
| `entry_kinds[].value/label/help` | 条目类型的值、**效果名**、说明 |
| `entry_kinds[].needs_task` / `needs_minutes` / `blocks_list` | 界面据此决定显示任务选择器还是时长选择器 |
| `duration_choices` | 时长可选项（分钟）|
| `order_field` / `order_group` | 写入位置（`script.optimization.run_list`）|
| `modes` | 四个调度模式的标签 |

**前端一行映射都不该自己写。**

### 2.2 每行控制

| 原型控件 | 接口 |
|---|---|
| `enableTask('X')` 启停 | `PUT /{script}/x/scheduler/enable/value?types=boolean&value=true` |
| 每行次数输入 | `PUT /{script}/x/scheduler/target/value?types=integer&value=N` |
| `addTask('X')` 加入列表 | 追加到 `task_order` |
| `del(i)` 从列表移除 | 从 `task_order` 移除 |

★ **`target` 与 `count` 的区别**（重要）：

| 字段 | 位置 | 含义 |
|---|---|---|
| `target` | `scheduler.target` | **调度决策**：本轮想打几次（界面上的每行次数框）|
| `count` | 任务配置的 `limit_count` | **能力上限**：这个任务最多打几次 |

界面上的"目标次数"改的是 **`target`**；`count` 只在任务详情页改。

### 2.3 休息（v2 只剩这一个控制条目）

#### 层次 1：立即暂停（不在列表里）

| 控件 | 接口 | 语义 |
|---|---|---|
| 暂停调度 / 本轮跑完再停 / 继续调度 | `PUT /{script}/run_control/{pause,resume}` | **两者都暂停**（固定+定时）|

★ v1 的「全部停止 N 分钟」/「只停列表 N 分钟」两个按钮**已去掉** ——
固定与定时分开管理后，"谁停谁不停"交给**总开关**表达（见 §2.6）。

#### 层次 2：列表里的**休息条目**

```
POST /{script}/run_list/entry?index=2   body: {"kind":"rest","minutes":30}
```

★ 区别：层次 1 是"**现在**就停"；层次 2 是"**执行到这一行时**才停"
（去庭院待着 N 分钟）。

### 2.4 顶部运行控制

| 原型控件 | 接口 |
|---|---|
| `#runbtn` `toggleRun()` | `PUT /{script}/run_control/pause?mode=battle` / `resume` |
| `#pmode` 暂停模式选择 | `mode` 参数：`battle`（⏸跑完本场）/ `round`（⏭本轮跑完）|
| 当前状态 | `GET /{script}/run_control` → `paused`/`pause_mode_label`/`rest_remaining` |

**三种控件语义**（用户已确认）：

| 控件 | `mode` | 行为 |
|---|---|---|
| ⏸ 暂停调度 | `battle` | 跑完**当前这场战斗**后不再开新任务 |
| ⏭ 本轮跑完再停 | `round` | 本任务本轮**打满目标次数**再停 |
| ▶ 继续调度 | （`resume`）| 恢复 |
| **立即停** | ❌ **不提供** | 会卡在半途（战斗中/组队房间中），不安全 |

### 2.5 全局设置区

| 原型控件 | 实际接口 | 说明 |
|---|---|---|
| `#pmode` 优先级依据 | `PUT /{script}/script/optimization/schedule_rule/value` | 四个模式；当前值读 `schema.list.current_mode` |
| `#loop` **跑完循环整表** | ❌ **后端没有这个字段** | 见 §5.1 —— 换成了 `when_task_queue_empty` |
| 预期执行流程（推算） | `GET /{script}/run_list/preview` | ✅ 已实现，带 `disclaimer` |

★ **当前值必须从 `/schema` 读**，不能硬编码 —— 否则界面会误报
"顺序不生效"（实际用户早设成 `List` 了）。见 §5.2。

### 2.6 ★ 两个总开关与"两者关系"（v2 新增）

**全部从 `schema.list.global_fields` 读**，前端**不要硬编码**字段名与可选值。

| 字段 | 类型 | 标签 | 说明 |
|---|---|---|---|
| `enable_fixed` | boolean | 启用固定任务 | 固定任务总开关 |
| `enable_timed` | boolean | 启用定时任务 | 定时任务总开关 |
| `timed_priority` | string | 定时任务优先级 | `timed` 定时优先 / `list` 列表优先 |
| `rest_interleave` | boolean | 休息时可穿插定时任务 | 判据：预期完成时间 < 休息剩余 |
| `when_task_queue_empty` | string | 队列跑空后 | `goto_main` / `close_game` |

每个条目都带 `group` / `field` / `type` / `label` / `current` /
（可选）`choices` / `help` —— 前端**直接渲染**即可。

写入走**既有通用接口**：

```
PUT /{script}/script/optimization/timed_priority/value?types=string&value=timed
PUT /{script}/script/optimization/enable_fixed/value?types=boolean&value=false
```

#### 语义要点

| 项 | 说明 |
|---|---|
| 两个总开关 | **互不影响** —— 关掉固定任务不该影响定时任务 |
| `timed_priority=timed` | 固定任务在跑、定时任务到点 → **打完当前这场**就让位 |
| `timed_priority=list` | 定时任务等固定任务跑完 |
| `rest_interleave` | 判据: 定时任务的 `scheduler.expected_minutes` < 休息剩余分钟数 |
| `expected_minutes=0` | **未知** → 不穿插（保守）|

★ 插队时机是**战斗边界**，不是立即打断 —— 与「暂停调度」同一个安全点。

---

### 2.7 「运行一次」（v2 新增）

放在「停用选中」旁边（与「重置选中」是邻居）。

| 操作 | 接口 |
|---|---|
| 点一次 | `PUT /{script}/manual_run`  body: `["Orochi"]` |
| 按顺序点多个 | `PUT /{script}/manual_run`  body: `["A","B"]`（**数组顺序 = 点击顺序**）|
| 读队列 | `GET /{script}/manual_run` |
| 取消一个 | `DELETE /{script}/manual_run?task=Orochi` |
| 清空 | `DELETE /{script}/manual_run` |

`/schema` 的 `list.manual_run` 带一份摘要（`{tasks, count, head}`），
界面可以直接显示"排队中（2）"。

★ 语义要点：

| 项 | 说明 |
|---|---|
| 排队顺序 | **按点击先后**（不是按任务名/优先级）|
| 插队时机 | **任务边界** —— 跑完当前任务/战斗后才切过去 |
| 只跑一次 | 跑完**自动出队** |
| 重复点同一任务 | **不会重复排队** |
| 请求但不在 `pending` | **忽略**（不能跳过调度约束）|
| 恢复方式 | 无 —— 它是一次性请求 |

★ **不是立即打断** —— 与「暂停调度」同样的理由（打断会卡在半途）。

## 3. 开放时段表单（原型里没有，新增功能）

原型里**没有**开放时段控件（那时后端还没有这个概念）。现在接口已支持：

| 字段 | 来源 | 说明 |
|---|---|---|
| `window_enable` | `schema.window_fields[0]` | 默认 `false` = 不限时段 |
| `window_start` | `schema.window_fields[1]` | 默认 `17:00` |
| `window_end` | `schema.window_fields[2]` | 默认 `23:00`；**`end <= start` 即跨午夜** |
| `window_days` | `schema.window_fields[3]` | 逗号分隔，周一=0 |

★ **前端不该硬编码这四个字段名** —— `schema.window_fields` 已给出
名称、类型、默认值、标签，直接按它渲染表单。

---

## 4. 平台能力（原型里没有，跨平台需要）

| 用途 | 接口 |
|---|---|
| 查当前平台能力 | `GET /capabilities` |

返回：

```json
{
  "platform": "windows",
  "capabilities": [
    {"name": "window_message", "label": "窗口消息点击", "available": true},
    {"name": "window_background", "label": "后台截图", "available": true},
    {"name": "emulator_manage", "label": "模拟器管理", "available": true}
  ]
}
```

★ **前端据此把不可用的控件置灰**，而不是让用户点了没反应。

---

## 5. ⚠ 缺口清单（后端需要补，或前端需绕开）

| # | 缺口 | 影响 | 建议 |
|---|---|---|---|
| 1 | **无批量写入端点** | 批量启停 50 个任务 = 50 次请求 | 后端加 `PUT /{script}/tasks/bulk`；或前端并发请求（可接受）|
| 2 | `teams` 是**账号级**而非**任务级** | "对方"列若要求"该任务的队友"，数据不够 | 需明确需求：是账号在线状态，还是任务级队友 |
| 3 | ~~无"预期执行流程"推算接口~~ | ✅ **已补** —— `GET /{script}/run_list/preview` | — |
| 4 | `schema` 与 `overview` 需要**两次请求** | 首次加载稍慢 | 可接受；也可后端合并（但破坏职责分离）|
| 5 | 无"任务详情页"接口规划 | 原型只画了总览+列表 | 详情页沿用既有 `GET /{script}/{task}/args` |
| 6 | **「跑完循环整表」后端没有对应字段** | 原型画了但 `Script.optimization` 里没有 | 见 §5.1 |

### 5.1 ★ 关于「跑完循环整表」

原型里画了一个"跑完循环整表"开关，但**后端不支持**。

**没有为了"界面上有这一项"就造一个假字段** —— 那会**静默失效**：
`script_set_arg` 遇到不存在的字段会返回 `False` 并记 error，
**界面完全看不出来**，用户会以为设置生效了。

**界面改成了什么** —— 「全局设置」面板里换成**后端真实支持**的字段：

| 控件 | 字段 | 取值 |
|---|---|---|
| 队列跑空后 | `script.optimization.when_task_queue_empty` | `goto_main` 回庭院待命 / `close_game` 关闭游戏 |

字段名、标题、可选值、当前值**全部来自 `/schema` 的 `list.global_fields`**。

**若要真正实现"循环整表"**（属于**新功能**，不是界面适配）：

1. `Script.optimization` 加字段（如 `loop_whole_list: bool`）
2. 调度器在列表跑空时（`when_task_queue_empty` 之前）判断：回列表开头还是走原逻辑
3. `run_list` 的一次性条目会被移除，所以"循环"要能重新入队

### 5.2 ★ 界面**不能硬编码**的两个初值

| 字段 | 位置 | 坑 |
|---|---|---|
| `list.current_mode` | `/schema` | 硬编码成 `'Filter'` 会让界面**误报**"顺序不生效"（实际用户早设成 `List`）|
| `list.global_fields.*.current` | `/schema` | 必须取枚举的 `.value` —— `str(枚举)` 会得到 `'WhenTaskQueueEmpty.GOTO_MAIN'` 而非 `'goto_main'` |

★ 另一个坑：**按脚本名取配置**（`mm.config_cache(name)`），
  不要用 `config_cache_list()[0]` —— 那会读到**另一个账号**的配置。

### 5.3 ★ `/{script}/Script/args` 曾经 500（已修）

**症状**：点「脚本」菜单（以及任何走 `ArgsController.loadGroups` 的页面）报 500。

**根因**（`module/config/config_model.py` 的 `merge_value()`）：

```python
item["default"] = value["default"]      # ← $ref 属性没有 default 键
```

pydantic 的 `model_json_schema()` 里，**带 `$ref` 的属性没有 `default` 键**
（默认值在 `$defs` 里）。而 `Script` 顶层组的 4 个属性
（`device` / `error` / `optimization` / `anti_ban`）**全是指向 `$defs` 的引用**，
所以必然 `KeyError: 'default'`。

★ 这是**原有 bug**（旧的生产版同样代码），不是本次改造引入的。
  触发条件是"顶层组的属性是 `$ref`" —— 只有 `Script` 满足，所以一直没被发现。

**修法**：`value.get("default", ...)`；同时把 `groups_value[key]` 也改成
`.get()` + 跳过（同一个函数里另一处同类隐患）。

**为什么值得记进文档**：这是"**静默型 vs 崩溃型**"的对照 ——
`/overview` 与 `/schema` 都正常，只有这一个接口炸，很容易误判成"前端问题"。

### 5.4 战斗中的"随机动作"改为**只滑动**

| 项 | 改动 |
|---|---|
| 位置 | `battle_wait.py` 的 `_bw_randomclick_default` + `general_battle.py` 的 `random_click_swipt` |
| 之前 | 1/3 概率 `click(C_RANDOM_CLICK)`，1/3 左滑，1/3 右滑 |
| 现在 | **只有**左滑/右滑（各 1/2），**不再点击** |

**理由**：`C_RANDOM_CLICK` 的 `roi_front=(104,79,1050,507)` ——
**覆盖整个战斗区**，其中包括右上角的**自动战斗 / 加速**按钮。
"随机点击"很容易误触它们（用户实测反馈），后果比"没防封"严重。

两个滑动区域都**避开按钮带**，只扫过战斗画面中部；
且滑动本身也更接近真人的操作类型。

★ `C_RANDOM_CLICK` 这个资产**保留在 `assets.py`**（未删）——
  它仍可用于"确实需要随机点击且区域安全"的场景。



---

## 6. 落定结论

| 项 | 结论 |
|---|---|
| 数据源 | `schema`（结构）+ `overview`（状态），两次请求 |
| 写入 | **全部走既有通用接口**，不新增 per-控件端点 |
| 界面职责 | 总览页 = 监控 + 批量；列表页 = **唯一**的单任务控制台 |
| 单个启停开关 | **只在列表页**；总览页显示状态但不提供开关 |
| 目标次数 | 列表页改 `scheduler.target` |
| 开放时段 | 按 `schema.window_fields` 渲染，**不硬编码字段名** |
| 平台能力 | 按 `/capabilities` 灰掉不可用项 |
| 三种运行控制 | ⏸ `battle` / ⏭ `round` / ▶ `resume`；**无"立即停"** |

---

## 7. 统一控制台（四轮用户反馈后的最终结构：**单页**）

### 没有 tab —— 一页从上到下

| 顺序 | 面板 | 接口 |
|---|---|---|
| 1 | 状态行（进程状态 / 待执行数 / 等待中数 / 冷却数）| **WebSocket** 推送 |
| 2 | 批量操作（进程开关 + 批量启停/运行一次/重置选中/搜索/筛选）| PUT /{script}/{task}/scheduler/enable/value |
| 3 | **全局开关** | GET /{script}/schema 的 list.global_fields<br>PUT /{script}/optimization/{field}/value |
| 4 | **执行队列**（正在运行 + 待执行 + 等待中, 可拖拽, 每行可改次数/耗时/优先级）| GET/PUT /{script}/run_list<br>POST/DELETE /{script}/run_list/entry<br>PUT /{script}/{task}/scheduler/{target,priority,expected_minutes}/value |
| 5 | 任务表格（Excel 式批量管理, 不改顺序）| GET /{script}/overview |
| 侧 | 运行控制条（暂停/继续）| GET /{script}/run_control · PUT /{script}/run_control/{pause,resume} |
| 侧 | 日志常驻右半栏（宽度可拖, 记忆在偏好）| subscribeLog 订阅（**不要另开 WebSocket**）|

★ 「预期执行流程」对应的 GET /{script}/run_list/preview **接口保留**,
  但**界面不再单独画一块** —— 队列已经按顺序列出接下来会跑什么, 重复。

### ★ 六个易错点

1. **	arget / count / effective_target 是三个不同的东西** ——
   界面**编辑**的是 	arget, **显示**的是 effective_target:

   | 字段 | 含义 |
   |---|---|
   | 	arget | **用户设的**（0 = 用默认值）—— 输入框读写它 |
   | count | 任务配置里的**能力默认值** |
   | effective_target | **本次真正会用**的（三级回落）|

   ★ 曾经 /overview **漏了 	arget** → 队列次数永远显示默认,
     用户改了看不到反馈。**这类漏一个字段只在界面上表现为改了没用**,
     很难从后端日志发现。
2. **priority / expected_minutes 在 /{task}/scheduler/ 分组**
3. **写入要传下划线键**（
ow['name']）不是大驼峰命令名
4. **日志用订阅**, 不要另开 WebSocket 连接
5. **运行控制条的状态要看脚本进程**（ScriptModel.state）,
   不能只看 
un_control.paused —— 否则进程停了还显示运行中
6. **Obx 的回调必须直接读一个 Rx 变量** —— 写 sm?.runningTask.value
   在 sm == null 时**一次都没读**, GetX 会抛 improper use of a GetX
   并让整块面板渲染失败。**拿不到服务时返回静态 widget, 不要进 Obx。**

---

## 8. 本会话（2026-10）新增的字段与端点

### 8.1 `/overview` 每任务新增两个**队列判定**字段

| 字段 | 类型 | 含义 | 前端用途 |
|---|---|---|---|
| `queued` | bool | **当前是否在队列里**（= 用户编排了 **或** 自动进队列）| 四类分区: `queued==True` → 可拖的"待运行"; `queued==False` → 见第 3 类 |
| `auto_queue` | bool | **是否自动进队列**（任务类别属性, 来自 `meta.py` 的 `TaskSpec.auto_queue`）| 决定它该出现在队列里还是【添加任务】里 |

**四类分区的判定（前端必须照这个来, 不许自己推导）**

| # | 分类 | 判定 | 位置 |
|---|---|---|---|
| 0 | 正在运行 | **WebSocket** `runningTask` | 队列第 0 行, **不可拖** |
| 1/2 | 待运行（可跑 / 未到窗口）| `queued == True`（再用 `slot` 分灰/不灰）| 队列主体, **可拖** |
| 3 | **启用但不会运行** | `enable == True && auto_queue == False && queued == False` | **只在【添加任务】里** |
| 4 | 未启用 | `enable == False` | 只在**任务列表**里 |

★ **权威在后端**。前端不重新推导调度规则（本项目已因"知识存在两处"栽过多次）。

### 8.2 执行队列的三个端点

| 端点 | 用途 | 关键语义 |
|---|---|---|
| `GET /{script}/queue/candidates` | 【添加任务】的候选列表 | = `enable && !auto_queue && !queued`。**未启用的不出现**（用户原话: "需要先在任务列表启用，再添加任务才能进队列"）|
| `POST /{script}/queue/remove` | 把任务移出队列 | ★ **同时 `enable=false`** —— 否则自动进队列的任务会被 `build_queue()` **重新补回来**，"移除"变成无效操作。返回里带 `message`（中文提示）|
| `GET/PUT /{script}/run_list` | 用户编排（**不含**自动补齐）| 队列 = `run_list` **+ 自动补齐**（追加在已编排之后）。补齐是**派生结果**, **不回写 `run_list`** |

### 8.3 ★ 用户配置面只剩 **4** 个字段（原 16 个）

`/{script}/{task}/args` 的 `scheduler` 组**只返回**:

```
enable · priority · target · expected_minutes
```

其余 12 个字段（`next_run` / `success_interval` / `failure_interval` /
`server_update` / `delay_date` / `float_time` / `period` / `reset_at` /
`window_enable` / `window_start` / `window_end` / `window_days`）
打有 `json_schema_extra={'internal': True}`，**不下发给前端**。

`charge_*`（3 个任务的各 4 个字段）同样标记为 internal。

★ **字段仍在模型里** —— `task_delay()` 要落盘 `next_run`、
`_skip_by_period()` 要读 `period`/`reset_at`。只是**不再让用户看到**。

### 8.4 翻译（单一数据源）

| 端点 | 用途 |
|---|---|
| `GET /home/chinese_translate` | **权威全量**中文表（`module/config/i18n/zh-CN.json` + `assets/i18n` 额外词条，实测 1191 条）。**前端启动时拉它** |
| `PUT /home/chinese_translate` | **增量合并**（只补后端没有的 key, **绝不删除**）。原来它做整份覆盖 → 每次启动丢 344 条 |
| `PUT /home/chinese_translate/replace` | 整份替换（危险, 正常流程不用）|
| `POST /home/missing_translate` | 前端上报**运行时未命中的 key** → 落 `log/missing_translate.txt`，让"还剩哪些没翻"可见 |

★ 为什么需要"上报未命中": GetX 的 `.tr` 查不到 key 时**原样返回 key**，
**没有任何报错** —— 于是 `charge_enable_help` 赤裸裸显示在界面上却长期无人发现。


## 附：字段命名对照（前端易错点）

| 名字 | 出现位置 | 形式 | 例子 |
|---|---|---|---|
| 任务键 | `overview.tasks[].name` | 下划线 | `fallen_sun` |
| 任务命令 | `overview.tasks[].command` | 大驼峰 | `FallenSun` |
| 中文名 | `overview.tasks[].name_zh` | 中文 | `日轮之陨` |
| 充能记录键 | `task_state` 内部 | **压缩小写** | `experienceyoukai` |

★ 第三行那个坑**已经踩过**：`task_state.summarize()` 返回的键是
**压缩小写**（`experienceyoukai`），而 `model_dump` 的键是**下划线**
（`experience_youkai`）。后端已在 `build_overview()` 里做归一化；
前端若直接调 `task_status`，需要自己注意这个差异。
