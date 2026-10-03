@echo off
chcp 65001 > nul
echo ==========================================================
echo          LUGA ASSIST - GLOBAL DESKTOP AGENT (WINDOWS)
echo ==========================================================

echo.
echo 🎙️ TRỢ LÝ TOÀN HỆ THỐNG ĐÃ KÍCH HOẠT (GLOBAL WAY)!
echo 👉 Nhấn phím F8 (hoặc Ctrl + Space) BẤT CỨ ĐÂU trên máy tính để nói lệnh.
echo 👉 KHÔNG CẦN MỞ TRÌNH DUYỆT - Màn hình hoàn toàn thoáng đãng để AI quan sát.
echo.
set PYTHONPATH=.
python app/main.py

pause
