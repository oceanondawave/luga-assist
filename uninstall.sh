#!/bin/bash
# ==============================================================================
# Luga Assist - Friendly Uninstaller for macOS / Linux
# ==============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR"

clear
echo -e "${RED}${BOLD}======================================================================${NC}"
echo -e "${RED}${BOLD}        🗑️   LUGA ASSIST - TRÌNH GỠ CÀI ĐẶT (UNINSTALLER)            ${NC}"
echo -e "${RED}${BOLD}======================================================================${NC}"
echo -e "${BLUE}Thư mục dự án:${NC} $PROJECT_DIR"
echo ""

read -p "❓ Bạn có chắc chắn muốn gỡ cài đặt Luga Assist khỏi hệ thống không? (y/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Đã hủy thao tác gỡ cài đặt. Luga Assist vẫn được giữ nguyên.${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}[1/4] Đang dừng tiến trình Luga Assist nếu đang chạy ngầm...${NC}"
if [ -f "$PROJECT_DIR/stop_background.sh" ]; then
    bash "$PROJECT_DIR/stop_background.sh" 2>/dev/null || true
fi
echo -e "${GREEN}✓ Đã dừng tiến trình.${NC}"

echo ""
echo -e "${YELLOW}[2/4] Đang gỡ bỏ liên kết lệnh toàn cầu 'luga'...${NC}"
if [ -L "/usr/local/bin/luga" ]; then
    if [ -w "/usr/local/bin" ]; then
        rm -f "/usr/local/bin/luga"
    elif command -v sudo &> /dev/null; then
        sudo rm -f "/usr/local/bin/luga" 2>/dev/null || true
    fi
fi
if [ -L "$HOME/.local/bin/luga" ]; then
    rm -f "$HOME/.local/bin/luga"
fi
echo -e "${GREEN}✓ Đã xóa liên kết lệnh toàn cầu.${NC}"

echo ""
echo -e "${YELLOW}[3/4] Đang dọn dẹp cấu hình shell (~/.zshrc, ~/.bashrc)...${NC}"
for RC in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.bash_profile"; do
    if [ -f "$RC" ]; then
        # Remove luga alias / export lines safely
        sed -i '' '/alias luga=/d' "$RC" 2>/dev/null || sed -i '/alias luga=/d' "$RC" 2>/dev/null || true
    fi
done
echo -e "${GREEN}✓ Đã dọn dẹp biến môi trường shell.${NC}"

echo ""
echo -e "${YELLOW}[4/5] Đang xóa các ứng dụng Luga trên Màn hình chính (Desktop)...${NC}"
rm -rf "$HOME/Desktop/Luga Assist.app" "$HOME/Desktop/Chat Nhanh (Spotlight).app" "$HOME/Desktop/Dừng Luga.app" "$HOME/Desktop/Trạng thái Luga.app" 2>/dev/null || true
echo -e "${GREEN}✓ Đã dọn dẹp các ứng dụng trên Desktop.${NC}"

echo ""
echo -e "${YELLOW}[5/5] Dọn dẹp dữ liệu tạm thời & nhật ký...${NC}"
read -p "❓ Bạn có muốn xóa nhật ký (logs) và phiên đăng nhập lưu tạm không? (Y/n): " CLEAN_DATA
if [[ "$CLEAN_DATA" =~ ^[Yy]?$ ]]; then
    rm -rf "$PROJECT_DIR/logs/"*.log 2>/dev/null || true
    rm -rf "$PROJECT_DIR/temp/"*.json 2>/dev/null || true
    rm -rf "$HOME/.luga_cli_history" 2>/dev/null || true
    echo -e "${GREEN}✓ Đã xóa file logs và session lưu tạm.${NC}"
fi

echo ""
echo -e "${CYAN}${BOLD}======================================================================${NC}"
echo -e "${GREEN}${BOLD}           ✅ GỠ CÀI ĐẶT LUGA ASSIST HOÀN TẤT THÀNH CÔNG!            ${NC}"
echo -e "${CYAN}${BOLD}======================================================================${NC}"
echo -e "Lệnh 'luga' đã được gỡ bỏ khỏi hệ thống."
echo -e "Thư mục mã nguồn dự án tại: ${CYAN}$PROJECT_DIR${NC} vẫn được bảo toàn."
echo -e "Nếu muốn cài đặt lại trong tương lai, bạn chỉ cần chạy: ${CYAN}./install.sh${NC}"
echo -e "${CYAN}======================================================================${NC}\n"
