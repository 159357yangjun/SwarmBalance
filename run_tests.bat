@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo ============================================================
echo   群智优衡 - 单元测试一键运行
echo ============================================================
echo   说明：
echo     - console / experiments / 根目录 下是真正的单元测试
echo     - frontend 下带 test 字样的文件是命令行工具，不是单元测试
echo     - 使用标准库 unittest，无需安装任何额外依赖
echo ============================================================
echo.

set "PY="
if exist ".venv310\Scripts\python.exe" set "PY=.venv310\Scripts\python.exe"
if not defined PY if exist "..\.venv310\Scripts\python.exe" set "PY=..\.venv310\Scripts\python.exe"
if not defined PY set "PY=python"

echo 使用解释器: %PY%
echo.

set "FAIL=0"

echo ---------- [1/3] console 模块 ----------
%PY% -m unittest discover -s console -t .
if errorlevel 1 set "FAIL=1"
echo.

echo ---------- [2/3] experiments 模块 ----------
%PY% -m unittest discover -s experiments -t .
if errorlevel 1 set "FAIL=1"
echo.

echo ---------- [3/3] 结项打包 ----------
%PY% -m unittest test_build_conclusion_package
if errorlevel 1 set "FAIL=1"
echo.

echo ============================================================
if "%FAIL%"=="0" (
    echo   结果：全部测试通过
) else (
    echo   结果：存在失败用例，请查看上方输出
)
echo ============================================================
echo.
pause
endlocal
