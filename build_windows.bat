@echo off
chcp 65001 >nul
echo ============================================================
echo       LUGA ASSIST - BUILD STANDALONE WINDOWS APP & RELEASE  
echo ============================================================

cd /d "%~dp0"

echo [Build] Kiểm tra và cài đặt thư viện cần thiết...
python -m pip install --upgrade pip
python -m pip install pyinstaller
python -m pip install -r requirements.txt

echo [Build] Đang đóng gói ứng dụng với PyInstaller (Không hiện cửa sổ CMD)...
pyinstaller --clean -y luga_assist_win.spec

if %ERRORLEVEL% EQU 0 (
    echo [Build] Đang sao chép Chrome Extension vào thư mục phát hành...
    if not exist "dist\Luga Assist\extension" mkdir "dist\Luga Assist\extension"
    xcopy /E /I /Y "extension" "dist\Luga Assist\extension" >nul

    echo [Build] Đang tạo file ZIP để phát hành Release...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path 'dist\Luga-Assist-Windows.zip') { Remove-Item 'dist\Luga-Assist-Windows.zip' -Force }; Compress-Archive -Path 'dist\Luga Assist' -DestinationPath 'dist\Luga-Assist-Windows.zip' -Force"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path 'dist\Luga-Assist-Chrome-Extension.zip') { Remove-Item 'dist\Luga-Assist-Chrome-Extension.zip' -Force }; Compress-Archive -Path 'extension' -DestinationPath 'dist\Luga-Assist-Chrome-Extension.zip' -Force"
    echo ============================================================
    echo ✅ HOÀN TẤT BUILD THÀNH CÔNG!
    echo    1. Thư mục chạy : dist\Luga Assist\Luga Assist.exe
    echo    2. File nén ZIP : dist\Luga-Assist-Windows.zip (Đã kèm Extension)
    echo    3. Extension ZIP: dist\Luga-Assist-Chrome-Extension.zip
    echo    Bắt buộc: Nạp Extension vào Chrome trước khi chạy 'Luga Assist.exe'.
    echo ============================================================
) else (
    echo ❌ Có lỗi xảy ra trong quá trình đóng gói!
)

pause
