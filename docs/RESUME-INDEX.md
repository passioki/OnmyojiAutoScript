# RESUME-INDEX — 断点索引（session-memory 强制 6）

> 规则：**只追加、不改旧行**。每行 = 一个断点；seq 与 `RESUME.md` 的 `checkpoint_seq` 对齐。
> 历史细节不写这里（放 handoff / git / 台账）。

**阅读顺序**：`START-HERE` → `RESUME.md` → 本文件最新行 → 行内"文档锚点/证据"。

| seq | task_id | 阶段 | 焦点 | 文档锚点 | 证据 | 下一步 | 状态 |
|---|---|---|---|---|---|---|---|
| 1 | scheduler-v3-task-template | P0 | 设计定稿 + START-HERE 引擎版；实现未开始 | `docs/ENGINE-DESIGN.md §22.34` | backend `309a4a89` · `_verify/n38/` | `cd oas-core && cargo test --workspace`；然后 P0-1 `crates/oas-task/src/lib.rs` 模板字段 | done |
| 2 | oas-core-live-v1 | M0 | 扩展终点到"实机可创建任务并运行"：交付路线 M0~M5 定稿；实现未开始 | `docs/DELIVERY-PLAN.md` | backend `e085d726` + `_verify/n38/` | `cargo test --workspace`；M0：`crates/oas-task/src/lib.rs` 模板契约字段 + `param()` + `task lint` | done |
| 3 | oas-core-live-v1 | M0 | 范围确认：+探索/个人突破任务（Android 客户端）；APK 明确排除；开始 M0 实现 | `docs/DELIVERY-PLAN.md` §3 · `docs/ENGINE-DESIGN.md §22.34` | backend `e085d726` · MuMu Android12/阴阳师2.8.84 · `_verify/n41/now2.png` | M0 模板契约 + `param()` + lint；随后 M1 创建闭环 | done |
| 4 | oas-core-live-v1 | V1.0 | V1.0 功能全部交付：模板/创建/探索+个人突破/调度v3/交付包；仅 24h soak 待回填 | `docs/ENGINE-DESIGN.md §22.35` · `docs/DELIVERY-PLAN.md §8` | engine `7a4c58c` · zip SHA256 `6169…` · `_verify/n42/REPORT-V1.0.md` | 检查 soak pid=1268 / events，满 24h 回填 D8 | in_progress |
