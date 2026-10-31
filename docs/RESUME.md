# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round35
checkpoint_seq: 64
updated_at: 2026-11-01T00:40:00+08:00
trigger: 压缩后恢复门禁（skill + START-HERE）
status: in_progress
```

## 0. 当前状态（磁盘实测）

- 引擎 `e3721e6`，本地 `main` 干净；workspace **349 passed / 0 failed**。
- 后端文档 `d8a39313`，本地 `dev` 干净。
- 版本 **1.2.2**；v1.2.3 开发中，**未 tag/release**。
- stage 已重建/部署：`http://127.0.0.1:8788/` = HTTP 200（pid 见端口监听）。

## 1. 最近完成（U-55）

- `ScreenCache` 成为唯一截图状态所有者；
- Interpreter 删除直接持有的 `frame/matcher/frame_size/frame_seq`；
- 三入口：`observe_screen`（同一判断内共享）、`reobserve_screen`（新判断强制新帧）、`invalidate_frame`（输入后丢弃）；
- 新增 `screen_cache_shares_one_observation_until_invalidated` 测试；
- 349 tests。

## 2. 恢复门禁结果

- skill `session-memory` 已重新加载；
- `START-HERE.md` 已读；
- `RESUME.md` / `RESUME-INDEX.md` 最新行已读；
- `SESSION-HANDOFF.md` / `ENGINE-DESIGN §22.34/§22.39` / `PENDING-LEDGER §E-24~§E-26` 已读；
- 用 git/测试/端口核实：与磁盘一致（除下文文档漂移）。

## 3. 发现的文档漂移（未改代码）

| 文档 | 文档说 | 实测 |
|---|---|---|
| `START-HERE.md` §0.1/§1.3/§3 E10 | 当前基线 330 passed | **349 passed**（v1.2.3 开发后） |
| `START-HERE.md` §0.1 | 当前 V1.2.2 已发布 | 正确；另有 v1.2.3 开发中、未发布 |
| `RESUME.md`（上一版） | stage 待重建 | **已重建/部署，8788=200** |
| `SESSION-HANDOFF.md` §1 | 引擎 HEAD `678e915` / 312 tests（10-24 旧值） | 现行以 RESUME/INDEX 为准 |

## 4. 下一步

1. U-32b 批量实帧验收；
2. 发布前整体验收；
3. 仅当用户明确“发布”才 tag/release。

## 5. 证据

- PENDING §E-55；代码 `e3721e6`；349 tests；stage 8788=200。
