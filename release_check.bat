@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

rem 定位虚拟环境：本仓库的 .venv310 位于项目上一级，原先只找项目内，
rem 找不到就静默回落系统 python（可能是 3.13），使「发布检查通过」失去意义。
set "PY="
if exist ".venv310\Scripts\python.exe" set "PY=.venv310\Scripts\python.exe"
if not defined PY if exist "..\.venv310\Scripts\python.exe" set "PY=..\.venv310\Scripts\python.exe"
if not defined PY (
  echo [警告] 未找到 .venv310 虚拟环境，将使用系统 python。
  echo        项目正式环境为 Python 3.10；系统 python 会导致启动预检直接失败。
  set "PY=python"
)
echo 使用解释器: %PY%
echo.
%PY% release_check.py
if errorlevel 1 pause
endlocal
