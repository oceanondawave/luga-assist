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

if __name__ == "__main__":
    test_prompt_generation()
    test_screen_capture_and_annotation()
    test_extract_json_payload()
    test_os_controller_to_pixel_coords()
    test_tts_generation()
    test_multi_action_sequence()
    print("\n🎉 ALL TESTS (INCLUDING MULTI-ACTION) PASSED SUCCESSFULLY!")
