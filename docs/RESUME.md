# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round22
checkpoint_seq: 51
updated_at: 2026-10-31T22:15:00+08:00
trigger: 素材分类/实时画面/回边外绕/搜索候选已实现；等验收
status: in_progress
```

## 0. 当前状态

- 引擎代码 `9ce1cc3`；workspace **346 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步/重启 8788。

## 1. 本轮完成（U-43）

| ID | 内容 |
|---|---|
| U-43a | `/task/assets` 返回 `category`（继承第一个位置帧分类；集合=素材集合）；素材库/任务引用/builder 按分类分组；素材库新增分类筛选 |
| U-43b | 移除启动 `do_capture`；新增 `/frame.png?live=1` 实时抓帧但不入库；UI 默认实时轮询 1.2s；「实时：开/暂停」；截图/选帧/上传暂停 |
| U-43c | loop/continue 回边走图外侧正交 lane（body 底部→外围右→header 右），虚线；分层图 back-edge 外绕常用做法 |
| U-43d | `OASAssetUI.createSearchPicker` 统一搜索+候选；builder 素材字段与素材位置选择共用；位置候选 = `分类 / #id 帧名` |

## 2. 验证

- stage `GET /frame.png?live=1` 200，frames 数量不变；
- CDP 位置候选可选并加入列表；回边路径 `M 430 722 V 884 H 579 V 193 H 435`；
- `__oasErrors=[]`；346 tests。

## 3. 仍待/说明

- 实时画面目前是 1.2s 轮询；旧 OAS 是 WebSocket 2fps，后续可升级后台采集/MJPEG；
- 素材分类依赖 positions；未设置位置 → 未分类；
- U-32b 批量实帧验收、U-20 多选整组拖动仍待。

## 4. 下一步

1. 用户验收分类/实时/图/位置搜索；
2. U-32b positions 批量；
3. U-20；
4. 发布时才 bump/tag/release。

## 5. 证据

- PENDING §E-43；代码 `9ce1cc3`；346 tests；stage 8788。
