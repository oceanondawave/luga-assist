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

if sys.platform == "darwin":
    os.environ["ApplePersistence"] = "NO"

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
        win_w = 780
        win_h = 240
        screen_w = self.root.winfo_screenwidth()
        x_pos = max(0, (screen_w - win_w) // 2)
        y_pos = 100
        self.root.geometry(f"{win_w}x{win_h}+{x_pos}+{y_pos}")
        self.root.minsize(680, 200)

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
        title_lbl.pack(side="left", padx=(0, 6))

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
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.toggle_mode
        )
        self.btn_mode.pack(side="left", padx=(0, 6))

        # Microphone selector button
        self.btn_mic_select = tk.Button(
            header,
            text="🎤 Micro ▾",
            font=("Arial", 11),
            bg="#1e293b",
            fg="#94a3b8",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=6,
            pady=2,
            cursor="hand2",
            command=self.show_mic_menu
        )
        self.btn_mic_select.pack(side="left", padx=(0, 6))

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
            padx=6,
            pady=2,
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
            padx=8,
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
            font=("Arial", 13),
            bg="#1e293b",
            fg="#38bdf8",
            activebackground="#334155",
            activeforeground="#38bdf8",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=4,
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

        # Initial microphone badge label
        self._update_mic_label()

    def show(self):
        """Show the HUD and immediately focus the input."""
        if not self.root:
            return
        def _do_show():
            try:
                self._update_mic_label()
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

    def set_status(self, text: str, fg: str = "#94a3b8"):
        """Safely set status label text and color."""
        if hasattr(self, "status_lbl") and self.status_lbl:
            self.status_lbl.config(text=text, fg=fg)

    def _update_mic_label(self):
        """Update the microphone button label with currently active device name."""
        try:
            from app.audio_manager import audio_manager
            saved = audio_manager.get_saved_device_name()
            _, name = audio_manager.get_active_device_index()
            if saved and saved.lower() in ("default", "auto", "mặc định", ""):
                short_name = f"Mặc định ({name[:10]}…)" if len(name) > 10 else f"Mặc định ({name})"
            else:
                short_name = name if len(name) <= 16 else (name[:14] + "…")
            if hasattr(self, "btn_mic_select") and self.btn_mic_select:
                self.btn_mic_select.config(text=f"🎤 {short_name} ▾")
        except Exception:
            pass

    def show_mic_menu(self):
        """Open popup dropdown menu allowing user to select or test their microphone."""
        try:
            from app.audio_manager import audio_manager
            devices = audio_manager.list_input_devices(force_refresh=True)
            active_id, active_name = audio_manager.get_active_device_index()
            saved = audio_manager.get_saved_device_name()
            is_default = (saved is None or saved.lower() in ("default", "auto", "mặc định", ""))

            menu = tk.Menu(
                self.root,
                tearoff=0,
                bg="#1e293b",
                fg="#f8fafc",
                activebackground="#0284c7",
                activeforeground="#ffffff",
                font=("Arial", 11)
            )

            for d in devices:
                d_id = d["id"]
                d_name = d["name"]
                if d_id == -1:
                    is_sel = is_default
                else:
                    is_sel = not is_default and (d_id == active_id or d_name == active_name)
                mark = "✔ " if is_sel else "    "
                label = f"{mark}{d_name}"
                def _make_cmd(target_name=d_name):
                    return lambda: self.select_microphone(target_name)
                menu.add_command(label=label, command=_make_cmd())

            menu.add_separator()
            menu.add_command(label="📊 Thử tín hiệu Micro (Test Signal)", command=self.test_current_microphone)

            x = self.btn_mic_select.winfo_rootx()
            y = self.btn_mic_select.winfo_rooty() + self.btn_mic_select.winfo_height() + 4
            menu.tk_popup(x, y)
        except Exception as e:
            logger.error(f"Error opening mic menu: {e}")

    def select_microphone(self, name: str):
        """Save selected microphone and update UI and server."""
        try:
            from app.audio_manager import audio_manager
            audio_manager.set_active_device(name)
            self._update_mic_label()
            self.set_status(f"Đã chọn Micro: {name}", fg="#38bdf8")
            sound_manager.play_click()

            def _notify_server():
                try:
                    url = f"http://{self.host}:{self.port}/api/audio/device"
                    req = urllib.request.Request(
                        url,
                        data=json.dumps({"device": name}).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    urllib.request.urlopen(req, timeout=1.0)
                except Exception:
                    pass
            threading.Thread(target=_notify_server, daemon=True).start()
        except Exception as e:
            logger.error(f"Error selecting microphone: {e}")

    def test_current_microphone(self):
        """Record a live sample with real-time VU meter to verify audio signal from active device."""
        self.set_status("⏳ Đang lắng nghe tín hiệu trực tiếp...", fg="#fbbf24")
        def _test_worker():
            try:
                import sounddevice as sd
                import audioop
                import time
                from app.audio_manager import audio_manager

                dev_idx, dev_name = audio_manager.get_active_device_index()
                dev_info = sd.query_devices(dev_idx) if dev_idx is not None else {}
                sr = int(dev_info.get("default_samplerate", 44100)) if isinstance(dev_info, dict) else 44100
                channels = min(2, int(dev_info.get("max_input_channels", 1))) if isinstance(dev_info, dict) else 1

                chunk_samples = int(sr * 0.1)  # 100ms
                peak_rms = 0
                total_rms = 0
                sample_count = 0
                max_iterations = 15  # 1.5 seconds live test

                with sd.RawInputStream(samplerate=sr, channels=channels, dtype="int16", device=dev_idx, blocksize=chunk_samples) as s:
                    for _ in range(max_iterations):
                        data, _ = s.read(chunk_samples)
                        raw = bytes(data)
                        if channels == 2:
                            raw = audioop.tomono(raw, 2, 0.5, 0.5)
                        chunk_rms = audioop.rms(raw, 2)
                        total_rms += chunk_rms
                        sample_count += 1
                        if chunk_rms > peak_rms:
                            peak_rms = chunk_rms

                        bars = min(12, int(chunk_rms / 250))
                        meter = "█" * bars if bars > 0 else "·"
                        color = "#4ade80" if chunk_rms > 50 else "#38bdf8"
                        self.root.after(0, lambda r=chunk_rms, m=meter, c=color: self.set_status(f"📊 Đang đo: {dev_name} | Mức: {r} [{m}]", fg=c))
                        time.sleep(0.01)

                avg_rms = total_rms // max(1, sample_count)
                if peak_rms > 10:
                    msg = f"✅ Nhận tín hiệu tốt từ [{dev_name}] (RMS: {avg_rms}, Đỉnh: {peak_rms})"
                    col = "#4ade80"
                    sound_manager.play_success()
                else:
                    msg = f"ℹ️ Nguồn [{dev_name}] đã kết nối (chưa có âm thanh phát qua, RMS: 0)."
                    col = "#38bdf8"
                    sound_manager.play_click()

                self.root.after(0, lambda m=msg, c=col: self.set_status(m, fg=c))
            except Exception as e:
                err_str = str(e)
                logger.error(f"Error testing audio source: {err_str}")
                self.root.after(0, lambda err=err_str: self.set_status(f"Lỗi kiểm tra: {err}", fg="#f87171"))
        threading.Thread(target=_test_worker, daemon=True).start()

    def trigger_voice(self):
        """Trigger voice recognition via mic."""
        self.set_status("🎙️ Đang lắng nghe... Hãy nói lệnh vào Micro!", fg="#38bdf8")
        sound_manager.play_start()
        def _req():
            try:
                url = f"http://{self.host}:{self.port}/api/voice/trigger"
                req = urllib.request.Request(
                    url,
                    data=b"{}",
                    headers={"Content-Type": "application/json"}
                )
                urllib.request.urlopen(req, timeout=1.5)
            except Exception:
                pass
        threading.Thread(target=_req, daemon=True).start()

    def quit_app(self):
        """Cleanly terminate the entire unified application and server without triggering crash reporters."""
        logger.info("SpotlightHUD: Graceful quit initiated.")
        try:
            sound_manager.play_done()
        except Exception:
            pass

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

        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
            except Exception:
                pass

        if self.server:
            self.server.should_exit = True

        def _do_exit():
            try:
                if self.root:
                    self.root.quit()
                    self.root.destroy()
            except Exception:
                pass
            sys.exit(0)

        if self.root:
            self.root.after(50, _do_exit)
        else:
            sys.exit(0)

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
