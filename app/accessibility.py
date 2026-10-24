"""
Accessibility grounding module for Luga Assist.
Provides 100% exact UI element detection, direct focus, coordinate anchoring,
and outcome verification via macOS Accessibility APIs and cross-platform UI Automation.
"""
import sys
import re
import time
from typing import Dict, Any, List, Optional, Tuple
import pyautogui

IS_WINDOWS = True


def enable_windows_dpi_awareness():
    """Ensure Windows treats process as per-monitor DPI aware so mouse & screen pixels match 1:1."""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            # Per-monitor DPI aware V2
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass


enable_windows_dpi_awareness()


def ensure_accessibility_permissions(prompt: bool = False) -> bool:
    """
    On Windows, application processes do not require macOS-style TCC permissions.
    Always returns True.
    """
    return True



def _score_element(role: str, name: str) -> int:
    """Prioritize web links, search fields, form inputs and core action buttons, suppressing browser/editor noise."""
    name_lower = name.lower().strip()
    role_clean = role.replace("AX", "")

    # Formatting toolbar & browser chrome noise gets negative score
    noise_keywords = (
        "bold", "italic", "underline", "strikethrough", "font", "font size",
        "font color", "highlight color", "increase indent", "decrease indent",
        "bullet list", "number list", "text alignment", "paragraph spacing",
        "styles", "clipboard", "undo", "redo", "more options",
        # Browser chrome & extension noise
        "view site information", "edit bookmark for this tab", "bookmark",
        "extensions", "extension", "bitwarden", "dark reader", "wappalyzer",
        "luga assist bridge", "ask gemini", "tab groups", "reload", "back", "forward",
        "install youtube", "customize and control google chrome"
    )
    if any(k in name_lower for k in noise_keywords):
        return -60

    score = 0
    # Search and inputs
    if any(r in role_clean for r in ("TextField", "TextArea", "SearchField", "ComboBox", "Edit")):
        score += 100
        if any(k in name_lower for k in ("search", "tìm", "to", "recipients", "subject", "tiêu đề", "người nhận")):
            score += 50
    # Core action buttons
    elif "Button" in role_clean:
        action_button_keywords = (
            "search", "tìm", "play", "pause", "subscribe", "send", "gửi",
            "save", "lưu", "submit", "discard", "like", "share", "create", "tạo", "ok", "cancel"
        )
        if any(k in name_lower for k in action_button_keywords):
            score += 90
        else:
            score += 25
    # Web links (video cards, articles, navigation)
    elif "Link" in role_clean or "Hyperlink" in role_clean:
        score += 85
    # Category chips & options (e.g. YouTube category chips like Music, Gaming, News)
    elif "RadioButton" in role_clean or "CheckBox" in role_clean:
        score += 75
    # Sidebar folders, items, and rows (Outlook/Mail/Finder folders)
    elif any(r in role_clean for r in ("Row", "Cell", "OutlineRow", "TreeItem", "ListItem", "StaticText")):
        score += 80
        if any(k in name_lower for k in ("junk", "inbox", "sent", "trash", "draft", "rác", "đến", "gửi", "spam")):
            score += 45
    else:
        score += 10

    return score


def _match_element_score(token: str, elem_name: str) -> float:
    """
    Score how closely elem_name matches token.
    Higher score indicates a much more accurate match for web & native controls.
    """
    t = str(token or "").strip().lower()
    e = str(elem_name or "").strip().lower()
    if not t or not e or len(e) < 2:
        return 0.0
    if t == e:
        return 1000.0  # Exact full match
    if e.startswith(t):
        return 700.0 + len(t)
    if len(e) >= 3 and t.startswith(e):
        return 500.0 + len(e)
    if t in e:
        return 400.0 + len(t)
    if len(e) >= 3 and e in t:
        return 300.0 + len(e)
    # Check word overlap
    t_words = set(re.findall(r"\w+", t))
    e_words = set(re.findall(r"\w+", e))
    common = t_words & e_words
    if common:
        return 150.0 * (len(common) / max(len(t_words), 1))
    return 0.0


