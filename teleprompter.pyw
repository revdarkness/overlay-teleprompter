#!/usr/bin/env python3
"""
Overlay Teleprompter
--------------------
A frameless, always-on-top teleprompter that floats over any application
while you record. Zero third-party dependencies: standard library only.

Run with:  pythonw teleprompter.pyw
"""

import json
import os
import sys
import tkinter as tk
from tkinter import filedialog

IS_WIN = sys.platform.startswith("win")

if IS_WIN:
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ----------------------------------------------------------------------------
# Appearance
# ----------------------------------------------------------------------------
BG = "#0b0d10"
BAR = "#15181d"
FG = "#f2f4f7"
MUTED = "#8b94a3"
ACCENT = "#4da3ff"
LINE = "#ff8a3d"

FRAME_MS = 16  # ~60 fps

DEFAULTS = {
    "speed": 60.0,          # pixels per second
    "font_size": 34,
    "opacity": 0.88,
    "width": 900,
    "height": 460,
    "x": 200,
    "y": 120,
    "script": (
        "Paste your script here.\n\n"
        "Click EDIT to open the editor, drop in your text, then click START.\n\n"
        "Press SPACE to roll and pause. Use the UP and DOWN arrows to change "
        "speed while you are reading, so you can slow down for a dense "
        "paragraph and pick the pace back up afterward.\n\n"
        "Global hotkeys work even when this window is not focused:\n"
        "Ctrl+Alt+Space rolls and pauses.\n"
        "Ctrl+Alt+Up and Ctrl+Alt+Down change speed.\n"
        "Ctrl+Alt+Home jumps back to the top.\n"
        "Ctrl+Alt+T makes the window click-through so you can work behind it.\n"
    ),
}

