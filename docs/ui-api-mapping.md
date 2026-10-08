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

### 2.1 执行顺序（拖拽）

| 原型 | 实现 |
|---|---|
| 拖动 `⠿` 调整 | 前端拖拽 → 生成新顺序 |
| 序号即优先级 | 写入 `script.optimization.task_order` |
| 高亮行 = 当前执行位置 | `overview.tasks[].slot == 'pending'` + `priority` |
| 默认顺序 | `schema.tasks[].list_pos`（来自 `meta.py`）|

**写入方式**（既有通用接口，无需新端点）：

```
PUT /{script}/script/optimization/task_order/value?types=string&value=A,B,C
```

**同时必须设置调度模式**，否则顺序不生效：

```
PUT /{script}/script/optimization/schedule_rule/value?types=string&value=List
```

★ `schema.list.mode_value` 就是 `'List'`，`schema.list.modes` 给出四个可选模式的标签。

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

### 2.3 休息 / 延后

| 原型控件 | 接口 | 语义 |
|---|---|---|
| `addRest('rest', N)` | `PUT /{script}/run_control/rest?minutes=N` | **全局**暂停 N 分钟（定时任务也停）|
| `addRest('delay', N)` | `PUT /{script}/run_control/delay?minutes=N` | 只推迟**列表**推进（定时任务照常）|
| `openPicker('rest')` | 前端弹窗选时长 | ✅ |
| 取消 | `minutes=0` | ✅ |

★ **这是两个不同概念，不是"作用范围"参数**（设计过程中曾混淆过）。
测试里专门有一条断言"延后不阻止定时任务"。

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

| 原型控件 | 接口 |
|---|---|
| `#loop` 循环模式 | `PUT /{script}/script/optimization/schedule_rule/value` |
| 预期执行流程（推算） | 前端根据 `next_run` + `schema.resource` 推算 |

---

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
| 3 | 无"预期执行流程"推算接口 | 原型里那张流程图要前端自己算 | 前端用 `next_run` + `resource.interval/period` 推算；或后端加 `/plan` |
| 4 | `schema` 与 `overview` 需要**两次请求** | 首次加载稍慢 | 可接受；也可后端合并（但破坏职责分离）|
| 5 | 无"任务详情页"接口规划 | 原型只画了总览+列表 | 详情页沿用既有 `GET /{script}/{task}/args`（返回完整 pydantic schema）|

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
