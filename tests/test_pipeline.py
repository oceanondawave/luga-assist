"""
Automated unit & integration tests for Luga Assist components.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from app.prompt_templates import build_gemini_prompt
from app.screen_capture import screen_capturer
from app.tts_service import tts_service
from app.os_controller import os_controller
from app.main import extract_json_payload

def test_prompt_generation():
    cmd = "Mở trình duyệt Google Chrome"
    prompt = build_gemini_prompt(cmd)
    assert cmd in prompt
    assert "x_percent" in prompt
    assert "speech" in prompt
    print("test_prompt_generation: PASSED")

def test_screen_capture_and_annotation():
    uri, size = screen_capturer.capture(with_grid=True)
    assert uri.startswith("data:image/jpeg;base64,")
    assert size[0] > 0 and size[1] > 0

    # Test annotation
    annotated = screen_capturer.annotate_action(0.5, 0.5, "click")
    assert annotated is not None
    assert annotated.startswith("data:image/jpeg;base64,")
    print("test_screen_capture_and_annotation: PASSED")

def test_extract_json_payload():
    # Test case 1: Raw JSON
    raw1 = '{"speech": "Đang mở Chrome", "action": "click", "x_percent": 0.1, "y_percent": 0.9}'
    res1 = extract_json_payload(raw1)
    assert res1["action"] == "click"
    assert res1["x_percent"] == 0.1

    # Test case 2: Markdown fence with conversation
    raw2 = """Chào bạn, tôi sẽ giúp bạn ngay!
