@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

rem 定位虚拟环境：项目内优先，其次上一级（本仓库的 .venv310 实际位于上一级）。
rem 这里原先用裸 python，会命中系统 Python 3.13，使第 1 步 release_check --strict
rem 的预检以「当前 Python 3.13.5；项目正式环境锁定 Python 3.10」直接失败。
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

echo [1/3] Python 3.10 完整环境发布检查...
%PY% release_check.py --strict
if errorlevel 1 goto :fail

echo [2/3] 运行标准结项实验...
%PY% run_conclusion.py --preset conclusion
if errorlevel 1 goto :fail

echo [3/3] 构建结项证据包...
%PY% build_conclusion_package.py
if errorlevel 1 goto :fail

echo.
echo ===== 结项流水线完成 =====
echo 结果见 results\experiments 和 deliverables\
pause
exit /b 0

:fail
echo.
echo ===== 结项流水线失败，请检查上方错误 =====
pause
exit /b 1
