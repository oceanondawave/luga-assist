#!/bin/bash

echo "=========================================================="
echo "          KHỞI ĐỘNG LUGA ASSIST AGENT                     "
echo "=========================================================="

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "🚀 Đang khởi chạy Local Agent Server tại http://127.0.0.1:8000..."
echo "Ứng dụng Luga Assist sẽ tự động mở trên trình duyệt của bạn sau giây lát."
echo "Nhấn Ctrl+C để dừng server."
echo ""

PYTHONPATH=. python3 app/main.py
