@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

set PROJECT_DIR=%~dp0
if "%PROJECT_DIR:~-1%"=="\" set PROJECT_DIR=%PROJECT_DIR:~0,-1%
cd /d "%PROJECT_DIR%"

cls
echo ======================================================================
echo         🗑️   LUGA ASSIST - TRÌNH GỠ CÀI ĐẶT (WINDOWS UNINSTALLER)      
echo ======================================================================
echo Thư mục dự án: %PROJECT_DIR%
echo.

set /p CONFIRM="❓ Bạn có chắc chắn muốn gỡ cài đặt Luga Assist khỏi hệ thống Windows? (y/N): "
if /i not "%CONFIRM%"=="y" (
    echo Đã hủy thao tác. Luga Assist vẫn được giữ nguyên.
    pause
    exit /b 0
)

echo.
echo [1/3] Đang dừng tiến trình Luga Assist nếu đang chạy ngầm...
python -m app.daemon stop >nul 2>&1
echo [✓] Đã dừng tiến trình.

echo.
echo [2/3] Đang gỡ bỏ Luga Assist khỏi User PATH của Windows...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$escaped = [regex]::Escape('%PROJECT_DIR%'); " ^
    "$path = [Environment]::GetEnvironmentVariable('Path', 'User'); " ^
    "$newPath = ($path -split ';' | Where-Object { $_ -and $_ -notmatch $escaped }) -join ';'; " ^
    "[Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); " ^
    "Write-Host '    [✓] Đã xóa đường dẫn khỏi User PATH!' -ForegroundColor Green;"

echo.
echo [3/3] Đang xóa các biểu tượng lối tắt trên Desktop...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
    "@('Luga Assist.lnk', 'Chat Nhanh (Spotlight).lnk', 'Dừng Luga.lnk', 'Trạng thái Luga.lnk') | ForEach-Object { " ^
    "    $f = Join-Path $desktop $_; " ^
    "    if (Test-Path $f) { Remove-Item $f -Force; Write-Host ('    [✓] Đã xóa ' + $_) -ForegroundColor Green; } " ^
    "}"

echo.
set /p CLEAN_LOGS="❓ Bạn có muốn xóa các file nhật ký (logs) và phiên lưu tạm không? (Y/n): "
if /i "%CLEAN_LOGS%"=="y" (
    del /q "%PROJECT_DIR%\logs\*.log" >nul 2>&1
    del /q "%PROJECT_DIR%\temp\*.json" >nul 2>&1
    echo [✓] Đã dọn dẹp logs và cache tạm thời.
) else if "%CLEAN_LOGS%"=="" (
    del /q "%PROJECT_DIR%\logs\*.log" >nul 2>&1
    del /q "%PROJECT_DIR%\temp\*.json" >nul 2>&1
    echo [✓] Đã dọn dẹp logs và cache tạm thời.
)

echo.
echo ======================================================================
echo            ✅ GỠ CÀI ĐẶT LUGA ASSIST HOÀN TẤT THÀNH CÔNG!             
echo ======================================================================
echo Lệnh 'luga' và shortcut Desktop đã được gỡ bỏ khỏi hệ thống Windows.
echo Thư mục mã nguồn dự án tại %PROJECT_DIR% vẫn được giữ nguyên.
echo Nếu muốn cài lại sau này, bạn chỉ cần chạy: install.bat
echo ======================================================================
echo.
pause
