# 🎙️ LUGA ASSIST - AI AGENT ĐIỀU KHIỂN MÁY TÍNH CHO NGƯỜI KHIẾM THỊ

**Luga Assist** là trợ lý AI (Computer-Use Agent) nhẹ, đa nền tảng (**macOS** và **Windows**), giúp người khiếm thị và người thị lực kém có thể điều khiển hoàn toàn máy tính thông qua **giọng nói tiếng Việt**: tìm kiếm ứng dụng, click chuột, nhấp đúp, gõ phím, cuộn trang và đọc to nội dung trên màn hình.

---

## 🌟 ĐIỂM NỔI BẬT

1. **Hoàn toàn miễn phí 100%:** 
   - Tận dụng trực tiếp phiên chat **Google Gemini Web** cá nhân có sẵn thông qua Chrome Extension.
   - Không cần trả phí OpenAI/Claude API, không lo hết hạn Credit.
2. **Tự động xử lý quá tải (Auto New Chat):** 
   - Tự động duy trì phiên chat hiện tại và tự động bấm **"Cuộc trò chuyện mới" (`+`)** khi phiên đạt ngưỡng giới hạn hoặc context quá tải.
3. **Độ chính xác tọa độ vượt trội (Visual Coordinate Grid):**
   - Chụp màn hình siêu nhanh (< 10ms) và tự động phủ **lưới tọa độ phần trăm mờ** lên ảnh trước khi gửi tới Gemini. Điều này giúp AI xác định tâm nút/biểu tượng chuẩn xác từng pixel.
4. **Nhận diện giọng nói chuẩn Google (Web Speech API):**
   - Hỗ trợ tiếng Việt tự nhiên, có dấu câu, nhận diện theo thời gian thực (Real-time Streaming).
5. **Giọng đọc tiếng Việt tự nhiên như người thật (Neural TTS):**
   - Tích hợp giọng đọc Microsoft Edge Neural (`vi-VN-HoaiMyNeural` và `vi-VN-NamMinhNeural`), phát âm rõ ràng, ấm áp, truyền cảm.
6. **Thiết kế chuyên biệt cho Trợ năng (Accessibility - WCAG 2.1 AAA):**
   - Giao diện tương phản cao (High-contrast Dark theme).
   - Âm thanh tín hiệu (Earcons) báo hiệu khi bắt đầu/kết thúc lắng nghe và khi hoàn thành tác vụ.
   - Hỗ trợ phím tắt cực đại: **Phím Space** (bấm để nói), **F2** (chế độ nghe liên tục), **F4** (đọc màn hình), **Esc** (dừng khẩn cấp).

---

## 🏛️ KIẾN TRÚC HỆ THỐNG

```
       [ Người dùng khiếm thị ]
                 │
      (Nói tiếng Việt vào Mic)
                 ▼
     [ Web Interface (Port 8000) ]  <--- (Web Speech STT tiếng Việt)
                 │
            (WebSocket)
                 ▼
     [ Local Agent (Python Core) ]  <--- (MSS Chụp màn hình + Lưới tọa độ + OS Automation + Edge-TTS)
                 │
            (WebSocket)
                 ▼
     [ Chrome Extension Bridge ]    <--- (Paste ảnh vào gemini.google.com -> Lấy JSON -> Tự tạo New Chat)
```

---

## 🚀 HƯỚNG DẪN CÀI ĐẶT & CHẠY

### BƯỚC 1: Cài đặt thư viện

#### Trên macOS / Linux:
Mở Terminal tại thư mục dự án và chạy:
```bash
./setup.sh
```

#### Trên Windows:
Nhấp đúp chuột vào file:
```bat
setup.bat
```

---

### BƯỚC 2: Cài đặt Chrome Extension (Chỉ cần làm 1 lần duy nhất)

1. Mở trình duyệt **Google Chrome** (hoặc Microsoft Edge).
2. Truy cập vào thanh địa chỉ: `chrome://extensions/`
3. Bật công tắc **"Chế độ cho nhà phát triển" (Developer mode)** ở góc trên cùng bên phải.
4. Nhấn nút **"Tải tiện ích đã giải nén" (Load unpacked)**.
5. Chọn thư mục `extension` nằm trong thư mục dự án này.
6. Bạn sẽ thấy biểu tượng **Luga Assist - Gemini Web Bridge** xuất hiện trên thanh tiện ích!

---

### BƯỚC 3: Cấp quyền hệ thống (Chỉ dành cho macOS)

