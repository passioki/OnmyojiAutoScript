# 从 git 拉下来后，如何把环境补齐
> ★ 目的：`git clone` 只给你**代码 + 配置模板 + 文档**。
> Python 运行时、依赖、i18n、账号配置**不在 git 里**（见文末"为什么"）。
> 按本文 **3 步**即可跑起来。

---

## 一、你需要额外准备的两样东西

| # | 东西 | 去哪拿 | 大小 |
|---|---|---|---|
| ① | **`OnmyojiAutoScript-easy-install.rar`** | 上游 Releases（或你本地已下载的）| 63 MB |
| ② | 你的**账号配置**（可选）| 你旧环境的 `config/*.json` | 几十 KB |

> ★ 为什么 ① 必须：它带 **`toolkit\`（Python 运行时）** 和 **`oas.exe`（启动器）**。
> ★ 这两个 **1.2 GB** 且与平台绑定，**不适合进 git**。

---

## 二、三步装好

### 第 1 步：把 easy-install 的内容铺到仓库根

把 `OnmyojiAutoScript-easy-install.rar` 解压，**把里面的内容复制到本仓库根目录**，
让结构变成：

```
<仓库根>\
├── toolkit\            ← ★ 来自 easy-install（Python 运行时）
├── oas.exe             ← ★ 来自 easy-install（启动器）
├── console.bat         ← ★ 来自 easy-install
├── deploy\             ← 仓库已有（会用仓库的覆盖）
├── module\  tasks\  script.py  server.py   ← 仓库的
└── config\template.json                    ← 仓库的
```

> ⚠ **`deploy\` 请用仓库里的版本**（`script.py` / `config.py` 等已改），
> 只从 easy-install 取 `deploy\launcher\*.bat` 与 `toolkit\`、`oas.exe`、`console.bat`。

### 第 2 步：跑引导

双击 **`1-bootstrap.bat`**（或命令行执行）。它会：

1. 校验 `toolkit\python.exe` 存在
2. `pip install -r requirements.txt`（★ 升级到本分支需要的依赖）
3. 生成 i18n：`toolkit\python.exe dev_tools\gen_i18n.py`
   > ★ 注意：这一步生成的是 **`zh_CN.xml` / `.qm`**（Qt 格式）。
   > ★ 而 **`module/config/i18n/zh-CN.json`** 是**运行时产物** ——
   >   由**前端**通过 `/chinese_translate` 推给后端（见
   >   `dev_tools/diag_i18n_drift.py` 的说明）。
   > ★ 缺它**不影响后端启动**，只是中文名可能回落到英文键。
   >   连上前端跑一次即会自动生成。
4. 若 `config\deploy.yaml` 不存在 ⇒ 从 `deploy\template` 复制一份
5. 自检：`toolkit\python.exe -c "import fastapi, uvicorn, ..."`

### 第 3 步：放配置 + 启动

1. 把**你的账号配置**（`config\恋鸟树.json` 等）放回 `config\`
   —— ★ 没有就跳过，首次启动会按 `config\template.json` 新建
2. 双击 **`console.bat`**（或 `oas.exe`）启动
3. 前端：另开一份 `passioki/OASX` 的 `oasx.exe`
   （★ 注意：必须用**官方 0.3.2 运行时 + 本仓库的 app.so**，见前端仓库说明）

---

## 三、验证装好了

```bat
toolkit\python.exe -c "import fastapi,uvicorn,pydantic;print('ok')"
toolkit\python.exe -m pytest tests -q
```

预期：`1696 passed`（★ 其中 35 项失败是"本副本缺前端仓库"导致的已知项）

---

## 四、为什么这些东西不在 git 里

| 东西 | 为什么不进 git |
|---|---|
| `toolkit\`（含 Python 与 1GB 依赖）| ★ 平台绑定 + 体积太大；`.gitignore` 里 `/toolkit` |
| `config\*.json`（账号配置）| ★ **用户数据**（含队列/次数/设置），不该公开；`.gitignore` 里 `config/*.json`（只放行 `template*.json`）|
| `config\*.yaml` | ★ 部署配置（含本机路径）；`.gitignore` 里 `config/*.yaml` |
| `module/config/i18n/*.json` | ★ **可生成**（`dev_tools/gen_i18n.py`）；`.gitignore` 明确排除 |
| `console.bat` / `deploy/launcher/*.bat` | ★ 上游 `.gitignore` 明确排除（属发布物）|
| `log/` `tmp*` `__pycache__/` `pytest-of-*` | ★ 运行时产物 |

---

## 五、一句话总结

```
★ git 提供：代码 + 模板 + 文档        ⇒  能"看到"全部逻辑
★ 你还要补：toolkit（运行时）+ 账号配置  ⇒  才能"跑起来"
★ 补齐靠：OnmyojiAutoScript-easy-install.rar  +  1-bootstrap.bat
```
