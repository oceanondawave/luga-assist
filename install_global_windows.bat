@echo off
chcp 65001 > nul
echo ==========================================================
echo       CÀI ĐẶT LỆNH TOÀN CẦU 'luga' CHO WINDOWS
echo ==========================================================
echo.

set CURRENT_DIR=%~dp0
if "%CURRENT_DIR:~-1%"=="\" set CURRENT_DIR=%CURRENT_DIR:~0,-1%

echo Đang thêm thư mục Luga Assist vào Windows PATH của người dùng...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Environment]::SetEnvironmentVariable('Path', [Environment]::GetEnvironmentVariable('Path', 'User') + ';%CURRENT_DIR%', 'User')"

echo.
echo ✅ CÀI ĐẶT THÀNH CÔNG!
echo ----------------------------------------------------------
echo Từ bây giờ, ở BẤT KỲ ĐÂU trên Windows (CMD hoặc PowerShell),
echo bạn không cần vào thư mục dự án mà chỉ cần gõ trực tiếp:
echo.
echo    luga start     - Bật app chạy ngầm
echo    luga stop      - Dừng app chạy ngầm
echo    luga status    - Kiểm tra trạng thái
echo    luga logs      - Xem nhật ký hoạt động
echo    luga fg        - Chạy trực tiếp có cửa sổ
echo ----------------------------------------------------------
echo (Lưu ý: Hãy mở một cửa sổ CMD/PowerShell mới để nhận lệnh)
echo.
pause
