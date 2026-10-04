"""
Luga Assist - Native Desktop Spotlight Floating Chat HUD.
Provides a floating, always-on-top Spotlight-style chat bar for instant PC control & chat
from ANY application with a single global hotkey (F7 or Ctrl+Alt+Space).

Zero browser tab needed!
Automatically hides momentarily during screen capture so the AI sees 100% of the screen.
"""
import sys
import os
import time
import json
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import font as tkfont
from typing import Optional, Callable, Any

from pynput import keyboard

from app.config import HOST, PORT, DEFAULT_TTS_VOICE
from app.screen_capture import screen_capturer
from app.sound_effects import sound_manager
from app.logger import get_logger

logger = get_logger("SpotlightUI")


class SpotlightHUD:
    _instance = None

    def __init__(self, host: str = HOST, port: int = PORT, server: Optional[Any] = None, manage_hotkeys: bool = True):
        SpotlightHUD._instance = self
        self.host = host
        self.port = port
        self.server = server
        self.manage_hotkeys = manage_hotkeys
        self.root: Optional[tk.Tk] = None
        self.is_visible = False
        self.was_visible_before_capture = False
        self.current_mode = "control"
        self._keys_held = set()
        self._hotkey_listener = None
        self._last_toggle_time = 0.0

        # Thread synchronization
        self.ready_event = threading.Event()

    def run(self, show_immediately: bool = False):
        """Run the Tkinter GUI main loop on this thread."""
        logger.info("Initializing Spotlight Tkinter HUD...")
        self.root = tk.Tk()
        self.root.title("Luga Assist - Spotlight Chat (F7)")

        # Configure window properties
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#0f172a")

        # Dimensions & position at top center
        win_w = 640
        win_h = 240
        screen_w = self.root.winfo_screenwidth()
        x_pos = max(0, (screen_w - win_w) // 2)
        y_pos = 100
        self.root.geometry(f"{win_w}x{win_h}+{x_pos}+{y_pos}")
        self.root.minsize(560, 200)

        # Build UI layout
        self._build_ui()

        # Bind window keys
        self.root.bind("<Escape>", lambda e: self.hide())
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        # Start hidden initially unless show_immediately is requested
        if show_immediately:
            self.show()
        else:
            self.root.withdraw()
            self.is_visible = False

        # Register capture hooks with screen_capturer
        screen_capturer.register_pre_capture_hook(self.on_pre_screen_capture)
        screen_capturer.register_post_capture_hook(self.on_post_screen_capture)

        # Start global hotkeys listener if managing hotkeys
        if self.manage_hotkeys:
            self._start_global_hotkeys()

        self.ready_event.set()
        logger.info("Spotlight HUD ready! Press F7 or Ctrl+Alt+Space anywhere.")

        # Tkinter main loop
        self.root.mainloop()

    def _build_ui(self):
        # Outer Card Container
        self.card = tk.Frame(self.root, bg="#0f172a", padx=14, pady=12)
        self.card.pack(fill="both", expand=True)

        # Header Row
        header = tk.Frame(self.card, bg="#0f172a")
        header.pack(fill="x", pady=(0, 10))

        title_lbl = tk.Label(
            header,
            text="🎙️ Luga Assist",
            font=("Arial", 13, "bold"),
            fg="#38bdf8",
            bg="#0f172a"
        )
        title_lbl.pack(side="left")

        # Mode toggle badge
        self.btn_mode = tk.Button(
            header,
            text="🎮 Điều khiển PC",
            font=("Arial", 11, "bold"),
            bg="#1e293b",
            fg="#38bdf8",
            activebackground="#334155",
            activeforeground="#38bdf8",
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
            command=self.toggle_mode
        )
        self.btn_mode.pack(side="left", padx=(10, 0))

        # Close button
        btn_close = tk.Button(
            header,
            text="✕ Ẩn (Esc)",
            font=("Arial", 11),
            bg="#0f172a",
            fg="#94a3b8",
            activebackground="#1e293b",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            command=self.hide
        )
        btn_close.pack(side="right")

        # Shutdown app button
        btn_stop = tk.Button(
            header,
            text="🛑 Tắt Luga",
            font=("Arial", 11, "bold"),
            bg="#7f1d1d",
            fg="#fca5a5",
            activebackground="#ef4444",
            activeforeground="#ffffff",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.quit_app
        )
        btn_stop.pack(side="right", padx=(6, 6))

        # Open Web dashboard button
        btn_web = tk.Button(
            header,
            text="🌐 Web",
            font=("Arial", 11),
            bg="#1e293b",
            fg="#94a3b8",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.open_web
        )
        btn_web.pack(side="right", padx=(0, 6))

        # Input Row Container (Surface Card)
        input_box = tk.Frame(self.card, bg="#1e293b", padx=10, pady=8, relief="flat", highlightthickness=1, highlightbackground="#334155")
        input_box.pack(fill="x")

        # Mic button
        btn_mic = tk.Button(
            input_box,
            text="🎙️",
            font=("Arial", 12),
            bg="#0f172a",
            fg="#ffffff",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.trigger_voice
        )
        btn_mic.pack(side="left", padx=(0, 6))

        self.txt_input = tk.Entry(
            input_box,
            font=("Arial", 14),
            bg="#1e293b",
            fg="#ffffff",
            insertbackground="#38bdf8",
            relief="flat",
            highlightthickness=0
        )
        self.txt_input.pack(side="left", fill="x", expand=True, padx=(4, 8))
        self.txt_input.bind("<Return>", lambda e: self.submit_command())

        btn_send = tk.Button(
            input_box,
            text="Gửi ➔",
            font=("Arial", 12, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            command=self.submit_command
        )
        btn_send.pack(side="right")

        # Status & Response Area
        self.status_lbl = tk.Label(
            self.card,
            text="Nhập lệnh hoặc câu hỏi rồi nhấn Enter (Màn hình sẽ tự động giữ thông thoáng cho AI).",
            font=("Arial", 11),
            fg="#94a3b8",
            bg="#0f172a",
            anchor="w",
            wraplength=600,
            justify="left"
        )
        self.status_lbl.pack(fill="x", pady=(8, 4))

        # Response details box (expandable)
        self.resp_box = tk.Frame(self.card, bg="#0f172a")
        self.resp_box.pack(fill="both", expand=True)

        self.resp_text = tk.Label(
            self.resp_box,
            text="",
            font=("Arial", 12),
            fg="#f1f5f9",
            bg="#0f172a",
            anchor="nw",
            wraplength=600,
            justify="left"
        )
        self.resp_text.pack(fill="both", expand=True)

        # Footer hints
        footer = tk.Frame(self.card, bg="#0f172a")
        footer.pack(fill="x", side="bottom")

        hints = tk.Label(
            footer,
            text="Phím tắt: [F7] Bật/Tắt Chat • [Esc] Ẩn • [F8] Nói qua Micro • [F9] Đổi chế độ",
            font=("Arial", 10),
            fg="#64748b",
            bg="#0f172a"
        )
        hints.pack(side="left")

    def show(self):
        """Show the HUD and immediately focus the input."""
        if not self.root:
            return
        def _do_show():
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)
                if sys.platform == "darwin":
                    try:
                        import subprocess
                        subprocess.run(
                            ["osascript", "-e", f'tell application "System Events" to set frontmost of first process whose unix id is {os.getpid()} to true'],
                            capture_output=True,
                            timeout=0.4
                        )
                    except Exception:
                        pass
                self.root.focus_force()
                self.txt_input.focus_set()
                self.txt_input.select_range(0, tk.END)
                self.is_visible = True
            except Exception as e:
                logger.error(f"Error in show HUD: {e}")
            try:
                sound_manager.play_start()
            except Exception:
                pass
        self.root.after(0, _do_show)

    def hide(self):
        """Hide the HUD."""
        if not self.root:
            return
        def _do_hide():
            self.root.withdraw()
            self.is_visible = False
        self.root.after(0, _do_hide)

    def toggle(self):
        """Toggle HUD visibility with debounce."""
        now = time.time()
        if now - self._last_toggle_time < 0.35:
            return
        self._last_toggle_time = now
        if self.is_visible:
            self.hide()
        else:
            self.show()

    def on_pre_screen_capture(self):
        """
        Called right before ScreenCapturer grabs the screenshot.
        Momentarily hides the Spotlight HUD so the AI captures the 100% full, unobstructed screen!
        """
        if self.root and self.is_visible:
            self.was_visible_before_capture = True
            done_evt = threading.Event()
            def _hide():
                try:
                    self.root.withdraw()
                    self.root.update_idletasks()
                finally:
                    done_evt.set()
            self.root.after(0, _hide)
            done_evt.wait(timeout=0.1)
            time.sleep(0.04)

    def on_post_screen_capture(self):
        """
        Called right after ScreenCapturer finishes grabbing the screenshot.
        Restores the HUD if it was visible before.
        """
        if self.root and self.was_visible_before_capture:
            self.was_visible_before_capture = False
            def _restore():
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)
            self.root.after(0, _restore)

    def toggle_mode(self):
        """Toggle mode between Control and Chat."""
        target_mode = "chat" if self.current_mode == "control" else "control"
        def _req():
            try:
                url = f"http://{self.host}:{self.port}/api/set_mode"
                req = urllib.request.Request(
                    url,
                    data=json.dumps({"mode": target_mode, "announce": True}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=2.0) as res:
                    data = json.loads(res.read())
                    mode = data.get("mode", target_mode)
                    self.current_mode = mode
                    def _update_btn():
                        if mode == "chat":
                            self.btn_mode.config(text="💬 Trò chuyện AI", fg="#a855f7")
                        else:
                            self.btn_mode.config(text="🎮 Điều khiển PC", fg="#38bdf8")
                    self.root.after(0, _update_btn)
            except Exception as e:
                logger.error(f"Failed to toggle mode via HTTP: {e}")
        threading.Thread(target=_req, daemon=True).start()

    def open_web(self):
        """Open web dashboard in browser."""
        import webbrowser
        webbrowser.open(f"http://{self.host}:{self.port}")

    def trigger_voice(self):
        """Trigger voice recognition via mic."""
        self.status_lbl.config(text="🎙️ Bạn có thể nhấn phím F8 để nói trực tiếp qua Micro!", fg="#38bdf8")
        sound_manager.play_start()

    def quit_app(self):
        """Cleanly terminate the entire unified application and server."""
        logger.info("SpotlightHUD: Quit requested.")
        sound_manager.play_done()
        try:
            from app.system_ui import show_desktop_notification
            show_desktop_notification("Luga Assist", "Đã tắt hoàn toàn Luga Assist. Tạm biệt bạn!")
        except Exception:
            pass

        try:
            from app.config import PID_FILE
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass

        if self.server:
            self.server.should_exit = True

        if self.root:
            self.root.destroy()

        os._exit(0)

    def submit_command(self):
        """Submit command from text entry box."""
        cmd = self.txt_input.get().strip()
        if not cmd:
            return

        self.status_lbl.config(
            text="⏳ Luga đang phân tích màn hình và thực thi câu lệnh...",
            fg="#38bdf8"
        )
        self.resp_text.config(text="")

        # Temporarily hide HUD during execution if controlling screen
        def _send():
            try:
                url = f"http://{self.host}:{self.port}/api/chat"
                req = urllib.request.Request(
                    url,
                    data=json.dumps({"message": cmd, "speak": True}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30.0) as res:
                    data = json.loads(res.read())
                    speech = data.get("response") or data.get("speech") or "Đã hoàn thành thao tác."
                    def _update_ui():
                        self.status_lbl.config(text="✅ Kết quả hoàn tất:", fg="#10b981")
                        self.resp_text.config(text=speech)
                        # Clear input after success
                        self.txt_input.delete(0, tk.END)
                        # Re-expand window if response is long
                        if len(speech) > 60:
                            self.root.geometry(f"640x300")
                        else:
                            self.root.geometry(f"640x220")
                        self.root.deiconify()
                        self.root.lift()
                        self.root.attributes("-topmost", True)
                    self.root.after(0, _update_ui)
            except Exception as e:
                def _err_ui():
                    self.status_lbl.config(text=f"⚠️ Lỗi kết nối: {e}", fg="#ef4444")
                    self.root.deiconify()
                self.root.after(0, _err_ui)

        threading.Thread(target=_send, daemon=True).start()

    def _start_global_hotkeys(self):
        """
        Global hotkeys:
        - F7: Toggle Spotlight HUD
        - Ctrl + Alt + Space: Alternative hotkey
        """
        def on_press(key):
            try:
                # F7 key
                if key == keyboard.Key.f7:
                    print("\n[Global Hotkey] Đã nhấn F7 -> Bật/Tắt Spotlight Chat!")
                    self.toggle()
                    return

                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._keys_held.add("ctrl")
                elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._keys_held.add("alt")
                elif key == keyboard.Key.space:
                    if "ctrl" in self._keys_held and "alt" in self._keys_held:
                        print("\n[Global Hotkey] Đã nhấn Ctrl + Alt + Space -> Bật/Tắt Spotlight Chat!")
                        self.toggle()
                        return
            except Exception:
                pass

        def on_release(key):
            try:
                if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    self._keys_held.discard("ctrl")
                elif key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                    self._keys_held.discard("alt")
            except Exception:
                pass

        self._hotkey_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()


def get_spotlight_hud() -> Optional[SpotlightHUD]:
    return SpotlightHUD._instance


def start_spotlight_process():
    """Start Spotlight HUD as a detached subprocess or entry point."""
    hud = SpotlightHUD()
    hud.run()


if __name__ == "__main__":
    start_spotlight_process()
