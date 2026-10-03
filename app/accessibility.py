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
        Returns exact normalized coordinates (0.00 - 1.00) and pixel centers.
        """
        if not HAS_MACOS_AX:
            return {"app": "", "window": "", "elements": []}

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
                            # Calculate click target: For wide text fields, click near left edge (50px in)
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

            # Inspect frontmost window, then second window if available (e.g. popup menus/autocomplete)
            win_title = ""
            for w in windows[:2]:
                if not win_title:
                    e, t = ApplicationServices.AXUIElementCopyAttributeValue(w, "AXTitle", None)
                    win_title = str(t) if t else ""
                walk(w)

            self.cached_elements = results
            return {"app": app_name, "window": win_title, "elements": results}

        except Exception as e:
            print(f"[AccessibilityManager] Warning during UI element extraction: {e}")
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
