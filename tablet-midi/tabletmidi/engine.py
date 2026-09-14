"""The running loop, shared by the command line and the window.

A worker thread owns the tablet and the MIDI port; callers read a snapshot of
what it is doing. Nothing here touches Tk, and with the simulated reader it
runs on any platform, which is what makes the behaviour testable.
"""

from __future__ import annotations

import copy
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .config import Config
from .mapping import Mapper, MidiMsg, PenSample, PenState

#: How long to wait before trying a disconnected tablet again.
RETRY_SECONDS = 2.0


class Reader:
    """What the engine needs from a source of pen samples."""

    label = "none"
    x_limit = 0
    y_limit = 0

    def sample(self, t: float, timeout_ms: int = 20) -> Optional[PenSample]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class SimulatedReader(Reader):
    """A pen that draws a slow Lissajous figure and taps the strip.

    Useful for checking that the host reacts to the controllers before any
    driver-level change has been made.
    """

    label = "simulated tablet"
    x_limit = 32767
    y_limit = 32767

    def __init__(
        self,
        period: float = 9.0,
        first_tap: float = 0.8,
        gap: float = 1.6,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        """
        ``clock`` and ``sleep`` are injectable so tests can run the simulation
        without waiting for it.
        """
        self.period = period
        self.gap = gap
        self._clock = clock
        self._sleep = sleep
        self._start = clock()
        self._next_tap = first_tap
        self._tap_until = 0.0
        self._cell = 0

    def sample(self, t: float, timeout_ms: int = 20) -> Optional[PenSample]:
        self._sleep(min(timeout_ms, 8) / 1000.0)
        t = self._clock()
        age = t - self._start
        if age >= self._next_tap:
            self._next_tap = age + self.gap
            self._tap_until = t + 0.12
            self._cell = (self._cell + 3) % 10

        if t < self._tap_until:
            nx = (self._cell + 0.5) / 10.0
            ny = 0.95
            tip = True
        else:
            phase = 2 * math.pi * age / self.period
            nx = 0.5 + 0.45 * math.sin(phase)
            ny = 0.42 + 0.33 * math.sin(phase * 1.37 + 0.6)
            tip = False
        return PenSample(
            x=nx * self.x_limit, y=ny * self.y_limit,
            tip=tip, in_range=True, pressure=800 if tip else 0, t=t,
        )


class NullMidiOut:
    """Stands in for a MIDI port when there is nowhere to send."""

    class _Port:
        name = "none (messages discarded)"

    port = _Port()

    def send(self, msg: MidiMsg) -> None:
        pass

    def send_all(self, messages) -> None:
        pass

    def close(self) -> None:
        pass


@dataclass
class Snapshot:
    """Everything a UI needs to draw one frame."""

    running: bool = False
    device: str = ""
    midi: str = ""
    error: str = ""
    calibrating: bool = False
    pen: PenState = field(default_factory=PenState)
    toggles: List[bool] = field(default_factory=list)
    samples: int = 0
    messages: int = 0
    x_limit: int = 0
    y_limit: int = 0


class Engine:
    """Owns the tablet, the mapper and the MIDI port."""

    def __init__(
        self,
        cfg: Config,
        log: Optional[Callable[[str], None]] = None,
        simulate: bool = False,
        midi_enabled: bool = True,
    ) -> None:
        self.cfg = cfg.validate()
        self.simulate = simulate
        self.midi_enabled = midi_enabled
        self._log = log or (lambda msg: None)

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pending: List[Callable[[], None]] = []

        self.mapper = Mapper(cfg)
        self._snapshot = Snapshot(toggles=list(self.mapper.toggles))
        self._reader: Optional[Reader] = None
        self._midi = None

        self._calibrating = False
        self._cal: Optional[List[float]] = None
        self._samples = 0
        self._messages = 0

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tabletmidi", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)
        self._thread = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def snapshot(self) -> Snapshot:
        with self._lock:
            snap = Snapshot(
                running=self.running,
                device=self._snapshot.device,
                midi=self._snapshot.midi,
                error=self._snapshot.error,
                calibrating=self._calibrating,
                pen=copy.copy(self.mapper.state),
                toggles=list(self.mapper.toggles),
                samples=self._samples,
                messages=self._messages,
                x_limit=self.mapper.x_limit,
                y_limit=self.mapper.y_limit,
            )
        return snap

    def post(self, fn: Callable[[], None]) -> None:
        """Queue work to run on the engine thread, between samples."""
        with self._lock:
            self._pending.append(fn)

    # -- actions ---------------------------------------------------------

    def toggle(self, index: int, on: Optional[bool] = None) -> None:
        def action() -> None:
            want = (not self.mapper.toggles[index]) if on is None else on
            self._send(self.mapper.set_toggle(index, want))

        if 0 <= index < len(self.mapper.toggles):
            self.post(action)

    def all_off(self) -> None:
        self.post(lambda: self._send(self.mapper.all_off()))

    def resend(self) -> None:
        self.post(lambda: self._send(self.mapper.sync_messages()))

    def begin_calibration(self) -> None:
        def action() -> None:
            self._cal = None
            self._calibrating = True
            self._log("Calibration: sweep the pen over the whole area you want to use.")

        self.post(action)

    def end_calibration(self, keep: bool = True) -> bool:
        """Stop collecting and, when asked, store the swept rectangle."""
        done = threading.Event()
        result = {"ok": False}

        def action() -> None:
            self._calibrating = False
            box = self._cal
            self._cal = None
            if keep and box and box[1] > box[0] and box[3] > box[2]:
                area = self.cfg.area
                area.x_min, area.x_max = int(box[0]), int(box[1])
                area.y_min, area.y_max = int(box[2]), int(box[3])
                self.mapper.cfg = self.cfg.validate()
                self._log(
                    "Calibrated: X %d-%d, Y %d-%d"
                    % (area.x_min, area.x_max, area.y_min, area.y_max)
                )
                result["ok"] = True
            elif keep:
                self._log("Calibration discarded: the pen did not cover an area.")
            done.set()

        self.post(action)
        done.wait(2.0)
        return result["ok"]

    def apply_config(self, cfg: Config) -> None:
        """Swap in an edited configuration without dropping the tablet."""
        cfg.validate()

        def action() -> None:
            keep = list(self.mapper.toggles)
            self.cfg = cfg
            self.mapper = Mapper(cfg, self.mapper.x_limit, self.mapper.y_limit)
            for index, on in enumerate(keep[: len(self.mapper.toggles)]):
                self.mapper.toggles[index] = on
            self._send(self.mapper.sync_messages())
            self._log("Configuration applied.")

        self.post(action)

    # -- the worker ------------------------------------------------------

    def _send(self, messages: List[MidiMsg]) -> None:
        if not messages:
            return
        if self._midi is not None:
            try:
                self._midi.send_all(messages)
            except Exception as exc:  # a port can vanish under us
                self._set(error="MIDI: %s" % exc)
                self._close_midi()
                return
        self._messages += len(messages)

    def _set(self, **kwargs) -> None:
        with self._lock:
            for key, value in kwargs.items():
                setattr(self._snapshot, key, value)

    def _close_midi(self) -> None:
        if self._midi is not None:
            try:
                self._midi.close()
            except Exception:
                pass
        self._midi = None
        self._set(midi="")

    def _close_reader(self) -> None:
        if self._reader is not None:
            try:
                self._reader.close()
            except Exception:
                pass
        self._reader = None
        self._set(device="")

    def _open_midi(self) -> bool:
        if self._midi is not None:
            return True
        if not self.midi_enabled:
            self._midi = NullMidiOut()
            self._set(midi=self._midi.port.name)
            return True
        from .midi_win import MidiOut, MidiUnavailable

        try:
            self._midi = MidiOut.open_named(self.cfg.midi.port_name)
        except MidiUnavailable as exc:
            self._set(error=str(exc))
            return False
        self._set(midi=self._midi.port.name, error="")
        self._log("MIDI output: %s" % self._midi.port.name)
        return True

    def _open_reader(self) -> bool:
        if self._reader is not None:
            return True
        if self.simulate:
            self._reader = SimulatedReader()
        else:
            from .hid_win import (
                HidUnavailable, PenReader, enumerate_devices, pick_device,
                wake_uclogic,
            )

            try:
                devices = enumerate_devices()
                dev = pick_device(
                    devices,
                    vid=self.cfg.device.vid,
                    pid=self.cfg.device.pid,
                    path=self.cfg.device.path,
                    name_hint=self.cfg.device.name_hint,
                )
                if dev is None:
                    self._set(error="No tablet found. Plug it in, or pick it in Settings.")
                    return False
                if not dev.readable:
                    wake_uclogic(dev)
                self._reader = PenReader(dev)
                self._reader.label = dev.describe()
            except HidUnavailable as exc:
                self._set(error=str(exc))
                return False

        self.mapper.x_limit = self._reader.x_limit
        self.mapper.y_limit = self._reader.y_limit
        self._set(device=self._reader.label, error="")
        self._log("Tablet: %s" % self._reader.label)
        return True

    def _drain(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, []
        for fn in pending:
            try:
                fn()
            except Exception as exc:
                self._log("action failed: %s" % exc)

    def _run(self) -> None:
        synced = False
        next_try = 0.0
        try:
            while not self._stop.is_set():
                self._drain()

                now = time.monotonic()
                if self._reader is None or self._midi is None:
                    if now < next_try:
                        time.sleep(0.05)
                        continue
                    if not (self._open_reader() and self._open_midi()):
                        next_try = now + RETRY_SECONDS
                        continue
                    if self.cfg.behaviour.sync_on_start and not synced:
                        self._send(self.mapper.sync_messages())
                        synced = True

                try:
                    sample = self._reader.sample(time.monotonic(), timeout_ms=20)
                except Exception as exc:
                    self._log("Tablet disconnected: %s" % exc)
                    self._set(error=str(exc))
                    self._close_reader()
                    next_try = time.monotonic() + RETRY_SECONDS
                    continue

                if sample is None:
                    continue
                self._samples += 1

                if self._calibrating:
                    if self._cal is None:
                        self._cal = [sample.x, sample.x, sample.y, sample.y]
                    else:
                        self._cal[0] = min(self._cal[0], sample.x)
                        self._cal[1] = max(self._cal[1], sample.x)
                        self._cal[2] = min(self._cal[2], sample.y)
                        self._cal[3] = max(self._cal[3], sample.y)

                self._send(self.mapper.feed(sample))
        finally:
            self._close_reader()
            self._close_midi()
