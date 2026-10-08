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
rm -f "dist/Luga-Assist-macOS.zip" "dist/Luga-Assist-macOS.dmg" "dist/Luga-Assist-Chrome-Extension.zip"

# Package standalone extension zip for release
python3 -c "
import zipfile, os
from pathlib import Path
ext_dir = Path('extension')
zip_path = Path('dist/Luga-Assist-Chrome-Extension.zip')
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(ext_dir):
        for f in files:
            p = Path(root) / f
            arcname = p.relative_to(ext_dir.parent)
            z.write(p, arcname)
print('[Build] Đã đóng gói dist/Luga-Assist-Chrome-Extension.zip')
"

(cd dist && zip -r -q "Luga-Assist-macOS.zip" "Luga Assist.app")

if command -v hdiutil &> /dev/null; then
    echo "[Build] Đang đóng gói đĩa cài đặt DMG kèm Extension..."
    DMG_DIR="dist/dmg_staging"
    rm -rf "$DMG_DIR"
    mkdir -p "$DMG_DIR"
    cp -R "dist/Luga Assist.app" "$DMG_DIR/"
    cp -R "extension" "$DMG_DIR/Chrome_Extension"
    cat << 'EOF' > "$DMG_DIR/HUONG_DAN_CAI_EXTENSION.txt"
============================================================
BƯỚC BẮT BUỘC TRƯỚC KHI KHỞI CHẠY LUGA ASSIST:
============================================================
Luga Assist BẮT BUỘC cần tiện ích Chrome Extension để kết nối
Google Gemini ngầm mà không cần tốn phí API hay mở tab trình duyệt:

1. Mở Google Chrome (hoặc Edge / Brave / Cốc Cốc) -> Truy cập:
   chrome://extensions/  (hoặc edge://extensions/)
2. Bật công tắc "Chế độ cho nhà phát triển" (Developer mode) ở góc trên bên phải.
3. Kéo thả thư mục "Chrome_Extension" vào cửa sổ đó
   (hoặc bấm "Tải tiện ích đã giải nén" / "Load unpacked" và chọn thư mục này).
4. Đảm bảo tài khoản Google đã đăng nhập trên trình duyệt.
5. Kéo "Luga Assist.app" vào Applications và mở app để sử dụng!
============================================================
EOF
    hdiutil create -volname "Luga Assist" -srcfolder "$DMG_DIR" -ov -format UDZO "dist/Luga-Assist-macOS.dmg"
    rm -rf "$DMG_DIR"
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
echo "   1. File cài đặt DMG  : dist/Luga-Assist-macOS.dmg (Kèm sẵn Chrome_Extension)"
echo "   2. File nén App ZIP  : dist/Luga-Assist-macOS.zip"
echo "   3. Extension ZIP     : dist/Luga-Assist-Chrome-Extension.zip"
echo "   4. Ứng dụng Desktop  : ~/Desktop/Luga Assist.app"
echo "============================================================"

