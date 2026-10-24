# 🚀 Luga Assist v1.2.1 — Release Notes

> **Bản cập nhật Luga Assist v1.2.1: Hỗ trợ Trình duyệt mặc định hệ thống (Chrome, Brave, Cốc Cốc, Edge), khắc phục triệt để lỗi Session Google, tối ưu độ chính xác nhấp chuột 100% với DPI Awareness & Snapping, và kết nối trực tiếp Mức độ suy nghĩ (Thinking Level) vào Gemini.**

---

## 🌟 Điểm nổi bật trong bản phát hành v1.2.1 (Key Highlights)

### 1. 🌐 Tự động Nhận diện & Tôn trọng Trình duyệt Mặc định (Default Browser Support)
* **Không còn ép buộc Microsoft Edge**: Tự động truy vấn cấu hình Windows Registry (`UrlAssociations\https\UserChoice`) để xác định chính xác trình duyệt mặc định mà người dùng đang sử dụng (Google Chrome, Brave Browser, Cốc Cốc, Microsoft Edge, v.v.).
* Nếu trình duyệt mặc định là Chromium-based, Luga Assist sẽ mở chính trình duyệt đó để đăng nhập.
* Nếu trình duyệt mặc định không phải Chromium (ví dụ Firefox) hoặc không xác định được, hệ thống ưu tiên tìm theo thứ tự người dùng cài đặt: **Chrome $\rightarrow$ Brave $\rightarrow$ Cốc Cốc $\rightarrow$ Edge**.

### 2. 🛡️ Khắc phục Triệt để Lỗi "Session Google đã hết hạn"
* **Bắt đủ cặp Tokens xác thực**: Modern Google Gemini bắt buộc phải có cặp cookie `__Secure-1PSID` và `__Secure-1PSIDTS` (kèm `__Secure-1PSIDCC`). Phiên bản mới lắng nghe liên tục cho đến khi đủ toàn bộ token cần thiết thay vì đóng sớm sau vài giây.
* **Tự động điều hướng kích hoạt token**: Nếu người dùng hoàn tất đăng nhập trên `accounts.google.com` mà chưa được chuyển tiếp, hệ thống gửi lệnh qua Chrome DevTools Protocol (CDP) mở thẳng `gemini.google.com` để hoàn tất lưu cookie.
* **Xác thực trước khi đóng trình duyệt**: Chỉ đóng cửa sổ đăng nhập và thông báo thành công sau khi `GeminiClient` đã kết nối thành công 100%. Nếu kết nối chưa hoàn tất, trình duyệt vẫn mở để người dùng thao tác tiếp.
* **Phân biệt lỗi chính xác**: Không còn tự động gán nhãn "Session hết hạn" cho các lỗi mạng gián đoạn tạm thời hay timeout.

### 3. 🎯 Độ Chính Xác Nhấp Chuột 100% (100% Click Precision)
* **Kích hoạt Windows Per-Monitor DPI Awareness (V2)**: Đồng bộ hóa hoàn hảo 1:1 giữa độ phân giải vật lý của màn hình, tọa độ chụp ảnh của thư viện MSS, hệ thống lưới thị giác Visual Grid và tọa độ chuột `pyautogui`. Khắc phục triệt để hiện tượng click lệch trên màn hình có tỷ lệ phóng to (125%, 150%, 175%, 200%).
* **Công nghệ Hít Tọa độ Thông minh (UI Automation Coordinate Snapping)**: Khi AI trả về tọa độ nhấp chuột, hệ thống tự động đối chiếu với Bounding Rectangle của các phần tử giao diện thực tế (nút bấm, ô tìm kiếm, liên kết) và tự động "hít" con trỏ chuột vào đúng tâm của nút bấm.
* **Ảnh chụp màn hình Siêu nét (High-Resolution Capture)**: Giữ nguyên độ phân giải gốc lên đến 2K/QHD (2560px), chất lượng JPEG 92 với tính năng chống nhòe `subsampling=0` và thuật toán thu nhỏ `LANCZOS` cho màn hình 4K. Chữ và biểu tượng hiển thị sắc nét tuyệt đối cho Gemini Vision.

### 4. 🧠 Kết Nối Thực Tế Mức Độ Suy Nghĩ (Thinking Level) vào Động Cơ Gemini
* Menu chọn mức độ suy nghĩ (Thấp / Vừa / Sâu) trên Spotlight và phím tắt giờ đây được liên kết trực tiếp vào hàm gọi API của Gemini:
  * **⚡ Thấp (Low)**: Chạy mô hình phản hồi nhanh nhất, tắt extended thinking, tối ưu tốc độ ra lệnh.
  * **🧠 Vừa (Medium - Mặc định)**: Cân bằng lý tưởng giữa tốc độ và độ chuẩn xác.
  * **🔍 Sâu (High)**: Truyền tham số `extended_thinking=True` trực tiếp vào phiên Gemini Web để AI phân tích đa bước và suy luận kỹ lưỡng trước khi thao tác màn hình phức tạp.

### 5. ♿ Tương Thích Hoàn Hảo NVDA & Giao Diện Web Spotlight
* Cửa sổ Spotlight (F7) mượt mà, nhỏ gọn, phản hồi tức thì với phím Tab.
* Cơ chế Single-Instance Toggle: Mỗi lần bấm F7 chỉ kích hoạt hoặc ẩn một cửa sổ duy nhất, không tạo tiến trình thừa.
* Đầy đủ nút **✕ Ẩn (Esc)** và **🛑 Thoát (Ctrl + Q)**.

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

1. Tải file **`Luga-Assist-Setup.exe`** từ mục Assets.
2. Mở file và bấm **Next** để cài đặt vào máy tính.
3. Mở icon **Luga Assist** trên màn hình Desktop.
4. Bấm **`F7`**, chọn **"Đăng nhập Google"** để liên kết tài khoản Gemini trên trình duyệt mặc định của bạn (chỉ cần làm 1 lần).
5. Bấm **`F8`** để bắt đầu ra lệnh bằng giọng nói!

---

## 🧪 Kết Quả Kiểm Thử (Verification)
* **25/25 tests passed**: Vượt qua 100% các bài kiểm tra toàn diện: nhận diện trình duyệt mặc định, hít tọa độ thông minh, kiểm soát DPI, mức độ suy nghĩ AI, xử lý sự kiện ngắt khẩn cấp, âm thanh và xác thực Google Web.
* **100% NVDA Screen Reader Compatible**: Đã kiểm tra thực tế với NVDA trên Windows 10 và Windows 11.