```json
{
  "speech": "Tôi đang nhấn vào biểu tượng Spotify",
  "action": "click",
  "x_percent": 0.45,
  "y_percent": 0.88
}
```
Chúc bạn nghe nhạc vui vẻ!"""
    res2 = extract_json_payload(raw2)
    assert res2["action"] == "click"
    assert res2["speech"] == "Tôi đang nhấn vào biểu tượng Spotify"
    assert res2["x_percent"] == 0.45

    # Test case 3: Malformed / double markdown fence
    raw3 = """```json
{
  "speech": "Đang sửa lại địa chỉ email",
  "actions": [
    {
      "action": "click",
      "x_percent": 0.472,
      "y_percent": 0.468
```json
{
  "speech": "Đang sửa lại email cho bạn",
  "actions": [
    {
      "action": "click",
      "x_percent": 0.47,
      "y_percent": 0.47
    },
    {
      "action": "press",
      "key": "cmd+a"
    },
    {
      "action": "type",
      "text": "minh.ngntri@gmail.com"
    }
  ]
}
```"""
    res3 = extract_json_payload(raw3)
    assert len(res3["actions"]) == 3
    assert res3["actions"][2]["text"] == "minh.ngntri@gmail.com"
    print("test_extract_json_payload: PASSED")

def test_os_controller_to_pixel_coords():
    w, h = os_controller.get_screen_size()
    x, y = os_controller.to_pixel_coords(0.5, 0.5)
    assert x == int(w * 0.5)
    assert y == int(h * 0.5)
    print("test_os_controller_to_pixel_coords: PASSED")

def test_tts_generation():
    async def run_tts():
        path = await tts_service.generate_audio("Kiểm tra giọng nói Luga Assist")
        assert path.exists()
        assert path.stat().st_size > 0
    asyncio.run(run_tts())
    print("test_tts_generation: PASSED")

def test_multi_action_sequence():
    multi_json = """
```json
{
  "speech": "Đang bấm ô tìm kiếm, gõ từ khóa và nhấn Enter",
  "actions": [
    {"action": "click", "x_percent": 0.8, "y_percent": 0.1},
    {"action": "type", "text": "Spotify"},
    {"action": "press", "key": "enter"},
    {"action": "wait", "delay": 0.1}
  ]
}
```
"""
    res = extract_json_payload(multi_json)
    assert "actions" in res
    assert len(res["actions"]) == 4
    assert res["actions"][0]["action"] == "click"
    assert res["actions"][1]["text"] == "Spotify"

    # Test multi-action visual annotation
    annotated = screen_capturer.annotate_actions(res["actions"])
    assert annotated is not None
    assert annotated.startswith("data:image/jpeg;base64,")

    # Test multi-action execution with mock/noop
    result = os_controller.execute_action_sequence([
        {"action": "wait", "delay": 0.05},
        {"action": "none"}
    ])
    assert result["success"] is True
    assert result["count"] == 2
    print("test_multi_action_sequence: PASSED")

def test_sound_effects():
    import time
    from app.sound_effects import sound_manager
    sound_manager.play_start()
    sound_manager.start_pulsing()
    time.sleep(0.6)
    sound_manager.play_done()
    time.sleep(0.1)
    sound_manager.play_error()
    print("test_sound_effects: PASSED")

def test_accessibility_and_precision_focus():
    from app.accessibility import accessibility_manager
    ctx = accessibility_manager.get_ui_grounding_context()
    assert isinstance(ctx, str)
    print("test_accessibility_context: PASSED (length:", len(ctx), ")")

    # Test focus action execution
    res = os_controller.execute_action({"action": "focus", "target": "next"})
    assert res["success"] is True
    assert "Tab" in res["details"]
    print("test_precision_focus_action: PASSED")

def test_windows_cross_platform_compatibility():
    # Verify Windows shortcut mappings
    from app.accessibility import accessibility_manager
    assert hasattr(accessibility_manager, "_get_windows_app_elements")
    print("test_windows_cross_platform_compatibility: PASSED")

def test_outcome_verification_prompt():
    from app.prompt_templates import build_verification_prompt
    v_prompt = build_verification_prompt(
        user_command="Gửi email cho Minh",
        step=2,
        previous_actions_desc="Gõ email và nhấn nút gửi",
        ui_context="[UI Elements detected]"
    )
    assert "OUTCOME VERIFICATION" in v_prompt
    assert "Gửi email cho Minh" in v_prompt
    assert "TRƯỜNG HỢP A" in v_prompt
    print("test_outcome_verification_prompt: PASSED")

def test_element_scoring_and_email_action():
    from app.accessibility import _score_element, accessibility_manager
    # 1. Test scoring prioritizing input fields and action buttons over formatting noise
    to_score = _score_element("AXTextField", "To Recipients")
    subject_score = _score_element("AXTextField", "Subject")
    send_score = _score_element("AXButton", "Send")
    bold_score = _score_element("AXButton", "Bold")
    italic_score = _score_element("AXButton", "Italic")

    assert to_score > 100
    assert subject_score > 100
    assert send_score > 70
    assert bold_score < 0
    assert italic_score < 0
    assert to_score > bold_score
    assert subject_score > italic_score

    # 2. Test send_email in prompt templates
    from app.prompt_templates import build_gemini_prompt
    prompt = build_gemini_prompt("Gửi email tới phuongma.luga, tiêu đề test, nội dung test")
    assert "send_email" in prompt
    assert "To Recipients" not in prompt or "x_percent" in prompt

    # 3. Test send_email action schema in extract_json_payload
    from app.main import extract_json_payload
    email_json = '{"speech": "Đang gửi thư", "done": false, "actions": [{"action": "send_email", "to": "phuongma.luga", "subject": "test", "body": "test"}]}'
    payload = extract_json_payload(email_json)
    assert payload is not None
    assert payload["actions"][0]["action"] == "send_email"
    assert payload["actions"][0]["to"] == "phuongma.luga"

    # 4. Test is_compose_window_active method exists
    assert hasattr(accessibility_manager, "is_compose_window_active")
    print("test_element_scoring_and_email_action: PASSED")

def test_system_control_action():
    from app.prompt_templates import build_gemini_prompt
    prompt = build_gemini_prompt("Tắt tiếng âm thanh hệ thống")
    assert "system_control" in prompt
    assert "mute" in prompt
    assert "sleep" in prompt

    # Test extract_json_payload for system_control
    from app.main import extract_json_payload
    mute_json = '{"speech": "Đang tắt tiếng hệ thống", "done": true, "actions": [{"action": "system_control", "command": "mute"}]}'
    payload = extract_json_payload(mute_json)
    assert payload is not None
    assert payload["actions"][0]["action"] == "system_control"
    assert payload["actions"][0]["command"] == "mute"
    print("test_system_control_action: PASSED")

def test_bilingual_voice_selection_and_normalization():
    from app.native_voice import (
        select_best_transcript,
        normalize_spoken_terms,
        count_vietnamese_diacritics,
        evaluate_english_word_ratio,
    )

    # 1. Test pure English vs Vietnamese hallucination
    # E.g. 'mute system audio' misheard as 'Musical' or 'mì xào'
    res_en = select_best_transcript(
        vi_res=("Musical Open Google Chrome", 0.87),
        en_res=("mute system audio and open Google Chrome", 0.90)
    )
    assert res_en == "mute system audio and open Google Chrome"

    res_mute = select_best_transcript(
        vi_res=("mì xào", 0.88),
        en_res=("mute sound", 0.92)
    )
    assert res_mute == "mute sound"

    res_vol = select_best_transcript(
        vi_res=("Doraemon", 0.94),
        en_res=("volume up", 0.96)
    )
    assert res_vol == "volume up"

    # 2. Test pure Vietnamese vs English nonsense
    res_vi = select_best_transcript(
        vi_res=("cho máy tính ngủ ngay lập tức", 0.95),
        en_res=("the amazing world I love you", 0.20)
    )
    assert res_vi == "cho máy tính ngủ ngay lập tức"

    # 3. Test mixed Vietnamese + English apps
    res_mixed = select_best_transcript(
        vi_res=("Mở Google Chrome và vào trang YouTube", 0.94),
        en_res=("my Google turn YouTube", 0.51)
    )
    assert res_mixed == "Mở Google Chrome và vào trang YouTube"

    # 4. Test term normalization for spoken Vietnamese tech loanwords
    norm1 = normalize_spoken_terms("soạn một email mới đến Phương Mai chấm Loga tiêu đề taxi nội dung cũng là test")
    assert "phuongma.luga" in norm1
    assert "tiêu đề test" in norm1
    assert "nội dung cũng là test" in norm1

    norm2 = normalize_spoken_terms("mở cơ rôm và tìm kiếm trên gúc gồ")
    assert norm2 == "mở Chrome và tìm kiếm trên Google"

    norm3 = normalize_spoken_terms("bật ứng dụng bóp phi và nghe nhạc")
    assert norm3 == "bật ứng dụng Spotify và nghe nhạc"

    print("test_bilingual_voice_selection_and_normalization: PASSED")

def test_file_management_and_terminal_suite():
    import tempfile
    from pathlib import Path
    from app.prompt_templates import build_gemini_prompt
    from app.file_and_terminal import file_and_terminal

    # 1. Test prompt generation includes terminal and file actions
    prompt = build_gemini_prompt("Tìm file báo cáo trong thư mục Downloads")
    assert "find_files" in prompt
    assert "terminal_command" in prompt
    assert "open_file" in prompt

    # 2. Test terminal command execution
    res_term = os_controller.execute_action({
        "action": "terminal_command",
        "command": "echo 'LUGA_TERMINAL_OK'"
    })
    assert res_term["success"] is True
    assert "LUGA_TERMINAL_OK" in res_term.get("stdout", "") or "LUGA_TERMINAL_OK" in res_term.get("details", "")
    assert res_term.get("speech_result") is not None

    # 3. Test find_files action
    res_find = os_controller.execute_action({
        "action": "find_files",
        "query": "test_pipeline.py"
    })
    assert res_find["success"] is True
    assert len(res_find.get("files", [])) > 0
    assert "test_pipeline.py" in res_find.get("speech_result", "")

    # 4. Test create_file, read_file, and delete_file
    tmp_path = Path(tempfile.gettempdir()) / "luga_pipeline_test.txt"
    res_create = os_controller.execute_action({
        "action": "create_file",
        "path": str(tmp_path),
        "content": "Dòng 1: Nội dung kiểm thử Luga Assist\nDòng 2: Hàng thứ hai"
    })
    assert res_create["success"] is True
    assert tmp_path.exists()

    res_read = os_controller.execute_action({
        "action": "read_file",
        "path": str(tmp_path)
    })
    assert res_read["success"] is True
    assert "Nội dung kiểm thử Luga Assist" in res_read.get("content", "")

    res_del = os_controller.execute_action({
        "action": "delete_file",
        "path": str(tmp_path),
        "safe_trash": False
    })
    assert res_del["success"] is True
    assert not tmp_path.exists()

    # 5. Test JSON parsing for terminal and powershell
    payload1 = extract_json_payload("""```json
{
  "speech": "Đang chạy lệnh powershell",
  "done": true,
  "actions": [
    {
      "action": "powershell_command",
      "command": "Get-Process | Select-Object -First 5"
    }
  ]
}
```""")
    assert payload1["actions"][0]["action"] == "powershell_command"
    assert "Get-Process" in payload1["actions"][0]["command"]

    print("test_file_management_and_terminal_suite: PASSED")

def test_narrative_extraction_and_speech_cleanup():
    from app.main import extract_payload_and_narrative, clean_text_for_speech

    sample_raw = """```json
{
  "speech": "Đang tóm tắt các video nổi bật trên trang chủ YouTube",
  "done": true,
  "actions": [
    {
      "action": "none"
    }
  ]
}
```

Trên trang chủ YouTube hiện đang hiển thị các video nổi bật sau:

o   Video giải trí & đời sống: "Đầu Phòng TV - Tập 85: Nợ Tình". JPG
o   Video công nghệ & nhiếp ảnh: So sánh "DSLR vs MIRRORLESS" và "Mua máy ảnh đầu tiên? Mọi thứ bạn cần biết". JPG
o   Video game & thể thao: "SERI ĐỘI HÌNH GIAO DỊCH FO4 TRỞ LẠI #18: Siêu Cò | Love - Cực Đồ Đón Cristiano Ronaldo +10". JPG
o   Video âm nhạc: "Chris Brown Ft Drake - Another Level (Official Music Video)" và "Machiot - Đổi Nhạc Nền Vol. 4 (Office Mixset)". JPG
"""

    payload, narrative = extract_payload_and_narrative(sample_raw)
    assert payload is not None
    assert payload["speech"] == "Đang tóm tắt các video nổi bật trên trang chủ YouTube"
    assert "Trên trang chủ YouTube" in narrative
    assert "Đầu Phòng TV" in narrative
    assert len(narrative) > 200

    # Test speech cleanup
    cleaned = clean_text_for_speech(narrative)
    assert "```" not in cleaned
    assert "JPG" not in cleaned
    assert "Đầu Phòng TV" in cleaned
    assert "Trên trang chủ YouTube" in cleaned

    print("test_narrative_extraction_and_speech_cleanup: PASSED")

