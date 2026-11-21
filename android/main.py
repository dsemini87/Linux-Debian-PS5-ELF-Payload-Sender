"""
PS5 ELF Sender - Android (Kivy) version.

Same job as the desktop app: stream .elf payloads over TCP to an ELF loader
on a jailbroken PS5 (e.g. elfldr on port 9021). Tkinter does not run on
Android, so this is a separate, smaller UI around the same send logic.
"""

import json
import os
import socket
import threading
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

CHUNK = 64 * 1024
TIMEOUT = 5.0


def send_file(ip, port, path, on_progress=None, cancel=None):
    size = os.path.getsize(path)
    sent = 0
    with socket.create_connection((ip, port), timeout=TIMEOUT) as s, open(path, "rb") as f:
        s.settimeout(30)
        while True:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("cancelled")
            chunk = f.read(CHUNK)
            if not chunk:
                break
            s.sendall(chunk)
            sent += len(chunk)
            if on_progress:
                on_progress(sent, size)
        try:
            s.shutdown(socket.SHUT_WR)
        except OSError:
            pass
    return sent


class Root(BoxLayout):
    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", spacing=dp(6), padding=dp(10), **kw)
        self.app = app
        self.cancel = threading.Event()
        self.sending = False
        cfg = app.load_cfg()
        self.queue = [p for p in cfg.get("queue", []) if os.path.isfile(p)]

        self.ip = TextInput(
            text=cfg.get("ip", ""), hint_text="PS5 IP (e.g. 192.168.1.50)",
            multiline=False, size_hint_y=None, height=dp(44), input_filter=None,
        )
        self.port = TextInput(
            text=str(cfg.get("port", "9021")), hint_text="Port",
            multiline=False, size_hint_y=None, height=dp(44), input_filter="int",
        )
        self.delay = TextInput(
            text=str(cfg.get("delay", "1.0")), hint_text="Delay (s)",
            multiline=False, size_hint_y=None, height=dp(44), input_filter="float",
        )
        row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        row.add_widget(self.port)
        row.add_widget(self.delay)

        self.queue_label = Label(size_hint_y=None, halign="left", valign="top")
        self.queue_label.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        self.queue_label.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1] + dp(8)))
        qscroll = ScrollView(size_hint_y=0.3)
        qscroll.add_widget(self.queue_label)

        qbtns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        qbtns.add_widget(Button(text="Add files", on_release=lambda *_: self.pick_files()))
        qbtns.add_widget(Button(text="Remove last", on_release=lambda *_: self.remove_last()))
        qbtns.add_widget(Button(text="Clear", on_release=lambda *_: self.clear()))

        abtns = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.test_btn = Button(text="Test", on_release=lambda *_: self.test())
        self.send_btn = Button(text="Send all", on_release=lambda *_: self.send_all())
        self.cancel_btn = Button(text="Cancel", disabled=True, on_release=lambda *_: self.cancel.set())
        for b in (self.test_btn, self.send_btn, self.cancel_btn):
            abtns.add_widget(b)

        self.status = Label(text="Idle", size_hint_y=None, height=dp(24))
        self.progress = ProgressBar(max=1, value=0, size_hint_y=None, height=dp(16))

        self.log = Label(size_hint_y=None, halign="left", valign="top", text="")
        self.log.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        self.log.bind(texture_size=lambda w, ts: setattr(w, "height", ts[1] + dp(8)))
        self.log_scroll = ScrollView()
        self.log_scroll.add_widget(self.log)

        for w in (self.ip, row, Label(text="Payload queue", size_hint_y=None, height=dp(24)),
                  qscroll, qbtns, abtns, self.status, self.progress, self.log_scroll):
            self.add_widget(w)
        self.refresh_queue()

    # ----- UI helpers (safe from any thread) -----
    def ui(self, fn):
        Clock.schedule_once(lambda dt: fn(), 0)

    def log_msg(self, msg):
        def _do():
            lines = (self.log.text + msg + "\n").splitlines()[-200:]
            self.log.text = "\n".join(lines) + "\n"
            self.log_scroll.scroll_y = 0
        self.ui(_do)

    def set_status(self, text):
        self.ui(lambda: setattr(self.status, "text", text))

    def set_progress(self, value, maximum):
        def _do():
            self.progress.max = max(maximum, 1)
            self.progress.value = value
        self.ui(_do)

    def set_busy(self, busy):
        def _do():
            self.test_btn.disabled = busy
            self.send_btn.disabled = busy
            self.cancel_btn.disabled = not busy
        self.sending = busy
        self.ui(_do)

    # ----- queue -----
    def refresh_queue(self):
        if self.queue:
            self.queue_label.text = "\n".join(f"{i+1}. {os.path.basename(p)}" for i, p in enumerate(self.queue))
        else:
            self.queue_label.text = "(empty - tap Add files)"

    def pick_files(self):
        try:
            from plyer import filechooser

            filechooser.open_file(on_selection=self.on_picked, multiple=True)
        except Exception as e:  # plyer missing or chooser unavailable
            self.log_msg(f"[error] File picker unavailable: {e}")

    def on_picked(self, selection):
        added = 0
        for p in selection or []:
            if p and os.path.isfile(p) and p not in self.queue:
                self.queue.append(p)
                added += 1
        if selection and not added:
            self.log_msg("[warn] Couldn't read the selected file(s). Try one from the Downloads folder.")
        self.ui(self.refresh_queue)

    def remove_last(self):
        if self.queue:
            self.queue.pop()
            self.refresh_queue()

    def clear(self):
        self.queue = []
        self.refresh_queue()

    # ----- actions -----
    def target(self):
        ip = self.ip.text.strip()
        try:
            port = int(self.port.text.strip())
            if not ip or not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.log_msg("[error] Enter a valid IP and port.")
            return None
        return ip, port

    def test(self):
        t = self.target()
        if not t or self.sending:
            return
        self.set_busy(True)

        def work():
            try:
                with socket.create_connection(t, timeout=TIMEOUT):
                    self.log_msg(f"[ok] {t[0]}:{t[1]} is accepting connections.")
            except OSError as e:
                self.log_msg(f"[fail] {t[0]}:{t[1]} - {e}")
            finally:
                self.set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def send_all(self):
        t = self.target()
        if not t or self.sending:
            return
        if not self.queue:
            self.log_msg("[warn] Queue is empty.")
            return
        try:
            delay = max(0.0, float(self.delay.text or 0))
        except ValueError:
            delay = 1.0
        self.cancel.clear()
        self.set_busy(True)
        threading.Thread(target=self._worker, args=(*t, list(self.queue), delay), daemon=True).start()

    def _worker(self, ip, port, paths, delay):
        total, ok = len(paths), 0
        try:
            for n, path in enumerate(paths, 1):
                name = os.path.basename(path)
                self.set_status(f"Sending {n}/{total}: {name}")
                self.set_progress(0, 1)
                self.log_msg(f"[{n}/{total}] {name} -> {ip}:{port}")
                try:
                    sent = send_file(ip, port, path, self.set_progress, self.cancel)
                except InterruptedError:
                    self.log_msg("[cancelled]")
                    break
                except OSError as e:
                    self.log_msg(f"[error] {name}: {e}")
                    break
                ok += 1
                self.log_msg(f"[ok] {sent:,} bytes sent")
                if n < total:
                    end = time.monotonic() + delay
                    while time.monotonic() < end and not self.cancel.is_set():
                        time.sleep(0.05)
                    if self.cancel.is_set():
                        self.log_msg("[cancelled]")
                        break
        finally:
            self.log_msg(f"Finished: {ok}/{total} sent.")
            self.set_status("Idle")
            self.set_busy(False)

    def state(self):
        return {
            "ip": self.ip.text.strip(),
            "port": self.port.text.strip(),
            "delay": self.delay.text.strip(),
            "queue": self.queue,
        }


class PS5ElfSenderApp(App):
    title = "PS5 ELF Sender"

    def cfg_path(self):
        return os.path.join(self.user_data_dir, "config.json")

    def load_cfg(self):
        try:
            with open(self.cfg_path()) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def build(self):
        if platform == "android":
            try:
                from android.permissions import Permission, request_permissions

                request_permissions([Permission.READ_EXTERNAL_STORAGE])
            except Exception:
                pass
        self.root_widget = Root(self)
        return self.root_widget

    def on_stop(self):
        try:
            with open(self.cfg_path(), "w") as f:
                json.dump(self.root_widget.state(), f)
        except OSError:
            pass

    def on_pause(self):
        return True  # keep running if the user switches apps mid-send


if __name__ == "__main__":
    PS5ElfSenderApp().run()
