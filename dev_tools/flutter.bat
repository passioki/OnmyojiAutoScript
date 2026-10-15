@echo off
REM ★ [10-15] 前端命令包装（★ 去盘符：Flutter SDK 由 dev_tools\paths.py 解析）
REM 用法（★ 与 cwd 无关；★ 自动补 --no-version-check，见坑 P16）：
REM   dev_tools\flutter.bat test
REM   dev_tools\flutter.bat analyze lib
REM   dev_tools\flutter.bat build windows --release
"%~dp0..\toolkit\python.exe" "%~dp0run_flutter.py" %*