def test_citation_stripping():
    from app.main import strip_citations, clean_text_for_speech, extract_payload_and_narrative

    # 1. Test varied cite badge forms
    sample1 = "Theo thông tin tìm kiếm [cite: 1], ngày mai trời có thể mưa [cite: 1, 2]."
    cleaned1 = strip_citations(sample1)
    assert "[cite:" not in cleaned1
    assert cleaned1 == "Theo thông tin tìm kiếm, ngày mai trời có thể mưa."

    sample2 = "Nội dung tóm tắt [cite: https://youtube.com/watch?v=123] [cite: 1-4] [CITE: 5] đã được đọc [cite]."
    cleaned2 = strip_citations(sample2)
    assert "[cite" not in cleaned2.lower()
    assert "đã được đọc." in cleaned2

    # 2. Test inside clean_text_for_speech
    sample_tts = "**Tiêu đề** [cite: 1]: Nội dung [cite: 2] rất chi tiết."
    cleaned_tts = clean_text_for_speech(sample_tts)
    assert "[cite" not in cleaned_tts
    assert "Tiêu đề: Nội dung rất chi tiết." in cleaned_tts

    # 3. Test inside extract_payload_and_narrative with JSON payload
    raw_with_cite = """```json
{
  "speech": "Đã tìm thấy thông tin [cite: 1, 3] cho bạn",
  "actions": [{"action": "none"}],
  "done": true
}
```
Dưới đây là chi tiết [cite: 2]: Video Đậu Phộng TV [cite: 4] có 1.5M views."""
    payload, narrative = extract_payload_and_narrative(raw_with_cite)
    assert payload is not None
    assert "[cite" not in payload["speech"]
    assert "[cite" not in narrative
    assert "Đã tìm thấy thông tin cho bạn" in payload["speech"]
    assert "Dưới đây là chi tiết: Video Đậu Phộng TV có 1.5M views." in narrative
    print("test_citation_stripping: PASSED")

