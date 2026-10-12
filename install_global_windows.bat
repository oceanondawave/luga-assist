@echo off
setlocal
echo ==========================================================
echo       REGISTER GLOBAL 'luga' COMMAND FOR WINDOWS
echo ==========================================================
echo.

set CURRENT_DIR=%~dp0
if "%CURRENT_DIR:~-1%"=="\" set CURRENT_DIR=%CURRENT_DIR:~0,-1%

echo Registering Luga Assist directory to Windows User PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($p -notlike '*%CURRENT_DIR%*') { [Environment]::SetEnvironmentVariable('Path', $p.TrimEnd(';') + ';%CURRENT_DIR%', 'User'); Write-Host '    [OK] Added to User PATH!' -ForegroundColor Green; } else { Write-Host '    [OK] Already in User PATH.' -ForegroundColor Green; }"

echo.
echo [OK] INSTALLATION COMPLETED!
echo ----------------------------------------------------------
echo From now on, in ANY Windows CMD or PowerShell window:
echo.
echo    luga start     - Start background agent
echo    luga stop      - Stop background agent
echo    luga status    - Check agent status
echo    luga chat      - Open interactive terminal chat
echo    luga logs      - View recent activity logs
echo    luga fg        - Run directly in foreground
echo ----------------------------------------------------------
echo Note: Please open a new CMD or PowerShell window to use 'luga'.
echo.
pause
