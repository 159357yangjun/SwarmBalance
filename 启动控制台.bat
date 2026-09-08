@echo off
cd /d "%~dp0"
echo ================================================
echo   SwarmBalance Console - Starting...
echo ================================================
"..\.venv310\Scripts\python.exe" -m app.console.run --open
echo.
echo Console stopped.
pause