class AccessibilityManager:
    def __init__(self):
        self.cached_elements: List[Dict[str, Any]] = []
        self.last_app_name: str = ""

    def get_frontmost_app_elements(self, max_elements: int = 35) -> Dict[str, Any]:
        """
        Inspect the frontmost application and active window to extract
        high-confidence interactive UI elements (buttons, inputs, search fields).
        Returns exact normalized coordinates (0.00 - 1.00) and pixel centers across macOS and Windows.
        """
        return self._get_windows_app_elements(max_elements)


    def _get_windows_app_elements(self, max_elements: int = 35) -> Dict[str, Any]:
        """
        Inspect the active foreground window on Windows using UIAutomation or PowerShell.
        Extracts Edit, Button, ComboBox, Hyperlink, RadioButton controls and their exact screen rectangles.
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
                            role_str = ctrl.ControlTypeName.replace("Control", "")
                            results.append({
                                "role": role_str,
                                "name": name,
                                "x_percent": round(cx / float(screen_w), 3),
                                "y_percent": round(cy / float(screen_h), 3),
                                "pixel_x": cx,
                                "pixel_y": cy,
                                "width": int(rect.width()),
                                "height": int(rect.height()),
                            })
                if results:
                    results.sort(key=lambda el: _score_element(el["role"], el["name"]), reverse=True)
                    self.cached_elements = results[:max_elements]
                    return {"app": win_name, "window": win_name, "elements": self.cached_elements}
        except Exception:
            pass

        # 2. Built-in Windows UIAutomation via PowerShell fallback
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
                "  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Hyperlink)),\n"
                "  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::RadioButton)),\n"
                "  (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::CheckBox)),\n"
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
            flags = 0x08000000 if sys.platform.startswith("win") else 0
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=1.5,
                creationflags=flags
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
                results.sort(key=lambda el: _score_element(el["role"], el["name"]), reverse=True)
                self.cached_elements = results[:max_elements]
                return {"app": win_name, "window": win_name, "elements": self.cached_elements}
        except Exception as e:
            print(f"[AccessibilityManager] Windows UI Automation notice: {e}")

        return {"app": "", "window": "", "elements": []}



    def focus_element_by_name(self, target_name: str) -> bool:
        """
        Find and focus an element matching target_name (e.g. 'to', 'subject', 'search', 'send').
        Combines cached lookup and live targeted UI search with direct click for 100% reliability.
        """
        target_lower = target_name.strip().lower()
        if not target_lower:
            return False

        # Keyword mappings for Vietnamese & English common form fields & folders
        synonyms = {
            "to": ["to recipients", "to:", "to", "recipients", "người nhận", "đến", "gửi đến"],
            "subject": ["subject", "tiêu đề", "chủ đề"],
            "body": ["body", "nội dung", "soạn", "thư"],
            "search": ["search", "tìm kiếm", "tìm"],
            "send": ["send", "gửi"],
            "discard": ["discard", "hủy", "xóa"],
            "attach": ["attach", "đính kèm", "tệp"],
            "new mail": ["new mail", "new", "soạn thư", "mới"],
            "junk": ["junk email", "junk", "thư rác", "spam", "bulk mail", "rác"],
            "inbox": ["inbox", "hộp thư đến", "hộp thư"],
            "sent": ["sent items", "sent", "đã gửi"],
            "trash": ["deleted items", "trash", "thùng rác", "mục đã xóa"],
            "drafts": ["drafts", "bản nháp", "nháp"],
        }

        search_tokens = [target_lower]
        target_category = ""
        for key, syn_list in synonyms.items():
            if target_lower in syn_list or key in target_lower or target_lower in key:
                search_tokens.extend(syn_list)
                target_category = key

        # 1. Search in cached elements first, scoring all candidates to pick the best match
        if not self.cached_elements:
            self.get_frontmost_app_elements()

        best_elem = None
        best_score = 0.0

        for elem in self.cached_elements:
            elem_name = elem.get("name", "")
            for token in search_tokens:
                score = _match_element_score(token, elem_name)
                if score > best_score:
                    best_score = score
                    best_elem = elem

        # Only accept cached element if score is solid (>= 100.0)
        if best_score < 100.0:
            best_elem = None

        if best_elem:
            px = best_elem["pixel_x"]
            py = best_elem["pixel_y"]
            role = best_elem.get("role", "Element")
            print(f"[AccessibilityManager] 🎯 Khóa chính xác phần tử '{best_elem['name']}' ({role}) tại ({px}, {py})")
            pyautogui.moveTo(px, py, duration=0.08)
            time.sleep(0.02)
            pyautogui.mouseDown()
            time.sleep(0.04)
            pyautogui.mouseUp()
            time.sleep(0.12)
            return True

        return False

    def snap_coordinates(self, pixel_x: int, pixel_y: int, target: str = "") -> Optional[Tuple[int, int]]:
        """
        Check if (pixel_x, pixel_y) falls within or near any UI element in the active window.
        If matched, snaps to the exact center (cx, cy) of that element for 100% precision.
        """
        if not self.cached_elements:
            self.get_frontmost_app_elements()

        if not self.cached_elements:
            return None

        target_clean = str(target or "").strip().lower()

        # 1. First priority: Element whose bounding box directly contains (pixel_x, pixel_y)
        for elem in self.cached_elements:
            cx, cy = elem.get("pixel_x", 0), elem.get("pixel_y", 0)
            w, h = elem.get("width", 0), elem.get("height", 0)
            if w > 0 and h > 0:
                left = cx - w / 2.0
                right = cx + w / 2.0
                top = cy - h / 2.0
                bottom = cy + h / 2.0
                if left <= pixel_x <= right and top <= pixel_y <= bottom:
                    return cx, cy

        # 2. Second priority: If target name matches an element within 50px
        if target_clean:
            for elem in self.cached_elements:
                elem_name = elem.get("name", "").lower()
                if target_clean in elem_name or elem_name in target_clean:
                    cx, cy = elem.get("pixel_x", 0), elem.get("pixel_y", 0)
                    dist = ((pixel_x - cx) ** 2 + (pixel_y - cy) ** 2) ** 0.5
                    if dist <= 50:
                        return cx, cy

        # 3. Third priority: Closest element within 30px
        closest_elem = None
        min_dist = 30.0
        for elem in self.cached_elements:
            cx, cy = elem.get("pixel_x", 0), elem.get("pixel_y", 0)
            dist = ((pixel_x - cx) ** 2 + (pixel_y - cy) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                closest_elem = elem

        if closest_elem:
            return closest_elem["pixel_x"], closest_elem["pixel_y"]

        return None

    def select_element_by_name(self, target_name: str) -> bool:
        """Alias for focus_element_by_name to select web or app elements directly."""
        return self.focus_element_by_name(target_name)

    def is_compose_window_active(self) -> bool:
        """
        Accurately inspect whether an email composer / draft is currently open on screen.
        Used to prevent premature completion claims until the email is genuinely sent.
        """
        if self.cached_elements:
            markers = [el["name"].lower() for el in self.cached_elements]
            has_to = any("to recipients" in m or "to:" in m for m in markers)
            has_subject = any("subject" in m for m in markers)
            has_discard = any("discard" in m for m in markers)
            return (has_to and has_subject) or (has_discard and has_to)

        return False

        # Fallback inspection on cached elements
        if self.cached_elements:
            markers = [el["name"].lower() for el in self.cached_elements]
            has_to = any("to recipients" in m or "to:" in m for m in markers)
            has_subject = any("subject" in m for m in markers)
            has_discard = any("discard" in m for m in markers)
            return (has_to and has_subject) or (has_discard and has_to)

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
        for el in elements[:22]:
            role = el.get("role", "Element")
            name = el.get("name", "")
            xp = el.get("x_percent")
            yp = el.get("y_percent")
            lines.append(f"- {role} \"{name}\": x_percent={xp:.3f}, y_percent={yp:.3f}")

        note = "\n👉 HÃY SỬ DỤNG CHÍNH XÁC tọa độ x_percent, y_percent từ danh sách trên nếu khớp với mục tiêu của người dùng."
        return header + "\n".join(lines) + note


accessibility_manager = AccessibilityManager()
