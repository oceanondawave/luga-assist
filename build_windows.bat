@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   LUGA ASSIST - BUILD STANDALONE SETUP INSTALLER (SETUP.EXE)
echo ============================================================

set PYTHON_CMD=
py -3.11-64 -c "import sys; exit(0)" >nul 2>&1
if %ERRORLEVEL% EQU 0 set PYTHON_CMD=py -3.11-64
if "%PYTHON_CMD%"=="" (
    py -3.12-64 -c "import sys; exit(0)" >nul 2>&1
    if %ERRORLEVEL% EQU 0 set PYTHON_CMD=py -3.12-64
)
if "%PYTHON_CMD%"=="" (
    py -3.13-64 -c "import sys; exit(0)" >nul 2>&1
    if %ERRORLEVEL% EQU 0 set PYTHON_CMD=py -3.13-64
)
if "%PYTHON_CMD%"=="" (
    py -3-64 -c "import sys; exit(0 if sys.version_info < (3, 14) else 1)" >nul 2>&1
    if %ERRORLEVEL% EQU 0 set PYTHON_CMD=py -3-64
)
if "%PYTHON_CMD%"=="" (
    where python >nul 2>&1
    if %ERRORLEVEL% EQU 0 set PYTHON_CMD=python
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.11 64-bit from:
    echo   https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    pause
    exit /b 1
)

%PYTHON_CMD% scripts\build_windows.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Build failed with exit code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

echo.
pause
