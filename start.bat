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
set PYTHONPATH=.
python app/main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Luga Assist exited with code %ERRORLEVEL%.
    pause
)