def test_web_element_selection_and_matching():
    from app.accessibility import _match_element_score, accessibility_manager
    from app.prompt_templates import SYSTEM_GROUNDING_PROMPT

    # 1. Test prompt grounding includes web guidelines and select_element
    assert "select_element" in SYSTEM_GROUNDING_PROMPT
    assert "QUY TẮC THAO TÁC TRÊN GIAO DIỆN WEB" in SYSTEM_GROUNDING_PROMPT
    assert "ZERO CITATIONS" in SYSTEM_GROUNDING_PROMPT

    # 2. Test _match_element_score
    # Exact match
    score_exact = _match_element_score("Đậu Phộng TV", "Đậu Phộng TV")
    assert score_exact == 1000.0

    # Prefix match
    score_prefix = _match_element_score("Đậu Phộng TV", "Đậu Phộng TV - Tập 85")
    assert score_prefix > 700.0

    # Substring match
    score_sub = _match_element_score("Tập 85", "Đậu Phộng TV - Tập 85")
    assert score_sub > 400.0

    # Reject 1-letter noise nodes
    score_noise = _match_element_score("Đậu Phộng TV", "a")
    assert score_noise == 0.0

    # 3. Test element selection through cached element lookup
    accessibility_manager.cached_elements = [
        {"role": "Button", "name": "Reload this page", "pixel_x": 50, "pixel_y": 80, "x_percent": 0.02, "y_percent": 0.05},
        {"role": "Link", "name": "Đậu Phộng TV - Tập 85", "pixel_x": 450, "pixel_y": 320, "x_percent": 0.35, "y_percent": 0.25},
        {"role": "SearchField", "name": "Search", "pixel_x": 600, "pixel_y": 80, "x_percent": 0.50, "y_percent": 0.05},
    ]

    # Test select_element execution via os_controller
    res = os_controller.execute_action({
        "action": "select_element",
        "target": "Đậu Phộng TV"
    })
    assert res["success"] is True
    assert "Selected 'Đậu Phộng TV'" in res["details"] or "Accessibility Grounding" in res["details"]

    print("test_web_element_selection_and_matching: PASSED")

