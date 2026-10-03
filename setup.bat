@echo off
chcp 65001 > nul
echo ==========================================================
echo          CÀI ĐẶT DỰ ÁN LUGA ASSIST (WINDOWS)
echo ==========================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] May tinh chua cai dat Python. Vui long cai Python tu python.org va tich chon "Add to PATH".
    pause
    exit /b
)

echo [1/2] Dang cai dat thu vien Python tu requirements.txt...
pip install -r requirements.txt

echo.
echo [2/2] Huong dan cai Chrome Extension:
echo 1. Mo trinh duyet Chrome, go vao thanh dia chi: chrome://extensions/
echo 2. Bat "Developer mode" (Che do cho nha phat trien) o goc tren phai.
echo 3. Bam "Load unpacked" (Tai tien ich da giai nen) -> Chon thu muc "extension" trong thu muc du an nay.
echo.
echo Cai dat hoan tat! Chay start.bat de khoi dong.
pause
