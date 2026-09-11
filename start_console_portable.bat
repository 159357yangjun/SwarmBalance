@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ================================================
echo   群智优衡 - 便携 Web 演示模式 v0.9
echo ================================================
echo.
echo 此模式优先保证答辩机可启动：
echo - 可使用内置本地 OSM XML 解析器，不强制 osmnx
echo - 缺少 pygame 时仅关闭桌面窗口，不影响浏览器控制台
echo - 缺少 OR-Tools 时其选项会标记为不可用，Greedy/GA/PSO 仍可运行
echo.

if exist ".venv310\Scripts\python.exe" (
  set "PY=.venv310\Scripts\python.exe"
) else (
  set "PY=python"
)

echo [1/2] 运行端到端自检...
%PY% -m console.selfcheck --steps 1
if errorlevel 1 (
  echo.
  echo 自检失败，未启动控制台。请阅读上方错误。
  pause
  exit /b 2
)

echo.
echo [2/2] 启动浏览器控制台...
%PY% -m console.run --portable
if errorlevel 1 (
  echo.
  echo 启动失败。请阅读上方预检提示。
  pause
)
endlocal