def test_logger_and_file_persistence():
    import os
    from app.logger import setup_logging, get_logger, read_recent_logs, clear_logs
    from app.config import LOG_FILE, LOGS_DIR

    assert LOGS_DIR.exists()
    logger = setup_logging()
    test_msg = "TEST_LOG_VERIFICATION_MESSAGE_12345"
    logger.info(test_msg)

    # Verify log content can be read
    recent = "".join(read_recent_logs(20))
    assert test_msg in recent
    print("test_logger_and_file_persistence: PASSED")

def test_daemon_utilities():
    import os
    from app.daemon import is_pid_running

    current_pid = os.getpid()
    assert is_pid_running(current_pid) is True
    assert is_pid_running(99999999) is False
    assert is_pid_running(-1) is False
    print("test_daemon_utilities: PASSED")

def test_browser_helper():
    from app.browser_helper import find_chrome_executable, is_chrome_running
    # On macOS or developer workstation, chrome should be detectable or handled gracefully
    exe = find_chrome_executable()
    # is_chrome_running should return boolean without throwing
    running = is_chrome_running()
    assert isinstance(running, bool)
    print("test_browser_helper: PASSED (chrome_exe:", exe, ", running:", running, ")")

def test_chat_mode_and_endpoints():
    import app.main as main_module
    from app.native_voice import NativeVoiceListener
    from app.gemini_service import gemini_service

    # 1. Test mode toggle & set_mode
    asyncio.run(main_module.set_mode("control", announce=False))
    assert main_module.current_mode == "control"

    mode1 = asyncio.run(main_module.set_mode("chat", announce=False))
    assert mode1 == "chat"
    assert main_module.current_mode == "chat"

    mode2 = asyncio.run(main_module.toggle_mode(announce=False))
    assert mode2 == "control"
    assert main_module.current_mode == "control"

    # 2. Test voice intents to switch modes
    asyncio.run(main_module.process_user_command("Bật chế độ trò chuyện", "vi-VN-HoaiMyNeural"))
    assert main_module.current_mode == "chat"

    asyncio.run(main_module.process_user_command("Chuyển sang chế độ điều khiển máy tính", "vi-VN-HoaiMyNeural"))
    assert main_module.current_mode == "control"

    # 3. Test REST endpoint handlers directly
    res_mode = asyncio.run(main_module.get_current_mode())
    assert res_mode["status"] == "ok"
    assert res_mode["mode"] == "control"

    res_set = asyncio.run(main_module.api_set_mode(main_module.SetModePayload(mode="chat", announce=False)))
    assert res_set["status"] == "ok"
    assert res_set["mode"] == "chat"
    assert main_module.current_mode == "chat"

    res_clear = asyncio.run(main_module.api_chat_clear())
    assert res_clear["status"] == "ok"

    # Reset mode back to control
    asyncio.run(main_module.api_set_mode(main_module.SetModePayload(mode="control", announce=False)))
    assert main_module.current_mode == "control"

    # 4. Test NativeVoiceListener with mode toggle callback
    toggled = []
    def dummy_toggle():
        toggled.append(True)

    listener = NativeVoiceListener(
        on_command_callback=lambda x: None,
        on_mode_toggle_callback=dummy_toggle
    )
    assert listener.on_mode_toggle is dummy_toggle
    listener.on_mode_toggle()
    assert len(toggled) == 1

    # 5. Test gemini_service conversation reset
    gemini_service.reset_conversation()

    # 6. Test api_command with text command (test fast-path without network)
    res_cmd = asyncio.run(main_module.api_command(main_module.CommandPayload(command="tắt tiếng processing", speak=False)))
    assert res_cmd["status"] == "ok"
    assert res_cmd["success"] is True
    assert "Đã tắt âm thanh" in res_cmd["speech"]

    # 7. Test api_chat with text command
    res_chat = asyncio.run(main_module.api_chat(main_module.ChatPayload(message="bật tiếng processing", speak=False)))
    assert res_chat["status"] == "ok"
    assert res_chat["success"] is True
    assert "Đã bật lại âm thanh" in res_chat["response"]

    print("test_chat_mode_and_endpoints: PASSED")

