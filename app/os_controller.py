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
from app.accessibility import accessibility_manager, enable_windows_dpi_awareness
from app.file_and_terminal import file_and_terminal

# Ensure Windows treats process as DPI aware so pyautogui and screen coordinates match 1:1
enable_windows_dpi_awareness()

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

    def _native_click(self, x: int, y: int, button: str = "left", click_count: int = 1):
        """
        Rock-solid physical click across macOS and Windows.
        Ensures target window is activated, cursor is physically moved to (x, y),
        and click events are dispatched cleanly at the exact coordinates without any relative offsets.
        """
        w, h = self.get_screen_size()
        # Clamp coordinates to stay within screen boundaries and avoid (0,0) failsafe
        x = max(2, min(w - 2, int(x)))
        y = max(2, min(h - 2, int(y)))

        # 1. Smoothly move cursor so user visually sees movement to target
        try:
            pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION)
        except Exception:
            pass

        # 2. Windows native click pipeline
        if sys.platform.startswith("win"):
            try:
                import ctypes
                import ctypes.wintypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                # Structure for WindowFromPoint
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

                user32.WindowFromPoint.argtypes = [POINT]
                user32.WindowFromPoint.restype = ctypes.c_void_p

                # Activate window under cursor if not active so click is immediately processed
                pt = POINT(x, y)
                hwnd = user32.WindowFromPoint(pt)
                if hwnd:
                    root_hwnd = user32.GetAncestor(hwnd, 2)  # GA_ROOT = 2
                    cur_fore = user32.GetForegroundWindow()
                    if root_hwnd and root_hwnd != cur_fore:
                        try:
                            # Safely attach thread input to grant foreground activation
                            fg_thread = user32.GetWindowThreadProcessId(cur_fore, None) if cur_fore else 0
                            cur_thread = kernel32.GetCurrentThreadId()
                            attached = False
                            if fg_thread and fg_thread != cur_thread:
                                attached = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))
                            try:
                                if user32.IsIconic(root_hwnd):
                                    user32.ShowWindow(root_hwnd, 9)  # SW_RESTORE only if minimized
                                user32.BringWindowToTop(root_hwnd)
                                user32.SetForegroundWindow(root_hwnd)
                                user32.SetFocus(root_hwnd)
                            finally:
                                if attached:
                                    user32.AttachThreadInput(cur_thread, fg_thread, False)
                            time.sleep(0.05)
                        except Exception:
                            pass

                # Firmly set physical cursor position at (x, y)
                user32.SetCursorPos(x, y)
                time.sleep(0.03)

                # Win32 mouse_event: when dx=0 and dy=0, Windows dispatches the event
                # EXACTLY at current cursor position with ZERO relative shift!
                MOUSEEVENTF_LEFTDOWN = 0x0002
                MOUSEEVENTF_LEFTUP = 0x0004
                MOUSEEVENTF_RIGHTDOWN = 0x0008
                MOUSEEVENTF_RIGHTUP = 0x0010

                if button == "right":
                    user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
                    time.sleep(0.05)
                    user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                elif click_count == 2:
                    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.04)
                    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    time.sleep(0.08)
                    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.04)
                    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                else:
                    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.05)
                    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

                print(f"[OSController] ⚡ Đã phát sự kiện click vật lý Win32 tại ({x}, {y}) [button={button}]")
                time.sleep(0.04)
                return
            except Exception as win_err:
                print(f"[OSController] Windows native click fallback due to: {win_err}")

        # 3. Universal Fallback
        try:
            btn = "right" if button == "right" else "left"
            pyautogui.click(x=x, y=y, clicks=click_count, button=btn)
        except Exception as e:
            print(f"[OSController] Click fallback error: {e}")

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
                else:
                    x_pct = action_data.get("x_percent") if action_data.get("x_percent") is not None else action_data.get("x")
                    y_pct = action_data.get("y_percent") if action_data.get("y_percent") is not None else action_data.get("y")
                    if x_pct is None and "point" in action_data and isinstance(action_data["point"], (list, tuple)) and len(action_data["point"]) >= 2:
                        x_pct, y_pct = action_data["point"][0], action_data["point"][1]
                    if x_pct is None and "coordinates" in action_data and isinstance(action_data["coordinates"], dict):
                        x_pct = action_data["coordinates"].get("x")
                        y_pct = action_data["coordinates"].get("y")

                    if x_pct is not None and y_pct is not None:
                        try:
                            fx, fy = float(x_pct), float(y_pct)
                            # Handle case where AI gave pixel coords directly (> 1.0)
                            if fx > 1.0 or fy > 1.0:
                                x, y = int(round(fx)), int(round(fy))
                            else:
                                x, y = self.to_pixel_coords(fx, fy)

                            snapped = accessibility_manager.snap_coordinates(x, y, target=target_str)
                            if snapped:
                                x, y = snapped
                                print(f"[OSController] 🎯 Khóa chính xác tâm phần tử UI: ({x}, {y})")
                            else:
                                print(f"[OSController] 🖱️ Nhấp chuột tại tọa độ trực quan: ({x}, {y})")
                            self._native_click(x, y, button="left", click_count=1)
                            target_info = f" '{target}'" if target else ""
                            result["details"] = f"Clicked{target_info} at ({x}, {y})"
                        except Exception as click_err:
                            result["success"] = False
                            result["details"] = f"Lỗi khi thực hiện click: {click_err}"
                            print(f"[OSController] Lỗi click: {click_err}")
                    elif target:
                        # Attempt to find by name in cached elements
                        clicked_via_ax = accessibility_manager.focus_element_by_name(target)
                        if clicked_via_ax:
                            result["details"] = f"Selected '{target}' via 100% Accessibility Grounding"
                        else:
                            # Fuzzy search in cached elements directly
                            matched_elem = None
                            for el in accessibility_manager.cached_elements:
                                el_name = el.get("name", "").lower()
                                if target_str in el_name or el_name in target_str:
                                    matched_elem = el
                                    break
                            if matched_elem:
                                px = matched_elem["pixel_x"]
                                py = matched_elem["pixel_y"]
                                print(f"[OSController] 🎯 Khớp tên phần tử '{matched_elem['name']}' tại ({px}, {py})")
                                self._native_click(px, py, button="left", click_count=1)
                                result["details"] = f"Clicked '{matched_elem['name']}' at ({px}, {py})"
                            else:
                                result["success"] = False
                                result["details"] = f"Không tìm thấy phần tử '{target}' và AI không cung cấp tọa độ x_percent, y_percent để click"
                                print(f"[OSController] ⚠️ CẢNH BÁO: Không tìm thấy phần tử '{target}' và thiếu tọa độ click!")

            elif action == "double_click":
                x, y = self.to_pixel_coords(action_data.get("x_percent", 0.5), action_data.get("y_percent", 0.5))
                self._native_click(x, y, button="left", click_count=2)
                result["details"] = f"Double clicked at ({x}, {y})"

            elif action == "right_click":
                x, y = self.to_pixel_coords(action_data.get("x_percent", 0.5), action_data.get("y_percent", 0.5))
                self._native_click(x, y, button="right", click_count=1)
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
                    self._press_key_combo("ctrl+l")
                    result["details"] = "Focused address bar"
                elif target_str in ("find", "in_page_search"):
                    self._press_key_combo("ctrl+f")
                    result["details"] = "Focused find bar (Ctrl+F)"
                else:
                    ok = accessibility_manager.focus_element_by_name(target_str)
                    if ok:
                        result["details"] = f"Focused '{target_str}' via 100% Accessibility"
                    elif "x_percent" in action_data and "y_percent" in action_data:
                        x, y = self.to_pixel_coords(action_data["x_percent"], action_data["y_percent"])
                        self._native_click(x, y, button="left", click_count=1)
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
                        self._press_key_combo("ctrl+n")
                    time.sleep(0.6)

                # 1. Focus To field
                focused_to = accessibility_manager.focus_element_by_name("to")
                time.sleep(0.12)

                # 2. Type recipient and commit contact chip
                if to_addr:
                    self._press_key_combo("ctrl+a")
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
                    self._press_key_combo("ctrl+a")
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
                    self._press_key_combo("ctrl+a")
                    time.sleep(0.04)
                    self._paste_unicode_text(body)
                    time.sleep(0.15)
                    details.append(f"Body: {body}")

                # 5. Send Email: try clicking Send button or pressing send shortcut
                send_clicked = accessibility_manager.focus_element_by_name("send")
                if send_clicked:
                    details.append("Clicked Send button")
                else:
                    send_key = "ctrl+enter"
                    self._press_key_combo(send_key)
                    details.append(f"Pressed {send_key}")

                result["details"] = " | ".join(details)

            elif action == "type":
                text = action_data.get("text", "")
                if text:
                    # Guard: If typing 'Settings' directly (e.g. into Run Win+R dialog or search),
                    # convert to 'ms-settings:' so Windows doesn't fail with "Windows cannot find 'Settings'"
                    clean_text = text.strip().lower().replace(".exe", "").replace('"', '').replace("'", "").rstrip(":").strip()
                    if clean_text in ("settings", "cài đặt", "setting", "windows settings", "cài đặt windows", "ms-settings", "windows update") or clean_text.startswith("start settings"):
                        text = "ms-settings:"

                    target = action_data.get("target") or action_data.get("field")
                    focused = False
                    if target:
                        focused = accessibility_manager.focus_element_by_name(target)
                        if focused:
                            time.sleep(0.1)

                    if not focused and "x_percent" in action_data and "y_percent" in action_data:
                        x, y = self.to_pixel_coords(action_data["x_percent"], action_data["y_percent"])
                        self._native_click(x, y, button="left", click_count=1)
                        time.sleep(0.08)
                        focused = True

                    # Clear existing content if requested (default True for clean input)
                    clear_first = action_data.get("clear_first", True)
                    if clear_first:
                        self._press_key_combo("ctrl+a")
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
                direction = action_data.get("direction", "down")
                amount = int(action_data.get("amount", 5))
                x_p = action_data.get("x_percent")
                y_p = action_data.get("y_percent")
                s_res = self.scroll(direction=direction, amount=amount, x_percent=x_p, y_percent=y_p)
                result["details"] = s_res["details"]

            elif action in ("system_control", "system", "sleep", "mute", "unmute", "volume_up", "volume_down", "lock"):
                cmd_type = action_data.get("command") or action_data.get("type") or action
                cmd_clean = str(cmd_type).lower().strip()

                if cmd_clean in ("sleep", "ngủ"):
                    subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
                    result["details"] = "Put computer into Sleep mode"

                elif cmd_clean in ("mute", "tắt tiếng", "tắt âm"):
                    pyautogui.press("volumemute")
                    result["details"] = "Muted system audio"

                elif cmd_clean in ("unmute", "bật tiếng", "bật âm"):
                    pyautogui.press("volumemute")
                    result["details"] = "Unmuted system audio"

                elif cmd_clean in ("volume_up", "tăng âm", "tăng âm lượng"):
                    pyautogui.press("volumeup")
                    result["details"] = "Increased volume"

                elif cmd_clean in ("volume_down", "giảm âm", "giảm âm lượng"):
                    pyautogui.press("volumedown")
                    result["details"] = "Decreased volume"

                elif cmd_clean in ("lock", "khóa màn hình"):
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
        Copy text to clipboard and simulate Ctrl+V (Windows)
        to preserve full Vietnamese accents and diacritics without dropping modifiers.
        """
        pyperclip.copy(text)
        time.sleep(0.05)
        # Windows: Cleanly hold Ctrl, press V, and release to avoid IME drops
        pyautogui.keyDown("ctrl")
        time.sleep(0.02)
        pyautogui.press("v")
        time.sleep(0.02)
        pyautogui.keyUp("ctrl")
        time.sleep(0.05)

    def _press_key_combo(self, combo: str):
        """Parse and press single keys or combinations like 'ctrl+l', 'alt+f4', 'win', 'enter'."""
        combo_clean = combo.strip().lower()
        parts = [p.strip() for p in combo_clean.split("+")]

        # Automatically translate legacy/cross-platform names to Windows equivalents
        normalized_parts = []
        for p in parts:
            if p in ("cmd", "command"):
                normalized_parts.append("ctrl")
            elif p in ("return",):
                normalized_parts.append("enter")
            elif p in ("esc",):
                normalized_parts.append("escape")
            elif p in ("super", "windows"):
                normalized_parts.append("win")
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

    def _open_windows_protocol(self, uri: str):
        """Open a Windows URI protocol like ms-settings: cleanly without CMD error dialogs."""
        if sys.platform.startswith("win"):
            try:
                import ctypes
                res = ctypes.windll.shell32.ShellExecuteW(None, "open", uri, None, None, 1)
                if int(res) > 32:
                    return
            except Exception:
                pass
        try:
            subprocess.Popen(f'start "" "{uri}"', shell=True)
        except Exception as e:
            print(f"[OSController] Không thể mở URI {uri}: {e}")

    def _launch_app(self, app_name: str):
        """Open application natively on Windows."""
        clean = (app_name or "").strip().lower()
        if not clean:
            return

        # 1. Native Windows Settings & Sub-settings (100% reliable via ms-settings: protocol)
        if any(k in clean for k in ("setting", "cài đặt", "ms-settings", "update", "cập nhật")):
            if any(k in clean for k in ("update", "cập nhật")):
                self._open_windows_protocol("ms-settings:windowsupdate")
                return
            if "bluetooth" in clean:
                self._open_windows_protocol("ms-settings:bluetooth")
                return
            if any(k in clean for k in ("wifi", "wi-fi", "mạng", "network")):
                self._open_windows_protocol("ms-settings:network-wifi")
                return
            if any(k in clean for k in ("sound", "âm thanh", "volume", "loa")):
                self._open_windows_protocol("ms-settings:sound")
                return
            if any(k in clean for k in ("display", "màn hình")):
                self._open_windows_protocol("ms-settings:display")
                return

            self._open_windows_protocol("ms-settings:")
            return

        # 2. Native System Apps
        if clean in ("explorer", "file explorer", "thư mục", "quản lý file", "my computer", "this pc"):
            pyautogui.hotkey("win", "e")
            return

        if clean in ("taskmgr", "task manager", "trình quản lý tác vụ", "quản lý tác vụ"):
            pyautogui.hotkey("ctrl", "shift", "esc")
            return

        if clean in ("calc", "calculator", "máy tính"):
            subprocess.Popen(["cmd", "/c", "start", "calc.exe"], shell=True)
            return

        if clean in ("control panel", "bảng điều khiển"):
            subprocess.Popen(["cmd", "/c", "start", "control.exe"], shell=True)
            return

        if clean in ("notepad", "ghi chú", "sổ tay"):
            subprocess.Popen(["cmd", "/c", "start", "notepad.exe"], shell=True)
            return

        if clean in ("paint", "mspaint", "vẽ"):
            subprocess.Popen(["cmd", "/c", "start", "mspaint.exe"], shell=True)
            return

        if clean in ("snipping tool", "snip", "cắt màn hình"):
            pyautogui.hotkey("win", "shift", "s")
            return

        if clean in ("store", "microsoft store", "cửa hàng"):
            subprocess.Popen(["cmd", "/c", "start", "ms-windows-store:"], shell=True)
            return

        if clean in ("cmd", "command prompt", "terminal", "powershell", "windows terminal"):
            subprocess.Popen(["cmd", "/c", "start", "wt.exe"], shell=True)
            return

        if clean in ("chrome", "google chrome"):
            subprocess.Popen(["cmd", "/c", "start", "chrome.exe"], shell=True)
            return

        if clean in ("edge", "microsoft edge"):
            subprocess.Popen(["cmd", "/c", "start", "msedge.exe"], shell=True)
            return

        # 3. For any other application (Zalo, Telegram, Spotify, Word, Excel, Photoshop, etc.):
        # Launching via Windows Start Search is 100% native on Windows 10 & 11:
        # Press Win, paste app name, wait briefly, press Enter.
        # This NEVER triggers the modal "Windows cannot find..." error box!
        try:
            pyautogui.press("win")
            time.sleep(0.35)
            self._paste_unicode_text(app_name)
            time.sleep(0.35)
            pyautogui.press("enter")
        except Exception as e:
            print(f"[OSController] Lỗi khi mở app qua Start menu: {e}")

    def window_control(self, command: str, app_name: str = "") -> Dict[str, Any]:
        """
        Manage window states natively on Windows (maximize, zoom, minimize, close, fullscreen, restore).
        """
        cmd = str(command or "maximize").lower().strip()
        details = ""
        success = False

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
        else:
            pyautogui.hotkey("win", "up")
            success = True
            details = f"Default window action executed for '{cmd}' (Win+Up)"

        return {"success": success, "details": details}

    def scroll(
        self,
        direction: str = "down",
        amount: int = 5,
        x_percent: Optional[float] = None,
        y_percent: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Scroll page or active window with 100% reliability on Windows.
        Ensures cursor is positioned over the scrollable content and window is focused before sending wheel events.
        """
        direction = str(direction or "down").lower().strip()
        amount = int(amount or 5)
        if amount <= 0:
            amount = 5

        # Determine target position for scroll
        if x_percent is not None and y_percent is not None:
            x, y = self.to_pixel_coords(x_percent, y_percent)
        else:
            # Default to center of screen (0.5, 0.5) so wheel events hit main content area
            w, h = self.get_screen_size()
            x, y = int(w * 0.5), int(h * 0.5)

        # 1. Position cursor over scrollable area
        pyautogui.moveTo(x, y, duration=0.08)
        time.sleep(0.03)

        # 2. Focus window under cursor on Windows so scroll events are accepted
        if sys.platform.startswith("win"):
            try:
                import ctypes
                import ctypes.wintypes
                user32 = ctypes.windll.user32
                hwnd = user32.WindowFromPoint(ctypes.wintypes.POINT(x, y))
                if hwnd:
                    root_hwnd = user32.GetAncestor(hwnd, 2)
                    cur_fore = user32.GetForegroundWindow()
                    if root_hwnd and root_hwnd != cur_fore:
                        user32.SetForegroundWindow(root_hwnd)
                        time.sleep(0.04)

                # Send Windows native wheel events (WHEEL_DELTA = 120 per notch)
                # Negative delta scrolls DOWN, positive delta scrolls UP
                MOUSEEVENTF_WHEEL = 0x0800
                delta = -120 * amount if direction in ("down", "dưới", "xuống") else 120 * amount
                user32.mouse_event(MOUSEEVENTF_WHEEL, x, y, delta, 0)
                time.sleep(0.2)
                return {"success": True, "details": f"Scrolled {direction} by {amount} at ({x}, {y})"}
            except Exception:
                pass

        # Fallback to pyautogui scroll
        clicks = -amount if direction in ("down", "dưới", "xuống") else amount
        pyautogui.scroll(clicks * 120)
        time.sleep(0.2)
        return {"success": True, "details": f"Scrolled {direction} by {amount} at ({x}, {y})"}

os_controller = OSController()
