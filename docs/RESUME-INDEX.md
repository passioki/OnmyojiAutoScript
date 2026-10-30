# RESUME-INDEX — 断点索引（session-memory 强制 6）

> 规则：**只追加、不改旧行**。每行 = 一个断点；seq 与 `RESUME.md` 的 `checkpoint_seq` 对齐。
> 历史细节不写这里（放 handoff / git / 台账）。

**阅读顺序**：`START-HERE` → `RESUME.md` → 本文件最新行 → 行内"文档锚点/证据"。

| seq | task_id | 阶段 | 焦点 | 文档锚点 | 证据 | 下一步 | 状态 |
|---|---|---|---|---|---|---|---|
| 1 | scheduler-v3-task-template | P0 | 设计定稿 + START-HERE 引擎版；实现未开始 | `docs/ENGINE-DESIGN.md §22.34` | backend `309a4a89` · `_verify/n38/` | 完成 | done |
| 2 | oas-core-live-v1 | M0 | 扩展终点到"实机可创建任务并运行"：交付路线 M0~M5 定稿 | `docs/DELIVERY-PLAN.md` | backend `e085d726` | 完成 | done |
| 3 | oas-core-live-v1 | M0 | 范围确认：+探索/个人突破任务（Android 客户端）；APK 明确排除 | `docs/DELIVERY-PLAN.md` §3 · `docs/ENGINE-DESIGN.md §22.34` | backend `e085d726` · MuMu Android12/阴阳师2.8.84 | 完成 | done |
| 4 | oas-core-live-v1 | V1.0 | V1.0 功能交付：模板/创建/探索+个人突破/调度v3/交付包 | `docs/ENGINE-DESIGN.md §22.35` · `docs/DELIVERY-PLAN.md §8` | engine `678e915` · zip SHA256 `6169…` · `_verify/n42/REPORT-V1.0.md` | 完成 | done |
| 5 | oas-core-live-v1 | D8 | 长跑验收：96 轮等效加速 soak 96/96 成功（48+48 跨重启）；wall-clock soak 运行中 | `docs/DELIVERY-PLAN.md §8` | `_verify/n42/accel-soak/runs/accel-report-*.json` | 观察 | done |
| 6 | oas-core-editor-v11 | P0 | v1.1 P0：整屏 OCR 内联直点 + ocr_lines 测试 /lines + 中文标签 + editor.log | 用户 v1.1 设计确认 | engine `4b9ee7c` · `_verify/n43/inline/clicks.jsonl` | P1 | done |
| 7 | oas-core-editor-v11 | P1 | 素材 CRUD + 独立区域 + 拟人拖动 + flow 生成 | 用户 v1.1 设计确认 | engine `fd005b0` · `_verify/n43/crud/` · `ui_p1.png` | P2 | done |
| 8 | oas-core-editor-v11 | P2 | 任务工作台 + meta.goal 完成条件（battles 自动 loop） | 用户 v1.1 设计确认 | engine `a62e803` · `_verify/n43/ui_p2.png` | P3 | done |
| 9 | oas-core-editor-v11 | P3 | 顶部页面（工作台/任务库/实例/调度/设置）+ 实例配置读写 | 用户 v1.1 设计确认 | engine `7551377` · `_verify/n43/page_tasks2.png` 等 | P4 | done |
| 10 | oas-core-editor-v11 | P4 | 点击分布聚合 + 删除到 _trash（默认全部运行） | 用户 v1.1 设计确认 | engine `4a06d97` · `_verify/n43/ui_p4.png` | 开始 P5：回归/打包/release | in_progress |
