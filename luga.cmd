@echo off
chcp 65001 > nul
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
) else if "%1"=="fg" (
    python app\main.py
) else if "%1"=="run" (
    python app\main.py
) else (
    echo ==========================================================
    echo               LỆNH ĐIỀU KHIỂN LUGA ASSIST (WINDOWS)
    echo ==========================================================
    echo   luga start    : Khởi động app chạy ngầm
    echo   luga stop     : Dừng app đang chạy ngầm
    echo   luga restart  : Khởi động lại app ngầm
    echo   luga status   : Kiểm tra app có đang chạy không
    echo   luga chat     : Mở phòng chat AI với Gemini ngay trên CMD/PowerShell
    echo   luga logs     : Xem nhật ký hoạt động (logs)
    echo   luga fg       : Chạy trực tiếp trên màn hình CMD
    echo ==========================================================
)
