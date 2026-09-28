@echo off
setlocal
set PRESET=%1
if "%PRESET%"=="" set PRESET=conclusion
cd /d "%~dp0"
chcp 65001 >nul

rem 定位虚拟环境：项目内优先，其次上一级（本仓库的 .venv310 实际位于上一级）。
rem 原先用裸 python，在系统 Python 为 3.13 的机器上会因依赖/版本不符而跑不起来。
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
%PY% run_conclusion.py --preset %PRESET%
if errorlevel 1 (
  echo.
  echo Experiment failed. Please check the error above.
) else (
  echo.
  echo Experiment finished. Results are under results\experiments\
)
pause
endlocal
