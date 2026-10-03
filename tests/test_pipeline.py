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
    print("\n🎉 ALL TESTS (INCLUDING SUMMARY NARRATIVE EXTRACTION) PASSED SUCCESSFULLY!")