def test_system_ui_and_lifecycle_controls():
    import app.main as main_module
    from app.system_ui import show_desktop_notification
    from unittest.mock import AsyncMock, patch

    # 1. Test Desktop Notification
    notif_ok = show_desktop_notification("Luga Assist Test", "Kiểm tra thông báo")
    assert isinstance(notif_ok, bool)

    # 2. Test GET /api/system/status
    res_status = asyncio.run(main_module.api_system_status())
    assert res_status["status"] == "online"
    assert res_status["app_name"] == "Luga Assist"
    assert "mode" in res_status
    assert "screen_resolution" in res_status
    assert res_status["pid"] > 0

    # 3. Test Voice Intent: "kiểm tra trạng thái"
    res_cmd = asyncio.run(main_module.process_user_command("kiểm tra trạng thái", speak=False))
    assert res_cmd["success"] is True
    assert "Luga Assist đang hoạt động bình thường" in res_cmd["speech"]
    assert res_cmd["action_result"]["action"] == "system_status"

    # 4. Test Voice Intent: "đổi chế độ"
    prev_mode = main_module.current_mode
    res_toggle = asyncio.run(main_module.process_user_command("đổi chế độ", speak=False))
    assert res_toggle["success"] is True
    assert res_toggle["action_result"]["action"] == "toggle_mode"
    assert main_module.current_mode != prev_mode
    # Toggle back
    asyncio.run(main_module.set_mode(prev_mode, announce=False))

    # 5. Test Voice Intent: "tắt trợ lý" (with mocked shutdown to avoid terminating test runner)
    with patch("app.main.trigger_graceful_shutdown", new_callable=AsyncMock) as mock_shutdown:
        res_shut = asyncio.run(main_module.process_user_command("tắt trợ lý", speak=False))
        assert res_shut["success"] is True
        assert res_shut["action_result"]["action"] == "shutdown"
        assert "Đang tắt Luga Assist" in res_shut["speech"]
        mock_shutdown.assert_awaited_once()

    print("test_system_ui_and_lifecycle_controls: PASSED")

