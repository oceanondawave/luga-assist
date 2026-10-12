@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   LUGA ASSIST - WINDOWS STANDALONE PACKAGING ^& RELEASE
echo ============================================================

where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

python scripts\build_windows.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Build failed with exit code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

echo.
pause
