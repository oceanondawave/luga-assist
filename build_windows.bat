@echo off
chcp 65001 >nul
echo ============================================================
echo       LUGA ASSIST - BUILD STANDALONE WINDOWS APP (.EXE)     
echo ============================================================

cd /d "%~dp0"

echo [Build] Kiểm tra và cài đặt thư viện cần thiết...
python -m pip install --upgrade pip
python -m pip install pyinstaller
python -m pip install -r requirements.txt

echo [Build] Đang đóng gói ứng dụng với PyInstaller (Không hiện cửa sổ CMD)...
pyinstaller --clean -y luga_assist_win.spec

if %ERRORLEVEL% EQU 0 (
    echo ============================================================
    echo ✅ HOÀN TẤT BUILD THÀNH CÔNG!
    echo    File chạy nằm tại: dist\Luga Assist\Luga Assist.exe
    echo    Chỉ cần click đúp vào 'Luga Assist.exe' để sử dụng.
    echo ============================================================
) else (
    echo ❌ Có lỗi xảy ra trong quá trình đóng gói!
)

pause
