#!/usr/bin/env python3
"""
PS5 ELF Sender - a small GUI that pushes .elf payloads to an ELF loader
listening on your jailbroken PS5 (e.g. elfldr on port 9021).

Features: saved console profiles, ordered payload queue, drag-and-drop
(if tkinterdnd2 is installed), delay between payloads, cancel.

Debian deps:  sudo apt install python3 python3-tk
"""

import json
import os
import socket
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    BaseTk = TkinterDnD.Tk
    HAVE_DND = True
except Exception:  # missing module or no tkdnd library
    BaseTk = tk.Tk
    HAVE_DND = False

VERSION = "1.1.0"

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"),
    "ps5-elf-sender",
)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CHUNK = 64 * 1024
TIMEOUT = 5.0
COMMON_PORTS = ["9021", "9020", "9022"]


# ---------- config ----------
def load_config():
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        cfg = {}
    # migrate v1.0 config (single ip/port/last_file)
    if "profiles" not in cfg:
        cfg["profiles"] = []
        if cfg.get("ip"):
            cfg["profiles"].append(
                {"name": "PS5", "ip": cfg["ip"], "port": int(cfg.get("port", 9021) or 9021)}
            )
            cfg["active_profile"] = "PS5"
    if "queue" not in cfg:
        last = cfg.get("last_file")
        cfg["queue"] = [last] if last else []
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        pass


# ---------- network ----------
def send_file(ip, port, path, on_progress=None, cancel=None):
    """Stream a file to ip:port. Returns bytes sent. Raises OSError on failure,
    InterruptedError if cancelled."""
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
            s.shutdown(socket.SHUT_WR)  # signal end of payload
        except OSError:
            pass
    return sent


