"""
OS Controller module for cross-platform mouse, keyboard, and application automation.
"""
import sys
import time
import subprocess
from typing import Dict, Any, Optional
import pyautogui
import pyperclip

from app.config import (
    MOUSE_MOVE_DURATION,
    ACTION_SAFETY_PAUSE,
)
from app.accessibility import accessibility_manager

# Enable failsafe: moving mouse cursor to any corner will raise pyautogui.FailSafeException
pyautogui.FAILSAFE = True
pyautogui.PAUSE = ACTION_SAFETY_PAUSE

class OSController:
    def __init__(self):
        self.screen_width, self.screen_height = pyautogui.size()
        print(f"[OSController] Initialized screen size: {self.screen_width}x{self.screen_height}")

    def get_screen_size(self):
        self.screen_width, self.screen_height = pyautogui.size()
        return self.screen_width, self.screen_height

    def to_pixel_coords(self, x_percent: float, y_percent: float):
        """Convert normalized percentage (0.00 - 1.00) to logical screen pixels."""
        w, h = self.get_screen_size()
        # Clamp to bounds
        clamped_x = max(0.0, min(1.0, float(x_percent)))
        clamped_y = max(0.0, min(1.0, float(y_percent)))
        return int(w * clamped_x), int(h * clamped_y)

    def execute_action(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an automated action returned by Gemini Vision.
        Supports 100% precision Accessibility snapping, direct focus, and reliable typing.
        """
        action = action_data.get("action", "none").lower()
        result = {"success": True, "action": action, "details": ""}

        try:
            if action == "click":
                target = action_data.get("target") or action_data.get("field")
                if target and accessibility_manager.focus_element_by_name(target):
                    result["details"] = f"Clicked '{target}' via 100% Accessibility Grounding"
                else:
                    x, y = self.to_pixel_coords(action_data.get("x_percent", 0.5), action_data.get("y_percent", 0.5))
                    pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION)
                    pyautogui.click(x, y)
                    result["details"] = f"Clicked at ({x}, {y})"

            elif action == "double_click":
                x, y = self.to_pixel_coords(action_data.get("x_percent", 0.5), action_data.get("y_percent", 0.5))
                pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION)
                pyautogui.doubleClick(x, y)
                result["details"] = f"Double clicked at ({x}, {y})"

            elif action == "right_click":
                x, y = self.to_pixel_coords(action_data.get("x_percent", 0.5), action_data.get("y_percent", 0.5))
                pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION)
                pyautogui.rightClick(x, y)
                result["details"] = f"Right clicked at ({x}, {y})"

            elif action == "focus":
                target = action_data.get("target") or action_data.get("field", "")
                target_str = str(target).lower().strip()
                if target_str in ("next", "tab"):
                    self._press_key_combo("tab")
                    result["details"] = "Focused next input field (Tab)"
                elif target_str in ("prev", "previous", "shift+tab"):
                    self._press_key_combo("shift+tab")
                    result["details"] = "Focused previous input field (Shift+Tab)"
                elif target_str in ("address", "url", "search_bar"):
                    self._press_key_combo("cmd+l" if sys.platform == "darwin" else "ctrl+l")
                    result["details"] = "Focused address bar"
                elif target_str in ("find", "in_page_search"):
                    self._press_key_combo("cmd+f" if sys.platform == "darwin" else "ctrl+f")
                    result["details"] = "Focused find bar (Cmd+F)"
                else:
                    ok = accessibility_manager.focus_element_by_name(target_str)
                    if ok:
                        result["details"] = f"Focused '{target_str}' via 100% Accessibility"
                    elif "x_percent" in action_data and "y_percent" in action_data:
                        x, y = self.to_pixel_coords(action_data["x_percent"], action_data["y_percent"])
                        pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION)
                        pyautogui.click(x, y)
                        result["details"] = f"Focused at ({x}, {y})"
                    else:
                        result["details"] = f"Could not focus '{target_str}'"

            elif action in ("send_email", "compose_email"):
                to_addr = action_data.get("to") or action_data.get("recipient", "")
                subject = action_data.get("subject", "")
                body = action_data.get("body", "")

                details = []

                # Ensure compose window / pane is open
                if not accessibility_manager.is_compose_window_active():
                    new_btn_ok = accessibility_manager.focus_element_by_name("new mail")
                    if not new_btn_ok:
                        self._press_key_combo("cmd+n" if sys.platform == "darwin" else "ctrl+n")
                    time.sleep(0.6)

                # 1. Focus To field
                focused_to = accessibility_manager.focus_element_by_name("to")
                time.sleep(0.12)

                # 2. Type recipient and commit contact chip
                if to_addr:
                    self._press_key_combo("cmd+a" if sys.platform == "darwin" else "ctrl+a")
                    time.sleep(0.04)
                    self._paste_unicode_text(to_addr)
                    time.sleep(0.1)
                    self._press_key_combo("enter")
                    time.sleep(0.15)
                    details.append(f"To: {to_addr}")

                # 3. Focus Subject field
                focused_subject = accessibility_manager.focus_element_by_name("subject")
                if not focused_subject:
                    self._press_key_combo("tab")
                    time.sleep(0.1)

                if subject:
                    self._press_key_combo("cmd+a" if sys.platform == "darwin" else "ctrl+a")
                    time.sleep(0.04)
                    self._paste_unicode_text(subject)
                    time.sleep(0.1)
                    details.append(f"Subject: {subject}")

                # 4. Focus Body field (Tab from Subject moves cleanly to Body)
                focused_body = accessibility_manager.focus_element_by_name("body")
                if not focused_body:
                    self._press_key_combo("tab")
                    time.sleep(0.1)

                if body:
                    self._press_key_combo("cmd+a" if sys.platform == "darwin" else "ctrl+a")
                    time.sleep(0.04)
                    self._paste_unicode_text(body)
                    time.sleep(0.15)
                    details.append(f"Body: {body}")

                # 5. Send Email: try clicking Send button or pressing send shortcut
                send_clicked = accessibility_manager.focus_element_by_name("send")
                if send_clicked:
                    details.append("Clicked Send button")
                else:
                    send_key = "cmd+return" if sys.platform == "darwin" else "ctrl+enter"
                    self._press_key_combo(send_key)
                    details.append(f"Pressed {send_key}")

                result["details"] = " | ".join(details)

            elif action == "type":
                text = action_data.get("text", "")
                if text:
                    target = action_data.get("target") or action_data.get("field")
                    focused = False
                    if target:
                        focused = accessibility_manager.focus_element_by_name(target)
                        if focused:
                            time.sleep(0.1)

                    if not focused and "x_percent" in action_data and "y_percent" in action_data:
                        x, y = self.to_pixel_coords(action_data["x_percent"], action_data["y_percent"])
                        pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION)
                        pyautogui.click(x, y)
                        time.sleep(0.12)
                        focused = True

                    # Clear existing content if requested (default True for clean input)
                    clear_first = action_data.get("clear_first", True)
                    if clear_first:
                        self._press_key_combo("cmd+a" if sys.platform == "darwin" else "ctrl+a")
                        time.sleep(0.04)

                    # Paste Unicode text reliably without IME interference
                    self._paste_unicode_text(text)

                    # If typing recipient, auto-commit with enter so contact chip resolves
                    target_str = str(target or "").lower().strip()
                    if any(k in target_str for k in ("to", "recipients", "người nhận", "đến")):
                        time.sleep(0.08)
                        self._press_key_combo("enter")

                    result["details"] = f"Typed: {text}"

            elif action == "press":
                key_combo = action_data.get("key", "enter").lower()
                self._press_key_combo(key_combo)
                result["details"] = f"Pressed: {key_combo}"

            elif action == "scroll":
                direction = action_data.get("direction", "down").lower()
                amount = int(action_data.get("amount", 5))
                clicks = -amount if direction == "down" else amount
                if "x_percent" in action_data and "y_percent" in action_data:
                    x, y = self.to_pixel_coords(action_data["x_percent"], action_data["y_percent"])
                    pyautogui.moveTo(x, y)
                pyautogui.scroll(clicks * 100)
                result["details"] = f"Scrolled {direction} by {amount}"

            elif action in ("system_control", "system", "sleep", "mute", "unmute", "volume_up", "volume_down", "lock"):
                cmd_type = action_data.get("command") or action_data.get("type") or action
                cmd_clean = str(cmd_type).lower().strip()

                if cmd_clean in ("sleep", "ngủ"):
                    if sys.platform == "darwin":
                        subprocess.Popen(["osascript", "-e", 'tell application "System Events" to sleep'])
                    elif sys.platform.startswith("win"):
                        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
                    result["details"] = "Put computer into Sleep mode"

                elif cmd_clean in ("mute", "tắt tiếng", "tắt âm"):
                    if sys.platform == "darwin":
                        subprocess.run(["osascript", "-e", "set volume output muted true"], capture_output=True)
                    else:
                        pyautogui.press("volumemute")
                    result["details"] = "Muted system audio"

                elif cmd_clean in ("unmute", "bật tiếng", "bật âm"):
                    if sys.platform == "darwin":
                        subprocess.run(["osascript", "-e", "set volume output muted false"], capture_output=True)
                    else:
                        pyautogui.press("volumemute")
                    result["details"] = "Unmuted system audio"

                elif cmd_clean in ("volume_up", "tăng âm", "tăng âm lượng"):
                    if sys.platform == "darwin":
                        subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 10)"], capture_output=True)
                    else:
                        pyautogui.press("volumeup")
                    result["details"] = "Increased volume"

                elif cmd_clean in ("volume_down", "giảm âm", "giảm âm lượng"):
                    if sys.platform == "darwin":
                        subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 10)"], capture_output=True)
                    else:
                        pyautogui.press("volumedown")
                    result["details"] = "Decreased volume"

                elif cmd_clean in ("lock", "khóa màn hình"):
                    if sys.platform == "darwin":
                        subprocess.Popen(["osascript", "-e", 'tell application "System Events" to key code 12 using {control down, command down}'])
                    elif sys.platform.startswith("win"):
                        subprocess.Popen(["rundll32.exe", "user32.dll,LockWorkStation"])
                    result["details"] = "Locked computer screen"

            elif action == "launch_app":
                app_name = action_data.get("app_name", "").strip()
                if app_name:
                    self._launch_app(app_name)
                    result["details"] = f"Launched application: {app_name}"

            elif action == "wait":
                delay = float(action_data.get("delay", 0.5))
                time.sleep(delay)
                result["details"] = f"Waited for {delay}s"

            elif action in ("none", "read_screen"):
                result["details"] = "No mouse/keyboard action needed"

            else:
                result["success"] = False
                result["details"] = f"Unknown action: {action}"

        except Exception as e:
            result["success"] = False
            result["details"] = f"Error during action execution: {str(e)}"
            print(f"[OSController] Action error: {e}")

        return result

    def execute_action_sequence(self, actions_list: list) -> Dict[str, Any]:
        """
        Execute multiple actions sequentially in order.
        Supports complex multi-step instructions (e.g. click search bar -> type text -> press enter).
        """
        if not actions_list:
            return {"success": True, "action": "none", "details": "No actions to execute"}

        results = []
        overall_success = True

        for i, act in enumerate(actions_list):
            if not isinstance(act, dict):
                continue

            print(f"[OSController] Thực thi bước {i+1}/{len(actions_list)}: {act.get('action')}")
            res = self.execute_action(act)
            results.append(res)

            if not res.get("success", False):
                overall_success = False

            # Pause between sequential steps
            step_delay = float(act.get("delay", ACTION_SAFETY_PAUSE))
            time.sleep(max(0.04, step_delay))

        summary_details = " ➔ ".join([r.get("details", "") for r in results if r.get("details")])
        return {
            "success": overall_success,
            "action": "sequence",
            "count": len(actions_list),
            "details": summary_details,
            "results": results,
        }

    def _paste_unicode_text(self, text: str):
        """
        Copy text to clipboard and simulate Cmd+V (macOS) or Ctrl+V (Windows/Linux)
        to preserve full Vietnamese accents and diacritics without dropping modifiers.
        """
        pyperclip.copy(text)
        time.sleep(0.05)
        if sys.platform == "darwin":
            try:
                # AppleScript keystroke guarantees Command modifier is held (prevents typing literal 'v')
                subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
                    capture_output=True,
                    check=True
                )
            except Exception:
                pyautogui.hotkey("command", "v")
        elif sys.platform.startswith("win"):
            # Windows: Cleanly hold Ctrl, press V, and release to avoid IME drops
            pyautogui.keyDown("ctrl")
            time.sleep(0.02)
            pyautogui.press("v")
            time.sleep(0.02)
            pyautogui.keyUp("ctrl")
        else:
            pyautogui.hotkey("ctrl", "v")
        time.sleep(0.05)

    def _press_key_combo(self, combo: str):
        """Parse and press single keys or combinations like 'cmd+space', 'cmd+return', 'tab'."""
        combo_clean = combo.strip().lower()

        if sys.platform == "darwin":
            parts = [p.strip() for p in combo_clean.split("+")]
            modifiers = []
            key = ""
            for p in parts:
                if p in ("cmd", "command"):
                    modifiers.append("command down")
                elif p in ("ctrl", "control"):
                    modifiers.append("control down")
                elif p in ("alt", "option"):
                    modifiers.append("option down")
                elif p in ("shift",):
                    modifiers.append("shift down")
                else:
                    key = p

            mod_str = f" using {{{', '.join(modifiers)}}}" if modifiers else ""
            cmd = ""
            if key in ("enter", "return"):
                cmd = f'tell application "System Events" to key code 36{mod_str}'
            elif key == "tab":
                cmd = f'tell application "System Events" to key code 48{mod_str}'
            elif key == "space":
                cmd = f'tell application "System Events" to key code 49{mod_str}'
            elif key in ("escape", "esc"):
                cmd = f'tell application "System Events" to key code 53{mod_str}'
            elif key in ("backspace", "delete"):
                cmd = f'tell application "System Events" to key code 51{mod_str}'
            elif len(key) == 1:
                cmd = f'tell application "System Events" to keystroke "{key}"{mod_str}'

            if cmd:
                try:
                    subprocess.run(["osascript", "-e", cmd], capture_output=True, check=True)
                    return
                except Exception:
                    pass

        elif sys.platform.startswith("win"):
            parts = [p.strip() for p in combo_clean.split("+")]
            # Automatically translate macOS shortcuts to Windows equivalents
            normalized_parts = []
            for p in parts:
                if p in ("cmd", "command"):
                    normalized_parts.append("ctrl")
                elif p in ("return",):
                    normalized_parts.append("enter")
                elif p in ("esc",):
                    normalized_parts.append("escape")
                else:
                    normalized_parts.append(p)

            # Shortcut: cmd+space -> win (Windows Start)
            if normalized_parts == ["ctrl", "space"] and ("cmd" in combo_clean or "command" in combo_clean):
                pyautogui.press("win")
                return

            # Press modifiers cleanly without dropping
            modifiers = [p for p in normalized_parts if p in ("ctrl", "alt", "shift", "win")]
            main_keys = [p for p in normalized_parts if p not in ("ctrl", "alt", "shift", "win")]

            for m in modifiers:
                pyautogui.keyDown(m)
            time.sleep(0.02)
            for k in main_keys:
                pyautogui.press(k)
            time.sleep(0.02)
            for m in reversed(modifiers):
                pyautogui.keyUp(m)
            return

        # Fallback to pyautogui for Linux/other
        keys = [k.strip() for k in combo_clean.split("+")]
        mapped_keys = []
        for k in keys:
            if k in ("cmd", "command", "win", "windows", "super"):
                mapped_keys.append("win")
            elif k in ("ctrl", "control"):
                mapped_keys.append("ctrl")
            elif k in ("alt", "option"):
                mapped_keys.append("alt")
            elif k in ("return",):
                mapped_keys.append("enter")
            elif k in ("esc",):
                mapped_keys.append("escape")
            else:
                mapped_keys.append(k)

        if len(mapped_keys) == 1:
            pyautogui.press(mapped_keys[0])
        else:
            pyautogui.hotkey(*mapped_keys)

    def _launch_app(self, app_name: str):
        """Open application natively across operating systems."""
        if sys.platform == "darwin":  # macOS
            try:
                subprocess.Popen(["open", "-a", app_name])
            except Exception:
                # Fallback: Trigger Spotlight
                pyautogui.hotkey("command", "space")
                time.sleep(0.3)
                self._paste_unicode_text(app_name)
                time.sleep(0.2)
                pyautogui.press("enter")
        elif sys.platform.startswith("win"):  # Windows
            try:
                subprocess.Popen(["cmd", "/c", "start", "", app_name], shell=True)
            except Exception:
                pyautogui.press("win")
                time.sleep(0.3)
                self._paste_unicode_text(app_name)
                time.sleep(0.2)
                pyautogui.press("enter")
        else:  # Linux
            subprocess.Popen([app_name])

os_controller = OSController()
