@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title OAS 引导（从 git 拉下来后补齐环境）

rem ★★★ 从 git 拉下来后，跑本脚本补齐环境 ★★★
rem 详见 SETUP-FROM-GIT.md
rem
rem 做四件事：
rem   1. 校验 toolkit\python.exe 存在（没有就提示去拿 easy-install.rar）
rem   2. pip install -r requirements.txt
rem   3. 生成 i18n（dev_tools\gen_i18n.py）
rem   4. 补 config\deploy.yaml（若缺）
rem   5. 自检

set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ==============================================================
echo   OAS 引导（补齐 Python 依赖 / i18n / 配置）
echo   仓库根 = %ROOT%
echo ==============================================================
echo.

rem ---------- 1. toolkit ----------
if not exist "%ROOT%toolkit\python.exe" (
  echo [错误] 找不到 toolkit\python.exe
  echo.
  echo   ★ Python 运行时不在 git 里（1.2 GB，平台绑定）。
  echo   ★ 请先取 OnmyojiAutoScript-easy-install.rar，
  echo     解压后把里面的 toolkit\ oas.exe console.bat 复制到本目录，
  echo     再重新运行本脚本。详见 SETUP-FROM-GIT.md
  echo.
  pause
  exit /b 1
)
echo [1/5] 找到 %ROOT%toolkit\python.exe
"%ROOT%toolkit\python.exe" --version
echo.

rem ---------- 2. pip ----------
echo [2/5] 安装/升级依赖（requirements.txt）…
"%ROOT%toolkit\python.exe" -m pip install -r "%ROOT%requirements.txt" ^
  --trusted-host pypi.org --trusted-host files.pythonhosted.org ^
  --disable-pip-version-check
if errorlevel 1 (
  echo [警告] pip 返回非零；若只是"已满足"可忽略，继续。
)
echo.

rem ---------- 3. i18n ----------
echo [3/5] 生成 i18n …
if exist "%ROOT%dev_tools\gen_i18n.py" (
  "%ROOT%toolkit\python.exe" "%ROOT%dev_tools\gen_i18n.py"
  if errorlevel 1 echo [警告] i18n 生成失败，继续（界面可能缺中文）。
) else (
  echo       跳过（没有 dev_tools\gen_i18n.py）
)
echo.

rem ---------- 4. deploy.yaml ----------
echo [4/5] 检查 config\deploy.yaml …
if exist "%ROOT%config\deploy.yaml" (
  echo       已存在，跳过
) else (
  if exist "%ROOT%deploy\template" (
    mkdir "%ROOT%config" 2>nul
    copy /y "%ROOT%deploy\template" "%ROOT%config\deploy.yaml" >nul
    echo       已从 deploy\template 复制
  ) else (
    echo       [提示] 没有 deploy\template；首次启动会自动生成
  )
)
echo.

rem ---------- 5. 自检 ----------
echo [5/5] 自检关键依赖 …
"%ROOT%toolkit\python.exe" -c "import fastapi,uvicorn,pydantic;print('  核心依赖 ok')"
if errorlevel 1 (
  echo [错误] 核心依赖缺失 —— 请检查上面的 pip 输出
  pause
  exit /b 1
)
"%ROOT%toolkit\python.exe" -c "import module.config.config as c;print('  module 可导入 ok')"
echo.

echo ==============================================================
echo   引导完成
echo ==============================================================
echo   下一步：
echo     1) 把你的账号配置放进 config\  （如 恋鸟树.json；没有可跳过）
echo     2) 双击 console.bat 或 oas.exe 启动后端
echo     3) 前端用 passioki/OASX 的 oasx.exe
echo ==============================================================
pause
