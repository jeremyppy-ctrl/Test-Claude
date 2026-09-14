"""Turn pen samples into MIDI messages.

This is the whole behaviour of the tool, kept free of any operating-system
call so that it can be tested without a tablet attached.

The active area is split in two:

    +-----------------------------------+
    |                                   |
    |            pad zone               |  X -> cc_x, Y -> cc_y
    |                                   |
    +----+----+----+----+----+----+-----+
    | 0  | 1  | 2  | 3  | ...      |  9 |  tip down toggles one controller
    +----+----+----+----+----+----+-----+

Putting the tip down inside a cell of the strip flips that cell's toggle and
sends its controller; the pad's two controllers follow the pen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .config import Config

CC_STATUS = 0xB0


@dataclass(frozen=True)
class MidiMsg:
    """A channel-voice message, already resolved to its three bytes."""

    status: int
    data1: int
    data2: int

    def packed(self) -> int:
        """The little-endian word ``midiOutShortMsg`` expects."""
        return (
            (self.status & 0xFF)
            | ((self.data1 & 0x7F) << 8)
            | ((self.data2 & 0x7F) << 16)
        )

    def __str__(self) -> str:
        return "ch%-2d CC%-3d = %3d" % (
            (self.status & 0x0F) + 1,
            self.data1,
            self.data2,
        )


@dataclass
class PenSample:
    """One report from the tablet, in raw device units."""

    x: float
    y: float
    tip: bool
    in_range: bool = True
    pressure: Optional[int] = None
    #: Monotonic seconds. Only differences matter.
    t: float = 0.0


@dataclass
class PenState:
    """What the mapper made of the last sample, for the UI to draw."""

    in_range: bool = False
    tip: bool = False
    #: Normalised to the calibrated area, 0..1, after swap and inversion.
    nx: float = 0.0
    ny: float = 0.0
    in_strip: bool = False
    #: Index of the strip cell under the pen, or None outside the strip.
    cell: Optional[int] = None
    #: What the pad controllers currently hold, 0..127.
    cc_x_value: int = 0
    cc_y_value: int = 0


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


class Mapper:
    """Stateful translation of pen samples into MIDI messages."""

    def __init__(self, cfg: Config, x_limit: int = 0, y_limit: int = 0) -> None:
        """
        ``x_limit``/``y_limit`` are the tablet's logical maxima, used for any
        area bound left at 0 by the configuration.
        """
        self.cfg = cfg.validate()
        self.x_limit = x_limit
        self.y_limit = y_limit

        n = cfg.layout.buttons
        self.toggles: List[bool] = [False] * n
        self.state = PenState()

        self._last_toggle_t = [float("-inf")] * n
        self._prev_tip = False
        self._smooth_x: Optional[float] = None
        self._smooth_y: Optional[float] = None
        self._sent: Dict[int, int] = {}

    # -- geometry --------------------------------------------------------

    def _bounds(self, axis: str):
        area = self.cfg.area
        lo = getattr(area, axis + "_min")
        hi = getattr(area, axis + "_max")
        if not hi:
            hi = self.x_limit if axis == "x" else self.y_limit
        if hi <= lo:
            # Nothing sane to divide by; treat the axis as a single point.
            return lo, lo + 1
        return lo, hi

    def normalise(self, x: float, y: float):
        """Raw device units to 0..1 in display orientation."""
        x_lo, x_hi = self._bounds("x")
        y_lo, y_hi = self._bounds("y")
        nx = _clamp01((x - x_lo) / float(x_hi - x_lo))
        ny = _clamp01((y - y_lo) / float(y_hi - y_lo))
        area = self.cfg.area
        if area.swap_xy:
            nx, ny = ny, nx
        if area.invert_x:
            nx = 1.0 - nx
        if area.invert_y:
            ny = 1.0 - ny
        return nx, ny

    def in_strip(self, ny: float) -> bool:
        strip = self.cfg.layout.strip
        if self.cfg.layout.strip_at == "bottom":
            return ny >= 1.0 - strip
        return ny <= strip

    def cell_at(self, nx: float) -> int:
        n = self.cfg.layout.buttons
        idx = int(nx * n)
        return 0 if idx < 0 else (n - 1 if idx >= n else idx)

    def pad_y(self, ny: float) -> float:
        """Rescale the pad's slice of the area back to a full 0..1 travel."""
        strip = self.cfg.layout.strip
        span = 1.0 - strip
        if span <= 0.0:
            return 0.0
        if self.cfg.layout.strip_at == "bottom":
            return _clamp01(ny / span)
        return _clamp01((ny - strip) / span)

    # -- MIDI emission ---------------------------------------------------

    def _cc(self, number: int, value: int, out: List[MidiMsg]) -> None:
        value = 0 if value < 0 else (127 if value > 127 else value)
        if self._sent.get(number) == value:
            return
        self._sent[number] = value
        out.append(MidiMsg(CC_STATUS | (self.cfg.midi.channel - 1), number, value))

    def _emit_axis(self, number: int, unit: float, out: List[MidiMsg]) -> int:
        """Send one normalised axis; returns the 7-bit value it now holds."""
        if self.cfg.midi.high_res:
            raw = int(round(_clamp01(unit) * 16383))
            self._cc(number, raw >> 7, out)
            self._cc(number + 32, raw & 0x7F, out)
            return raw >> 7
        value = int(round(_clamp01(unit) * 127))
        self._cc(number, value, out)
        return value

    def _emit_toggle(self, index: int, out: List[MidiMsg]) -> None:
        midi = self.cfg.midi
        value = midi.button_on if self.toggles[index] else midi.button_off
        self._cc(midi.button_cc_base + index, value, out)

    # -- the loop --------------------------------------------------------

    def feed(self, sample: PenSample) -> List[MidiMsg]:
        """Consume one report and return the messages it produced."""
        out: List[MidiMsg] = []
        cfg = self.cfg

        if not sample.in_range:
            # The pen was lifted away. Freeze the controllers where they are,
            # forget the smoothing history so the pen does not sweep across
            # the pad when it comes back, and arm the next tip press.
            self._prev_tip = False
            self._smooth_x = self._smooth_y = None
            self.state.in_range = False
            self.state.tip = False
            self.state.cell = None
            self.state.in_strip = False
            return out

        nx, ny = self.normalise(sample.x, sample.y)

        if cfg.behaviour.smoothing > 0.0:
            a = cfg.behaviour.smoothing
            self._smooth_x = nx if self._smooth_x is None else a * self._smooth_x + (1 - a) * nx
            self._smooth_y = ny if self._smooth_y is None else a * self._smooth_y + (1 - a) * ny
            nx, ny = self._smooth_x, self._smooth_y

        strip = self.in_strip(ny)
        cell = self.cell_at(nx) if strip else None

        # Buttons: a toggle flips on the tip going down, not while it drags.
        if strip and sample.tip and not self._prev_tip:
            idx = self.cell_at(nx)
            debounce = cfg.behaviour.toggle_debounce_ms / 1000.0
            if sample.t - self._last_toggle_t[idx] >= debounce:
                self._last_toggle_t[idx] = sample.t
                self.toggles[idx] = not self.toggles[idx]
                self._emit_toggle(idx, out)

        self._prev_tip = sample.tip

        # Pad controllers.
        wants_xy = sample.tip if cfg.behaviour.xy_when == "tip" else True
        if strip and cfg.behaviour.freeze_xy_in_strip:
            wants_xy = False
        if wants_xy:
            vx = self._emit_axis(cfg.midi.cc_x, nx, out)
            vy = self._emit_axis(cfg.midi.cc_y, self.pad_y(ny), out)
            self.state.cc_x_value = vx
            self.state.cc_y_value = vy

        self.state.in_range = True
        self.state.tip = sample.tip
        self.state.nx = nx
        self.state.ny = ny
        self.state.in_strip = strip
        self.state.cell = cell
        return out

    # -- housekeeping ----------------------------------------------------

    def sync_messages(self) -> List[MidiMsg]:
        """Every toggle's current state, so the host starts out in agreement."""
        out: List[MidiMsg] = []
        self._sent.clear()
        for index in range(len(self.toggles)):
            self._emit_toggle(index, out)
        return out

    def set_toggle(self, index: int, on: bool) -> List[MidiMsg]:
        """Flip a toggle from outside -- the GUI clicking a cell."""
        out: List[MidiMsg] = []
        if 0 <= index < len(self.toggles) and self.toggles[index] != on:
            self.toggles[index] = on
            self._emit_toggle(index, out)
        return out

    def all_off(self) -> List[MidiMsg]:
        out: List[MidiMsg] = []
        for index in range(len(self.toggles)):
            self.toggles[index] = False
            self._emit_toggle(index, out)
        return out
