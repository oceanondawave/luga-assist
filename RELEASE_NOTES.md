# 🚀 Luga Assist v1.2.0 — Release Notes

> **Bản phát hành chính thức Luga Assist v1.2.0: Cửa sổ Web Spotlight độc lập, tương thích 100% trình đọc màn hình NVDA, đăng nhập Google Web trực tiếp 1-click không cần Extension.**

---

## 🌟 Điểm nổi bật trong bản phát hành v1.2.0 (Key Highlights)

### 1. 🚀 Đăng nhập Google Web Trực tiếp (Zero Extension, Zero API Key)
* **Không cần tiện ích mở rộng (No Extension)**: Đã loại bỏ hoàn toàn yêu cầu cài đặt Chrome Extension, không cần bật Developer Mode hay nạp Unpacked Extension.
* **Không tốn phí API Key**: Sử dụng trực tiếp bộ não Google Gemini Vision miễn phí qua giao diện Web.
* **Tự động hóa hoàn toàn**: Nhấn nút **"Đăng nhập Google"** trên Spotlight (F7), đăng nhập tài khoản Google trên cửa sổ trình duyệt xuất hiện. Hệ thống sẽ tự động bắt cặp cookies `__Secure-1PSID` & `__Secure-1PSIDTS`, tự đóng trình duyệt ngay khi đăng nhập xong và khôi phục Spotlight.
* Hỗ trợ đầy đủ menu **Đổi tài khoản** và **Đăng xuất**.

### 2. ♿ Giao diện Web Spotlight (F7) — 100% Tương thích NVDA
* **Thiết kế chuyên biệt cho Người khiếm thị**:
  * Tương phản cao, bố cục siêu gọn nhẹ, responsive, tương thích 100% với trình đọc màn hình NVDA và JAWS.
  * Đầy đủ thuộc tính trợ năng: `role="banner"`, `role="log"`, `role="contentinfo"`, nhãn `aria-label` chi tiết trên từng nút bấm.
  * Vùng cập nhật trực tiếp `aria-live="polite"` giúp NVDA tự động đọc to tin nhắn mới và trạng thái phân tích màn hình mà không cần rà soát lại.
* **Điều hướng bàn phím mượt mà**: Focus tự động vào ô soạn thảo khi mở, hỗ trợ phím Tab tuần tự qua tất cả các chức năng.

### 3. ⚡ Cơ chế Bật / Tắt 1 Cửa sổ Duy nhất (Single-Instance Toggle)
* Khắc phục triệt để hiện tượng mỗi lần bấm F7 lại tạo thêm một tiến trình Edge mới.
* Sử dụng Chromium App Window độc lập (`--user-data-dir` riêng biệt) kết hợp Win32 API (`EnumWindows`, `GetForegroundWindow`).
* **Hành vi thông minh**:
  * Nếu Spotlight đang hiển thị trên cùng $\rightarrow$ thu nhỏ / ẩn cửa sổ (SW_MINIMIZE).
  * Nếu Spotlight đang ở dưới hoặc thu nhỏ $\rightarrow$ khôi phục (SW_RESTORE), đưa lên trên cùng và tự động focus ô nhập liệu.

### 4. 🛑 Nút Ẩn và Nút Thoát Ứng Dụng Rõ Ràng
* **`✕ Ẩn (Esc)`**: Ẩn tạm thời cửa sổ Spotlight để làm việc khác; Luga Assist vẫn chạy ngầm lắng nghe các phím tắt F7, F8.
* **`🛑 Thoát (Ctrl + Q)`**: Hộp thoại xác nhận tắt hoàn toàn Luga Assist, phát giọng nói tạm biệt và dừng toàn bộ dịch vụ ngầm.

