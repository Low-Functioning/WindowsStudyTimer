"""
Simple Study Timer for Windows 10
- Standard library only (tkinter, winsound, ctypes). No installs needed.
- Double-click StudyTimer.pyw to run (no console window).
"""
import ctypes
import json
import math
import os
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import date
from tkinter import messagebox

try:
    import winsound
except ImportError:  
    winsound = None

# ----------------------------- Settings ------------------------------------
PRESETS = [5, 10, 20, 25, 30, 35, 40]
REMINDER_EVERY_SEC = 7 * 60      # soft reminder interval
REMINDER_SHOW_MS = 4000          # how long the overlay stays
DEFAULT_MINUTES = 25

BG, CARD, FG, MUTED = "#1e1f26", "#2a2c36", "#f2f3f7", "#8d91a3"
ACCENT, ACCENT_H, DANGER = "#4f8cff", "#6b9fff", "#ff5d5d"
FONT = "Segoe UI"

STATS_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "StudyTimer")
STATS_FILE = os.path.join(STATS_DIR, "stats.json")

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


def load_timer_font():
    """Privately load the Digital-7 .ttf (kept next to this script)."""
    folder = os.path.dirname(os.path.abspath(__file__))
    for d in (folder, os.getcwd()):
        try:
            names = [n for n in os.listdir(d)
                     if n.lower().endswith(".ttf") and "digital" in n.lower()]
        except OSError:
            continue
        for n in names:
            try:
                added = ctypes.windll.gdi32.AddFontResourceExW(os.path.join(d, n), 0x10, 0)  # FR_PRIVATE
                if added:
                    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001D, 0, 0, 2, 1000, None)  # WM_FONTCHANGE
                    return "Digital-7"
            except Exception:
                pass
    return "Digital-7"


TIME_FONT = load_timer_font()
MINI_W = 150             # px, width of the small always-on-top clock
MINI_H = 70              # px, height of the small always-on-top clock
MINI_ALPHA = 0.45        # idle opacity
MINI_ALPHA_HOVER = 0.9   # opacity while the mouse is over it


class SevenSeg(tk.Canvas):
    """Seven-segment clock drawn on a canvas (used if the font cannot be loaded)."""
    SEG = {"0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
           "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg"}

    def __init__(self, parent, w, h, bg):
        super().__init__(parent, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
        self.w, self.h, self.bgc = w, h, bg
        self.ghost = "#2c2e38" if bg != "#14151a" else "#22242c"

    def show(self, text, fg):
        self.delete("all")
        n_d = sum(c.isdigit() for c in text)
        n_c = len(text) - n_d
        gap = self.h * 0.12
        dh = self.h * 0.92
        dw = min(dh * 0.55, (self.w - gap * (len(text) - 1)) / max(1, n_d + n_c * 0.35))
        cw = dw * 0.35
        total = n_d * dw + n_c * cw + gap * (len(text) - 1)
        x = (self.w - total) / 2
        y0 = (self.h - dh) / 2
        for ch in text:
            if ch.isdigit():
                self._digit(x, y0, dw, dh, ch, fg)
                x += dw + gap
            else:
                t = dh * 0.1
                for yy in (y0 + dh * 0.32, y0 + dh * 0.68):
                    self.create_rectangle(x + cw / 2 - t / 2, yy - t / 2, x + cw / 2 + t / 2,
                                          yy + t / 2, fill=fg, outline="")
                x += cw + gap

    def _poly(self, pts, color):
        self.create_polygon(pts, fill=color, outline="")

    def _digit(self, x, y, w, h, ch, fg):
        t, g = h * 0.1, h * 0.012
        xl, xr, yt, ym, yb = x + t / 2, x + w - t / 2, y + t / 2, y + h / 2, y + h - t / 2

        def hs(x1, x2, yy):
            x1, x2 = x1 + g, x2 - g
            return [x1, yy, x1 + t / 2, yy - t / 2, x2 - t / 2, yy - t / 2,
                    x2, yy, x2 - t / 2, yy + t / 2, x1 + t / 2, yy + t / 2]

        def vs(xx, y1, y2):
            y1, y2 = y1 + g, y2 - g
            return [xx, y1, xx + t / 2, y1 + t / 2, xx + t / 2, y2 - t / 2,
                    xx, y2, xx - t / 2, y2 - t / 2, xx - t / 2, y1 + t / 2]

        segs = {"a": hs(xl, xr, yt), "g": hs(xl, xr, ym), "d": hs(xl, xr, yb),
                "f": vs(xl, yt, ym), "e": vs(xl, ym, yb),
                "b": vs(xr, yt, ym), "c": vs(xr, ym, yb)}
        on = self.SEG.get(ch, "")
        for k, pts in segs.items():
            self._poly(pts, fg if k in on else self.ghost)


class FontClock(tk.Label):
    def show(self, text, fg):
        self.config(text=text, fg=fg)


# ----------------------------- Helpers -------------------------------------
def fmt_clock(sec):
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def fmt_long(sec):
    sec = int(sec)
    h, m = sec // 3600, (sec % 3600) // 60
    return f"{h}h {m:02d}m" if h else f"{m}m"


def load_stats():
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data.get("days"), dict) else {"days": {}}
    except Exception:
        return {"days": {}}