def test_spotlight_and_screen_capture_hooks():
    import app.main as main_module
    from unittest.mock import patch
    from app.screen_capture import screen_capturer
    from app.native_voice import NativeVoiceListener

    # 1. Test ScreenCapturer pre & post capture hooks (ensuring screen is clean for AI)
    events = []
    def dummy_pre():
        events.append("pre")
    def dummy_post():
        events.append("post")

    screen_capturer.register_pre_capture_hook(dummy_pre)
    screen_capturer.register_post_capture_hook(dummy_post)

    uri, size = screen_capturer.capture(with_grid=False)
    assert "pre" in events
    assert "post" in events
    assert events.index("pre") < events.index("post")

    # Clean up hooks
    screen_capturer.pre_capture_hooks.remove(dummy_pre)
    screen_capturer.post_capture_hooks.remove(dummy_post)

    # 2. Test Voice Intent: "mở chat nhanh" / "bật spotlight"
    res = asyncio.run(main_module.process_user_command("mở chat nhanh", speak=False))
    assert res["success"] is True
    assert "F7" in res["speech"]
    assert res["action_result"]["action"] == "spotlight_info"

    # 3. Test Web popup routes
    resp_popup = asyncio.run(main_module.serve_popup())
    assert resp_popup.status_code == 200
    assert "popup.html" in str(resp_popup.path)

    resp_popup_js = asyncio.run(main_module.serve_popup_js())
    assert resp_popup_js.status_code == 200
    assert "popup.js" in str(resp_popup_js.path)

    # 4. Test NativeVoiceListener with spotlight toggle callback
    toggled = []
    listener = NativeVoiceListener(
        on_spotlight_toggle_callback=lambda: toggled.append(True)
    )
    assert listener.on_spotlight_toggle is not None
    listener.on_spotlight_toggle()
    assert len(toggled) == 1

    # 5. Test Spotlight HUD API endpoints (show, hide, toggle)
    res_toggle_off = asyncio.run(main_module.api_spotlight_toggle())
    assert "status" in res_toggle_off
    res_show_off = asyncio.run(main_module.api_spotlight_show())
    assert "status" in res_show_off
    res_hide_off = asyncio.run(main_module.api_spotlight_hide())
    assert "status" in res_hide_off

    # Test with mock HUD
    class MockHUD:
        def __init__(self):
            self.shown = False
            self.hidden = False
            self.toggled = False
        def show(self): self.shown = True
        def hide(self): self.hidden = True
        def toggle(self): self.toggled = True

    mock_hud = MockHUD()
    with patch("app.spotlight_ui.get_spotlight_hud", return_value=mock_hud):
        res_show = asyncio.run(main_module.api_spotlight_show())
        assert res_show["status"] == "ok" and mock_hud.shown
        res_hide = asyncio.run(main_module.api_spotlight_hide())
        assert res_hide["status"] == "ok" and mock_hud.hidden
        res_tog = asyncio.run(main_module.api_spotlight_toggle())
        assert res_tog["status"] == "ok" and mock_hud.toggled

    print("test_spotlight_and_screen_capture_hooks: PASSED")

def test_audio_device_management():
    import app.main as main_module
    from app.audio_manager import audio_manager, AUDIO_CONFIG_FILE
    import asyncio

    # 1. Device enumeration
    devices = audio_manager.list_input_devices(force_refresh=True)
    assert isinstance(devices, list)
    if devices:
        for d in devices:
            assert "id" in d
            assert "name" in d
            assert "channels" in d
            assert "is_default" in d

    # 2. Get active device (should not be None or fail)
    dev_id, dev_name = audio_manager.get_active_device_index()
    assert dev_name is not None
    assert len(dev_name) > 0

    # 3. Setting active device
    real_devices = [d for d in devices if d.get("id", -1) >= 0]
    if real_devices:
        target = real_devices[0]["name"]
        res = audio_manager.set_active_device(target)
        assert res.get("name") == target
        saved_name = audio_manager.get_saved_device_name()
        assert saved_name == target

    # 4. Test API endpoints
    api_list = asyncio.run(main_module.api_audio_devices())
    assert api_list["status"] == "ok"
    assert "devices" in api_list
    assert "active_name" in api_list

    # 5. Test System status includes active_microphone
    status = asyncio.run(main_module.api_system_status())
    assert "active_microphone" in status
    assert status["active_microphone"] is not None

    # 6. Test set device endpoint
    if real_devices:
        payload = main_module.AudioDevicePayload(device=real_devices[0]["name"])
        api_set = asyncio.run(main_module.api_set_audio_device(payload))
        assert api_set["status"] == "ok"

    # 7. Restore active device to Default
    audio_manager.set_active_device("Default")

    print("test_audio_device_management: PASSED")

def test_window_control():
    from app.config import SCREENSHOT_MAX_WIDTH
    assert SCREENSHOT_MAX_WIDTH == 2560, f"Expected 2560, got {SCREENSHOT_MAX_WIDTH}"

    # Test window_control execution
    res1 = os_controller.execute_action({"action": "window_control", "command": "maximize"})
    assert "success" in res1
    assert "details" in res1
    assert "action" in res1 and res1["action"] == "window_control"

    # Test click action snapping to window maximize button
    res2 = os_controller.execute_action({"action": "click", "target": "phóng to cửa sổ"})
    assert "success" in res2
    assert "details" in res2

    print("test_window_control: PASSED")

