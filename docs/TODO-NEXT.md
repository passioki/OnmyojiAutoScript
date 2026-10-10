# 待办交接（本轮未完成的部分）

> 用户这批需求共 9 项。**已完成 8 项**（见文末）。本文件只记**剩下 2 项**
> 的**具体做法**，下一轮直接照着做，不必重新摸索。

---

## ① #6 执行顺序页 —— 顶部按钮**吸顶**（未完成）

### 用户原话

> "将执行顺序页面拎出来，**滚动时，上边的按钮和展示会一直存在**
>  而不是被滚动上去。"

### 现状（★ 只做到一半，**不要误以为已完成**）

我把「快捷排序 + 全局开关」放进了 `QueuePanel(header: ...)`
—— 那是**跟随滚动**，**不是吸顶**。

### 正确做法

`QueuePanel` 现在是**唯一滚动容器**（#7 的改动）：
`Card > ReorderableListView.builder(header: ..., footer: ...)`。

所以「吸顶 + 可拖同行」在同一个滚动体里 → 必须换成
**`CustomScrollView` + `SliverPersistentHeader(pinned: true)`**：

```
_QueueTab.build
└─ CustomScrollView
     ├─ SliverPersistentHeader(pinned: true)   ← ★ 快捷排序+全局开关（吸顶）
     ├─ SliverToBoxAdapter(QueuePanel.titleRow + statusBlock + segmentBar)
     ├─ SliverReorderableList(                     ← ★ 行; 它自己是可滚的
     │      itemCount: c.queuedTaskRows.length,
     │      onReorder: c.reorderQueue,
     │      itemBuilder: (_, i) => QueuePanel.rowBuilder(context, c, i),
     │  )
     └─ SliverToBoxAdapter(尾部提示)
```

**为什么 `SliverReorderableList` 仍能自动滚动**：它的 `autoScrollerVelocityScalar`
走的是 **`Scrollable.of(context)`**（= 外层那个 `CustomScrollView` 的
position），所以只要它在**可滚动的 viewport 内部**就生效
—— 不再要求"自己就是滚动容器"。

### ★ 唯一的难点（也是我上一轮停在这里的原因）

`QueuePanel._queueRow` 是 **239 行**，另调 **6 个同级私有方法**
（`_confirmAndRemove` / `_dupLabel` / `_settingsRow` / `_statusBadge` /
`_zhName`，约 500 行）。要让**外层**渲染每一行，必须把它们从
`_QueuePanelState` 移出来。

**建议做法（最低风险）**：

1. 新建一个 `QueueRow extends StatelessWidget`
   （字段: `TaskListController c`, `int index`）
2. 把 `_queueRow` 的方法体**整段复制**进去，`build(context)` 返回它
   - `c` 从 `widget.c` 来（把方法体里 `c.` 保持原样即可）
3. 把这 6 个辅助方法**一起**复制进去（它们是纯读操作 + `context` 用法，
   不依赖 State 生命周期；★ 逐个检查有没有用 `setState` / `mounted`）
4. 原 `_queueRow` 改为 `QueueRow(c: c, index: i)`（保持旧路径仍可用）
5. `QueuePanel.rowBuilder(context, c, i) => QueueRow(c: c, index: i)`
6. ★ **断言**：`_QueueTab` 用 `CustomScrollView`；`ReorderableListView`
   从 `queue_panel.dart` 消失；`SliverReorderableList` 存在
7. ★ 测试改动：`test/queue_scroll_sticky_test.dart` 里"QueuePanel 不许有
   `shrinkWrap: true`"要改成"不许有 `ReorderableListView`"，
   并新增"必须有 `SliverPersistentHeader(pinned: true)`"

### ⚠ 我踩过的坑（务必避开）

* **不要**在 `CustomScrollView` 里再套 `ReorderableListView`
  （滚动套滚动 → `0<=h<=Infinity` 约束错）
* 改 `queue_panel.dart` 时**不要**用"整体替换 build 开头/结尾"的脚本 ——
  我连栽两次（括号错位 / 缩进错位 / 方法被删）。**逐段小改 + 每次
  `flutter analyze <该文件>`**

---

## ② #9 执行顺序配置页 —— **前端 UI**（后端已完成）

### 用户原话

> "添加**执行顺序配置页 1/2/3/……**，可以添加、删除和切换配置页"

### 后端**已就绪并已推送**（`276e6d24`）

```
GET    /{script}/queue/profiles               -> {profiles:[{id,name,count,active}], active_id}
POST   /{script}/queue/profiles               -> 新建（不传 name 自动编号 1/2/3/…）
PUT    /{script}/queue/profiles/activate      -> 切换（★ 后端会自动先存当前页）
DELETE /{script}/queue/profiles/{id}          -> 删除（至少留一页）
```

`PUT activate` 的 `message` 已是要显示给用户的中文说明。

### 前端要做

1. `lib/api/api_client.dart` 加 4 个方法（读 `res.data ?? {}`）
2. `lib/controller/task_list/task_list_controller.dart`:
   * `List<Map<String,dynamic>> get queueProfiles`
   * `Future<void> loadQueueProfiles()` / `createQueueProfile()` /
     `activateQueueProfile(id)` / `deleteQueueProfile(id)`
   * ★ 切换/删除后要 `reload()`（`run_list` 变了）
3. `_QueueTab` 的 `header` 里（或吸顶那一行下方）加一行 chips：
   `[1][2][3] [+新建]`，当前页高亮；长按/右键或尾部小按钮出「删除」
4. 文案用后端 `message`（不要自己再拼一遍）
5. 测试：`test/queue_profiles_ui_test.dart`（源码守卫）
   * api_client 有 4 个方法
   * controller 有 4 个方法
   * `_QueueTab` 渲染 chips
   * ★ `await reload()` 在切换之后

---

## 已完成（8/9）

| # | 项 | 提交 |
|---|---|---|
| 1 | 暂停铺满（54/54） | `927f2c5d` `1c419c5d` |
| 2 | 取消运行中任务（聚合进暂停按钮） | `c6185831` `1280583` |
| 3 | 「等待到点」假象 | `5aa77dbb` |
| 3b | 寮突破 window（选 A） | `b5a64469` |
| 4 | 周期任务移除即停用 | `c6185831` |
| 5 | 判据同源（`auto_queue` ↔ `period`） | `c6185831` |
| 7 | 拖动越界自动滚动 | `7d1e9a5` |
| 8 | 首页 = 执行队列 | `7d1e9a5` |
| 9 | 配置页**后端** | `276e6d24` |

**测试基线**：后端 **1726 passed / 3 skipped / 0 failed**；
前端 **124 passed / 0 failed**；`analyze lib` **11 条既有问题**（0 新增）。
