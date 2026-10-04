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
        if IS_MACOS and HAS_MACOS_AX:
            return self._get_macos_app_elements(max_elements)
        elif IS_WINDOWS:
            return self._get_windows_app_elements(max_elements)
        return {"app": "", "window": "", "elements": []}

    def _get_macos_app_elements(self, max_elements: int = 35) -> Dict[str, Any]:
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
            candidates: List[Dict[str, Any]] = []
            seen_keys = set()
            visited_nodes = [0]

            interactive_roles = (
                "AXTextField", "AXTextArea", "AXButton", "AXPopUpButton",
                "AXComboBox", "AXCheckBox", "AXRadioButton", "AXMenuItem",
                "AXSearchField", "AXLink", "AXTab"
            )

            # Check if active window contains an AXWebArea (Chrome, Safari, Edge, Firefox, Electron apps)
            def find_web_area(elem, depth: int = 0):
                if depth > 8:
                    return None
                e, r = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXRole", None)
                if r == "AXWebArea":
                    return elem
                e, ch = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXChildren", None)
                if ch:
                    for c in ch:
                        res = find_web_area(c, depth + 1)
                        if res:
                            return res
                return None

            primary_win = windows[0]
            web_area = find_web_area(primary_win)

            # If web browser window, extract web elements directly from AXWebArea first
            if web_area:
                def walk_web(elem, depth: int = 0):
                    visited_nodes[0] += 1
                    if depth > 18 or visited_nodes[0] > 700 or len(candidates) >= max_elements * 2:
                        return
                    e, role = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXRole", None)
                    e, desc = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXDescription", None)
                    e, title = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXTitle", None)
                    e, val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXValue", None)
                    e, placeholder = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXPlaceholderValue", None)

                    name = desc or title or placeholder or (str(val)[:30] if role in ("AXTextField", "AXButton") and val else "")
                    name_str = str(name).strip() if name else ""

                    if role in interactive_roles and name_str and len(name_str) > 1:
                        e, pos_val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXPosition", None)
                        e, size_val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXSize", None)
                        if pos_val and size_val:
                            ok_p, pt = ApplicationServices.AXValueGetValue(pos_val, ApplicationServices.kAXValueCGPointType, None)
                            ok_s, sz = ApplicationServices.AXValueGetValue(size_val, ApplicationServices.kAXValueCGSizeType, None)
                            if ok_p and ok_s and sz.width >= 10 and sz.height >= 10:
                                cx = int(pt.x + sz.width / 2.0)
                                cy = int(pt.y + sz.height / 2.0)
                                xp = round(cx / float(screen_w), 3)
                                yp = round(cy / float(screen_h), 3)
                                dedup_key = f"{role}:{name_str}"
                                if dedup_key not in seen_keys:
                                    seen_keys.add(dedup_key)
                                    candidates.append({
                                        "role": role.replace("AX", ""),
                                        "name": name_str,
                                        "x_percent": xp,
                                        "y_percent": yp,
                                        "pixel_x": cx,
                                        "pixel_y": cy,
                                        "width": int(sz.width),
                                        "height": int(sz.height),
                                    })
                    e, ch = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXChildren", None)
                    if ch:
                        for c in ch:
                            walk_web(c, depth + 1)

                walk_web(web_area)

            # Also walk native window controls (or top browser address bar / search)
            def walk(elem, depth: int = 0):
                visited_nodes[0] += 1
                if depth > 14 or visited_nodes[0] > 900:
                    return
                # Skip re-traversing web area if already extracted
                e, role = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXRole", None)
                if web_area and role == "AXWebArea":
                    return

                e, desc = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXDescription", None)
                e, title = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXTitle", None)
                e, val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXValue", None)
                e, placeholder = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXPlaceholderValue", None)

                name = desc or title or placeholder or (str(val)[:25] if role in ("AXTextField", "AXButton") and val else "")
                name_str = str(name).strip() if name else ""

                if role in interactive_roles and name_str and len(name_str) > 1:
                    e, pos_val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXPosition", None)
                    e, size_val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXSize", None)

                    if pos_val and size_val:
                        ok_p, pt = ApplicationServices.AXValueGetValue(pos_val, ApplicationServices.kAXValueCGPointType, None)
                        ok_s, sz = ApplicationServices.AXValueGetValue(size_val, ApplicationServices.kAXValueCGSizeType, None)

                        if ok_p and ok_s and sz.width >= 12 and sz.height >= 12:
                            if "TextField" in role or "TextArea" in role or "ComboBox" in role:
                                click_x = int(pt.x + min(80, sz.width * 0.2))
                            else:
                                click_x = int(pt.x + sz.width / 2.0)
                            click_y = int(pt.y + sz.height / 2.0)

                            xp = round(click_x / float(screen_w), 3)
                            yp = round(click_y / float(screen_h), 3)

                            dedup_key = f"{role}:{name_str}"
                            if dedup_key not in seen_keys:
                                seen_keys.add(dedup_key)
                                candidates.append({
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

            # Sort candidates by relevance score (real web content & form inputs at top)
            candidates.sort(key=lambda el: _score_element(el["role"], el["name"]), reverse=True)
            self.cached_elements = candidates[:max_elements]
            return {"app": app_name, "window": win_title, "elements": self.cached_elements}

        except Exception as e:
            print(f"[AccessibilityManager] Warning during macOS UI element extraction: {e}")
            return {"app": "", "window": "", "elements": []}

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
                results.sort(key=lambda el: _score_element(el["role"], el["name"]), reverse=True)
                self.cached_elements = results[:max_elements]
                return {"app": win_name, "window": win_name, "elements": self.cached_elements}
        except Exception as e:
            print(f"[AccessibilityManager] Windows UI Automation notice: {e}")

        return {"app": "", "window": "", "elements": []}

    def _search_live_macos(self, search_tokens: List[str], allowed_roles: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Live deep search in active macOS window when element is not in top cached list."""
        if not (IS_MACOS and HAS_MACOS_AX):
            return None
        try:
            ws = AppKit.NSWorkspace.sharedWorkspace()
            front_app = ws.frontmostApplication()
            if not front_app:
                return None
            pid = front_app.processIdentifier()
            app_elem = ApplicationServices.AXUIElementCreateApplication(pid)
            err, windows = ApplicationServices.AXUIElementCopyAttributeValue(app_elem, "AXWindows", None)
            if not windows:
                return None

            screen_w, screen_h = pyautogui.size()

            def search_node(elem, depth: int = 0):
                if depth > 15:
                    return None
                e, role = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXRole", None)
                e, desc = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXDescription", None)
                e, title = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXTitle", None)
                e, ph = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXPlaceholderValue", None)
                e, val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXValue", None)

                name_str = str(desc or title or ph or (val if role in ("AXTextField", "AXButton") else "") or "").lower().strip()

                if allowed_roles is None or role in allowed_roles:
                    for token in search_tokens:
                        score = _match_element_score(token, name_str)
                        if score >= 100.0:
                            e, pos_val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXPosition", None)
                            e, size_val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXSize", None)
                            if pos_val and size_val:
                                ok_p, pt = ApplicationServices.AXValueGetValue(pos_val, ApplicationServices.kAXValueCGPointType, None)
                                ok_s, sz = ApplicationServices.AXValueGetValue(size_val, ApplicationServices.kAXValueCGSizeType, None)
                                if ok_p and ok_s and sz.width >= 10 and sz.height >= 10:
                                    if "TextField" in role or "TextArea" in role or "ComboBox" in role:
                                        cx = int(pt.x + min(80, sz.width * 0.2))
                                    else:
                                        cx = int(pt.x + sz.width / 2.0)
                                    cy = int(pt.y + sz.height / 2.0)
                                    return {
                                        "role": role.replace("AX", ""),
                                        "name": name_str,
                                        "pixel_x": cx,
                                        "pixel_y": cy,
                                        "x_percent": round(cx / float(screen_w), 3),
                                        "y_percent": round(cy / float(screen_h), 3),
                                    }

                e, children = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXChildren", None)
                if children:
                    for c in children:
                        res = search_node(c, depth + 1)
                        if res:
                            return res
                return None

            # Prioritize searching inside AXWebArea for web pages
            def find_web_area(elem, depth: int = 0):
                if depth > 8:
                    return None
                e, r = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXRole", None)
                if r == "AXWebArea":
                    return elem
                e, ch = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXChildren", None)
                if ch:
                    for c in ch:
                        res = find_web_area(c, depth + 1)
                        if res:
                            return res
                return None

            web_area = find_web_area(windows[0])
            if web_area:
                web_match = search_node(web_area)
                if web_match:
                    return web_match

            return search_node(windows[0])
        except Exception as e:
            print(f"[AccessibilityManager] Live search warning: {e}")
            return None

    def focus_element_by_name(self, target_name: str) -> bool:
        """
        Find and focus an element matching target_name (e.g. 'to', 'subject', 'search', 'send').
        Combines cached lookup and live targeted UI search with direct click for 100% reliability.
        """
        target_lower = target_name.strip().lower()
        if not target_lower:
            return False

        # Keyword mappings for Vietnamese & English common form fields
        synonyms = {
            "to": ["to recipients", "to:", "to", "recipients", "người nhận", "đến", "gửi đến"],
            "subject": ["subject", "tiêu đề", "chủ đề"],
            "body": ["body", "nội dung", "soạn", "thư"],
            "search": ["search", "tìm kiếm", "tìm"],
            "send": ["send", "gửi"],
            "discard": ["discard", "hủy", "xóa"],
            "attach": ["attach", "đính kèm", "tệp"],
            "new mail": ["new mail", "new", "soạn thư", "mới"],
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

        # 2. If not found in cached list with sufficient score, perform live targeted search
        if not best_elem and IS_MACOS:
            allowed_roles = None
            if target_category in ("to", "subject"):
                allowed_roles = ["AXTextField", "AXTextArea", "AXComboBox"]
            elif target_category in ("send", "discard", "new mail"):
                allowed_roles = ["AXButton"]
            best_elem = self._search_live_macos(search_tokens, allowed_roles=allowed_roles)

        if best_elem:
            px = best_elem["pixel_x"]
            py = best_elem["pixel_y"]
            role = best_elem.get("role", "Element")
            print(f"[AccessibilityManager] 🎯 Khóa chính xác phần tử '{best_elem['name']}' ({role}) tại ({px}, {py})")
            pyautogui.moveTo(px, py, duration=0.08)
            pyautogui.click()
            time.sleep(0.12)
            return True

        return False

    def select_element_by_name(self, target_name: str) -> bool:
        """Alias for focus_element_by_name to select web or app elements directly."""
        return self.focus_element_by_name(target_name)

    def is_compose_window_active(self) -> bool:
        """
        Accurately inspect whether an email composer / draft is currently open on screen.
        Used to prevent premature completion claims until the email is genuinely sent.
        """
        if IS_MACOS and HAS_MACOS_AX:
            try:
                ws = AppKit.NSWorkspace.sharedWorkspace()
                front_app = ws.frontmostApplication()
                if not front_app:
                    return False
                pid = front_app.processIdentifier()
                app_elem = ApplicationServices.AXUIElementCreateApplication(pid)
                err, windows = ApplicationServices.AXUIElementCopyAttributeValue(app_elem, "AXWindows", None)
                if not windows:
                    return False

                found_markers = set()

                def check_node(elem, depth: int = 0):
                    if depth > 12 or len(found_markers) >= 2:
                        return
                    e, role = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXRole", None)
                    e, desc = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXDescription", None)
                    e, title = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXTitle", None)
                    e, val = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXValue", None)
                    text = f"{desc or ''} {title or ''} {val or ''}".lower()

                    if "to recipients" in text or "to:" in text:
                        found_markers.add("to")
                    if "subject" in text and role in ("AXTextField", "AXStaticText"):
                        found_markers.add("subject")
                    if "discard" in text and role == "AXButton":
                        found_markers.add("discard")
                    if "draft saved" in text:
                        found_markers.add("draft")

                    e, children = ApplicationServices.AXUIElementCopyAttributeValue(elem, "AXChildren", None)
                    if children:
                        for c in children:
                            check_node(c, depth + 1)

                check_node(windows[0])
                return len(found_markers) >= 1
            except Exception:
                pass

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
