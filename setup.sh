#!/bin/bash
set -e

echo "=========================================================="
echo "          CÀI ĐẶT DỰ ÁN LUGA ASSIST (macOS / Linux)       "
echo "=========================================================="

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Lỗi: Máy tính chưa cài đặt Python 3. Vui lòng cài Python 3 trước."
    exit 1
fi

echo "📦 Đang cài đặt các thư viện cần thiết từ requirements.txt..."
python3 -m pip install -r requirements.txt

echo ""
echo "✅ Đã cài đặt xong tất cả thư viện thành công!"
echo ""
echo "🍎 LƯU Ý QUAN TRỌNG CHO macOS:"
echo "Để Luga Assist có thể điều khiển chuột và chụp màn hình, bạn cần cấp quyền tại:"
echo "1. System Settings -> Privacy & Security -> Accessibility (Trợ năng): Bật Terminal/iTerm/Python."
echo "2. System Settings -> Privacy & Security -> Screen Recording (Ghi màn hình): Bật Terminal/Python."
echo ""
echo "👉 Tiếp theo, hãy tải Chrome Extension vào trình duyệt:"
echo "1. Mở Chrome -> vào địa chỉ: chrome://extensions/"
echo "2. Bật 'Developer mode' (Chế độ cho nhà phát triển) ở góc trên bên phải."
echo "3. Bấm 'Load unpacked' (Tải tiện ích đã giải nén) -> chọn thư mục: $(pwd)/extension"
echo ""
echo "🚀 Chạy lệnh ./start.sh để khởi động hệ thống!"
