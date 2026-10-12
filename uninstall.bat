@echo off
setlocal enabledelayedexpansion

set PROJECT_DIR=%~dp0
if "%PROJECT_DIR:~-1%"=="\" set PROJECT_DIR=%PROJECT_DIR:~0,-1%
cd /d "%PROJECT_DIR%"

cls
echo ======================================================================
echo            LUGA ASSIST - WINDOWS UNINSTALLER
echo ======================================================================
echo Project Directory: %PROJECT_DIR%
echo.

set /p CONFIRM="Are you sure you want to uninstall Luga Assist from Windows? (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo Uninstallation cancelled. Luga Assist was not modified.
    pause
    exit /b 0
)

echo.
echo [1/3] Stopping Luga Assist background processes...
python -m app.daemon stop >nul 2>&1
echo [OK] Stopped processes.

echo.
echo [2/3] Removing Luga Assist from Windows User PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$escaped = [regex]::Escape('%PROJECT_DIR%'); $path = [Environment]::GetEnvironmentVariable('Path', 'User'); $newPath = ($path -split ';' | Where-Object { $_ -and $_ -notmatch $escaped }) -join ';'; [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); Write-Host '    [OK] Removed from User PATH!' -ForegroundColor Green;"

echo.
echo [3/3] Removing Desktop shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop = [Environment]::GetFolderPath('Desktop'); @('Luga Assist.lnk', 'Chat Nhanh (Spotlight).lnk', 'Dung Luga.lnk', 'Trang thai Luga.lnk') | ForEach-Object { $f = Join-Path $desktop $_; if (Test-Path $f) { Remove-Item $f -Force; Write-Host ('    [OK] Removed ' + $_) -ForegroundColor Green; } }"

echo.
set /p CLEAN_LOGS="Do you want to clean logs and temporary cache? (Y/n): "
if /i "%CLEAN_LOGS%"=="y" (
    del /q "%PROJECT_DIR%\logs\*.log" >nul 2>&1
    del /q "%PROJECT_DIR%\temp\*.json" >nul 2>&1
    echo [OK] Cleaned logs and temporary files.
) else if "%CLEAN_LOGS%"=="" (
    del /q "%PROJECT_DIR%\logs\*.log" >nul 2>&1
    del /q "%PROJECT_DIR%\temp\*.json" >nul 2>&1
    echo [OK] Cleaned logs and temporary files.
)

echo.
echo ======================================================================
echo            LUGA ASSIST UNINSTALLATION COMPLETED!
echo ======================================================================
pause
