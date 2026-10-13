@echo off
setlocal
cd /d "%~dp0"
echo ==========================================================
echo          LUGA ASSIST - GLOBAL DESKTOP AGENT (WINDOWS)
echo ==========================================================
echo.
echo [INFO] Global Desktop Agent is starting...
echo [INFO] Press F8 (or Ctrl+Space) anywhere to speak.
echo [INFO] Press F7 (or Ctrl+Alt+Space) to toggle Floating Chat.
echo [INFO] Press F9 to switch mode: OS Control vs AI Chat.
echo [INFO] Background mode: start_background.bat or start_windows.vbs
echo.

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
if "%PYTHON_CMD%"=="" set PYTHON_CMD=python

set PYTHONPATH=.
%PYTHON_CMD% app/main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Luga Assist exited with code %ERRORLEVEL%.
    pause
)
