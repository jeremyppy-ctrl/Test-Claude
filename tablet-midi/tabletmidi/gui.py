"""The window: a live picture of the tablet, and every setting.

Tk is used deliberately -- it ships with Python, so the frozen executable
needs nothing installed on the target machine.

The engine runs on its own thread; this file never calls into it except
through :meth:`Engine.post`, and never reads anything but a snapshot.
"""

from __future__ import annotations

import os
import queue
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Optional

from . import __version__, hidhide
from .config import Config, ConfigError, default_config_path
from .engine import Engine

BG = "#14161a"
PANEL = "#1c2027"
PAD_FILL = "#20242c"
STRIP_FILL = "#262b34"
CELL_ON = "#3ddc84"
CELL_OFF = "#31363f"
ACCENT = "#5aa9e6"
TEXT = "#e6e8eb"
MUTED = "#8b93a1"
WARN = "#e6a23c"
BAD = "#e05252"
GOOD = "#3ddc84"


class Dot(tk.Canvas):
    """A small status light with a caption."""

    def __init__(self, master, text: str) -> None:
        super().__init__(master, width=14, height=14, bg=PANEL, highlightthickness=0)
        self._id = self.create_oval(3, 3, 11, 11, fill=MUTED, outline="")
        self.caption = tk.Label(master, text=text, bg=PANEL, fg=TEXT, anchor="w")

    def set(self, colour: str, text: str) -> None:
        self.itemconfigure(self._id, fill=colour)
        self.caption.configure(text=text)


class TabletView(tk.Canvas):
    """Draws the active area, the strip, the toggles and the pen."""

    def __init__(self, master, on_cell_click) -> None:
        super().__init__(master, bg=BG, highlightthickness=0)
        self._on_cell_click = on_cell_click
        self._cells: List[int] = []
        self._cell_labels: List[int] = []
        self._geometry = (0, 0, 0, 0)
        self._buttons = 0
        self._strip = 0.0
        self._strip_at = "bottom"
        self._ratio = 16 / 10
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Button-1>", self._click)

        self._pad = self.create_rectangle(0, 0, 0, 0, fill=PAD_FILL, outline="#2e3440")
        self._strip_rect = self.create_rectangle(0, 0, 0, 0, fill=STRIP_FILL, outline="")
        self._vline = self.create_line(0, 0, 0, 0, fill=ACCENT, width=1)
        self._hline = self.create_line(0, 0, 0, 0, fill=ACCENT, width=1)
        self._dot = self.create_oval(0, 0, 0, 0, fill=ACCENT, outline="")
        self._readout = self.create_text(
            8, 8, anchor="nw", fill=MUTED, text="", font=("Consolas", 10)
        )

    def configure_layout(self, buttons: int, strip: float, strip_at: str) -> None:
        if (buttons, strip, strip_at) == (self._buttons, self._strip, self._strip_at):
            return
        self._buttons, self._strip, self._strip_at = buttons, strip, strip_at
        for item in self._cells + self._cell_labels:
            self.delete(item)
        self._cells = [
            self.create_rectangle(0, 0, 0, 0, fill=CELL_OFF, outline=BG, width=2)
            for _ in range(buttons)
        ]
        self._cell_labels = [
            self.create_text(0, 0, text=str(i + 1), fill=TEXT, font=("Segoe UI", 9))
            for i in range(buttons)
        ]
        self.redraw()

    def _area(self):
        """The drawing rectangle, keeping a 16:10 tablet shape."""
        w, h = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        margin = 12
        aw, ah = w - 2 * margin, h - 2 * margin
        if aw <= 0 or ah <= 0:
            return 0, 0, 0, 0
        ratio = self._ratio
        if aw / ah > ratio:
            aw = int(ah * ratio)
        else:
            ah = int(aw / ratio)
        return (w - aw) // 2, (h - ah) // 2, aw, ah

    def redraw(self) -> None:
        x0, y0, w, h = self._area()
        self._geometry = (x0, y0, w, h)
        if w <= 0:
            return
        self.coords(self._pad, x0, y0, x0 + w, y0 + h)

        strip_h = int(h * self._strip)
        sy0 = y0 + h - strip_h if self._strip_at == "bottom" else y0
        self.coords(self._strip_rect, x0, sy0, x0 + w, sy0 + strip_h)

        n = max(self._buttons, 1)
        for index, item in enumerate(self._cells):
            cx0 = x0 + int(w * index / n)
            cx1 = x0 + int(w * (index + 1) / n)
            self.coords(item, cx0, sy0, cx1, sy0 + strip_h)
            self.coords(
                self._cell_labels[index], (cx0 + cx1) // 2, sy0 + strip_h // 2
            )
            self.tag_raise(self._cell_labels[index])

    def _click(self, event) -> None:
        x0, y0, w, h = self._geometry
        if w <= 0 or not self._cells:
            return
        strip_h = int(h * self._strip)
        sy0 = y0 + h - strip_h if self._strip_at == "bottom" else y0
        if not (sy0 <= event.y <= sy0 + strip_h and x0 <= event.x <= x0 + w):
            return
        index = int((event.x - x0) / w * self._buttons)
        self._on_cell_click(max(0, min(self._buttons - 1, index)))

    def set_ratio(self, x_limit: int, y_limit: int) -> None:
        """Match the drawing to the tablet's own proportions once known."""
        if x_limit > 0 and y_limit > 0:
            ratio = x_limit / float(y_limit)
            if 0.2 < ratio < 5.0 and abs(ratio - self._ratio) > 0.01:
                self._ratio = ratio
                self.redraw()

    def update_state(self, snap, cc_x: int, cc_y: int) -> None:
        x0, y0, w, h = self._geometry
        if w <= 0:
            return
        for index, item in enumerate(self._cells):
            on = index < len(snap.toggles) and snap.toggles[index]
            hot = snap.pen.in_strip and snap.pen.cell == index
            self.itemconfigure(
                item,
                fill=CELL_ON if on else CELL_OFF,
                outline=ACCENT if hot else BG,
            )
            self.itemconfigure(
                self._cell_labels[index], fill="#10261a" if on else TEXT
            )

        pen = snap.pen
        if pen.in_range:
            px, py = x0 + pen.nx * w, y0 + pen.ny * h
            colour = GOOD if pen.tip else ACCENT
            self.coords(self._vline, px, y0, px, y0 + h)
            self.coords(self._hline, x0, py, x0 + w, py)
            r = 7 if pen.tip else 4
            self.coords(self._dot, px - r, py - r, px + r, py + r)
            for item in (self._vline, self._hline, self._dot):
                self.itemconfigure(item, state="normal")
            self.itemconfigure(self._vline, fill=colour)
            self.itemconfigure(self._hline, fill=colour)
            self.itemconfigure(self._dot, fill=colour)
        else:
            for item in (self._vline, self._hline, self._dot):
                self.itemconfigure(item, state="hidden")

        self.itemconfigure(
            self._readout,
            text="CC %d = %3d    CC %d = %3d"
            % (cc_x, pen.cc_x_value, cc_y, pen.cc_y_value),
        )


