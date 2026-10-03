#!/bin/bash

echo "=========================================================="
echo "          LUGA ASSIST - GLOBAL DESKTOP AGENT              "
echo "=========================================================="

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "🎙️ TRỢ LÝ TOÀN HỆ THỐNG ĐÃ KÍCH HOẠT (GLOBAL WAY)!"
echo "👉 Nhấn phím F8 (hoặc Ctrl + Space) BẤT CỨ ĐÂU trên máy tính để nói lệnh."
echo "👉 KHÔNG CẦN MỞ TRÌNH DUYỆT - Màn hình hoàn toàn thoáng đãng để AI quan sát."
echo ""
echo "Nhấn Ctrl+C để dừng."
echo ""

PYTHONPATH=. python3 app/main.py
