@echo off
REM [10-15] Flutter command wrapper. The Flutter SDK is resolved by
REM dev_tools\paths.py, so no drive letter is needed here (see
REM docs/LAYOUT.md, rules R1/R3).
REM
REM Usage (independent of the current directory; --no-version-check is added
REM automatically -- see pitfall P16):
REM   dev_tools\flutter.bat test
REM   dev_tools\flutter.bat analyze lib
REM   dev_tools\flutter.bat build windows --release
REM
REM NOTE: keep this file PURE ASCII (see run-tests.bat for the reason).
"%~dp0..\toolkit\python.exe" "%~dp0run_flutter.py" %*