class SettingsPanel(ttk.Frame):
    """Every configuration field, with Apply and Save."""

    def __init__(self, master, app: "App") -> None:
        super().__init__(master, padding=(12, 10))
        self.app = app
        self.vars = {}
        row = 0

        row = self._heading("MIDI", row)
        self.port = ttk.Combobox(self, width=22, state="normal")
        self._field("Port", self.port, row); row += 1
        row = self._entry("channel", "Channel", row, width=5)
        row = self._entry("cc_x", "CC for X", row, width=5)
        row = self._entry("cc_y", "CC for Y", row, width=5)
        row = self._entry("button_cc_base", "Buttons start at CC", row, width=5)
        row = self._check("high_res", "14-bit X/Y (CC + CC+32)", row)

        row = self._heading("Layout", row)
        row = self._entry("buttons", "Buttons", row, width=5)
        row = self._entry("strip", "Strip height %", row, width=5)
        self.strip_at = ttk.Combobox(
            self, width=10, state="readonly", values=("bottom", "top")
        )
        self._field("Strip at", self.strip_at, row); row += 1

        row = self._heading("Behaviour", row)
        self.xy_when = ttk.Combobox(
            self, width=10, state="readonly", values=("hover", "tip")
        )
        self._field("X/Y follow", self.xy_when, row); row += 1
        row = self._entry("smoothing", "Smoothing %", row, width=5)
        row = self._entry("toggle_debounce_ms", "Debounce ms", row, width=5)
        row = self._check("freeze_xy_in_strip", "Hold X/Y over the strip", row)
        row = self._check("invert_x", "Invert X", row)
        row = self._check("invert_y", "Invert Y", row)
        row = self._check("swap_xy", "Swap X and Y", row)

        self.columnconfigure(1, weight=1)

    def _heading(self, text: str, row: int) -> int:
        label = ttk.Label(self, text=text.upper(), style="Heading.TLabel")
        label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 4))
        return row + 1

    def _field(self, label: str, widget, row: int) -> None:
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=2)
        widget.grid(row=row, column=1, sticky="e", pady=2)

    def _entry(self, key: str, label: str, row: int, width: int = 8) -> int:
        var = tk.StringVar()
        self.vars[key] = var
        self._field(label, ttk.Entry(self, textvariable=var, width=width), row)
        return row + 1

    def _check(self, key: str, label: str, row: int) -> int:
        var = tk.BooleanVar()
        self.vars[key] = var
        ttk.Checkbutton(self, text=label, variable=var).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=2
        )
        return row + 1

    # -- binding ---------------------------------------------------------

    def load(self, cfg: Config) -> None:
        set_ = lambda key, value: self.vars[key].set(value)
        set_("channel", cfg.midi.channel)
        set_("cc_x", cfg.midi.cc_x)
        set_("cc_y", cfg.midi.cc_y)
        set_("button_cc_base", cfg.midi.button_cc_base)
        set_("high_res", cfg.midi.high_res)
        set_("buttons", cfg.layout.buttons)
        set_("strip", round(cfg.layout.strip * 100))
        set_("smoothing", round(cfg.behaviour.smoothing * 100))
        set_("toggle_debounce_ms", cfg.behaviour.toggle_debounce_ms)
        set_("freeze_xy_in_strip", cfg.behaviour.freeze_xy_in_strip)
        set_("invert_x", cfg.area.invert_x)
        set_("invert_y", cfg.area.invert_y)
        set_("swap_xy", cfg.area.swap_xy)
        self.port.set(cfg.midi.port_name)
        self.strip_at.set(cfg.layout.strip_at)
        self.xy_when.set(cfg.behaviour.xy_when)

    def collect(self, base: Config) -> Config:
        """Read the widgets into a fresh, validated configuration."""
        cfg = Config.from_dict(base.to_dict())

        def number(key: str, cast=int) -> object:
            raw = self.vars[key].get().strip()
            try:
                return cast(raw)
            except ValueError:
                raise ConfigError("'%s' is not a number for %s" % (raw, key))

        cfg.midi.port_name = self.port.get().strip() or cfg.midi.port_name
        cfg.midi.channel = number("channel")
        cfg.midi.cc_x = number("cc_x")
        cfg.midi.cc_y = number("cc_y")
        cfg.midi.button_cc_base = number("button_cc_base")
        cfg.midi.high_res = bool(self.vars["high_res"].get())
        cfg.layout.buttons = number("buttons")
        cfg.layout.strip = max(1.0, min(90.0, number("strip", float))) / 100.0
        cfg.layout.strip_at = self.strip_at.get() or "bottom"
        cfg.behaviour.xy_when = self.xy_when.get() or "hover"
        cfg.behaviour.smoothing = max(0.0, min(95.0, number("smoothing", float))) / 100.0
        cfg.behaviour.toggle_debounce_ms = number("toggle_debounce_ms")
        cfg.behaviour.freeze_xy_in_strip = bool(self.vars["freeze_xy_in_strip"].get())
        cfg.area.invert_x = bool(self.vars["invert_x"].get())
        cfg.area.invert_y = bool(self.vars["invert_y"].get())
        cfg.area.swap_xy = bool(self.vars["swap_xy"].get())
        return cfg.validate()