def test_click_safety_and_coordinates():
    # 1. Missing target and no coordinates should report failure, not click center (0.5, 0.5)
    res_fail = os_controller.execute_action({"action": "click", "target": "completely_non_existent_element_xyz_12345"})
    assert res_fail["success"] is False
    assert "Không tìm thấy" in res_fail["details"]

    # 2. Explicit coordinates should succeed and calculate exact pixels
    expected_x, expected_y = os_controller.to_pixel_coords(0.25, 0.35)
    res_coord = os_controller.execute_action({"action": "click", "x_percent": 0.25, "y_percent": 0.35})
    assert res_coord["success"] is True
    assert f"({expected_x}, {expected_y})" in res_coord["details"]

    print("test_click_safety_and_coordinates: PASSED")

def test_accessibility_permissions_and_hotkey_supervisor():
    from app.accessibility import ensure_accessibility_permissions
    from app.native_voice import NativeVoiceListener
    import app.main as main_mod

    # 1. Test accessibility permission check returns boolean without error
    is_trusted = ensure_accessibility_permissions(prompt=False)
    assert isinstance(is_trusted, bool)

    # 2. Test listener lifecycle and supervisor state controls
    listener = NativeVoiceListener()
    assert listener._hotkeys_active is False
    assert listener._stop_hotkeys is False

    # Start and stop hotkeys safely
    started = listener._start_listener_internal()
    assert isinstance(started, bool)
    listener.stop_global_hotkeys()
    assert listener._stop_hotkeys is True
    assert listener._hotkey_listener is None

    # 3. Test Spotlight broadcast sync helper
    main_mod.send_spotlight_action_sync("toggle")
    main_mod.send_spotlight_action_sync("show")
    main_mod.send_spotlight_action_sync("hide")

    print("test_accessibility_permissions_and_hotkey_supervisor: PASSED")

def test_cancellation_and_emergency_stop():
    import app.main as main_mod
    from app.native_voice import NativeVoiceListener

    # 1. Test pipeline_abort_event and cancel_active_pipeline
    main_mod.pipeline_abort_event.clear()
    assert main_mod.pipeline_abort_event.is_set() is False

    main_mod.cancel_active_pipeline()
    assert main_mod.pipeline_abort_event.is_set() is True

    # 2. Test NativeVoiceListener cancellation
    cancelled_called = False
    def on_cancel_test():
        nonlocal cancelled_called
        cancelled_called = True

    voice_listener = NativeVoiceListener(on_cancel_callback=on_cancel_test)
    voice_listener.is_recording = True
    voice_listener.is_processing = True

    voice_listener.cancel_all()
    assert cancelled_called is True
    assert voice_listener.is_recording is False
    assert voice_listener.is_processing is False
    assert voice_listener._stop_requested is True
    assert voice_listener._discard_recording is True

    # 3. Test API /api/cancel endpoint directly
    res = asyncio.run(main_mod.api_cancel())
    assert res["status"] == "ok"
    assert "Đã ngắt" in res["message"]

    print("test_cancellation_and_emergency_stop: PASSED")

if __name__ == "__main__":
    test_prompt_generation()
    test_screen_capture_and_annotation()
    test_extract_json_payload()
    test_os_controller_to_pixel_coords()
    test_tts_generation()
    test_multi_action_sequence()
    test_sound_effects()
    test_accessibility_and_precision_focus()
    test_windows_cross_platform_compatibility()
    test_outcome_verification_prompt()
    test_element_scoring_and_email_action()
    test_system_control_action()
    test_bilingual_voice_selection_and_normalization()
    test_file_management_and_terminal_suite()
    test_narrative_extraction_and_speech_cleanup()
    test_citation_stripping()
    test_web_element_selection_and_matching()
    test_logger_and_file_persistence()
    test_daemon_utilities()
    test_browser_helper()
    test_chat_mode_and_endpoints()
    test_system_ui_and_lifecycle_controls()
    test_spotlight_and_screen_capture_hooks()
    test_audio_device_management()
    test_window_control()
    test_click_safety_and_coordinates()
    test_accessibility_permissions_and_hotkey_supervisor()
    test_cancellation_and_emergency_stop()
    print("\n🎉 ALL TESTS (INCLUDING EMERGENCY STOP & CANCELLATION) PASSED SUCCESSFULLY!")




