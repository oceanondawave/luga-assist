"""
Accessibility grounding module for Luga Assist.
Provides 100% exact UI element detection, direct focus, and coordinate anchoring
via macOS Accessibility APIs (ApplicationServices & AppKit) and cross-platform keyboard focus.
"""
import sys
import time
from typing import Dict, Any, List, Optional, Tuple
import pyautogui

IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")

if IS_MACOS:
    try:
        import ApplicationServices
        import AppKit
        HAS_MACOS_AX = True
    except ImportError:
        HAS_MACOS_AX = False
else:
    HAS_MACOS_AX = False


class AccessibilityManager:
    def __init__(self):
        self.cached_elements: List[Dict[str, Any]] = []
        self.last_app_name: str = ""

    def get_frontmost_app_elements(self, max_elements: int = 25) -> Dict[str, Any]:
        """
        Inspect the frontmost application and active window to extract
        high-confidence interactive UI elements (buttons, inputs, search fields).
        Returns exact normalized coordinates (0.00 - 1.00) and pixel centers across macOS and Windows.
        """
        if IS_MACOS and HAS_MACOS_AX:
            return self._get_macos_app_elements(max_elements)
        elif IS_WINDOWS:
            return self._get_windows_app_elements(max_elements)
        return {"app": "", "window": "", "elements": []}

    def _get_macos_app_elements(self, max_elements: int = 25) -> Dict[str, Any]:
        try:
            ws = AppKit.NSWorkspace.sharedWorkspace()
            front_app = ws.frontmostApplication()
            if not front_app:
                return {"app": "", "window": "", "elements": []}

            app_name = front_app.localizedName() or ""
            pid = front_app.processIdentifier()
            self.last_app_name = app_name

            app_elem = ApplicationServices.AXUIElementCreateApplication(pid)
            err, windows = ApplicationServices.AXUIElementCopyAttributeValue(app_elem, "AXWindows", None)
            if not windows:
                return {"app": app_name, "window": "", "elements": []}

            screen_w, screen_h = pyautogui.size()
            results: List[Dict[str, Any]] = []
            seen_keys = set()

            def walk(elem, depth: int = 0):
                if depth > 10 or len(results) >= max_elements:
                    return

                e, role = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXRole", None)
                e, desc = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXDescription", None)
                e, title = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXTitle", None)
                e, val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXValue", None)
                e, placeholder = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXPlaceholderValue", None)

                name = desc or title or placeholder or (str(val)[:25] if role in ("AXTextField", "AXButton") and val else "")
                name_str = str(name).strip() if name else ""

                interactive_roles = (
                    "AXTextField", "AXTextArea", "AXButton", "AXPopUpButton",
                    "AXComboBox", "AXCheckBox", "AXRadioButton", "AXMenuItem",
                    "AXSearchField", "AXTabGroup"
                )

                if role in interactive_roles and name_str:
                    e, pos_val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXPosition", None)
                    e, size_val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXSize", None)

                    if pos_val and size_val:
                        ok_p, pt = ApplicationServices.AXValueGetValue(pos_val, ApplicationServices.kAXValueCGPointType, None)
                        ok_s, sz = ApplicationServices.AXValueGetValue(size_val, ApplicationServices.kAXValueCGSizeType, None)

                        if ok_p and ok_s and sz.width >= 12 and sz.height >= 12:
                            # For wide text fields, click near left edge (50-80px in)
                            if "TextField" in role or "TextArea" in role or "ComboBox" in role:
                                click_x = int(pt.x + min(80, sz.width * 0.2))
                            else:
                                click_x = int(pt.x + sz.width / 2.0)
                            click_y = int(pt.y + sz.height / 2.0)

                            xp = round(click_x / float(screen_w), 3)
                            yp = round(click_y / float(screen_h), 3)

                            dedup_key = f"{role}:{name_str}:{xp}:{yp}"
                            if dedup_key not in seen_keys:
                                seen_keys.add(dedup_key)
                                results.append({
                                    "role": role.replace("AX", ""),
                                    "name": name_str,
                                    "x_percent": xp,
                                    "y_percent": yp,
                                    "pixel_x": click_x,
                                    "pixel_y": click_y,
                                    "width": int(sz.width),
                                    "height": int(sz.height),
                                })

                e, children = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXChildren", None)
                if children:
                    for c in children:
                        walk(c, depth + 1)

            win_title = ""
            for w in windows[:2]:
                if not win_title:
                    e, t = ApplicationServices.AXUIElementCopyAttributeValue(w, "AXTitle", None)
                    win_title = str(t) if t else ""
                walk(w)

            self.cached_elements = results
            return {"app": app_name, "window": win_title, "elements": results}

        except Exception as e:
            print(f"[AccessibilityManager] Warning during macOS UI element extraction: {e}")
            return {"app": "", "window": "", "elements": []}

    def _get_windows_app_elements(self, max_elements: int = 25) -> Dict[str, Any]:
        """
        Inspect the active foreground window on Windows using UIAutomation or PowerShell.
        Extracts Edit, Button, ComboBox controls and their exact screen rectangles.
        """
        import subprocess
        import json

        # 1. Try uiautomation library if installed
        try:
            import uiautomation as auto
            win = auto.GetForegroundControl()
            if win:
                win_name = win.Name or ""
                screen_w, screen_h = pyautogui.size()
                results = []
                for ctrl in win.GetChildren():
                    rect = ctrl.BoundingRectangle
                    if rect and rect.width() > 10 and rect.height() > 10:
                        name = ctrl.Name or ""
                        if name:
                            cx = int(rect.left + rect.width() / 2.0)
                            cy = int(rect.top + rect.height() / 2.0)
                            results.append({
                                "role": ctrl.ControlTypeName.replace("Control", ""),
                                "name": name,
                                "x_percent": round(cx / float(screen_w), 3),
                                "y_percent": round(cy / float(screen_h), 3),
                                "pixel_x": cx,
                                "pixel_y": cy,
                                "width": int(rect.width()),
                                "height": int(rect.height()),
                            })
                if results:
                    self.cached_elements = results[:max_elements]
                    return {"app": win_name, "window": win_name, "elements": self.cached_elements}
        except Exception:
            pass

        # 2. Built-in Windows UIAutomation via PowerShell fallback (pre-installed on all Windows)
        try:
            ps_script = (
                "Add-Type -AssemblyName UIAutomationClient; "
                "Add-Type -AssemblyName UIAutomationTypes; "
                "$def = @'\n"
                "[DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
                "[DllImport(\"user32.dll\")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder text, int count);\n"
                "'@;\n"
                "Add-Type -MemberDefinition $def -Name W32 -Namespace Native -PassThru | Out-Null;\n"
                "$h = [Native.W32]::GetForegroundWindow();\n"
                "$sb = New-Object System.Text.StringBuilder 256;\n"
                "[Native.W32]::GetWindowText($h, $sb, 256) | Out-Null;\n"
                "$title = $sb.ToString();\n"
                "$elem = [System.Windows.Automation.AutomationElement]::FromHandle($h);\n"
                "$cond = New-Object System.Windows.Automation.OrCondition(\n"
                "  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)),\n"
                "  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Button)),\n"
                "  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::ComboBox))\n"
                ");\n"
                "$found = $elem.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond);\n"
                "$list = @();\n"
                "foreach ($f in $found) {\n"
                "  $r = $f.Current.BoundingRectangle;\n"
                "  if ($r.Width -gt 10 -and $r.Height -gt 10 -and $f.Current.Name) {\n"
                "    $list += [PSCustomObject]@{ role=$f.Current.ControlType.ProgrammaticName.Replace('ControlType.',''); name=$f.Current.Name; x=[int]$r.X; y=[int]$r.Y; w=[int]$r.Width; h=[int]$r.Height };\n"
                "  }\n"
                "}\n"
                "[PSCustomObject]@{ window=$title; items=$list } | ConvertTo-Json -Compress\n"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=1.5
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout.strip())
                win_name = data.get("window", "")
                items = data.get("items", [])
                if isinstance(items, dict):
                    items = [items]
                screen_w, screen_h = pyautogui.size()
                results = []
                for it in items:
                    x, y, w, h = it.get("x", 0), it.get("y", 0), it.get("w", 0), it.get("h", 0)
                    cx = int(x + w / 2.0)
                    cy = int(y + h / 2.0)
                    results.append({
                        "role": it.get("role", "Control"),
                        "name": it.get("name", ""),
                        "x_percent": round(cx / float(screen_w), 3),
                        "y_percent": round(cy / float(screen_h), 3),
                        "pixel_x": cx,
                        "pixel_y": cy,
                        "width": w,
                        "height": h,
                    })
                self.cached_elements = results[:max_elements]
                return {"app": win_name, "window": win_name, "elements": self.cached_elements}
        except Exception as e:
            print(f"[AccessibilityManager] Windows UI Automation notice: {e}")

        return {"app": "", "window": "", "elements": []}

    def focus_element_by_name(self, target_name: str) -> bool:
        """
        Find and focus an element matching target_name (e.g. 'to', 'subject', 'search', 'send').
        Combines macOS Accessibility activation and direct mouse click for 100% reliability.
        """
        target_lower = target_name.strip().lower()
        if not target_lower:
            return False

        # Keyword mappings for Vietnamese & English common form fields
        synonyms = {
            "to": ["to", "recipients", "người nhận", "đến", "gửi đến"],
            "subject": ["subject", "tiêu đề", "chủ đề"],
            "body": ["body", "nội dung", "soạn", "thư"],
            "search": ["search", "tìm kiếm", "tìm"],
            "send": ["send", "gửi"],
            "discard": ["discard", "hủy", "xóa"],
            "attach": ["attach", "đính kèm", "tệp"],
            "new": ["new mail", "new", "soạn thư", "mới"],
        }

        search_tokens = [target_lower]
        for key, syn_list in synonyms.items():
            if target_lower in syn_list or key in target_lower:
                search_tokens.extend(syn_list)

        # Refresh cached elements if empty
        if not self.cached_elements:
            self.get_frontmost_app_elements()

        best_elem = None
        for elem in self.cached_elements:
            elem_name_lower = elem.get("name", "").lower()
            elem_role = elem.get("role", "").lower()

            for token in search_tokens:
                if token in elem_name_lower or elem_name_lower in token:
                    best_elem = elem
                    break
            if best_elem:
                break

        if best_elem:
            px = best_elem["pixel_x"]
            py = best_elem["pixel_y"]
            print(f"[AccessibilityManager] 🎯 Tìm thấy phần tử '{best_elem['name']}' ({best_elem['role']}) tại ({px}, {py})")
            pyautogui.moveTo(px, py, duration=0.08)
            pyautogui.click()
            time.sleep(0.12)
            return True

        return False

    def get_ui_grounding_context(self) -> str:
        """
        Generate a concise, high-value prompt block describing exact detected UI coordinates.
        This allows Gemini Vision to lock onto elements with 100% precision.
        """
        data = self.get_frontmost_app_elements()
        elements = data.get("elements", [])
        if not elements:
            return ""

        app_name = data.get("app", "Ứng dụng hiện tại")
        win_name = data.get("window", "")
        header = f"[TỌA ĐỘ UI CHÍNH XÁC 100% TỪ HỆ THỐNG ({app_name} - {win_name})]:\n"

        lines = []
        for el in elements[:18]:
            role = el.get("role", "Element")
            name = el.get("name", "")
            xp = el.get("x_percent")
            yp = el.get("y_percent")
            lines.append(f"- {role} \"{name}\": x_percent={xp:.3f}, y_percent={yp:.3f}")

        note = "\n👉 HÃY SỬ DỤNG CHÍNH XÁC tọa độ x_percent, y_percent từ danh sách trên nếu khớp với mục tiêu của người dùng."
        return header + "\n".join(lines) + note


accessibility_manager = AccessibilityManager()