### 5. 🧠 Tùy chọn Mức độ Suy nghĩ AI (Thinking Level)
* Tích hợp menu chọn mức độ suy nghĩ ngay trên thanh công cụ Spotlight:
  * **⚡ Thấp (Low)**: Phản hồi nhanh tức thì.
  * **🧠 Vừa (Medium - Mặc định)**: Cân bằng tốc độ và độ chuẩn xác.
  * **🔍 Sâu (High)**: Phân tích kỹ lưỡng các tác vụ phức tạp đa bước.

### 6. 🔊 Âm thanh Earcon & Giọng đọc Thông minh
* Hệ thống âm thanh phản hồi trực quan:
  * 🔔 **Chime**: Phát khi bắt đầu lắng nghe lệnh giọng nói.
  * ⏳ **Pulse**: Nhịp tim âm thanh phát ngầm trong lúc AI chụp ảnh và phân tích màn hình.
  * 🔔 **Glass**: Phát khi tác vụ đã hoàn thành xuất sắc.
  * ⚠️ **Basso**: Phát khi có lỗi hoặc khi người dùng kích hoạt ngắt khẩn cấp.
* Giọng đọc Edge Neural Tiếng Việt (`vi-VN-HoaiMyNeural` / `vi-VN-NamMinhNeural`) và Tiếng Anh (`en-US-AriaNeural`), tự động chuyển tiếp an toàn sang gTTS khi đường truyền mạng có sự cố.

---

## ⌨️ Bảng Phím Tắt Toàn Cầu (Global Shortcuts)

| Phím tắt | Phím dự phòng | Tác vụ |
| :--- | :--- | :--- |
| **`F7`** | `Ctrl + Alt + Space` | **Bật / Tắt Cửa sổ Web Spotlight (F7)** (Single-instance toggle) |
| **`F8`** | `Ctrl + Space` | **Nói lệnh qua Micro** (Lắng nghe giọng nói tiếng Việt tự nhiên) |
| **`F9`** | `Ctrl + Alt + M` | **Chuyển đổi chế độ** [Điều khiển PC 🎮] ⇄ [Trò chuyện hỏi đáp 💬] |
| **`F10`** | `Ctrl + Esc` | **⏹️ NGẮT KHẨN CẤP** (Dừng ngay thao tác chuột, ngắt micro, ngắt giọng đọc) |
| **`Esc`** | — | **Ẩn cửa sổ Spotlight** |
| **`Ctrl + Q`** | — | **🛑 Tắt và thoát hoàn toàn Luga Assist** |

---

## 📦 Danh Sách File Phát Hành (Release Assets)

| File | Kích thước | Mô tả |
| :--- | :--- | :--- |
| **`Luga-Assist-Setup.exe`** | ~40-60 MB | **Bộ cài đặt Windows tự động (Khuyên dùng)**: Tự tạo icon Desktop, Start Menu và trình gỡ cài đặt chuẩn. |
| **`Luga-Assist-Windows.zip`** | ~40-60 MB | **Bản Portable giải nén chạy ngay**: Chạy trực tiếp qua `start_windows.vbs` không cần cài đặt. |

---

## 🚀 Hướng Dẫn Cài Đặt Nhanh

1. Tải file **`Luga-Assist-Setup.exe`** bên dưới.
2. Mở file và bấm **Next** để cài đặt vào máy tính.
3. Sau khi cài, mở icon **Luga Assist** trên màn hình Desktop.
4. Bấm **`F7`**, chọn **"Đăng nhập Google"** để liên kết tài khoản Gemini (chỉ cần làm 1 lần duy nhất).
5. Bấm **`F8`** để bắt đầu ra lệnh bằng giọng nói!

---

## 🧪 Kết Quả Kiểm Thử (Verification)
* **24/24 tests passed**: Vượt qua 100% các bài kiểm tra toàn diện pipeline, xử lý sự kiện ngắt khẩn cấp, kiểm tra phím tắt, âm thanh, điều khiển màn hình và xác thực Google Web.
* **100% NVDA Screen Reader Compatible**: Đã kiểm tra thực tế với NVDA trên Windows 10 và Windows 11.
