"""
Screen capture module with Visual Grid Grounding and Action Annotation.
"""
import io
import base64
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
import mss
from PIL import Image, ImageDraw, ImageFont

from app.config import (
    TEMP_DIR,
    ENABLE_VISUAL_GRID,
    GRID_PERCENT_STEP,
    SCREENSHOT_MAX_WIDTH,
)

class ScreenCapturer:
    def __init__(self):
        self.last_screen_size: Tuple[int, int] = (1920, 1080)
        self.screenshot_path = TEMP_DIR / "current_screen.jpg"
        self.annotated_path = TEMP_DIR / "last_action.jpg"

    def get_primary_monitor(self, sct: mss.mss) -> Dict[str, Any]:
        """Get the primary monitor specification."""
        # sct.monitors[0] is all monitors combined, sct.monitors[1] is the primary
        if len(sct.monitors) > 1:
            return sct.monitors[1]
        return sct.monitors[0]

    def capture(self, with_grid: bool = ENABLE_VISUAL_GRID) -> Tuple[str, Tuple[int, int]]:
        """
        Capture the screen, optionally overlay coordinate grid, and return:
        (base64_data_uri, (physical_width, physical_height))
        """
        with mss.mss() as sct:
            monitor = self.get_primary_monitor(sct)
            sct_img = sct.grab(monitor)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            self.last_screen_size = img.size  # (width, height)
        orig_w, orig_h = img.size

        # 1. High-speed scale down first (reduces memory & drawing time by 75%)
        if orig_w > SCREENSHOT_MAX_WIDTH:
            scale_ratio = SCREENSHOT_MAX_WIDTH / float(orig_w)
            new_h = int(orig_h * scale_ratio)
            processed_img = img.resize((SCREENSHOT_MAX_WIDTH, new_h), Image.Resampling.BILINEAR)
        else:
            processed_img = img

        # 2. Draw visual coordinate grid on the optimized image
        if with_grid:
            processed_img = self._draw_coordinate_grid(processed_img)

        # 3. High-speed JPEG save & Base64 encoding in memory
        buffered = io.BytesIO()
        processed_img.save(buffered, format="JPEG", quality=75)
        raw_bytes = buffered.getvalue()

        with open(self.screenshot_path, "wb") as f:
            f.write(raw_bytes)

        img_str = base64.b64encode(raw_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{img_str}"

        return data_uri, self.last_screen_size

    def _draw_coordinate_grid(self, img: Image.Image) -> Image.Image:
        """
        Draw a dual-tier visual coordinate grid with primary (10%) and secondary (5%) indicators.
        Enables Gemini Vision to anchor coordinates with extreme precision down to individual input fields.
        """
        draw = ImageDraw.Draw(img)
        w, h = img.size

        # Draw vertical lines (x_percent)
        for p in range(5, 100, 5):
            is_primary = (p % 10 == 0)
            x = int(w * (p / 100.0))
            line_color = (0, 230, 255) if is_primary else (0, 130, 170)
            line_width = 2 if is_primary else 1
            draw.line([(x, 0), (x, h)], fill=line_color, width=line_width)

            label = f"{p}%"
            if is_primary:
                draw.rectangle([(x - 14, 2), (x + 14, 18)], fill=(0, 0, 0))
                draw.text((x - 11, 3), label, fill=(255, 255, 0))
            else:
                draw.rectangle([(x - 11, 2), (x + 11, 15)], fill=(0, 0, 0))
                draw.text((x - 9, 2), label, fill=(0, 240, 255))

        # Draw horizontal lines (y_percent)
        for p in range(5, 100, 5):
            is_primary = (p % 10 == 0)
            y = int(h * (p / 100.0))
            line_color = (0, 230, 255) if is_primary else (0, 130, 170)
            line_width = 2 if is_primary else 1
            draw.line([(0, y), (w, y)], fill=line_color, width=line_width)

            label = f"{p}%"
            if is_primary:
                draw.rectangle([(2, y - 8), (32, y + 8)], fill=(0, 0, 0))
                draw.text((4, y - 7), label, fill=(255, 255, 0))
            else:
                draw.rectangle([(2, y - 7), (28, y + 7)], fill=(0, 0, 0))
                draw.text((3, y - 6), label, fill=(0, 240, 255))

        return img

    def annotate_action(self, x_percent: float, y_percent: float, action_type: str = "click") -> Optional[str]:
        """
        Annotate the target click location with a high-contrast target ring
        so the user/developer can review what was clicked on the WebUI.
        """
        if not self.screenshot_path.exists():
            return None

        try:
            img = Image.open(self.screenshot_path).convert("RGB")
            draw = ImageDraw.Draw(img)
            w, h = img.size

            px = int(w * x_percent)
            py = int(h * y_percent)

            radius = 24
            # Draw bullseye target
            # Outer ring
            draw.ellipse([(px - radius, py - radius), (px + radius, py + radius)], outline=(255, 0, 50), width=4)
            # Inner circle
            draw.ellipse([(px - 6, py - 6), (px + 6, py + 6)], fill=(255, 255, 0), outline=(0, 0, 0), width=1)
            # Crosshairs
            draw.line([(px - radius - 10, py), (px + radius + 10, py)], fill=(255, 0, 50), width=2)
            draw.line([(px, py - radius - 10), (px, py + radius + 10)], fill=(255, 0, 50), width=2)

            # Label action
            tag_text = f"Action: {action_type.upper()} ({int(x_percent*100)}%, {int(y_percent*100)}%)"
            draw.rectangle([(px + radius + 6, py - 12), (px + radius + 180, py + 12)], fill=(0, 0, 0))
            draw.text((px + radius + 10, py - 8), tag_text, fill=(255, 255, 255))

            img.save(self.annotated_path, format="JPEG", quality=85)

            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
        except Exception as e:
            print(f"[ScreenCapturer] Error annotating action: {e}")
            return None

    def annotate_actions(self, actions_list: list) -> Optional[str]:
        """
        Annotate multiple action locations sequentially on the screenshot
        with numbered step badges (#1, #2, #3).
        """
        if not self.screenshot_path.exists() or not actions_list:
            return None

        try:
            img = Image.open(self.screenshot_path).convert("RGB")
            draw = ImageDraw.Draw(img)
            w, h = img.size

            points = []
            step = 1

            for act in actions_list:
                if not isinstance(act, dict):
                    continue

                xp = act.get("x_percent")
                yp = act.get("y_percent")
                act_name = act.get("action", "").upper()

                if xp is not None and yp is not None:
                    px = int(w * float(xp))
                    py = int(h * float(yp))
                    points.append((px, py))

                    radius = 22
                    # Draw target ring
                    draw.ellipse([(px - radius, py - radius), (px + radius, py + radius)], outline=(255, 50, 50), width=3)
                    # Step badge
                    badge_text = f"#{step} {act_name}"
                    draw.rectangle([(px - 14, py - 14), (px + 14, py + 14)], fill=(255, 230, 0), outline=(0, 0, 0))
                    draw.text((px - 8, py - 8), f"#{step}", fill=(0, 0, 0))
                    # Action label
                    draw.rectangle([(px + radius + 4, py - 10), (px + radius + 140, py + 12)], fill=(0, 0, 0))
                    draw.text((px + radius + 8, py - 6), badge_text, fill=(255, 255, 255))
                    step += 1

            # Draw directional lines between sequence points if multiple
            if len(points) > 1:
                for i in range(len(points) - 1):
                    draw.line([points[i], points[i + 1]], fill=(0, 255, 255), width=2)

            img.save(self.annotated_path, format="JPEG", quality=85)

            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            return f"data:image/jpeg;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"
        except Exception as e:
            print(f"[ScreenCapturer] Error annotating actions sequence: {e}")
            return None

# Singleton instance
screen_capturer = ScreenCapturer()
