@echo off
REM ★ [10-15] 起【开发】后端（★ 去盘符：靠 %~dp0 定位）
REM 端口取自 config\deploy.yaml 的 WebuiPort（开发 = 22288；实机 = 22287）
title OAS backend (dev)
cd /d "%~dp0"
"%~dp0toolkit\python.exe" "%~dp0server.py" %*
pause
