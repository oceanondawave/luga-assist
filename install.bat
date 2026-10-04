@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

set PROJECT_DIR=%~dp0
if "%PROJECT_DIR:~-1%"=="\" set PROJECT_DIR=%PROJECT_DIR:~0,-1%
cd /d "%PROJECT_DIR%"

cls
echo ======================================================================
echo        🎙️   LUGA ASSIST - BỘ CÀI ĐẶT TOÀN DIỆN CHO WINDOWS             
echo ======================================================================
echo Thư mục cài đặt: %PROJECT_DIR%
echo.

:: 1. Check Python
echo [1/4] Kiểm tra môi trường Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [X] LỖI: Máy tính chưa cài đặt Python hoặc chưa bật tùy chọn Add to PATH.
    echo Vui lòng tải Python từ trang chủ: https://www.python.org/downloads/
    echo QUAN TRỌNG: Hãy tích chọn ô "Add Python to PATH" trong khi cài đặt!
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo [✓] Đã tìm thấy: %%v

:: 2. Install requirements
echo.
echo [2/4] Đang cài đặt các thư viện cần thiết từ requirements.txt...
python -m pip install --quiet --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] Cảnh báo: Có lỗi khi cài đặt thư viện qua pip. Vui lòng kiểm tra kết nối mạng.
) else (
    echo [✓] Đã cài đặt đầy đủ tất cả thư viện (FastAPI, Rich, SoundDevice, PyAutoGUI, v.v.)
)

:: 3. Setup Global 'luga' command via User PATH
echo.
echo [3/4] Đang đăng ký lệnh toàn cầu 'luga' vào PATH của Windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$path = [Environment]::GetEnvironmentVariable('Path', 'User'); " ^
    "if ($path -notlike '*%PROJECT_DIR%*') { " ^
    "    [Environment]::SetEnvironmentVariable('Path', $path.TrimEnd(';') + ';%PROJECT_DIR%', 'User'); " ^
    "    Write-Host '    [✓] Đã thêm thư mục dự án vào User PATH!' -ForegroundColor Green; " ^
    "} else { " ^
    "    Write-Host '    [✓] Lệnh luga đã có sẵn trong User PATH.' -ForegroundColor Green; " ^
    "}"

:: 4. Create Desktop Shortcut
echo.
echo [4/4] Tạo biểu tượng lối tắt (Desktop Shortcut)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$wsh = New-Object -ComObject WScript.Shell; " ^
    "$shortcut = $wsh.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Luga Assist.lnk'); " ^
    "$shortcut.TargetPath = '%PROJECT_DIR%\luga.cmd'; " ^
    "$shortcut.Arguments = 'chat'; " ^
    "$shortcut.WorkingDirectory = '%PROJECT_DIR%'; " ^
    "$shortcut.Description = 'Luga Assist AI Agent'; " ^
    "$shortcut.Save(); " ^
    "Write-Host '    [✓] Đã tạo shortcut Luga Assist trên Desktop!' -ForegroundColor Green;"

echo.
echo ======================================================================
echo              🎉 CÀI ĐẶT LUGA ASSIST HOÀN TẤT THÀNH CÔNG!              
echo ======================================================================
echo Từ bất kỳ cửa sổ CMD hoặc PowerShell nào, bạn chỉ cần gõ:
echo   • luga start    : Khởi động app chạy ngầm
echo   • luga stop     : Dừng app đang chạy ngầm
echo   • luga status   : Kiểm tra app có đang chạy hay không
echo   • luga chat     : Mở giao diện Chat điều khiển máy tính cực đẹp trên CMD
echo   • luga logs     : Xem nhật ký hoạt động gần nhất
echo   • Phím F8       : Nói lệnh giọng nói từ bất kỳ đâu trên Windows
echo   • Giao diện Web : http://localhost:8000
echo ======================================================================
echo.

set /p START_CHOICE="👉 Bạn có muốn mở ngay phòng Chat điều khiển (luga chat) không? (Y/n): "
if /i "%START_CHOICE%"=="y" (
    call "%PROJECT_DIR%\luga.cmd" chat
) else if "%START_CHOICE%"=="" (
    call "%PROJECT_DIR%\luga.cmd" chat
)

pause
