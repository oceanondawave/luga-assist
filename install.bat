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

:: 4. Create Desktop Shortcuts (Zero Terminal Required)
echo.
echo [4/4] Tạo các biểu tượng lối tắt trên Màn hình chính (Desktop)...
python scripts\create_desktop_launchers.py

echo.
echo ======================================================================
echo              🎉 CÀI ĐẶT LUGA ASSIST HOÀN TẤT THÀNH CÔNG!              
echo ======================================================================
echo DÀNH CHO NGƯỜI DÙNG THÔNG THƯỜNG (KHÔNG CẦN TERMINAL/CMD):
echo   🖱️ Bấm đôi 'Luga Assist' trên Desktop     : Bật app và mở Web
echo   🛑 Bấm đôi 'Dừng Luga' trên Desktop       : Tắt app ngay lập tức
echo   ℹ️ Bấm đôi 'Trạng thái Luga' trên Desktop : Xem trạng thái app
echo   🌐 Nút '🛑 Tắt Luga' trên góc WebUI       : Tắt app bằng 1 click
echo   🎙️ Phím F8 (Nói qua Micro)                : 'Kiểm tra trạng thái', 'Tắt trợ lý', 'Đổi chế độ'
echo.
echo DÀNH CHO LẬP TRÌNH VIÊN / CMD (Toàn cục ở mọi thư mục):
echo   • luga start    : Khởi động app chạy ngầm
echo   • luga stop     : Dừng app đang chạy ngầm
echo   • luga status   : Kiểm tra app có đang chạy hay không
echo   • luga chat     : Mở giao diện Chat điều khiển trên CMD
echo   • luga logs     : Xem nhật ký hoạt động gần nhất
echo ======================================================================
echo.

set /p START_CHOICE="👉 Bạn có muốn mở ngay phòng Chat điều khiển (luga chat) không? (Y/n): "
if /i "%START_CHOICE%"=="y" (
    call "%PROJECT_DIR%\luga.cmd" chat
) else if "%START_CHOICE%"=="" (
    call "%PROJECT_DIR%\luga.cmd" chat
)

pause
