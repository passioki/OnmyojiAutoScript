这个是qt的翻译系统

[TS file format | Qt Linguist Manual](https://doc.qt.io/qt-6/linguist-ts-file-format.html)

## ⚠ 定位说明(2026-10 死代码清扫时核实)

**`zh_CN.qm` 在生产代码里已经没有任何读者。** 核实结果:

| 谁读 `.qm` | 结论 |
|---|---|
| OAS 生产代码(Python) | ❌ **无** —— 只用 `module/server/i18n.py` 的 `I18n.trans_zh_cn()`, 它读的是 `zh-CN.json`(由 OASX 通过 `/home/chinese_translate` 推送) |
| OASX(Flutter) | ❌ 无 —— 用它自己的 Dart i18n |
| 测试 / `dev_tools/gen_i18n.py` | ✅ 有 |

原本的读者是**已删除的 PySide6/QML GUI**(QTranslator 是 Qt 的东西), 见提交 `7d980485`。

**为什么仍保留**: `zh_CN.qm` 已随仓库发布, 无法排除旧版本 OASX 或第三方前端仍在读它。
删文件是**破坏性**的, 保留的代价很小。因此当前定位是「**仅为向后兼容**」。

**任务中文名的权威来源是 `tasks/<Name>/meta.py`。** 改任务名只改那里, 然后跑:

    python dev_tools/gen_i18n.py            # 分发到 xml / OASX dart, 并重编译 .qm
    python dev_tools/gen_i18n.py --check    # 只检查(可进 CI)

它会保证 xml、OASX 的 `i18n_cn.dart` / `i18n_content.dart`、以及 `.qm` 四处一致。
(此前这四处靠人工同步, 实测漂移了 **39 处**。)

---
以下是原有的手动说明(现已自动化, 保留作背景):

你需要手动的编写ts文件并用linguist编译生成对应的qm文件

可以手动的用记事本打开ts文件.
context就是对应的qml所使用的翻译的文件名

![image-20230528155846492](https://runhey-img-stg1.oss-cn-chengdu.aliyuncs.com/img2/202305281558027.png)
