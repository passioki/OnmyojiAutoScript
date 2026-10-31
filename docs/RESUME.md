# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round13
checkpoint_seq: 42
updated_at: 2026-10-31T19:40:00+08:00
trigger: 8787 打不开诊断（实际服务在 8788）；等待用户确认是否统一端口/注册服务
status: in_progress
```

## 0. 当前状态

- 代码 `a9e7703`；workspace 344 passed；版本 1.2.2 未发布。
- **stage 当前监听 8788**（pid 12416，OCR/det 正常）；8787 无监听。
- stage UI/exe 已同步。

## 1. 本轮诊断（U-37）

- Firefox 打开 `127.0.0.1:8787` → 连接失败；
- 原因不是程序崩溃，而是**端口不一致**：
  - `START-HERE` 的开发手动 serve 用 8787；
  - `dist\stage\start-editor.bat` 固定 8788；
  - 用户书签/地址还是 8787。
- 正确 stage 地址：**http://127.0.0.1:8788/**。

## 2. 注册为程序能否避免

不能自动避免：

- Windows 服务/计划任务能保证进程启动 + 失败重启；
- 但若服务端口/启动参数/书签仍是 8787 而服务跑 8788，仍然 connection refused。
- 要真正稳定需要：
  1. 端口统一到 `config/live.json`，launcher 读取；
  2. 启动后健康检查 `/state` 成功再打开正确 URL；
  3. 服务失败重启；
  4. 桌面快捷方式用 canonical URL。

## 3. 待用户确认

- 统一端口用 **8788**（保持 stage launcher）还是改回 **8787**（匹配书签）？
- 是否要我做 Windows 开机自启/服务 + 健康检查 launcher？

## 4. 下一步

1. 用户先用 8788 打开；
2. 决定端口后统一脚本/书签/文档；
3. U-32b 实帧验收、U-20 多选整组拖动仍待办。

## 5. 证据

- `Get-NetTCPConnection`：8787 down、8788 LISTEN pid 12416；
- `/state` 8788：captured=true, ocr=true, det=true；
- PENDING §E-37；START-HERE 端口说明已补。
