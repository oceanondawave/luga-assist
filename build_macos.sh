#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "============================================================"
echo "      LUGA ASSIST - BUILD STANDALONE MACOS APP (.APP)       "
echo "============================================================"

# 1. Ensure pyinstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "[Build] Đang cài đặt PyInstaller..."
    python3 -m pip install pyinstaller
fi

# 2. Compile native launcher Mach-O binary
echo "[Build] Đang biên dịch native Mach-O launcher..."
clang -O2 -target arm64-apple-macos11.0 scripts/macos/launcher.c -o scripts/macos/launcher

# 3. Build standalone app bundle with PyInstaller
echo "[Build] Đang đóng gói PyInstaller standalone .app..."
pyinstaller --clean -y luga_assist_mac.spec

# 4. Ad-hoc codesign the output .app
echo "[Build] Đang ký mã quyền riêng tư TCC (Microphone, Accessibility, Screen Recording)..."
codesign --force --deep --sign - "dist/Luga Assist.app"

# 5. Copy to Desktop for immediate one-click launch
echo "[Build] Cập nhật Luga Assist.app ngoài Desktop..."
rm -rf "/Users/$(whoami)/Desktop/Luga Assist.app"
cp -R "dist/Luga Assist.app" "/Users/$(whoami)/Desktop/Luga Assist.app"
codesign --force --deep --sign - "/Users/$(whoami)/Desktop/Luga Assist.app"

echo "============================================================"
echo "✅ HOÀN TẤT BUILD MACOS! App đã sẵn sàng ngoài Desktop."
echo "   Chỉ cần click đúp vào 'Luga Assist.app' để sử dụng."
echo "============================================================"
