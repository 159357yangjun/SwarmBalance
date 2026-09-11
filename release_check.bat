@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if exist ".venv310\Scripts\python.exe" (
  set "PY=.venv310\Scripts\python.exe"
) else (
  set "PY=python"
)
%PY% release_check.py
if errorlevel 1 pause
endlocal