# ----------------------------------------------------------------------------
# Config persistence
# ----------------------------------------------------------------------------
def config_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, "OverlayTeleprompter")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "config.json")


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(config_path(), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Windows global hotkeys (polled, no admin rights, no extra packages)
# ----------------------------------------------------------------------------
VK = {
    "ctrl": 0x11,
    "alt": 0x12,
    "space": 0x20,
    "up": 0x26,
    "down": 0x28,
    "home": 0x24,
    "t": 0x54,
}


class GlobalHotkeys:
    def __init__(self, root, bindings):
        self.root = root
        self.bindings = bindings
        self.down = set()
        self.enabled = IS_WIN
        if self.enabled:
            self.poll()

    def pressed(self, vk):
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

    def poll(self):
        try:
            mods = self.pressed(VK["ctrl"]) and self.pressed(VK["alt"])
            for name, callback in self.bindings.items():
                hit = mods and self.pressed(VK[name])
                if hit and name not in self.down:
                    self.down.add(name)
                    callback()
                elif not hit:
                    self.down.discard(name)
        except Exception:
            pass
        self.root.after(50, self.poll)


# ----------------------------------------------------------------------------
# Application
# ----------------------------------------------------------------------------
class Teleprompter:
    def __init__(self):
        self.cfg = load_config()
        self.speed = float(self.cfg["speed"])
        self.font_size = int(self.cfg["font_size"])
        self.opacity = float(self.cfg["opacity"])
        self.script = self.cfg["script"]

        self.rolling = False
        self.editing = False
        self.click_through = False
        self.scroll_debt = 0.0
        self.countdown = 0

        self.build_window()
        self.build_bar()
        self.build_body()
        self.bind_keys()

        self.apply_script()
        self.refresh_labels()
        self.tick()

        GlobalHotkeys(
            self.root,
            {
                "space": self.toggle_roll,
                "up": lambda: self.bump_speed(10),
                "down": lambda: self.bump_speed(-10),
                "home": self.to_top,
                "t": self.toggle_click_through,
            },
        )

    # -- window ---------------------------------------------------------------
    def build_window(self):
        self.root = tk.Tk()
        self.root.title("Teleprompter")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.opacity)
        self.root.configure(bg=BG)
        self.root.geometry(
            "%dx%d+%d+%d"
            % (self.cfg["width"], self.cfg["height"], self.cfg["x"], self.cfg["y"])
        )
        self.root.minsize(420, 220)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        if IS_WIN:
            self.root.after(20, self.show_in_taskbar)

    def hwnd(self):
        try:
            parent = ctypes.windll.user32.GetParent(self.root.winfo_id())
            return parent if parent else self.root.winfo_id()
        except Exception:
            return self.root.winfo_id()

    def show_in_taskbar(self):
        """A frameless window is hidden from Alt+Tab by default. Put it back."""
        try:
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            h = self.hwnd()
            style = ctypes.windll.user32.GetWindowLongW(h, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(h, GWL_EXSTYLE, style)
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
        except Exception:
            pass

    def toggle_click_through(self):
        """Let mouse clicks fall through to whatever is behind the prompter."""
        if not IS_WIN:
            return
        try:
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            h = self.hwnd()
            style = ctypes.windll.user32.GetWindowLongW(h, GWL_EXSTYLE)
            self.click_through = not self.click_through
            if self.click_through:
                style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(h, GWL_EXSTYLE, style)
            self.root.attributes("-alpha", self.opacity)
            self.ghost_btn.config(
                text="GHOST ON" if self.click_through else "GHOST",
                fg=ACCENT if self.click_through else MUTED,
            )
        except Exception:
            pass

    # -- chrome ---------------------------------------------------------------
    def build_bar(self):
        self.bar = tk.Frame(self.root, bg=BAR, height=38)
        self.bar.pack(side="top", fill="x")
        self.bar.pack_propagate(False)

        self.bar.bind("<Button-1>", self.drag_start)
        self.bar.bind("<B1-Motion>", self.drag_move)

        self.play_btn = self.button(self.bar, "\u25b6  ROLL", self.toggle_roll, ACCENT)
        self.play_btn.pack(side="left", padx=(10, 6), pady=6)

        self.button(self.bar, "\u23ee", self.to_top, MUTED).pack(side="left", padx=2)

        tk.Frame(self.bar, bg="#2a2f38", width=1).pack(
            side="left", fill="y", pady=9, padx=8
        )

        self.button(self.bar, "\u2212", lambda: self.bump_speed(-10), MUTED).pack(
            side="left"
        )
        self.speed_lbl = tk.Label(
            self.bar, text="", bg=BAR, fg=FG, font=("Segoe UI", 9, "bold"), width=8
        )
        self.speed_lbl.pack(side="left")
        self.button(self.bar, "+", lambda: self.bump_speed(10), MUTED).pack(side="left")

        self.speed_scale = tk.Scale(
            self.bar,
            from_=10,
            to=400,
            orient="horizontal",
            showvalue=False,
            length=130,
            bg=BAR,
            fg=FG,
            troughcolor="#242a33",
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            activebackground=ACCENT,
            command=self.on_scale,
        )
        self.speed_scale.set(self.speed)
        self.speed_scale.pack(side="left", padx=8)

        tk.Frame(self.bar, bg="#2a2f38", width=1).pack(
            side="left", fill="y", pady=9, padx=8
        )

        self.button(self.bar, "A\u2212", lambda: self.bump_font(-2), MUTED).pack(
            side="left"
        )
        self.button(self.bar, "A+", lambda: self.bump_font(2), MUTED).pack(side="left")
        self.button(self.bar, "\u25d1", lambda: self.bump_opacity(-0.06), MUTED).pack(
            side="left", padx=(8, 0)
        )
        self.button(self.bar, "\u25cf", lambda: self.bump_opacity(0.06), MUTED).pack(
            side="left"
        )

        self.button(self.bar, "\u2715", self.quit, "#ff6b6b").pack(
            side="right", padx=(4, 10)
        )
        self.edit_btn = self.button(self.bar, "EDIT", self.toggle_edit, FG)
        self.edit_btn.pack(side="right", padx=4)
        self.ghost_btn = self.button(self.bar, "GHOST", self.toggle_click_through, MUTED)
        self.ghost_btn.pack(side="right", padx=4)

        self.info_lbl = tk.Label(
            self.bar, text="", bg=BAR, fg=MUTED, font=("Segoe UI", 8)
        )
        self.info_lbl.pack(side="right", padx=10)

    def button(self, parent, text, command, fg):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=BAR,
            fg=fg,
            activebackground="#232932",
            activeforeground=FG,
            bd=0,
            relief="flat",
            padx=8,
            pady=3,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )

    def build_body(self):
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True)

        self.text = tk.Text(
            self.body,
            bg=BG,
            fg=FG,
            bd=0,
            highlightthickness=0,
            wrap="word",
            padx=48,
            pady=10,
            spacing1=6,
            spacing2=10,
            spacing3=22,
            insertbackground=FG,
            selectbackground="#26405c",
            cursor="arrow",
        )
        self.text.pack(fill="both", expand=True)
        self.text.bind("<MouseWheel>", self.on_wheel)
        self.text.bind("<Button-1>", lambda e: "break" if not self.editing else None)

        # Reading-line marker, drawn over the text.
        self.marker = tk.Frame(self.body, bg=LINE, height=2)
        self.place_marker()
        self.root.bind("<Configure>", lambda e: self.place_marker())

        self.grip = tk.Frame(self.root, bg="#2a2f38", width=16, height=16, cursor="sizing")
        self.grip.place(relx=1.0, rely=1.0, anchor="se")
        self.grip.bind("<Button-1>", self.resize_start)
        self.grip.bind("<B1-Motion>", self.resize_move)

    def place_marker(self):
        if self.editing:
            self.marker.place_forget()
        else:
            self.marker.place(relx=0, rely=0.32, relwidth=1.0)

    # -- keyboard -------------------------------------------------------------
    def bind_keys(self):
        r = self.root
        r.bind("<space>", self.key_space)
        r.bind("<Up>", lambda e: self.guard(lambda: self.bump_speed(10)))
        r.bind("<Down>", lambda e: self.guard(lambda: self.bump_speed(-10)))
        r.bind("<Prior>", lambda e: self.guard(lambda: self.nudge(-160)))
        r.bind("<Next>", lambda e: self.guard(lambda: self.nudge(160)))
        r.bind("<Home>", lambda e: self.guard(self.to_top))
        r.bind("<Control-plus>", lambda e: self.bump_font(2))
        r.bind("<Control-equal>", lambda e: self.bump_font(2))
        r.bind("<Control-minus>", lambda e: self.bump_font(-2))
        r.bind("<Control-e>", lambda e: self.toggle_edit())
        r.bind("<Control-o>", lambda e: self.open_file())
        r.bind("<Control-s>", lambda e: self.save_file())
        r.bind("<Escape>", lambda e: self.quit())

    def guard(self, fn):
        """Ignore bare-key shortcuts while the editor has focus."""
        if self.editing:
            return
        fn()
        return "break"

    def key_space(self, event=None):
        if self.editing:
            return
        self.toggle_roll()
        return "break"

    # -- script ---------------------------------------------------------------
    def apply_script(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.script.rstrip() + "\n" * 12)
        self.text.config(
            state="disabled", font=("Segoe UI", self.font_size), cursor="arrow"
        )
        self.to_top()

    def content_pixels(self):
        try:
            return self.text.count("1.0", "end", "ypixels")[0]
        except Exception:
            return 0

    def word_count(self):
        return len(self.script.split())

    # -- transport ------------------------------------------------------------
    def toggle_roll(self):
        if self.editing:
            return
        if self.rolling:
            self.rolling = False
            self.countdown = 0
            self.play_btn.config(text="\u25b6  ROLL", fg=ACCENT)
        else:
            at_top = self.text.yview()[0] <= 0.0001
            self.countdown = 3 if at_top else 0
            self.rolling = True
            self.play_btn.config(text="\u2016  PAUSE", fg=LINE)
            if self.countdown:
                self.run_countdown()

    def run_countdown(self):
        if not self.rolling or self.countdown <= 0:
            self.refresh_labels()
            return
        self.info_lbl.config(text="starting in %d" % self.countdown, fg=LINE)
        self.countdown -= 1
        self.root.after(1000, self.run_countdown)

    def to_top(self):
        self.text.yview_moveto(0.0)
        self.scroll_debt = 0.0

    def nudge(self, pixels):
        self.text.yview_scroll(int(pixels), "pixels")

    def on_wheel(self, event):
        if self.editing:
            return
        self.text.yview_scroll(int(-event.delta / 3), "pixels")
        return "break"

    def tick(self):
        if self.rolling and not self.editing and self.countdown <= 0:
            self.scroll_debt += self.speed * (FRAME_MS / 1000.0)
            step = int(self.scroll_debt)
            if step:
                self.scroll_debt -= step
                self.text.yview_scroll(step, "pixels")
            if self.text.yview()[1] >= 1.0:
                self.rolling = False
                self.play_btn.config(text="\u25b6  ROLL", fg=ACCENT)
            self.refresh_labels()
        self.root.after(FRAME_MS, self.tick)

    # -- adjustments ----------------------------------------------------------
    def on_scale(self, value):
        self.speed = float(value)
        self.refresh_labels()

    def bump_speed(self, delta):
        self.speed = max(10.0, min(400.0, self.speed + delta))
        self.speed_scale.set(self.speed)
        self.refresh_labels()

    def bump_font(self, delta):
        self.font_size = max(14, min(96, self.font_size + delta))
        self.text.config(font=("Segoe UI", self.font_size))
        self.refresh_labels()

    def bump_opacity(self, delta):
        self.opacity = max(0.25, min(1.0, self.opacity + delta))
        self.root.attributes("-alpha", self.opacity)

    def refresh_labels(self):
        self.speed_lbl.config(text="%d px/s" % int(self.speed))
        total = self.content_pixels()
        words = self.word_count()
        if total > 0 and words > 0 and self.speed > 0:
            minutes = (total / self.speed) / 60.0
            wpm = words / minutes if minutes > 0 else 0
            remaining = max(0.0, (1.0 - self.text.yview()[0]) * total / self.speed)
            self.info_lbl.config(
                text="\u2248%d wpm   \u00b7   %d:%02d left"
                % (wpm, int(remaining // 60), int(remaining % 60)),
                fg=MUTED,
            )

    # -- editing --------------------------------------------------------------
    def toggle_edit(self):
        if self.editing:
            self.script = self.text.get("1.0", "end").rstrip()
            self.editing = False
            self.apply_script()
            self.edit_btn.config(text="EDIT", fg=FG)
            self.refresh_labels()
        else:
            self.rolling = False
            self.play_btn.config(text="\u25b6  ROLL", fg=ACCENT)
            self.editing = True
            self.text.config(
                state="normal", font=("Segoe UI", 13), cursor="xterm", wrap="word"
            )
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self.script)
            self.text.focus_set()
            self.edit_btn.config(text="START", fg=ACCENT)
            self.info_lbl.config(
                text="Ctrl+O open   \u00b7   Ctrl+S save   \u00b7   Ctrl+E done", fg=MUTED
            )
        self.place_marker()

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open script",
            filetypes=[("Text files", "*.txt *.md"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                self.script = fh.read()
        except Exception:
            return
        if self.editing:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self.script)
        else:
            self.apply_script()

    def save_file(self):
        if self.editing:
            self.script = self.text.get("1.0", "end").rstrip()
        path = filedialog.asksaveasfilename(
            title="Save script",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.script)
        except Exception:
            pass

    # -- move and resize ------------------------------------------------------
    def drag_start(self, event):
        self._dx, self._dy = event.x_root, event.y_root
        self._ox, self._oy = self.root.winfo_x(), self.root.winfo_y()

    def drag_move(self, event):
        x = self._ox + (event.x_root - self._dx)
        y = self._oy + (event.y_root - self._dy)
        self.root.geometry("+%d+%d" % (x, y))

    def resize_start(self, event):
        self._rx, self._ry = event.x_root, event.y_root
        self._rw, self._rh = self.root.winfo_width(), self.root.winfo_height()

    def resize_move(self, event):
        w = max(420, self._rw + (event.x_root - self._rx))
        h = max(220, self._rh + (event.y_root - self._ry))
        self.root.geometry("%dx%d" % (w, h))

    # -- lifecycle ------------------------------------------------------------
    def quit(self):
        if self.editing:
            self.script = self.text.get("1.0", "end").rstrip()
        save_config(
            {
                "speed": self.speed,
                "font_size": self.font_size,
                "opacity": self.opacity,
                "width": self.root.winfo_width(),
                "height": self.root.winfo_height(),
                "x": self.root.winfo_x(),
                "y": self.root.winfo_y(),
                "script": self.script,
            }
        )
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Teleprompter().run()
