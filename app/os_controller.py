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
from app.file_and_terminal import file_and_terminal

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
        return int(round(w * clamped_x)), int(round(h * clamped_y))

    def execute_action(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an automated action returned by Gemini Vision.
        Supports 100% precision Accessibility snapping, direct focus, and reliable typing.
        """
        action = action_data.get("action", "none").lower()
        result = {"success": True, "action": action, "details": ""}

        try:
            if action in ("click", "select_element", "choose_element", "click_element", "select"):
                target = (
                    action_data.get("target")
                    or action_data.get("field")
                    or action_data.get("element")
                    or action_data.get("name")
                )
                target_str = str(target or "").lower().strip()
                # Check if target is a window control button (maximize, zoom, minimize, close)
                if any(k in target_str for k in ("maximize", "phóng to", "zoom", "nút xanh", "green button")):
                    w_res = self.window_control("maximize")
                    result["details"] = w_res["details"] or "Clicked Maximize/Zoom window button"
                elif any(k in target_str for k in ("minimize", "thu nhỏ", "yellow button", "nút vàng")):
                    w_res = self.window_control("minimize")
                    result["details"] = w_res["details"] or "Clicked Minimize window button"
                elif any(k in target_str for k in ("close window", "đóng cửa sổ", "red button", "nút đỏ")):
                    w_res = self.window_control("close")
                    result["details"] = w_res["details"] or "Clicked Close window button"
                elif target and accessibility_manager.focus_element_by_name(target):
                    result["details"] = f"Selected '{target}' via 100% Accessibility Grounding"
                elif "x_percent" in action_data and "y_percent" in action_data:
                    x, y = self.to_pixel_coords(action_data["x_percent"], action_data["y_percent"])
                    pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION)
                    pyautogui.click(x, y)
                    target_info = f" '{target}'" if target else ""
                    result["details"] = f"Clicked{target_info} at ({x}, {y})"
                else:
                    # Target not found in AX and no visual coordinates provided
                    result["success"] = False
                    result["details"] = f"Không tìm thấy phần tử '{target or 'unknown'}' qua Accessibility và thiếu tọa độ (x_percent, y_percent)"
                    print(f"[OSController] ⚠️ CẢNH BÁO: Không tìm thấy phần tử '{target}' và AI không cung cấp tọa độ x_percent, y_percent để click!")

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

            elif action in ("focus", "focus_element"):
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

            elif action in ("window_control", "manage_window", "window"):
                cmd = action_data.get("command") or action_data.get("type") or "maximize"
                app_name = action_data.get("app_name") or action_data.get("target", "")
                w_res = self.window_control(command=cmd, app_name=app_name)
                result["success"] = w_res["success"]
                result["details"] = w_res["details"]

            elif action == "launch_app":
                app_name = action_data.get("app_name", "").strip()
                if app_name:
                    self._launch_app(app_name)
                    result["details"] = f"Launched application: {app_name}"

            elif action == "wait":
                delay = float(action_data.get("delay", 0.5))
                time.sleep(delay)
                result["details"] = f"Waited for {delay}s"

            elif action in ("terminal_command", "terminal", "run_terminal", "bash", "cmd", "powershell", "powershell_command"):
                cmd = action_data.get("command") or action_data.get("cmd", "")
                cwd = action_data.get("cwd")
                open_visible = bool(action_data.get("open_visible", False))
                shell_type = action_data.get("shell_type")
                if action in ("powershell", "powershell_command"):
                    shell_type = "powershell"
                elif action == "cmd":
                    shell_type = "cmd"

                t_res = file_and_terminal.execute_terminal(
                    command=cmd, cwd=cwd, open_visible=open_visible, shell_type=shell_type
                )
                result["success"] = t_res["success"]
                result["details"] = t_res["details"]
                if t_res.get("speech_result"):
                    result["speech_result"] = t_res["speech_result"]
                if "stdout" in t_res:
                    result["stdout"] = t_res["stdout"]

            elif action in ("find_files", "find_file", "search_file", "search_files"):
                query = action_data.get("query") or action_data.get("name") or action_data.get("pattern", "")
                location = action_data.get("location") or action_data.get("dir")
                limit = int(action_data.get("limit", 10))
                open_first = bool(action_data.get("open_first", False))

                f_res = file_and_terminal.find_files(query=query, location=location, limit=limit, open_first=open_first)
                result["success"] = f_res["success"]
                result["details"] = f_res["details"]
                if f_res.get("speech_result"):
                    result["speech_result"] = f_res["speech_result"]
                result["files"] = f_res.get("files", [])

            elif action in ("open_file", "open", "open_folder"):
                path_str = action_data.get("path") or action_data.get("file") or action_data.get("target", "")
                o_res = file_and_terminal.open_file(path_str=str(path_str))
                result["success"] = o_res["success"]
                result["details"] = o_res["details"]
                if o_res.get("speech_result"):
                    result["speech_result"] = o_res["speech_result"]

            elif action in ("list_files", "list_dir", "dir", "ls"):
                path_str = action_data.get("path") or action_data.get("dir") or action_data.get("folder")
                limit = int(action_data.get("limit", 20))
                l_res = file_and_terminal.list_files(path_str=path_str, limit=limit)
                result["success"] = l_res["success"]
                result["details"] = l_res["details"]
                if l_res.get("speech_result"):
                    result["speech_result"] = l_res["speech_result"]

            elif action in ("read_file", "cat", "view_file"):
                path_str = action_data.get("path") or action_data.get("file", "")
                max_lines = int(action_data.get("max_lines", 40))
                r_res = file_and_terminal.read_file(path_str=str(path_str), max_lines=max_lines)
                result["success"] = r_res["success"]
                result["details"] = r_res["details"]
                if r_res.get("speech_result"):
                    result["speech_result"] = r_res["speech_result"]
                if "content" in r_res:
                    result["content"] = r_res["content"]

            elif action in ("create_file", "write_file", "new_file"):
                path_str = action_data.get("path") or action_data.get("file", "")
                content = action_data.get("content") or action_data.get("text", "")
                c_res = file_and_terminal.create_file(path_str=str(path_str), content=content)
                result["success"] = c_res["success"]
                result["details"] = c_res["details"]
                if c_res.get("speech_result"):
                    result["speech_result"] = c_res["speech_result"]

            elif action in ("delete_file", "remove_file", "trash_file"):
                path_str = action_data.get("path") or action_data.get("file", "")
                safe_trash = bool(action_data.get("safe_trash", True))
                d_res = file_and_terminal.delete_file(path_str=str(path_str), safe_trash=safe_trash)
                result["success"] = d_res["success"]
                result["details"] = d_res["details"]
                if d_res.get("speech_result"):
                    result["speech_result"] = d_res["speech_result"]

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
        summary_speech = " ".join([r.get("speech_result", "") for r in results if r.get("speech_result")])
        return {
            "success": overall_success,
            "action": "sequence",
            "count": len(actions_list),
            "details": summary_details,
            "speech_result": summary_speech,
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

    def window_control(self, command: str, app_name: str = "") -> Dict[str, Any]:
        """
        Manage window states natively (maximize, zoom, minimize, close, fullscreen, restore).
        Uses macOS Accessibility / AppleScript on macOS, and native Windows shortcuts on Windows.
        """
        cmd = str(command or "maximize").lower().strip()
        details = ""
        success = False

        if sys.platform == "darwin":
            try:
                import AppKit
                import ApplicationServices
                ws = AppKit.NSWorkspace.sharedWorkspace()
                target_app = None
                if app_name:
                    for app in ws.runningApplications():
                        if app.localizedName() and app.localizedName().lower() == app_name.lower():
                            target_app = app
                            break
                if not target_app:
                    target_app = ws.frontmostApplication()

                if target_app:
                    pid = target_app.processIdentifier()
                    app_elem = ApplicationServices.AXUIElementCreateApplication(pid)
                    err, windows = ApplicationServices.AXUIElementCopyAttributeValue(app_elem, "AXWindows", None)
                    if windows and len(windows) > 0:
                        front_win = windows[0]
                        # Map command to button attribute
                        btn_attr_map = {
                            "maximize": ["AXZoomButton", "AXFullScreenButton"],
                            "zoom": ["AXZoomButton", "AXFullScreenButton"],
                            "phóng to": ["AXZoomButton", "AXFullScreenButton"],
                            "fullscreen": ["AXFullScreenButton", "AXZoomButton"],
                            "toàn màn hình": ["AXFullScreenButton", "AXZoomButton"],
                            "minimize": ["AXMinimizeButton"],
                            "thu nhỏ": ["AXMinimizeButton"],
                            "close": ["AXCloseButton"],
                            "đóng": ["AXCloseButton"],
                        }

                        attrs_to_try = btn_attr_map.get(cmd, ["AXZoomButton", "AXFullScreenButton"])
                        target_btn = None
                        for attr in attrs_to_try:
                            err_b, btn = ApplicationServices.AXUIElementCopyAttributeValue(front_win, attr, None)
                            if err_b == 0 and btn:
                                target_btn = btn
                                break

                        if target_btn:
                            # 1. Move cursor visibly to button so user sees physical mouse feedback
                            err_pos, pos_val = ApplicationServices.AXUIElementCopyAttributeValue(target_btn, "AXPosition", None)
                            err_sz, size_val = ApplicationServices.AXUIElementCopyAttributeValue(target_btn, "AXSize", None)
                            if err_pos == 0 and err_sz == 0 and pos_val and size_val:
                                ok_p, pt = ApplicationServices.AXValueGetValue(pos_val, ApplicationServices.kAXValueCGPointType, None)
                                ok_s, sz = ApplicationServices.AXValueGetValue(size_val, ApplicationServices.kAXValueCGSizeType, None)
                                if ok_p and ok_s:
                                    cx = int(pt.x + sz.width / 2.0)
                                    cy = int(pt.y + sz.height / 2.0)
                                    pyautogui.moveTo(cx, cy, duration=MOUSE_MOVE_DURATION)
                                    pyautogui.click(cx, cy)
                            # 2. Also perform native AXPress for 100% guarantee
                            ApplicationServices.AXUIElementPerformAction(target_btn, "AXPress")
                            success = True
                            details = f"Executed '{cmd}' on window of '{target_app.localizedName()}' via Accessibility"
            except Exception as e:
                print(f"[OSController] Window control AX notice: {e}")

            # Fallback for macOS if AX didn't succeed
            if not success:
                if cmd in ("maximize", "zoom", "phóng to"):
                    as_code = '''
                    tell application "System Events"
                        set frontApp to first application process whose frontmost is true
                        tell frontApp
                            try
                                set frontWin to front window
                                set value of attribute "AXZoom" of frontWin to true
                            end try
                        end tell
                    end tell
                    '''
                    res = subprocess.run(["osascript", "-e", as_code], capture_output=True, text=True)
                    success = (res.returncode == 0)
                    details = "Maximized window via AppleScript AXZoom"
                elif cmd in ("minimize", "thu nhỏ"):
                    pyautogui.hotkey("command", "m")
                    success = True
                    details = "Minimized window via Cmd+M"
                elif cmd in ("close", "đóng"):
                    pyautogui.hotkey("command", "w")
                    success = True
                    details = "Closed window via Cmd+W"
                elif cmd in ("fullscreen", "toàn màn hình"):
                    pyautogui.hotkey("ctrl", "command", "f")
                    success = True
                    details = "Toggled fullscreen via Ctrl+Cmd+F"

        elif sys.platform.startswith("win"):
            if cmd in ("maximize", "zoom", "phóng to", "fullscreen"):
                pyautogui.hotkey("win", "up")
                success = True
                details = "Maximized window (Win+Up)"
            elif cmd in ("minimize", "thu nhỏ"):
                pyautogui.hotkey("win", "down")
                success = True
                details = "Minimized window (Win+Down)"
            elif cmd in ("close", "đóng"):
                pyautogui.hotkey("alt", "f4")
                success = True
                details = "Closed window (Alt+F4)"
            elif cmd in ("restore", "khôi phục"):
                pyautogui.hotkey("win", "down")
                success = True
                details = "Restored window size (Win+Down)"

        return {"success": success, "details": details}

os_controller = OSController()
