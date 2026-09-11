@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ================================================
echo   群智优衡 - 便携 Web 演示模式 v1.0
echo ================================================
echo.
echo 此模式优先保证答辩机可启动：
echo - 可使用内置本地 OSM XML 解析器，不强制 osmnx
echo - 缺少 pygame 时仅关闭桌面窗口，不影响浏览器控制台
echo - 缺少 OR-Tools 时其选项会标记为不可用，Greedy/GA/PSO 仍可运行
echo.

rem 定位虚拟环境：优先项目根目录，其次上一级目录（本仓库的 .venv310 位于上级）
set "PY="
if exist ".venv310\Scripts\python.exe" set "PY=.venv310\Scripts\python.exe"
if not defined PY if exist "..\.venv310\Scripts\python.exe" set "PY=..\.venv310\Scripts\python.exe"
if not defined PY (
  echo [警告] 未找到 .venv310 虚拟环境，将使用系统 python。
  echo        若启动预检失败，请先按 README 创建虚拟环境。
  set "PY=python"
)
echo 使用解释器: %PY%
echo.

rem 启动前清理占用 8765 的旧实例，避免重复实例互相抢端口
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if($c){ foreach($x in $c){ Write-Host ('[clean] killing stale process PID '+$x.OwningProcess+' holding port 8765'); Stop-Process -Id $x.OwningProcess -Force -ErrorAction SilentlyContinue }; Start-Sleep -Milliseconds 600 }"
echo.

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