class App(tk.Tk):
    def __init__(self, cfg: Config, config_path: str, simulate: bool = False) -> None:
        super().__init__()
        self.title("Tablet MIDI %s" % __version__)
        self.geometry("1060x720")
        self.minsize(820, 520)
        self.configure(bg=BG)

        self.cfg = cfg
        self.config_path = config_path
        self.logs: "queue.Queue[str]" = queue.Queue()
        self.engine = Engine(cfg, log=self.logs.put, simulate=simulate)
        self._calibrating = False

        self._style()
        self._build()
        self.settings.load(cfg)
        self._refresh_ports()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.log("Tablet MIDI %s -- press Start." % __version__)
        self.after(200, self._check_hiding)
        if simulate:
            self.log("Simulation mode: the pen is generated, no tablet is read.")
        self._tick()

    # -- construction ----------------------------------------------------

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=PANEL, foreground=TEXT, fieldbackground="#2a2f38")
        style.configure("TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=TEXT)
        style.configure("Heading.TLabel", foreground=ACCENT, font=("Segoe UI", 9, "bold"))
        style.configure("TButton", padding=6)
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", PANEL)])

    def _build(self) -> None:
        status = tk.Frame(self, bg=PANEL)
        status.pack(fill="x", side="top")
        self.dot_tablet = Dot(status, "Tablet: --")
        self.dot_midi = Dot(status, "MIDI: --")
        self.dot_hide = Dot(status, "Hiding: --")
        for dot in (self.dot_tablet, self.dot_midi, self.dot_hide):
            dot.pack(side="left", padx=(10, 4), pady=8)
            dot.caption.pack(side="left", padx=(0, 18))

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        self.view = TabletView(body, self._cell_clicked)
        self.view.pack(side="left", fill="both", expand=True)

        side = tk.Frame(body, bg=PANEL, width=304)
        side.pack(side="right", fill="y")
        side.pack_propagate(False)
        commit = ttk.Frame(side, padding=(10, 8))
        commit.pack(side="bottom", fill="x")
        ttk.Button(commit, text="Apply", command=self.apply_settings).pack(
            side="left", expand=True, fill="x", padx=(0, 4)
        )
        ttk.Button(commit, text="Save", command=self.save_settings).pack(
            side="left", expand=True, fill="x", padx=(4, 0)
        )

        scroller = tk.Canvas(side, bg=PANEL, highlightthickness=0)
        bar = ttk.Scrollbar(side, orient="vertical", command=scroller.yview)
        scroller.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        scroller.pack(side="left", fill="both", expand=True)
        self.settings = SettingsPanel(scroller, self)
        window = scroller.create_window((0, 0), window=self.settings, anchor="nw")

        def _fit(event) -> None:
            scroller.itemconfigure(window, width=event.width)

        def _extent(_event=None) -> None:
            scroller.configure(scrollregion=scroller.bbox("all"))

        scroller.bind("<Configure>", _fit)
        self.settings.bind("<Configure>", _extent)
        for sequence, delta in (("<Button-4>", -1), ("<Button-5>", 1)):
            scroller.bind_all(sequence, lambda e, d=delta: scroller.yview_scroll(d, "units"))
        scroller.bind_all(
            "<MouseWheel>",
            lambda e: scroller.yview_scroll(-1 if e.delta > 0 else 1, "units"),
        )

        controls = tk.Frame(self, bg=PANEL)
        controls.pack(fill="x")
        self.start_button = ttk.Button(controls, text="Start", command=self._toggle_run)
        self.start_button.pack(side="left", padx=(10, 4), pady=8)
        self.cal_button = ttk.Button(
            controls, text="Calibrate", command=self._calibrate
        )
        self.cal_button.pack(side="left", padx=4)
        ttk.Button(controls, text="All off", command=self.engine.all_off).pack(
            side="left", padx=4
        )
        ttk.Button(controls, text="Resend", command=self.engine.resend).pack(
            side="left", padx=4
        )
        ttk.Button(
            controls, text="Driver setup...", command=self._driver_setup
        ).pack(side="right", padx=10)

        self.text = tk.Text(
            self, height=6, bg="#0f1115", fg=MUTED, insertbackground=TEXT,
            relief="flat", font=("Consolas", 9), wrap="word",
        )
        self.text.pack(fill="x", side="bottom")
        self.text.configure(state="disabled")

    # -- helpers ---------------------------------------------------------

    def log(self, message: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", message.rstrip() + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def _refresh_ports(self) -> None:
        names: List[str] = []
        try:
            from .midi_win import list_ports

            names = [p.name for p in list_ports()]
        except Exception as exc:
            self.log("MIDI ports unavailable: %s" % exc)
        self.settings.port.configure(values=names)
        if names and not self.settings.port.get():
            self.settings.port.set(names[0])

    def _cell_clicked(self, index: int) -> None:
        self.engine.toggle(index)

    def _toggle_run(self) -> None:
        if self.engine.running:
            self.engine.stop()
            self.start_button.configure(text="Start")
            self.log("Stopped.")
        else:
            self.engine.start()
            self.start_button.configure(text="Stop")
            self.log("Started.")

    def _calibrate(self) -> None:
        if not self.engine.running:
            messagebox.showinfo(
                "Calibrate", "Press Start first, so the tablet is being read."
            )
            return
        if not self._calibrating:
            self._calibrating = True
            self.cal_button.configure(text="Finish")
            self.engine.begin_calibration()
            self.log("Sweep the pen over the area you want to use, then press Finish.")
        else:
            self._calibrating = False
            self.cal_button.configure(text="Calibrate")
            if self.engine.end_calibration(keep=True):
                self.cfg = self.engine.cfg
                self.settings.load(self.cfg)

    def apply_settings(self) -> None:
        try:
            cfg = self.settings.collect(self.cfg)
        except ConfigError as exc:
            messagebox.showerror("Settings", str(exc))
            return
        self.cfg = cfg
        self.engine.apply_config(cfg)
        self.view.configure_layout(cfg.layout.buttons, cfg.layout.strip, cfg.layout.strip_at)
        # A loopMIDI port created after launch should show up without a restart.
        self._refresh_ports()

    def save_settings(self) -> None:
        self.apply_settings()
        try:
            self.cfg.save(self.config_path)
        except OSError as exc:
            messagebox.showerror("Save", str(exc))
            return
        self.log("Saved to %s" % self.config_path)

    def _driver_setup(self) -> None:
        DriverSetup(self)

    def _check_hiding(self) -> None:
        """Say up front whether Windows can still see the tablet."""
        if sys.platform != "win32":
            self.dot_hide.set(MUTED, "Hiding: Windows only")
            return
        try:
            state = hidhide.status()
        except Exception as exc:
            self.dot_hide.set(BAD, "Hiding: %s" % exc)
            return
        if not state.installed:
            self.dot_hide.set(BAD, "Hiding: HidHide not installed")
            self.log("HidHide is not installed -- the pen will still move the cursor.")
            self.log("Get it from " + hidhide.DOWNLOAD_URL + ", then use Driver setup.")
            return
        allowed = state.allows(hidhide.current_executable())
        if state.hidden and state.cloaking and allowed:
            self.dot_hide.set(GOOD, "Hiding: on (%d device(s))" % len(state.hidden))
        elif state.hidden:
            self.dot_hide.set(
                WARN, "Hiding: incomplete -- open Driver setup"
            )
            if not allowed:
                self.log("This program is not on the HidHide allow list yet.")
        else:
            self.dot_hide.set(WARN, "Hiding: off -- open Driver setup")

    # -- the frame loop --------------------------------------------------

    def _tick(self) -> None:
        while True:
            try:
                self.log(self.logs.get_nowait())
            except queue.Empty:
                break

        snap = self.engine.snapshot()
        self.view.configure_layout(
            self.cfg.layout.buttons, self.cfg.layout.strip, self.cfg.layout.strip_at
        )
        self.view.set_ratio(snap.x_limit, snap.y_limit)
        self.view.update_state(snap, self.cfg.midi.cc_x, self.cfg.midi.cc_y)

        if snap.error:
            self.dot_tablet.set(BAD, "Tablet: %s" % snap.error[:60])
        elif snap.device:
            self.dot_tablet.set(GOOD, "Tablet: %s" % snap.device[:52])
        else:
            self.dot_tablet.set(MUTED, "Tablet: not started")
        self.dot_midi.set(
            GOOD if snap.midi else MUTED, "MIDI: %s" % (snap.midi or "not connected")
        )
        self.after(33, self._tick)

    def _close(self) -> None:
        self.engine.stop()
        self.destroy()


class DriverSetup(tk.Toplevel):
    """Hide the tablet from Windows, or give it back."""

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.app = app
        self.title("Driver setup -- hide the tablet from Windows")
        self.geometry("720x480")
        self.configure(bg=PANEL)
        self.transient(app)

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(
            top,
            wraplength=680,
            text=(
                "HidHide hides the tablet from Windows so the pen never moves the "
                "cursor, and lets this program read it instead. Everything here "
                "can be undone with Remove."
            ),
        ).pack(anchor="w")

        self.devices = tk.Listbox(
            self, height=8, bg="#0f1115", fg=TEXT, selectbackground=ACCENT,
            relief="flat", font=("Consolas", 9), exportselection=False,
        )
        self.devices.pack(fill="both", expand=True, padx=10, pady=6)

        self.text = tk.Text(
            self, height=8, bg="#0f1115", fg=MUTED, relief="flat",
            font=("Consolas", 9), wrap="word",
        )
        self.text.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        row = ttk.Frame(self, padding=(10, 0, 10, 10))
        row.pack(fill="x")
        ttk.Button(row, text="Rescan", command=self.rescan).pack(side="left")
        ttk.Button(row, text="Preview", command=lambda: self.apply(True)).pack(
            side="left", padx=4
        )
        ttk.Button(row, text="Hide tablet", command=lambda: self.apply(False)).pack(
            side="left", padx=4
        )
        ttk.Button(row, text="Remove", command=self.remove).pack(side="left", padx=4)
        ttk.Button(row, text="Close", command=self.destroy).pack(side="right")

        self.rescan()

    def say(self, message: str) -> None:
        self.text.insert("end", message.rstrip() + "\n")
        self.text.see("end")

    def rescan(self) -> None:
        self.devices.delete(0, "end")
        self.text.delete("1.0", "end")
        status = hidhide.status()
        if not status.installed:
            self.say("HidHide is not installed.")
            self.say("Download and install it from " + hidhide.DOWNLOAD_URL)
            self.app.dot_hide.set(BAD, "Hiding: HidHide missing")
            return
        self.say("HidHide: %s" % status.cli_path)
        self.say(
            "Administrator: %s" % ("yes" if status.elevated else "no -- needed to change anything")
        )
        self.say("Allow-listed program: %s" % hidhide.current_executable())

        try:
            from .hid_win import enumerate_devices

            pens = [d for d in enumerate_devices() if d.has_pen]
        except Exception as exc:
            self.say("Could not enumerate tablets: %s" % exc)
            pens = []
        self._pens = pens
        for dev in pens:
            mark = "hidden" if status.hides(dev.vid, dev.pid) else "visible"
            self.devices.insert("end", "[%s] %s" % (mark, dev.describe()))
        if pens:
            self.devices.selection_set(0)
            self.app.dot_hide.set(
                GOOD if status.hides(pens[0].vid, pens[0].pid) else WARN,
                "Hiding: %s" % ("on" if status.hides(pens[0].vid, pens[0].pid) else "off"),
            )
        else:
            self.say("No tablet with a pen was found.")

    def _selected(self):
        picks = self.devices.curselection()
        if not picks or not getattr(self, "_pens", None):
            messagebox.showinfo("Driver setup", "Pick the tablet in the list first.")
            return None
        return self._pens[picks[0]]

    def _paths(self, dev) -> List[str]:
        try:
            paths = hidhide.device_paths_for(dev.vid, dev.pid)
        except hidhide.HidHideError as exc:
            self.say(str(exc))
            return []
        if not paths and dev.instance_id:
            paths = [dev.instance_id]
        return paths

    def apply(self, preview: bool) -> None:
        dev = self._selected()
        if dev is None:
            return
        paths = self._paths(dev)
        if not paths:
            self.say("HidHide does not list this device; nothing to hide.")
            return
        steps = hidhide.plan_install(paths, hidhide.current_executable())
        self._run(steps, preview)

    def remove(self) -> None:
        dev = self._selected()
        if dev is None:
            return
        paths = self._paths(dev)
        steps = hidhide.plan_remove(paths, hidhide.current_executable())
        self._run(steps, False)

    def _run(self, steps, preview: bool) -> None:
        if not preview and not hidhide.is_elevated():
            if messagebox.askyesno(
                "Administrator needed",
                "Changing the HidHide configuration needs administrator rights.\n\n"
                "Restart Tablet MIDI as administrator now?",
            ):
                if hidhide.relaunch_as_admin():
                    self.app._close()
                    return
                self.say("Could not restart as administrator.")
            return
        try:
            ok = hidhide.apply(steps, dry_run=preview, log=self.say)
        except hidhide.HidHideError as exc:
            self.say(str(exc))
            return
        if not preview:
            self.say("Done." if ok else "Some steps failed; see above.")
            self.say("Unplug and replug the tablet for the change to take effect.")
            self.rescan()


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    simulate = "--simulate" in argv
    path = default_config_path()
    for index, arg in enumerate(argv):
        if arg == "--config" and index + 1 < len(argv):
            path = argv[index + 1]
    try:
        cfg = Config.load_or_default(path)
    except (OSError, ConfigError) as exc:
        cfg = Config()
        print("Could not read %s (%s); using defaults." % (path, exc))
    App(cfg, path, simulate=simulate).mainloop()
    return 0
