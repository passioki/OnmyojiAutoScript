# 待办交接

> **上一轮的 9 项需求全部完成**（本轮补完 #6 与 #9），本文件不再有待办。
> 下面保留**本轮两件事的具体做法与踩过的坑** —— 下次动这两块之前先读一遍。

---

## 本轮完成（#6 吸顶 + #9 配置页前端）

| # | 项 | 落点 |
|---|---|---|
| 6 | 执行顺序页顶部按钮**吸顶** | `_QueueTab.build` → `CustomScrollView` + `SliverPersistentHeader(pinned: true)` |
| 9 | 执行顺序**配置页 1/2/3…**（前端 UI） | `_profilesRow` chips + `api_client` 5 方法 + controller 5 动作 + 偏好按页隔离 |

### #6 吸顶 —— 最终形态

```
_QueueTab.build
└─ CustomScrollView
     ├─ SliverPersistentHeader(pinned: true)   ← ★ 配置页 chips + 快捷排序 + 全局开关
     │    （delegate = `_StickyQueueHeader`, 高度用 `LayoutBuilder` **实测**）
     └─ ...QueuePanel.slivers(context, c)      ← 队列本体（一组 sliver）
          ├─ SliverToBoxAdapter(标题行 + 调度状态 + 分段条)
          ├─ SliverPadding(SliverReorderableList(行))   ← ★ 行; 可拖
          └─ SliverToBoxAdapter(尾部提示)
```

**为什么 `SliverReorderableList` 仍能越界自动滚**（用户报的 #7 不退化）:
它的 `autoScrollerVelocityScalar` 走 **`Scrollable.of(context)`** ——
也就是外层那个 `CustomScrollView` 的 position。所以"自己不是滚动容器"
不再等于"不能自动滚"。

### ★★★ 本轮踩的坑（务必避开）★★★

1. **`SliverReorderableList` 断言 `child.key != null`**
   —— key **必须挂在 `itemBuilder` 返回的那个 widget 上**。
   我第一版把 key 挂在行**内部**的 `Container` 上 → 整页抛
   `All list items must have a key`。
   `flutter analyze` **完全查不出来**（只有 widget 测试能抓到）。
   ★ 现在有真渲染守卫: `task_list_panel_test.dart` 的「#6 吸顶真渲染」。

2. **不要再出现 `ReorderableListView`**（在 `queue_panel.dart` 里）
   —— 它**自己就是一个滚动体**, 塞不进外层 `CustomScrollView`
   （滚动套滚动 → `constraints: 0<=h<=Infinity`）。
   守卫已钉死: `queue_scroll_sticky_test.dart` +
   `task_list_panel_test.dart` 各一条。

3. **吸顶区高度不许写死**
   —— 系统字号缩放 / 窄屏 `Wrap` 折行都会改高度, 写死会**裁掉按钮**。
   现在 `_StickyQueueHeader` 用 `LayoutBuilder` 实测一次 + 兜底 `76`。

4. **`QueueRow` 的辅助方法已全部搬到顶层函数**
   （`_settingsRow` / `_statusBadge` / `_zhName` / `_dupLabel` /
   `_segmentBar` / `confirmAndRemove` / `confirmClearQueue` /
   `pickAndAddToQueue`）—— 行渲染不再住在 `_QueuePanelState` 里。
   ★ 搬之前逐个查过: 没有一个用 `setState` / `mounted`（都是读 `c` + 弹窗）。
   ★ 现在 `_QueuePanelState` 只剩 3 行（`CustomScrollView(slivers: ...)`）
   —— 它保留只是为了让既有 widget 测试能直接 pump `QueuePanel`。

### #9 配置页 —— 已完成的部分

后端（`575358d6`）:

```
GET    /{script}/queue/profiles                     -> {profiles:[{id,name,count,active}], active_id}
POST   /{script}/queue/profiles                     -> 新建（不传 name 自动编号 1/2/3/…）
PUT    /{script}/queue/profiles/activate  {id}      -> 切换（★ 自动先存当前整页）
PUT    /{script}/queue/profiles/rename    {id,name} -> 改名
DELETE /{script}/queue/profiles/{id}                -> 删除（至少留一页）
```

