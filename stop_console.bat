@echo off
setlocal
chcp 65001 >nul
echo ================================================
echo   群智优衡 - 停止控制台 / 清理残留进程
echo ================================================
echo 用途：双击即可停掉所有 console.run 后端进程并释放 8765 端口。
echo.

powershell -NoProfile -Command "$n=0; Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('[stop] killing PID '+$_.OwningProcess+' listening on port 8765'); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue; $n++ }; Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and [string]$_.CommandLine -match 'console\.run' } | ForEach-Object { Write-Host ('[stop] killing console.run PID '+$_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $n++ }; if($n -eq 0){ Write-Host '[stop] no stale console process found' } else { Write-Host ('[stop] cleaned '+$n+' process(es)') }"

echo.
pause
endlocal
