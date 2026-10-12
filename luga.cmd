@echo off
setlocal
set PROJECT_DIR=%~dp0
cd /d "%PROJECT_DIR%"
set PYTHONPATH=%PROJECT_DIR%

if "%1"=="start" (
    python -m app.daemon start
) else if "%1"=="stop" (
    python -m app.daemon stop
) else if "%1"=="restart" (
    python -m app.daemon restart
) else if "%1"=="status" (
    python -m app.daemon status
) else if "%1"=="logs" (
    python -m app.daemon logs -f
) else if "%1"=="chat" (
    python -m app.chat_cli %2 %3 %4 %5
) else if "%1"=="install" (
    call install.bat
) else if "%1"=="uninstall" (
    call uninstall.bat
) else if "%1"=="fg" (
    python app\main.py
) else if "%1"=="run" (
    python app\main.py
) else if "%1"=="desktop" (
    python scripts\create_desktop_launchers.py
) else if "%1"=="shortcuts" (
    python scripts\create_desktop_launchers.py
) else if "%1"=="spotlight" (
    python -m app.spotlight_ui
) else if "%1"=="popup" (
    python -m app.spotlight_ui
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
