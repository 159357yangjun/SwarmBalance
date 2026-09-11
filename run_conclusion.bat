@echo off
setlocal
set PRESET=%1
if "%PRESET%"=="" set PRESET=conclusion
cd /d "%~dp0"
python run_conclusion.py --preset %PRESET%
if errorlevel 1 (
  echo.
  echo Experiment failed. Please check the error above.
) else (
  echo.
  echo Experiment finished. Results are under results\experiments\
)
pause
endlocal
