@echo off
setlocal
set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"
set PYTHONPATH=%PROJECT_DIR%

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

if "%1"=="start" (
    %PYTHON_CMD% -m app.daemon start
) else if "%1"=="stop" (
    %PYTHON_CMD% -m app.daemon stop
) else if "%1"=="restart" (
    %PYTHON_CMD% -m app.daemon restart
) else if "%1"=="status" (
    %PYTHON_CMD% -m app.daemon status
) else if "%1"=="logs" (
    %PYTHON_CMD% -m app.daemon logs -f
) else if "%1"=="chat" (
    %PYTHON_CMD% -m app.chat_cli %2 %3 %4 %5
) else if "%1"=="install" (
    call install.bat
) else if "%1"=="uninstall" (
    call uninstall.bat
) else if "%1"=="fg" (
    %PYTHON_CMD% app\main.py
) else if "%1"=="run" (
    %PYTHON_CMD% app\main.py
) else if "%1"=="desktop" (
    %PYTHON_CMD% scripts\create_desktop_launchers.py
) else if "%1"=="shortcuts" (
    %PYTHON_CMD% scripts\create_desktop_launchers.py
) else if "%1"=="spotlight" (
    %PYTHON_CMD% -m app.spotlight_ui
) else if "%1"=="popup" (
    %PYTHON_CMD% -m app.spotlight_ui
) else (
    echo ==========================================================
    echo               LUGA ASSIST COMMANDS (WINDOWS)
    echo ==========================================================
    echo   luga start     : Start background agent
    echo   luga stop      : Stop background agent
    echo   luga restart   : Restart background agent
    echo   luga status    : Check agent status
    echo   luga chat      : Interactive Terminal chat
    echo   luga logs      : View recent logs
    echo   luga fg        : Run directly in console
    echo   luga install   : Run full Windows installer
    echo   luga uninstall : Uninstall Luga Assist from Windows
    echo ==========================================================
)
