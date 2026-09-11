@echo off
setlocal
cd /d "%~dp0"
echo [1/3] Python 3.10 完整环境发布检查...
python release_check.py --strict
if errorlevel 1 goto :fail

echo [2/3] 运行标准结项实验...
python run_conclusion.py --preset conclusion
if errorlevel 1 goto :fail

echo [3/3] 构建结项证据包...
python build_conclusion_package.py
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
