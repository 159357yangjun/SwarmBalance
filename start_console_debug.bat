@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ============================================================
echo   启动诊断模式  —— 本次运行无论成功失败都会暂停，方便看报错
echo ============================================================
echo.

set "PY="
if exist ".venv310\Scripts\python.exe" set "PY=.venv310\Scripts\python.exe"
if not defined PY if exist "..\.venv310\Scripts\python.exe" set "PY=..\.venv310\Scripts\python.exe"
if not defined PY set "PY=python"

echo [诊断 1/3] 当前目录
echo     %CD%
echo.
echo [诊断 2/3] 解释器
echo     %PY%
if exist "%PY%" (
    echo     路径存在 [OK]
    "%PY%" --version
) else (
    echo     注意：该路径不存在，将回退到系统 PATH 里的 python
)
echo.
echo [诊断 3/3] 启动控制台（输出如下）
echo ------------------------------------------------------------
echo.

"%PY%" -m console.run
set "RC=%ERRORLEVEL%"

echo.
echo ------------------------------------------------------------
echo   进程已退出，退出码 = %RC%
if not "%RC%"=="0" (
    echo   非零退出码说明启动失败，请把上方报错内容发给开发者。
) else (
    echo   退出码为 0 表示服务是被正常停止的。
)
echo ============================================================
echo.
echo 窗口会停在这里不会自动关闭，请把上面的信息看完或截图。
echo 看完后按任意键关闭本窗口。
echo.
pause
endlocal