def is_elf(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


# ---------- GUI ----------
class App(BaseTk):
    def __init__(self):
        super().__init__()
        self.title(f"PS5 ELF Sender {VERSION}")
        self.geometry("660x680")
        self.minsize(580, 600)

        self.cfg = load_config()
        self.sending = False
        self.cancel = threading.Event()
        self.queue = [p for p in self.cfg.get("queue", []) if os.path.isfile(p)]
        self.profiles = list(self.cfg.get("profiles", []))

        self.profile_var = tk.StringVar(value=self.cfg.get("active_profile", ""))
        self.ip_var = tk.StringVar(value=self.cfg.get("ip", ""))
        self.port_var = tk.StringVar(value=str(self.cfg.get("port", "9021")))
        self.delay_var = tk.StringVar(value=str(self.cfg.get("delay", "1.0")))
        self.status_var = tk.StringVar(value="Idle")

        if not self.ip_var.get():
            self._apply_profile(self.profile_var.get())

        self._build_ui()
        self.refresh_profiles()
        self.refresh_queue()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if HAVE_DND:
            for w in (self, self.listbox):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self.on_drop)
        else:
            self.log_msg("Drag-and-drop disabled (tkinterdnd2 not installed). Use Add files...")

    # ----- layout -----
    def _build_ui(self):
        pad = {"padx": 8, "pady": 5}
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=6, pady=6)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        root.rowconfigure(5, weight=1)

        # console / profile
        con = ttk.LabelFrame(root, text="Console")
        con.grid(row=0, column=0, sticky="ew", **pad)
        con.columnconfigure(1, weight=1)

        ttk.Label(con, text="Profile").grid(row=0, column=0, sticky="w", **pad)
        self.profile_box = ttk.Combobox(con, textvariable=self.profile_var, state="readonly")
        self.profile_box.grid(row=0, column=1, sticky="ew", **pad)
        self.profile_box.bind("<<ComboboxSelected>>", lambda e: self._apply_profile(self.profile_var.get()))
        pbtn = ttk.Frame(con)
        pbtn.grid(row=0, column=2, **pad)
        ttk.Button(pbtn, text="Save", width=7, command=self.save_profile).pack(side="left", padx=(0, 4))
        ttk.Button(pbtn, text="Delete", width=7, command=self.delete_profile).pack(side="left")

        ttk.Label(con, text="IP").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(con, textvariable=self.ip_var).grid(row=1, column=1, sticky="ew", **pad)
        row2 = ttk.Frame(con)
        row2.grid(row=1, column=2, **pad)
        ttk.Label(row2, text="Port").pack(side="left", padx=(0, 4))
        ttk.Combobox(row2, textvariable=self.port_var, values=COMMON_PORTS, width=7).pack(side="left")

        # queue
        ttk.Label(root, text="Payload queue (drag .elf files here)" if HAVE_DND else "Payload queue").grid(
            row=1, column=0, sticky="w", padx=10
        )
        qf = ttk.Frame(root)
        qf.grid(row=2, column=0, sticky="nsew", **pad)
        qf.columnconfigure(0, weight=1)
        qf.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(qf, selectmode="extended", activestyle="none", height=8)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(qf, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)
        qbtn = ttk.Frame(qf)
        qbtn.grid(row=0, column=2, sticky="n", padx=(8, 0))
        for text, cmd in (
            ("Add files...", self.add_files),
            ("Remove", self.remove_selected),
            ("Move up", lambda: self.move(-1)),
            ("Move down", lambda: self.move(1)),
            ("Clear", self.clear_queue),
        ):
            ttk.Button(qbtn, text=text, command=cmd, width=12).pack(pady=2)

        # delay + actions
        opts = ttk.Frame(root)
        opts.grid(row=3, column=0, sticky="ew", **pad)
        ttk.Label(opts, text="Delay between payloads (s)").pack(side="left")
        ttk.Spinbox(opts, from_=0, to=60, increment=0.5, width=6, textvariable=self.delay_var).pack(
            side="left", padx=6
        )

        act = ttk.Frame(root)
        act.grid(row=4, column=0, sticky="ew", **pad)
        self.test_btn = ttk.Button(act, text="Test connection", command=self.test_connection)
        self.test_btn.pack(side="left")
        self.cancel_btn = ttk.Button(act, text="Cancel", command=self.cancel.set, state="disabled")
        self.cancel_btn.pack(side="right")
        self.send_all_btn = ttk.Button(act, text="Send all", command=self.send_all)
        self.send_all_btn.pack(side="right", padx=6)
        self.send_sel_btn = ttk.Button(act, text="Send selected", command=self.send_selected)
        self.send_sel_btn.pack(side="right")

        # progress + log
        pf = ttk.Frame(root)
        pf.grid(row=5, column=0, sticky="nsew", **pad)
        pf.columnconfigure(0, weight=1)
        pf.rowconfigure(2, weight=1)
        ttk.Label(pf, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(pf, mode="determinate")
        self.progress.grid(row=1, column=0, sticky="ew", pady=4)
        self.log = tk.Text(pf, height=8, state="disabled", wrap="word")
        self.log.grid(row=2, column=0, sticky="nsew")

    # ----- thread-safe UI helpers -----
    def log_msg(self, msg):
        def _do():
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        self.after(0, _do)

    def set_status(self, text):
        self.after(0, lambda: self.status_var.set(text))

    def set_progress(self, value, maximum=None):
        def _do():
            if maximum is not None:
                self.progress.configure(maximum=max(maximum, 1))
            self.progress["value"] = value

        self.after(0, _do)

    def set_busy(self, busy):
        def _do():
            idle = "disabled" if busy else "normal"
            for b in (self.test_btn, self.send_all_btn, self.send_sel_btn):
                b.configure(state=idle)
            self.cancel_btn.configure(state="normal" if busy else "disabled")

        self.sending = busy
        self.after(0, _do)

    # ----- profiles -----
    def refresh_profiles(self):
        self.profile_box["values"] = [p["name"] for p in self.profiles]

    def _apply_profile(self, name):
        for p in self.profiles:
            if p["name"] == name:
                self.ip_var.set(p["ip"])
                self.port_var.set(str(p["port"]))
                return

    def save_profile(self):
        target = self.get_target()
        if not target:
            return
        name = simpledialog.askstring(
            "Save profile", "Profile name:", initialvalue=self.profile_var.get() or "PS5", parent=self
        )
        if not name or not name.strip():
            return
        name = name.strip()
        ip, port = target
        for p in self.profiles:
            if p["name"] == name:
                p["ip"], p["port"] = ip, port
                break
        else:
            self.profiles.append({"name": name, "ip": ip, "port": port})
        self.profile_var.set(name)
        self.refresh_profiles()
        self.persist()

    def delete_profile(self):
        name = self.profile_var.get()
        if not name:
            return
        if messagebox.askyesno("Delete profile", f"Delete profile '{name}'?"):
            self.profiles = [p for p in self.profiles if p["name"] != name]
            self.profile_var.set("")
            self.refresh_profiles()
            self.persist()

    # ----- queue -----
    def refresh_queue(self, select=None):
        self.listbox.delete(0, "end")
        for p in self.queue:
            try:
                size = human_size(os.path.getsize(p))
            except OSError:
                size = "missing"
            self.listbox.insert("end", f"{os.path.basename(p)}    ({size})    {os.path.dirname(p)}")
        for i in select or []:
            self.listbox.selection_set(i)

    def add_path(self, path):
        path = os.path.abspath(path)
        if os.path.isfile(path) and path not in self.queue:
            self.queue.append(path)
            return True
        return False

    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select ELF payloads",
            filetypes=[("ELF files", "*.elf"), ("All files", "*.*")],
        )
        for p in paths:
            self.add_path(p)
        self.refresh_queue()

    def on_drop(self, event):
        for p in self.tk.splitlist(event.data):
            self.add_path(p)
        self.refresh_queue()

    def remove_selected(self):
        sel = set(self.listbox.curselection())
        self.queue = [p for i, p in enumerate(self.queue) if i not in sel]
        self.refresh_queue()

    def move(self, delta):
        sel = self.listbox.curselection()
        if len(sel) != 1:
            return
        i = sel[0]
        j = i + delta
        if 0 <= j < len(self.queue):
            self.queue[i], self.queue[j] = self.queue[j], self.queue[i]
            self.refresh_queue(select=[j])

    def clear_queue(self):
        self.queue = []
        self.refresh_queue()

    # ----- target / actions -----
    def get_target(self):
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showerror("Missing IP", "Enter your PS5's IP address.")
            return None
        try:
            port = int(self.port_var.get().strip())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror("Bad port", "Port must be a number from 1 to 65535.")
            return None
        return ip, port

    def get_delay(self):
        try:
            return max(0.0, float(self.delay_var.get()))
        except ValueError:
            return 1.0

    def test_connection(self):
        target = self.get_target()
        if not target or self.sending:
            return
        self.set_busy(True)
        threading.Thread(target=self._test_worker, args=target, daemon=True).start()

    def _test_worker(self, ip, port):
        try:
            with socket.create_connection((ip, port), timeout=TIMEOUT):
                self.log_msg(f"[ok] {ip}:{port} is accepting connections.")
        except OSError as e:
            self.log_msg(f"[fail] Could not reach {ip}:{port} - {e}")
        finally:
            self.set_busy(False)

    def send_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Nothing selected", "Select one or more payloads, or use Send all.")
            return
        self._start_send([self.queue[i] for i in sel])

    def send_all(self):
        if not self.queue:
            messagebox.showinfo("Queue empty", "Add or drop some .elf files first.")
            return
        self._start_send(list(self.queue))

    def _start_send(self, paths):
        target = self.get_target()
        if not target or self.sending:
            return
        missing = [p for p in paths if not os.path.isfile(p)]
        if missing:
            messagebox.showerror("File missing", "Not found:\n" + "\n".join(missing))
            return
        non_elf = [os.path.basename(p) for p in paths if not is_elf(p)]
        if non_elf and not messagebox.askyesno(
            "Not an ELF?",
            "These files don't start with an ELF header:\n\n" + "\n".join(non_elf) + "\n\nSend anyway?",
        ):
            return
        self.cancel.clear()
        self.set_busy(True)
        threading.Thread(
            target=self._send_worker, args=(*target, paths, self.get_delay()), daemon=True
        ).start()

    def _wait(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.cancel.is_set():
                return False
            time.sleep(0.05)
        return True

    def _send_worker(self, ip, port, paths, delay):
        total, ok = len(paths), 0
        try:
            for n, path in enumerate(paths, 1):
                name = os.path.basename(path)
                self.set_status(f"Sending {n}/{total}: {name}")
                self.set_progress(0, 1)
                self.log_msg(f"[{n}/{total}] {name} -> {ip}:{port}")
                try:
                    sent = send_file(ip, port, path, on_progress=self.set_progress, cancel=self.cancel)
                except InterruptedError:
                    self.log_msg("[cancelled]")
                    break
                except OSError as e:
                    self.log_msg(f"[error] {name}: {e}")
                    break
                ok += 1
                self.log_msg(f"[ok] {sent:,} bytes sent")
                if n < total and not self._wait(delay):
                    self.log_msg("[cancelled]")
                    break
        finally:
            self.log_msg(f"Finished: {ok}/{total} sent.")
            self.set_status("Idle")
            self.set_busy(False)

    # ----- persistence -----
    def persist(self):
        save_config(
            {
                "ip": self.ip_var.get().strip(),
                "port": self.port_var.get().strip(),
                "delay": self.delay_var.get().strip(),
                "active_profile": self.profile_var.get(),
                "profiles": self.profiles,
                "queue": self.queue,
            }
        )

    def _on_close(self):
        self.cancel.set()
        self.persist()
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
