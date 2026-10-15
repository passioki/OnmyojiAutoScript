# 存放结构树 与 路径规约（LAYOUT）★ **"路径该怎么写"的唯一入口**

> ★★ **用户裁定（[10-15]）**：
> > "**要不全改成相对路径，先设计好存放的结构树，然后改成相对引用**"
> > "**彻底去盘符**"
> > "**前端仓库要存在**"
>
> ★ 本文是 **R1~R5 规约的正文**；`START-HERE.md` / `DEV-WORKFLOW.md` 只**引用**它，不重复。

---

## ★ 1. 结构树（★ 唯一的布局约定）

```
<WORKSPACE>\                          ← ★★ 工作区根（**唯一可搬移的锚点**；不含盘符）
│                                        ★ 本机现值写在 `backend\dev_tools\paths.local.json`（不进 git）
├── backend\                          ← ★ git 仓库 #1：OAS 后端
│   ├── module\  tasks\  tests\  docs\  dev_tools\
│   ├── config\
│   │   ├── template.json             ★ 在 git
│   │   ├── deploy.yaml               ★★ **机器私有**（端口/adb/模拟器）—— 不进 git
│   │   └── 伴生树.json / 恋鸟树.json   ★★ **用户数据** —— 永不进 git
│   ├── dev_tools\paths.local.json    ★★ **机器私有锚点**（oas / oasx / flutter）—— 不进 git
│   ├── dev_tools\paths.local.json.example  ★ 模板（在 git）
│   ├── toolkit\                      ★ 不在 git（Python 运行时 + 依赖）
│   ├── console.bat · run-*.bat       ★ 按需（见 §4）
│   └── docs\LAYOUT.md                ★ 本文件
└── frontend\                         ← ★ git 仓库 #2：OASX 前端（★★ **必须存在**，见 §7）
    ├── lib\  windows\  test\  docs\  pubspec.yaml
    ├── windows\flutter\ephemeral\    ★ 由 `pub get` 生成（不进 git）
    └── build\windows\x64\runner\Release\oasx-live.exe   ★ 构建产物
```

★ **实机（另一台电脑）**：`<WORKSPACE>\backend` 拷到实机的 `D:\OAS-live\backend`；
★ **实机上也保留一份 `<WORKSPACE>\frontend` 检出**（★ 用户 [10-15]："前端仓库要存在"）——
  它**不参与运行**（实机跑的是 `oasx-live.exe`），只为了让跨仓契约测试能跑。

---

## ★ 2. 规约 R1~R5

| # | 规约 | 说明 |
|---|---|---|
| **R1** | ★ **仓库内引用一律相对仓库根** | `docs/START-HERE.md` · `toolkit/python.exe` · `config/deploy.yaml`；脚本里用 `%~dp0`（bat）· `$PSScriptRoot`（ps1）· `Path(__file__).resolve().parents[N]`（py）⇒ **代码/文档里不出现盘符** |
| **R2** | ★ **跨仓库引用一律走解析器** | 后端要前端 ⇒ `from dev_tools.paths import require_oasx`；★ 解析顺序：`$OASX_REPO` → `paths.local.json:oasx` → **`<OAS 根>/../frontend`** → 同级 `../OASX*` 历史候选 → ★ **找不到就报错**（绝不猜） |
| **R3** | ★ **绝对路径只允许出现在两个文件** | `backend\config\deploy.yaml`（已有）· `backend\dev_tools\paths.local.json`（新增）—— 两者都 `.gitignore` |
| **R4** | ★ **文档只用"工作区相对记法"** | `backend\…` / `frontend\…`；命令走 §4 的包装脚本（★ 不写盘符、不写 `flutter3271` 这类本机路径） |
| **R5** | ★ **守卫把规约钉住** | `tests/module/config/test_no_hardcoded_paths.py`：扫描 `dev_tools/` + `module/` + `tasks/` + ★ **`tests/`**（[10-15] 扩大） |

★ **解析顺序不是"多级猜测"，是"多级覆盖"**：每一级都会**打印它选了哪个**（`oasx_root(verbose=True)`），
  **不静默**；★ 找不到时返回 `None`，要强制就用 `require_oasx()`（**抛**）。

---

## ★ 3. 唯一允许绝对路径的地方（★ 怎么配）

### 3.1 `backend\dev_tools\paths.local.json`（★ 不进 git · `.gitignore:280`）

```json
{
  "oas":     "",
  "oasx":    "",
  "flutter": "<Flutter SDK 根，例如某个盘下的 flutter 目录>"
}
```

* ★ **正常情况下留空即可** —— 前端在 `<WORKSPACE>\frontend`、Flutter 在 `<WORKSPACE>\flutter*` 时自动找到。
* ★ 只有"前端/Flutter 不在工作区里"时才填（★ 本机就是这种情况：Flutter 在别的盘）。
* ★ 模板见 `dev_tools\paths.local.json.example`（在 git，可提交改动）。

### 3.2 环境变量（★ 临时覆盖 / CI）

| 变量 | 作用 |
|---|---|
| `OAS_REPO` | 覆盖后端仓库根（一般不用） |
| `OASX_REPO` | 覆盖**前端仓库**根（★ 多份克隆 / 实验副本 / CI） |
| `FLUTTER_ROOT` | 覆盖 Flutter SDK 根 |

### 3.3 `backend\config\deploy.yaml`（★ 不进 git）

端口（`WebuiPort`：开发 **22288** / 实机 **22287**）· adb · 模拟器等**本机**设置。

---

## ★ 4. 命令怎么写（★ 去盘符的三种方式）

