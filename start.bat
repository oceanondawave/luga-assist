@echo off
chcp 65001 > nul
echo ==========================================================
echo          KHOI DONG LUGA ASSIST AGENT (WINDOWS)
echo ==========================================================

echo Dang khoi chay Local Agent Server tai http://127.0.0.1:8000...
echo Ung dung Luga Assist se tu dong mo tren trinh duyet cua ban.
echo.
set PYTHONPATH=.
python app/main.py

pause