Trên macOS, để phần mềm có thể di chuột và chụp ảnh màn hình các app khác, bạn cần cấp quyền:
1. Vào **Cài đặt hệ thống (System Settings)** -> **Quyền riêng tư & Bảo mật (Privacy & Security)**.
2. Mục **Trợ năng (Accessibility)**: Bật công tắc cho **Terminal** (hoặc iTerm / Python).
3. Mục **Ghi màn hình & Âm thanh (Screen Recording)**: Bật công tắc cho **Terminal** (hoặc Python).

---

### BƯỚC 4: Khởi động hệ thống

#### Trên macOS:
```bash
./start.sh
```

#### Trên Windows:
Nhấp đúp file:
```bat
start.bat
```

**Hệ thống sẽ hoàn toàn tự động:**
1. Server khởi chạy tại `http://127.0.0.1:8000`.
2. **Tự động mở ngay ứng dụng Luga Assist** trên trình duyệt của bạn.
3. **Bạn KHÔNG cần mở tab Google Gemini:** Chrome Extension sẽ tự động duy trì phiên Gemini chạy ngầm dưới nền hoàn toàn vô hình!

---

## 🎮 HƯỚNG DẪN SỬ DỤNG BẰNG PHÍM TẮT

| Phím tắt | Chức năng |
| :--- | :--- |
| **Phím Space (Cách)** | Bấm hoặc giữ để kích hoạt Microphone và nói lệnh |
| **Phím F2** | Bật / tắt chế độ lắng nghe liên tục (Always Listening) |
| **Phím F4** | Yêu cầu AI miêu tả chi tiết những gì đang hiển thị trên màn hình hiện tại |
| **Phím Esc** | Ngắt giọng đọc ngay lập tức / Hủy thao tác |

### Ví dụ các câu lệnh mẫu:
- *"Mở trình duyệt Google Chrome cho tôi"*
- *"Bấm vào biểu tượng tìm kiếm và gõ nhạc Trịnh Công Sơn"*
- *"Nhấp đúp vào thư mục Tài liệu trên màn hình"*
- *"Cuộn trang xuống phía dưới một chút"*
- *"Đọc giúp tôi cửa sổ đang mở trên màn hình có những gì"*

---

## 🧪 CHẠY TEST KIỂM THỬ TỰ ĐỘNG

Dự án đi kèm bộ test tự động kiểm tra toàn bộ pipeline từ chụp màn hình, phủ lưới tọa độ, dịch tọa độ Retina/DPI, bộ xử lý JSON và tạo giọng đọc:
```bash
python3 tests/test_pipeline.py
```
Kết quả kiểm thử: `🎉 ALL TESTS PASSED SUCCESSFULLY!`

---

## 📁 CẤU TRÚC MÃ NGUỒN

```
luga-assist/
├── app/
│   ├── config.py             # Cấu hình cổng, đường dẫn, giọng đọc, lưới tọa độ
│   ├── main.py               # FastAPI Server & WebSocket Hub điều phối chính
│   ├── os_controller.py      # Điều khiển chuột, bàn phím, phím nóng, mở app
│   ├── screen_capture.py     # Chụp màn hình (mss) + Phủ lưới tọa độ + Đánh dấu click
│   ├── tts_service.py        # Giọng đọc tiếng Việt Microsoft Edge Neural & gTTS
│   └── prompt_templates.py   # System prompt ép định dạng JSON Computer Use
├── extension/                # Chrome Extension Manifest V3 kết nối Gemini Web
│   ├── manifest.json         # Khai báo quyền Extension
│   ├── content.js            # Tự động hóa tab gemini.google.com & tạo New Chat
│   ├── background.js         # Service Worker quản lý trạng thái
│   ├── popup.html / .js      # Giao diện popup tiện ích
│   └── icons/                # Bộ biểu tượng ứng dụng
├── web/                      # Giao diện Web Trợ năng (Web Speech API)
│   ├── index.html            # Giao diện HTML chuẩn WCAG AAA
│   ├── style.css             # Giao diện Dark theme tương phản cao
│   └── app.js                # Xử lý nhận diện giọng nói Google & phím tắt
├── tests/
│   └── test_pipeline.py      # Kiểm thử toàn diện các module
├── setup.sh / setup.bat      # Cài đặt 1-click cho Mac / Windows
├── start.sh / start.bat      # Khởi động 1-click cho Mac / Windows
└── requirements.txt          # Danh sách thư viện Python
```
