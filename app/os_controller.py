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
        """
        action = action_data.get("action", "none").lower()
        result = {"success": True, "action": action, "details": ""}

        try:
            if action == "click":
                x, y = self.to_pixel_coords(action_data.get("x_percent", 0.5), action_data.get("y_percent", 0.5))
                pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION, tween=pyautogui.easeInOutQuad)
                pyautogui.click()
                result["details"] = f"Clicked at ({x}, {y})"

            elif action == "double_click":
                x, y = self.to_pixel_coords(action_data.get("x_percent", 0.5), action_data.get("y_percent", 0.5))
                pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION, tween=pyautogui.easeInOutQuad)
                pyautogui.doubleClick()
                result["details"] = f"Double clicked at ({x}, {y})"

            elif action == "right_click":
                x, y = self.to_pixel_coords(action_data.get("x_percent", 0.5), action_data.get("y_percent", 0.5))
                pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION, tween=pyautogui.easeInOutQuad)
                pyautogui.rightClick()
                result["details"] = f"Right clicked at ({x}, {y})"

            elif action == "type":
                text = action_data.get("text", "")
                if text:
                    # If coordinate provided, click there first
                    if "x_percent" in action_data and "y_percent" in action_data:
                        x, y = self.to_pixel_coords(action_data["x_percent"], action_data["y_percent"])
                        pyautogui.moveTo(x, y, duration=MOUSE_MOVE_DURATION)
                        pyautogui.click()
                        time.sleep(0.06)
                    
                    # For Vietnamese Unicode text: copy to clipboard and paste to avoid IME issues
                    self._paste_unicode_text(text)
                    result["details"] = f"Typed: {text}"

            elif action == "press":
                key_combo = action_data.get("key", "enter").lower()
                self._press_key_combo(key_combo)
                result["details"] = f"Pressed: {key_combo}"

            elif action == "scroll":
                direction = action_data.get("direction", "down").lower()
                amount = int(action_data.get("amount", 5))
                clicks = -amount if direction == "down" else amount
                # Move to center or specified coordinate
                if "x_percent" in action_data and "y_percent" in action_data:
                    x, y = self.to_pixel_coords(action_data["x_percent"], action_data["y_percent"])
                    pyautogui.moveTo(x, y)
                pyautogui.scroll(clicks * 100)
                result["details"] = f"Scrolled {direction} by {amount}"

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
        to preserve full Vietnamese accents and diacritics.
        """
        pyperclip.copy(text)
        time.sleep(0.04)
        if sys.platform == "darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")

    def _press_key_combo(self, combo: str):
        """Parse and press single keys or combinations like 'cmd+space' or 'ctrl+c'."""
        keys = [k.strip() for k in combo.split("+")]
        mapped_keys = []
        for k in keys:
            k_lower = k.lower()
            if k_lower in ("cmd", "command", "win", "windows", "super"):
                mapped_keys.append("command" if sys.platform == "darwin" else "win")
            elif k_lower in ("ctrl", "control"):
                mapped_keys.append("ctrl")
            elif k_lower in ("alt", "option"):
                mapped_keys.append("alt")
            elif k_lower == "return":
                mapped_keys.append("enter")
            elif k_lower == "esc":
                mapped_keys.append("escape")
            else:
                mapped_keys.append(k_lower)

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
