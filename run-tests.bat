@echo off
REM ★ [10-15] 全量 / 部分 pytest —— 用仓库内 toolkit（★ 去盘符：靠 %~dp0 定位）
REM 用法（★ 与 cwd 无关）：
REM   run-tests.bat                      全量
REM   run-tests.bat tests/ -q            指定范围
REM   run-tests.bat tests/module/config/test_loop_rounds.py -q
cd /d "%~dp0"
"%~dp0toolkit\python.exe" -m pytest %*
