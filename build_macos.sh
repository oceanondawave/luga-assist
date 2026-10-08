#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "============================================================"
echo "      LUGA ASSIST - BUILD STANDALONE MACOS APP & RELEASE    "
echo "============================================================"

# 1. Ensure PyInstaller is installed
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

# 5. Create Release Distribution Zip & DMG
echo "[Build] Đang tạo file nén ZIP và đĩa cài đặt DMG cho GitHub Releases..."
rm -f "dist/Luga-Assist-macOS.zip" "dist/Luga-Assist-macOS.dmg"
(cd dist && zip -r -q "Luga-Assist-macOS.zip" "Luga Assist.app")

if command -v hdiutil &> /dev/null; then
    echo "[Build] Đang đóng gói đĩa cài đặt DMG..."
    hdiutil create -volname "Luga Assist" -srcfolder "dist/Luga Assist.app" -ov -format UDZO "dist/Luga-Assist-macOS.dmg" || true
fi

# 6. Copy to Desktop for immediate local testing if run on local Mac
if [ -d "/Users/$(whoami)/Desktop" ]; then
    echo "[Build] Cập nhật Luga Assist.app ngoài Desktop..."
    rm -rf "/Users/$(whoami)/Desktop/Luga Assist.app"
    cp -R "dist/Luga Assist.app" "/Users/$(whoami)/Desktop/Luga Assist.app"
    codesign --force --deep --sign - "/Users/$(whoami)/Desktop/Luga Assist.app"
fi

echo "============================================================"
echo "✅ HOÀN TẤT BUILD MACOS RELEASE!"
echo "   1. File cài đặt DMG  : dist/Luga-Assist-macOS.dmg"
echo "   2. File nén ZIP      : dist/Luga-Assist-macOS.zip"
echo "   3. Ứng dụng Desktop  : ~/Desktop/Luga Assist.app"
echo "============================================================"
