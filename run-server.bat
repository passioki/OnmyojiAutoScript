@echo off
REM [10-15] Start the DEV backend.
REM Port comes from config\deploy.yaml -> WebuiPort (dev = 22288 ; live = 22287).
REM The script location is resolved via %~dp0, so it is independent of the
REM current directory (see docs/LAYOUT.md, rule R1).
REM
REM NOTE: keep this file PURE ASCII (see run-tests.bat for the reason).
title OAS backend (dev)
cd /d "%~dp0"
"%~dp0toolkit\python.exe" "%~dp0server.py" %*
pause