| 场景 | 写法 | 例子 |
|---|---|---|
| **bat** | `%~dp0` / `%~dp0..` | `"%~dp0toolkit\python.exe" "%~dp0server.py"` |
| **PowerShell** | `$PSScriptRoot` | `& "$PSScriptRoot\toolkit\python.exe" -m pytest tests -q` |
| **Python** | `Path(__file__).resolve().parents[N]` | `REPO = Path(__file__).resolve().parents[3]` |

★ **仓库自带的包装脚本**（★ 推荐直接用，**与 cwd 无关**）：

| 命令 | 作用 |
|---|---|
| `backend\run-tests.bat [pytest 参数]` | 全量/部分 pytest（用仓库内 `toolkit\python.exe`） |
| `backend\run-server.bat` | 起开发后端（端口取自 `config\deploy.yaml`） |
| `backend\dev_tools\flutter.bat <子命令> [参数]` | 跑前端命令（★ 自动补 `--no-version-check`，★ 自动找到 SDK） |
| `backend\toolkit\python.exe -m dev_tools.paths` | ★ **自查**：打印工作区根 / 后端 / 前端 / Flutter 各解析到哪 |

---

## ★ 5. 守卫与豁免（R5 怎么落地）

`tests/module/config/test_no_hardcoded_paths.py`：

* ★ **扫描**：`dev_tools/` · `module/` · `tasks/` · ★ **`tests/`**（[10-15] 扩大后的范围）
* ★ **判据**：形如 `Path(r'X:\…')` 或 `= r'X:\…'` 的**代码行**（先剥掉 `#` 之后的内容）
* ★ **豁免**（划清边界，**不是**放水）：
  | 豁免 | 理由 |
  |---|---|
  | `dev_tools/paths.py` | 解析器自身（★ 现在**也去盘符了**，只留相对候选） |
  | `if __name__ == '__main__':` 块内 | 手动调试代码，不参与运行 |
  | 带 `# 调试示例` 标记的行 | 极少数模块级调试常量（★ 必须显式标） |
  | **历史文档**（`SESSION-INDEX.md` / `SESSION-LEDGER.md` / `DESIGN-SPEC.md` 的旧证据） | ★ 那是**历史流水**（当时机器上的真实路径），**不改写历史** —— 守卫只扫 `.py` |
* ★ **配套守卫**：
  * `test_paths_module_resolves` —— 解析器必须能解析出后端仓库
  * `test_paths_refuses_to_guess` —— 找不到时**不许猜**（必须抛）
  * ★★ `test_negative_result_is_never_cached` —— **"找不到"不许进缓存**（[10-15] 修的真 bug：
    同进程里一次失败会污染后续全部调用 ⇒ 全量跑时 3 条跨仓测试变红）

---

## ★ 6. 换机器 / 换盘 = 只改一个锚点

```
① 把工作区整份放到任意位置：<WORKSPACE>\{backend, frontend}
② 补"不在 git"的运行时：toolkit\ · config\deploy.yaml · 两份账号配置 · console.bat
    （清单见 DEV-WORKFLOW §6；★ 逐项实测）
③ 装 Flutter，然后**只做一件事**：
    · 若 SDK 不在 <WORKSPACE>\flutter*  ⇒ 在 dev_tools\paths.local.json 里填 "flutter"
    · 若前端不在 <WORKSPACE>\frontend ⇒ 填 "oasx"（或设 $OASX_REPO）
④ 自查：toolkit\python.exe -m dev_tools.paths   （★ 四行都要指对）
⑤ 验基线：见 START-HERE §1.3
```
★ **换盘/换目录后，代码与文档一个字都不用改** —— 这就是 R1~R5 的全部意义。

---

## ★ 7. ★★ 前端仓库必须存在（★ 用户 [10-15] 裁定）

> ★ 用户原话：★ "**前端仓库要存在**"

* ★ 跨仓测试（i18n / 队列契约 / 前端源码断言，共 **9 个文件**）**一律**用 `require_oasx()` 取前端路径。
* ★ **缺前端仓库时：响亮失败，绝不 `pytest.skip`** ——
  * 模块级解析失败 ⇒ `SystemExit`（pytest 收集期报错 / 测试期 failed，★ 都算红）
  * 文件级缺失 ⇒ `assert src.is_file()`（★ 原本是 `pytest.skip('OASX 源码不在预期位置')`，[10-15] 已改成断言）
* ★ 报错信息自带解法：`请设 $OASX_REPO 或在 …\paths.local.json 里配 oasx 路径`。

---

## ★ 8. 为什么有这份文档（★ 历史沿革，别再踩）

| 时间 | 事件 |
|---|---|
| 2026-10-11 | ★ **真 bug**：`dev_tools/gen_i18n.py` 硬编码 `…\OASX-src`，而**实际编译的是另一个目录** ⇒ i18n 写进了没人编译的地方，界面显示英文 key；排查时看到的是"i18n 加了但界面没变" ⇒ ★ 用户裁定"**杜绝硬编码，写进文档里**" ⇒ 诞生 `dev_tools/paths.py` + 守卫 |
| [10-15] | ★ **9 个测试文件仍硬编码** `…\OASX-src` / `…\OnmyojiAutoScript`（★ 守卫当时**不扫 `tests/`**）⇒ 43 条测试在"前端仓库不在该绝对路径"时全红 |
| [10-15] | ★ 用户："**全改成相对路径**"＋"**彻底去盘符**" ⇒ ① `paths.py` 去盘符 + 新增 `../frontend` 候选与 `flutter_root()` ② 9 个测试改走解析器 ③ 守卫扫描范围加 `tests/` ④ 文档改工作区相对记法 |
