#!/bin/bash
# ==============================================================================
# Luga Assist - Comprehensive & Friendly Installer for macOS / Linux
# ==============================================================================
set -e

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

clear
echo -e "${CYAN}${BOLD}======================================================================${NC}"
echo -e "${CYAN}${BOLD}       🎙️  LUGA ASSIST - BỘ CÀI ĐẶT TOÀN DIỆN CHO macOS / LINUX      ${NC}"
echo -e "${CYAN}${BOLD}======================================================================${NC}"
echo -e "${BLUE}Thư mục cài đặt:${NC} $PROJECT_DIR"
echo ""

# 1. Check Python 3
echo -e "${YELLOW}[1/5] Kiểm tra môi trường Python 3...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Lỗi: Máy tính chưa cài đặt Python 3.${NC}"
    echo -e "Vui lòng tải và cài đặt Python từ trang chính thức: ${CYAN}https://www.python.org/downloads/${NC}"
    exit 1
fi
PY_VER=$(python3 --version)
echo -e "${GREEN}✓ Đã tìm thấy:${NC} $PY_VER"

# 2. Install Python Dependencies
echo ""
echo -e "${YELLOW}[2/5] Đang cài đặt các thư viện cần thiết từ requirements.txt...${NC}"
python3 -m pip install --quiet --upgrade pip 2>/dev/null || true
python3 -m pip install -r requirements.txt

echo -e "${GREEN}✓ Đã cài đặt đầy đủ tất cả thư viện (FastAPI, Rich, SoundDevice, PyAutoGUI, Gemini-WebAPI, v.v.)${NC}"

# 3. Setup Global 'luga' CLI Command
echo ""
echo -e "${YELLOW}[3/5] Đang cấu hình lệnh toàn cầu 'luga'...${NC}"
chmod +x "$PROJECT_DIR/luga"
chmod +x "$PROJECT_DIR/start_background.sh" 2>/dev/null || true
chmod +x "$PROJECT_DIR/stop_background.sh" 2>/dev/null || true
chmod +x "$PROJECT_DIR/status.sh" 2>/dev/null || true

GLOBAL_LINK_CREATED=false

# Try /usr/local/bin first
if [ -w "/usr/local/bin" ]; then
    ln -sf "$PROJECT_DIR/luga" /usr/local/bin/luga
    GLOBAL_LINK_CREATED=true
elif [ -d "/usr/local/bin" ] && command -v sudo &> /dev/null; then
    echo -e "${CYAN}Đang tạo liên kết toàn cầu vào /usr/local/bin/luga (có thể cần mật khẩu máy)...${NC}"
    if sudo ln -sf "$PROJECT_DIR/luga" /usr/local/bin/luga 2>/dev/null; then
        GLOBAL_LINK_CREATED=true
    fi
fi

# Fallback to ~/.local/bin or ~/.zshrc export
if [ "$GLOBAL_LINK_CREATED" = false ]; then
    USER_BIN="$HOME/.local/bin"
    mkdir -p "$USER_BIN"
    ln -sf "$PROJECT_DIR/luga" "$USER_BIN/luga"
    GLOBAL_LINK_CREATED=true

    # Ensure ~/.local/bin is in PATH in shell config
    for RC in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile"; do
        if [ -f "$RC" ]; then
            if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$RC"; then
                echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$RC"
            fi
            if ! grep -q "alias luga=\"$PROJECT_DIR/luga\"" "$RC"; then
                echo "alias luga=\"$PROJECT_DIR/luga\"" >> "$RC"
            fi
        fi
    done
fi

echo -e "${GREEN}✓ Lệnh 'luga' đã được cấu hình toàn cầu!${NC}"
echo -e "  Từ bây giờ, bạn có thể mở bất kỳ terminal nào và gõ lệnh ${CYAN}luga${NC} mà không cần 'cd'."

# 4. Check Google Chrome
echo ""
echo -e "${YELLOW}[4/5] Kiểm tra trình duyệt Google Chrome...${NC}"
CHROME_PATH="/Applications/Google Chrome.app"
if [ -d "$CHROME_PATH" ] || command -v google-chrome &> /dev/null || command -v chrome &> /dev/null; then
    echo -e "${GREEN}✓ Đã tìm thấy Google Chrome trên hệ thống.${NC}"
else
    echo -e "${YELLOW}⚠️ Chưa tìm thấy Google Chrome tại /Applications/Google Chrome.app${NC}"
    echo -e "  Luga Assist hoạt động tốt nhất khi có Google Chrome để duy trì phiên kết nối ngầm."
fi

# 5. macOS Permissions Check & Guide
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo ""
    echo -e "${YELLOW}[5/5] Cấp quyền trợ năng hệ thống (macOS Accessibility)...${NC}"
    echo -e "Để Luga Assist có thể tự động điều khiển chuột, bàn phím và chụp ảnh màn hình,"
    echo -e "macOS yêu cầu bạn bật quyền cho Terminal / Python tại:"
    echo -e "  1. ${BOLD}Cài đặt hệ thống (System Settings)${NC} -> ${BOLD}Quyền riêng tư & Bảo mật (Privacy & Security)${NC}"
    echo -e "  2. Bật quyền tại mục: ${CYAN}Trợ năng (Accessibility)${NC}"
    echo -e "  3. Bật quyền tại mục: ${CYAN}Ghi màn hình (Screen Recording)${NC}"
    echo ""
    read -p "👉 Bạn có muốn mở ngay Cài đặt Trợ năng để kiểm tra/bật quyền không? (Y/n): " OPEN_PERMS
    if [[ "$OPEN_PERMS" =~ ^[Yy]?$ ]]; then
        open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
    fi
fi

# Summary Banner
echo ""
echo -e "${CYAN}${BOLD}======================================================================${NC}"
echo -e "${GREEN}${BOLD}             🎉 CÀI ĐẶT LUGA ASSIST HOÀN TẤT THÀNH CÔNG!             ${NC}"
echo -e "${CYAN}${BOLD}======================================================================${NC}"
echo -e "${BOLD}Các lệnh điều khiển nhanh bạn có thể dùng ở BẤT CỨ ĐÂU:${NC}"
echo -e "  • ${CYAN}luga start${NC}    : Khởi động app chạy ngầm (Zero browser windows)"
echo -e "  • ${CYAN}luga stop${NC}     : Dừng app đang chạy ngầm"
echo -e "  • ${CYAN}luga status${NC}   : Kiểm tra app có đang chạy hay không"
echo -e "  • ${CYAN}luga chat${NC}     : Mở giao diện Chat điều khiển máy tính cực đẹp trên Terminal"
echo -e "  • ${CYAN}luga logs${NC}     : Xem nhật ký hoạt động gần nhất"
echo -e "  • ${CYAN}Phím F8${NC}       : Nói lệnh giọng nói từ bất kỳ ứng dụng nào (toàn hệ thống)"
echo -e "  • ${CYAN}Giao diện Web${NC} : http://localhost:8000"
echo -e "${CYAN}======================================================================${NC}"
echo ""

read -p "👉 Bạn có muốn khởi động Luga Assist chạy ngầm ngay bây giờ không? (Y/n): " START_NOW
if [[ "$START_NOW" =~ ^[Yy]?$ ]]; then
    ./start_background.sh
fi
