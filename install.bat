@echo off
setlocal enabledelayedexpansion

set PROJECT_DIR=%~dp0
if "%PROJECT_DIR:~-1%"=="\" set PROJECT_DIR=%PROJECT_DIR:~0,-1%
cd /d "%PROJECT_DIR%"

cls
echo ======================================================================
echo          LUGA ASSIST - WINDOWS FULL SETUP ^& INSTALLER
echo ======================================================================
echo Install Directory: %PROJECT_DIR%
echo.

:: Prefer 64-bit Python
set PYTHON_CMD=python
py -3-64 -c "import sys; exit(0 if sys.maxsize > 2**32 else 1)" >nul 2>&1
if %ERRORLEVEL% EQU 0 set PYTHON_CMD=py -3-64

:: 1. Check Python
echo [1/4] Checking Python environment...
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python is not installed or not added to PATH.
    echo Please download Python 64-bit from: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    echo IMPORTANT: Make sure to check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('%PYTHON_CMD% --version') do echo [OK] Found %%v

:: Warn if 32-bit
%PYTHON_CMD% -c "import sys; exit(0 if sys.maxsize > 2**32 else 1)" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARNING] 32-bit Python detected. Essential dependencies (e.g. curl-cffi)
    echo           require Python 64-bit to install without Visual C++ Build Tools.
    echo           Please install 64-bit Python: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    echo.
)

:: 2. Install requirements
echo.
echo [2/4] Installing required libraries from requirements.txt...
%PYTHON_CMD% -m pip install --quiet --upgrade pip >nul 2>&1
%PYTHON_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Failed to install some dependencies via pip. Please check network.
) else (
    echo [OK] All dependencies installed successfully.
)

:: 3. Setup Global 'luga' command via User PATH
echo.
echo [3/4] Registering 'luga' CLI command in Windows User PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($p -notlike '*%PROJECT_DIR%*') { [Environment]::SetEnvironmentVariable('Path', $p.TrimEnd(';') + ';%PROJECT_DIR%', 'User'); Write-Host '    [OK] Added project folder to User PATH!' -ForegroundColor Green; } else { Write-Host '    [OK] Luga command is already in User PATH.' -ForegroundColor Green; }"

:: 4. Create Desktop Shortcuts
echo.
echo [4/4] Creating Desktop shortcut (Zero terminal required)...
%PYTHON_CMD% scripts\create_desktop_launchers.py

echo.
echo ======================================================================
echo                 LUGA ASSIST SETUP COMPLETED!
echo ======================================================================
echo SINGLE UNIFIED APP - CONTROLLED VIA SHORTCUTS:
echo   Double click 'Luga Assist' on Desktop : Starts app and shows Chat HUD
echo   Key F7 (or Ctrl+Alt+Space)            : Toggle Floating Chat HUD
echo   Key Esc                               : Hide chat bar
echo   Key F8                                : Speak directly via Microphone
echo   Key F9                                : Switch mode [OS Control] vs [AI Chat]
echo   'Turn Off Luga' button in chat bar    : Completely exit application
echo.
echo COMMAND LINE USAGE (Global from any directory):
echo   luga start    : Start background agent
echo   luga stop     : Stop background agent
echo   luga status   : Check status
echo   luga chat     : Open interactive terminal chat
echo   luga logs     : View recent logs
echo ======================================================================
echo.

set /p START_CHOICE="Do you want to start Luga Chat now? (Y/n): "
if /i "%START_CHOICE%"=="y" (
    call "%PROJECT_DIR%\luga.cmd" chat
) else if "%START_CHOICE%"=="" (
    call "%PROJECT_DIR%\luga.cmd" chat
)

pause
