@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ================================================
echo   群智优衡 - 三维协同调度仿真平台 v0.9
echo ================================================
echo.

if exist ".venv310\Scripts\python.exe" (
  set "PY=.venv310\Scripts\python.exe"
) else (
  set "PY=python"
)

%PY% -m console.run
if errorlevel 1 (
  echo.
  echo 启动失败。请阅读上方预检提示，或查看 README 的环境安装章节。
  pause
)
endlocal