def save_stats(stats):
    try:
        os.makedirs(STATS_DIR, exist_ok=True)
        tmp = STATS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(stats, f)
        os.replace(tmp, STATS_FILE)
    except Exception:
        pass


def make_noactivate_clickthrough(window, clickthrough=True):
    """Window never steals focus; optionally mouse clicks pass through it."""
    try:
        window.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= 0x08000000 | 0x00000080 | 0x00080000 | 0x00000008
        # NOACTIVATE | TOOLWINDOW | LAYERED | TOPMOST
        if clickthrough:
            style |= 0x00000020  # TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass


# ----------------------------- App -----------------------------------------
class StudyTimer:
    def __init__(self, root):
        self.root = root
        root.title("Study Timer")
        root.configure(bg=BG)
        root.geometry("420x470")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.stats = load_stats()
        self.today_key = date.today().isoformat()
        self.state = "idle"            # idle | running | paused
        self.duration = DEFAULT_MINUTES * 60
        self.remaining = float(self.duration)
        self.elapsed = 0.0             # running seconds this session
        self.next_reminder = REMINDER_EVERY_SEC
        self.last_tick = time.monotonic()
        self.last_save = time.monotonic()
        self.overlay = None
        self.overlay_job = None
        self.alert_win = None
        self.alert_stop = None
        self.on_top = tk.BooleanVar(value=False)
        self.mini = None
        self._last_shown = None
        self.mini_lbl = None
        self.mini_pos = None
        self.use_font = TIME_FONT in tkfont.families(root)
        self.main_font = tkfont.Font(family=TIME_FONT, size=88)
        self.mini_px = 40
        self.mini_font = tkfont.Font(family=TIME_FONT, size=-40)

        self.build_ui()
        self.refresh()
        root.bind("<space>", self._space)
        self.tick()

    # ---------------- UI ----------------
    def build_ui(self):
        r = self.root

        if self.use_font:
            self.time_lbl = FontClock(r, text="25:00", font=self.main_font, bg=BG, fg=FG)
        else:
            self.time_lbl = SevenSeg(r, 380, 130, BG)
        self.time_lbl.pack(pady=(14, 0))
        self.status_lbl = tk.Label(r, text="Ready", font=(FONT, 11), bg=BG, fg=MUTED)
        self.status_lbl.pack()

        # presets
        pf = tk.Frame(r, bg=BG)
        pf.pack(pady=(16, 6))
        self.preset_btns = []
        for m in PRESETS:
            b = self.button(pf, str(m), lambda m=m: self.set_minutes(m), CARD, width=4, size=11)
            b.pack(side="left", padx=3)
            self.preset_btns.append(b)
        tk.Label(r, text="minutes", font=(FONT, 9), bg=BG, fg=MUTED).pack()

        # custom
        cf = tk.Frame(r, bg=BG)
        cf.pack(pady=8)
        tk.Label(cf, text="Custom:", font=(FONT, 11), bg=BG, fg=MUTED).pack(side="left", padx=(0, 6))
        self.entry_var = tk.StringVar(value=str(DEFAULT_MINUTES))
        self.entry = tk.Entry(cf, textvariable=self.entry_var, width=6, justify="center",
                              font=(FONT, 13), bg=CARD, fg=FG, insertbackground=FG,
                              relief="flat", highlightthickness=1,
                              highlightbackground=CARD, highlightcolor=ACCENT)
        self.entry.pack(side="left", ipady=3)
        self.entry.bind("<Return>", lambda e: self.apply_entry())
        self.entry.bind("<FocusOut>", lambda e: self.apply_entry(silent=True))
        tk.Label(cf, text="min", font=(FONT, 11), bg=BG, fg=MUTED).pack(side="left", padx=(6, 0))

        # controls
        bf = tk.Frame(r, bg=BG)
        bf.pack(pady=14)
        self.main_btn = self.button(bf, "Start", self.toggle, ACCENT, width=10, size=14)
        self.main_btn.pack(side="left", padx=5, ipady=4)
        self.reset_btn = self.button(bf, "Reset", self.reset, CARD, width=8, size=14)
        self.reset_btn.pack(side="left", padx=5, ipady=4)

        # studied block
        sf = tk.Frame(r, bg=CARD)
        sf.pack(fill="x", padx=24, pady=(6, 0))
        tk.Label(sf, text="TIME STUDIED", font=(FONT, 8, "bold"), bg=CARD, fg=MUTED).pack(pady=(8, 0))
        row = tk.Frame(sf, bg=CARD)
        row.pack(pady=(2, 8))
        self.today_lbl = tk.Label(row, text="", font=(FONT, 13, "bold"), bg=CARD, fg=FG)
        self.today_lbl.pack(side="left", padx=14)
        self.total_lbl = tk.Label(row, text="", font=(FONT, 13, "bold"), bg=CARD, fg=FG)
        self.total_lbl.pack(side="left", padx=14)

        # footer
        ff = tk.Frame(r, bg=BG)
        ff.pack(fill="x", padx=24, pady=8)
        tk.Checkbutton(ff, text="Always on top", variable=self.on_top, command=self.apply_topmost,
                       bg=BG, fg=MUTED, selectcolor=CARD, activebackground=BG,
                       activeforeground=FG, font=(FONT, 9), bd=0, highlightthickness=0).pack(side="left")
        clr = tk.Label(ff, text="Clear stats", font=(FONT, 9, "underline"), bg=BG, fg=MUTED, cursor="hand2")
        clr.pack(side="right")
        clr.bind("<Button-1>", lambda e: self.clear_stats())

    def button(self, parent, text, cmd, color, width, size):
        hover = ACCENT_H if color == ACCENT else "#363948"
        b = tk.Button(parent, text=text, command=cmd, width=width, font=(FONT, size, "bold"),
                      bg=color, fg=FG, activebackground=hover, activeforeground=FG,
                      relief="flat", bd=0, cursor="hand2", highlightthickness=0)
        b.bind("<Enter>", lambda e: b.config(bg=hover) if str(b["state"]) == "normal" else None)
        b.bind("<Leave>", lambda e: b.config(bg=color))
        return b

    # ---------------- Controls ----------------
    def _space(self, e):
        if self.root.focus_get() is not self.entry:
            self.toggle()

    def apply_topmost(self):
        if self.on_top.get():
            self.enter_mini()
        else:
            self.exit_mini()

    # ---------------- Mini always-on-top clock ----------------
    def enter_mini(self):
        if self.mini:
            return
        m = tk.Toplevel(self.root)
        self.mini = m
        m.overrideredirect(True)
        m.attributes("-topmost", True)
        m.attributes("-alpha", MINI_ALPHA)
        m.configure(bg="#14151a")
        sw = m.winfo_screenwidth()
        scale = m.winfo_fpixels("1i") / 96                 # follow Windows display scaling
        w, h = int(MINI_W * scale), int(MINI_H * scale)
        self.mini_px = int(min(0.44 * w, 1.0 * h))         # digit size fitted to the box
        x, y = self.mini_pos or (sw - w - 20, 60)
        m.geometry(f"{w}x{h}+{x}+{y}")
        if self.use_font:
            self.mini_lbl = FontClock(m, text="", font=self.mini_font, bg="#14151a", fg=FG)
        else:
            self.mini_lbl = SevenSeg(m, int(w * 0.92), int(h * 0.78), "#14151a")
        self.mini_lbl.place(relx=0.5, rely=0.5, anchor="center")

        menu = tk.Menu(m, tearoff=0, bg=CARD, fg=FG, activebackground=ACCENT, bd=0)
        menu.add_command(label="Start / Pause", command=self.toggle)
        menu.add_command(label="Reset", command=self.reset)
        menu.add_separator()
        menu.add_command(label="Show full window", command=self.exit_mini)
        menu.add_command(label="Quit", command=self.on_close)

        drag = {}
        def press(e):
            drag["x"], drag["y"] = e.x_root - m.winfo_x(), e.y_root - m.winfo_y()
        def move(e):
            nx, ny = e.x_root - drag["x"], e.y_root - drag["y"]
            m.geometry(f"+{nx}+{ny}")
            self.mini_pos = (nx, ny)
        def popup(e):
            menu.tk_popup(e.x_root, e.y_root)
        for wd in (m, self.mini_lbl):
            wd.bind("<ButtonPress-1>", press)
            wd.bind("<B1-Motion>", move)
            wd.bind("<Double-Button-1>", lambda e: self.exit_mini())
            wd.bind("<Button-3>", popup)
            wd.bind("<Enter>", lambda e: m.attributes("-alpha", MINI_ALPHA_HOVER))
            wd.bind("<Leave>", lambda e: m.attributes("-alpha", MINI_ALPHA))

        make_noactivate_clickthrough(m, clickthrough=False)
        self.root.withdraw()
        self._last_shown = None
        self.refresh()

    def exit_mini(self):
        if self.mini:
            self.mini_pos = (self.mini.winfo_x(), self.mini.winfo_y())
            self.mini.destroy()
            self.mini = self.mini_lbl = None
        self.on_top.set(False)
        self.root.deiconify()
        self.root.lift()

    def set_minutes(self, m):
        if self.state != "idle":
            self.reset()
        self.entry_var.set(str(m))
        self.apply_entry(silent=True)

    def apply_entry(self, silent=False):
        """Read custom minutes from the entry (idle only)."""
        if self.state != "idle":
            return True
        try:
            m = float(self.entry_var.get().replace(",", "."))
            if not (0 < m <= 1440):
                raise ValueError
        except ValueError:
            if not silent:
                messagebox.showwarning("Study Timer", "Enter minutes between 1 and 1440.")
            self.entry_var.set(str(int(self.duration // 60)) if self.duration % 60 == 0 else f"{self.duration/60:g}")
            return False
        self.duration = int(round(m * 60))
        self.remaining = float(self.duration)
        self.refresh()
        return True

    def toggle(self):
        if self.state == "idle":
            if not self.apply_entry():
                return
            self.elapsed = 0.0
            self.next_reminder = REMINDER_EVERY_SEC
            self.start_running()
        elif self.state == "running":
            self.state = "paused"
            self.save()
        else:
            self.start_running()
        self.refresh()

    def start_running(self):
        self.state = "running"
        self.last_tick = time.monotonic()
        self.root.focus_set()

    def reset(self):
        if self.state != "idle":
            self.save()
        self.state = "idle"
        self.hide_overlay()
        self.remaining = float(self.duration)
        self.elapsed = 0.0
        self.next_reminder = REMINDER_EVERY_SEC
        self.refresh()

    # ---------------- Main loop ----------------
    def tick(self):
        now = time.monotonic()
        dt = now - self.last_tick
        self.last_tick = now

        # roll over at midnight
        if date.today().isoformat() != self.today_key:
            self.save()
            self.today_key = date.today().isoformat()

        if self.state == "running":
            dt = min(dt, 1.0)  # don't count PC sleep / long stalls as study time
            self.remaining -= dt
            self.elapsed += dt
            self.stats["days"][self.today_key] = self.stats["days"].get(self.today_key, 0) + dt

            if self.remaining <= 0:
                self.finish()
            elif self.elapsed >= self.next_reminder:
                self.next_reminder += REMINDER_EVERY_SEC
                if self.remaining > 5:
                    self.show_overlay(f"{fmt_clock(math.ceil(self.remaining))} remaining")

            if now - self.last_save > 30:
                self.save()

        self.refresh()
        self.root.after(250, self.tick)

    def finish(self):
        self.state = "idle"
        self.remaining = 0
        self.save()
        self.hide_overlay()
        self.refresh()
        self.show_alert()

    # ---------------- Display ----------------
    def refresh(self):
        shown = math.ceil(self.remaining) if self.state != "idle" else int(self.remaining)
        text = fmt_clock(shown)
        color = ACCENT if self.state == "running" else FG
        n = max(5, len(text))
        self.main_font.configure(size=int(88 * 5 / n))
        self.mini_font.configure(size=-int(self.mini_px * 5 / n))
        key = (text, color)
        if key != self._last_shown:
            self._last_shown = key
            self.time_lbl.show(text, color)
            if self.mini_lbl:
                self.mini_lbl.show(text, color)
        self.status_lbl.config(text={"idle": "Ready", "running": "Studying…", "paused": "Paused"}[self.state])
        self.main_btn.config(text={"idle": "Start", "running": "Pause", "paused": "Resume"}[self.state])

        idle = self.state == "idle"
        for b in self.preset_btns:
            b.config(state="normal" if idle else "disabled")
        self.entry.config(state="normal" if idle else "disabled")

        title = f"{text} – Study Timer" if self.state != "idle" else "Study Timer"
        if self.root.title() != title:
            self.root.title(title)

        days = self.stats["days"]
        self.today_lbl.config(text=f"Today  {fmt_long(days.get(self.today_key, 0))}")
        self.total_lbl.config(text=f"All time  {fmt_long(sum(days.values()))}")

    # ---------------- Soft reminder overlay ----------------
    def show_overlay(self, text):
        self.hide_overlay()
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.88)
        ov.configure(bg="#14151a")
        tk.Label(ov, text=text, font=(FONT, 13), bg="#14151a", fg="#e8eaf2",
                 padx=18, pady=10).pack()
        ov.update_idletasks()
        w, h = ov.winfo_reqwidth(), ov.winfo_reqheight()
        ov.geometry(f"{w}x{h}+{ov.winfo_screenwidth() - w - 20}+20")
        make_noactivate_clickthrough(ov)
        self.overlay = ov
        self.overlay_job = self.root.after(REMINDER_SHOW_MS, self.hide_overlay)

    def hide_overlay(self):
        if self.overlay_job:
            self.root.after_cancel(self.overlay_job)
            self.overlay_job = None
        if self.overlay:
            try:
                self.overlay.destroy()
            except Exception:
                pass
            self.overlay = None

    # ---------------- Completion alert ----------------
    def show_alert(self):
        if self.alert_win:
            return
        # sound loops in a background thread until acknowledged
        self.alert_stop = threading.Event()
        threading.Thread(target=self._alarm_loop, args=(self.alert_stop,), daemon=True).start()

        w = tk.Toplevel(self.root)
        self.alert_win = w
        w.title("Time's up!")
        w.configure(bg=ACCENT)
        w.attributes("-topmost", True)
        w.resizable(False, False)
        w.protocol("WM_DELETE_WINDOW", self.dismiss_alert)
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        w.geometry(f"460x240+{(sw - 460) // 2}+{(sh - 240) // 2}")

        tk.Label(w, text="⏰  Time's up!", font=(FONT, 34, "bold"), bg=ACCENT, fg="white").pack(pady=(32, 4))
        mins = self.duration / 60
        tk.Label(w, text=f"{mins:g}-minute session complete", font=(FONT, 13),
                 bg=ACCENT, fg="#e6efff").pack()
        tk.Button(w, text="OK", command=self.dismiss_alert, font=(FONT, 14, "bold"), width=12,
                  bg="white", fg=ACCENT, activebackground="#e6efff", relief="flat",
                  cursor="hand2").pack(pady=24, ipady=4)
        w.bind("<Return>", lambda e: self.dismiss_alert())
        w.bind("<space>", lambda e: self.dismiss_alert())

        # bring to front over whatever is active
        w.deiconify(); w.lift(); w.focus_force()
        self._flash_alert(w, True)

    def _flash_alert(self, w, on):
        if self.alert_win is not w:
            return
        w.configure(bg=ACCENT if on else "#2f6fe0")
        for c in w.winfo_children():
            if isinstance(c, tk.Label):
                c.configure(bg=ACCENT if on else "#2f6fe0")
        w.attributes("-topmost", True)
        w.lift()
        w.after(600, lambda: self._flash_alert(w, not on))

    def _alarm_loop(self, stop):
        while not stop.is_set():
            for freq in (880, 1175, 880, 1175):
                if stop.is_set():
                    return
                try:
                    winsound.Beep(freq, 220)
                except Exception:
                    try:
                        winsound.MessageBeep()
                    except Exception:
                        pass
            stop.wait(1.2)

    def dismiss_alert(self):
        if self.alert_stop:
            self.alert_stop.set()
        if self.alert_win:
            self.alert_win.destroy()
            self.alert_win = None
        self.remaining = float(self.duration)
        self.refresh()

    # ---------------- Stats / exit ----------------
    def save(self):
        save_stats(self.stats)
        self.last_save = time.monotonic()

    def clear_stats(self):
        if messagebox.askyesno("Study Timer", "Clear all studied-time statistics?"):
            self.stats = {"days": {}}
            self.save()
            self.refresh()

    def on_close(self):
        if self.state == "running" and not messagebox.askyesno(
                "Study Timer", "Timer is still running. Quit anyway?"):
            return
        if self.alert_stop:
            self.alert_stop.set()
        self.save()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    StudyTimer(root)
    root.mainloop()
