# RESUME — 断点续接卡（session-memory 强制 6）

> 规则：本文件**每次断点覆盖重写**；≤150 行；另一个会话只读本文件 + `RESUME-INDEX.md` 最新行
> 就能继续。细节放 `ENGINE-DESIGN.md` / `DELIVERY-PLAN.md`。

```yaml
task_id: oas-core-v123-round12
checkpoint_seq: 41
updated_at: 2026-10-31T19:25:00+08:00
trigger: 诊断回到庭院 Done 但 while 0 次；等用户修正条件
status: in_progress
```

## 0. 当前状态

- 引擎代码 `a9e7703`；workspace **344 passed**。
- 版本 1.2.2，未 tag/release；stage UI/exe 已同步并重启 8788。
- U-32b 批量实帧验收仍未闭合。

## 1. 本轮诊断（U-36）

用户看到：

```text
任务运行结束：Done（exit 0）
step seq=0 op=log ...
```

完整 run status 实际为：

```text
step seq=1 op=while result=ok detail=while 0 iteration(s)
step seq=2 op=finish result=ok detail=finish Done
```

当前 flow 条件：

```text
not (not (appear('町中')) or not (appear('召唤')))
```

化简：

```text
A = appear('町中')
B = appear('召唤')
not(¬A or ¬B) = A and B
```

⇒ 只有町中与召唤**同时出现**才循环；当前画面不满足 → 0 次循环 → Done。  
这不是 run/OCR bug；OCR 日志已是 `ocr=on`。

## 2. UI 改进

条件预览在“行未出现 + 整组非”时显示：

```text
⚠ 行“未出现”+ 整组“非”是双重取反，请确认
```

代码 `a9e7703`；stage 已同步。

## 3. 正确写法（给用户）

- 想“排除 A、B 同时存在”：
  ```text
  not (appear('A') and appear('B'))
  ```
  A/B 行都勾“出现”，行间“且”，组非。

- 想“直到町中/召唤任一出现”：
  ```text
  not (appear('A') or appear('B'))
  ```
  A/B 行都勾“出现”，行间“或”，组非。

## 4. 下一步

1. 用户按目标改写条件；
2. U-32b 实帧验收（positions + 匹配帧）；
3. U-20 多选整组拖动；
4. 发布时才 bump/tag/release。

## 5. 证据

- PENDING §E-36；stage `/task/run/status` 完整日志；code `a9e7703`；tests 344。