前端（本轮）:

1. `lib/api/api_client.dart` —— 5 个方法（`res.data ?? {}`）
2. `lib/controller/task_list/task_list_controller.dart` ——
   `queueProfiles` / `queueProfileId` / `queueProfileName` +
   `loadQueueProfiles` / `createQueueProfile` / `activateQueueProfile` /
   `renameQueueProfile` / `deleteQueueProfile`
   ★ 切换 / 新建 / 删除之后**必须** `await reload()`（一页 = 队列 + 每任务
   调度 + **全局开关**, 见下）
3. ★ **偏好按页隔离**（用户裁定 2A）: key 从 `<账号>` 改成
   `<账号>:<页id>`（`_prefsKey`）; `_switchPrefsPage()` 负责
   **存旧页 → 换 key → 清 `_prefsLoaded` 闸 → 载新页**
   ⚠ `_prefsLoaded` 那道闸**必须清**（它只读一次盘）—— 不清的话切页后
   界面还是旧页的排序, 看起来"切页没反应"（这是**实测**踩过的坑）
4. `_QueueTab` 吸顶区第一行 = `配置页 ▪1▪ ▪2▪ [＋新建] [⋯管理]`
   * `▪N▪` 实心 = 当前页; **单击切页 / 双击改名**
   * `[⋯管理]` = 重命名 / 删除（删除有二次确认）
   * 文案一律用后端 `message`（**不自己再拼**）
   * 后端没有这组端点（旧版本）时整行不显示（不显示空壳）
5. 测试:
   * `test/queue_profiles_ui_test.dart`（18 条源码守卫: 5 方法 / 5 动作 /
     ★ `await reload()` 在切换之后 / ★ prefs key 含页 id / ★ 双击改名）
   * `task_list_panel_test.dart` 里 1 条**真渲染**守卫（吸顶滚动后仍在）

### ⚠ 一页 = **整页快照**（用户裁定 1甲）—— 最容易漏的一步

`activate` 换的不只是队列, 还有**每任务调度（启停/次数/优先级/预期耗时）
+ 全局开关**。所以"切页 / 新建 / 删页"之后**必须整体 `reload()`** ——
只刷队列会让总开关显示成**别的页**的值, 用户看到的是"改了不生效"。

---

## 全部 9 项（已完成）

| # | 项 | 提交 |
|---|---|---|
| 1 | 暂停铺满（54/54） | `927f2c5d` `1c419c5d` |
| 2 | 取消运行中任务（聚合进暂停按钮） | `c6185831` `1280583` |
| 3 | 「等待到点」假象 | `5aa77dbb` |
| 3b | 寮突破 window（选 A） | `b5a64469` |
| 4 | 周期任务移除即停用 | `c6185831` |
| 5 | 判据同源（`auto_queue` ↔ `period`） | `c6185831` |
| 6 | 执行顺序页顶部**吸顶** | 本轮 |
| 7 | 拖动越界自动滚动 | `7d1e9a5` |
| 8 | 首页 = 执行队列 | `7d1e9a5` |
| 9 | 配置页（后端 `575358d6` + 前端本轮） | `276e6d24` |

**测试基线**：后端 **1737 passed / 3 skipped / 4 subtests / 0 failed**；
前端 **145 passed / 0 failed**；`analyze lib` **11 条既有问题**（0 新增）；
`analyze test` **0 条**；后端文档死引用守卫 **20 passed**。

★ 工具链: `D:\flutter3271\bin\flutter`（Flutter 3.27.1 / Dart 3.6.0）
+ `OnmyojiAutoScript\toolkit\python.exe`。
⚠ `D:\flutter`（3.47.6）**解析不了本项目的 pubspec**（`intl` 约束冲突）—— 别用。
