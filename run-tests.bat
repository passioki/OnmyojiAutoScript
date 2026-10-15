@echo off
REM [10-15] Full / partial pytest -- uses the in-repo toolkit.
REM The script location is resolved via %~dp0, so it is independent of the
REM current directory (see docs/LAYOUT.md, rule R1).
REM
REM Usage:
REM   run-tests.bat                                   full suite
REM   run-tests.bat tests/ -q                         a scope
REM   run-tests.bat tests/module/config/test_loop_rounds.py -q
REM
REM NOTE: keep this file PURE ASCII. Chinese text inside a .bat is decoded
REM with the active code page (936 here) and makes cmd mis-parse the REM
REM lines, printing bogus "'...' is not recognized" errors. Same lesson as
REM the session-memory skill: a generic script must be pure ASCII.
cd /d "%~dp0"
"%~dp0toolkit\python.exe" -m pytest %*
