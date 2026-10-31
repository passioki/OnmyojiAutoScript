# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round14
checkpoint_seq: 43
updated_at: 2026-10-31T19:44:00+08:00
trigger: serve 自动打开浏览器已实现；等用户验证
status: in_progress
```

## 0. 当前状态

- 引擎代码 `e43c6c1`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release。
- stage 8788 已重建/重启；`oasd serve` 默认自动开浏览器。

## 1. 本轮完成（U-38）

- `oasd serve` 监听成功后、首帧抓取后自动打开 `http://127.0.0.1:<port>/`。
- Windows `cmd /C start`，macOS `open`，Linux `xdg-open`；失败不影响服务。
- `--no-open` 关闭；`--open` 显式开启。
- stage `start-editor.bat` 不带 `--no-open`，双击启动会自动打开 **8788**。
- 代码 `e43c6c1`。

## 2. 服务化注意

Windows 服务运行在 Session 0 时不会把浏览器弹到用户桌面。要“开机自动打开网页”：

- 用**当前用户登录触发的计划任务**启动 launcher；或
- 服务只跑后端（`--no-open`），用户 launcher 负责打开网页；
- 端口统一：stage canonical = **8788**。

## 3. 下一步

1. 用户双击 start-editor.bat / 重启后确认浏览器自动打开 8788；
2. U-32b 实帧验收（positions + 匹配帧）；
3. U-20 多选整组拖动；
4. 发布时才 bump/tag/release。

## 4. 证据

- `e43c6c1`；`open_editor_url`；stage `/` 200；`--no-open` 参数。
- PENDING §E-38；START-HERE 端口/自动打开说明。
