"""Configuration: defaults, JSON persistence and validation.

Portable on purpose -- no Windows API in here, so it can be unit tested
anywhere.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, fields
from typing import Any, Dict, Optional


class ConfigError(ValueError):
    """Raised when a configuration cannot be used as given."""


@dataclass
class DeviceCfg:
    """How to find the tablet again on the next run."""

    vid: Optional[int] = None
    pid: Optional[int] = None
    #: Exact HID interface path. Pinned by ``calibrate`` so that a tablet
    #: exposing several collections always comes back on the same one.
    path: Optional[str] = None
    #: Substring matched against the product string when vid/pid are unset.
    name_hint: str = ""


@dataclass
class AreaCfg:
    """The rectangle of the tablet that is actually used.

    Bounds are in raw device units. A ``max`` of 0 means "use the logical
    maximum the tablet reports", which is the right default before any
    calibration has happened.
    """

    x_min: int = 0
    x_max: int = 0
    y_min: int = 0
    y_max: int = 0
    invert_x: bool = False
    invert_y: bool = False
    swap_xy: bool = False


@dataclass
class MidiCfg:
    port_name: str = "loopMIDI"
    channel: int = 1
    cc_x: int = 16
    cc_y: int = 17
    #: Send X and Y as 14-bit pairs (CC n = MSB, CC n+32 = LSB).
    high_res: bool = False
    button_cc_base: int = 20
    button_on: int = 127
    button_off: int = 0


@dataclass
class LayoutCfg:
    buttons: int = 10
    #: Height of the button strip, as a fraction of the active area.
    strip: float = 0.15
    strip_at: str = "bottom"


@dataclass
class BehaviourCfg:
    #: "hover" -> X/Y follow the pen whenever it is in range;
    #: "tip"   -> only while the tip is pressed.
    xy_when: str = "hover"
    #: Hold X/Y still while the pen is over the button strip, so that hitting
    #: a button does not also throw the two continuous controllers.
    freeze_xy_in_strip: bool = True
    #: Weight of the previous sample, 0 disables smoothing.
    smoothing: float = 0.2
    toggle_debounce_ms: int = 150
    #: Send every toggle's state once at startup so the host agrees with us.
    sync_on_start: bool = True


_SECTIONS = {
    "device": DeviceCfg,
    "area": AreaCfg,
    "midi": MidiCfg,
    "layout": LayoutCfg,
    "behaviour": BehaviourCfg,
}


@dataclass
class Config:
    device: DeviceCfg = None  # type: ignore[assignment]
    area: AreaCfg = None  # type: ignore[assignment]
    midi: MidiCfg = None  # type: ignore[assignment]
    layout: LayoutCfg = None  # type: ignore[assignment]
    behaviour: BehaviourCfg = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        for name, cls in _SECTIONS.items():
            if getattr(self, name) is None:
                setattr(self, name, cls())

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {name: asdict(getattr(self, name)) for name in _SECTIONS}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        if not isinstance(data, dict):
            raise ConfigError("the configuration file must hold a JSON object")
        kwargs = {}
        for name, section_cls in _SECTIONS.items():
            raw = data.get(name, {})
            if not isinstance(raw, dict):
                raise ConfigError("section '%s' must be a JSON object" % name)
            known = {f.name for f in fields(section_cls)}
            unknown = set(raw) - known
            if unknown:
                raise ConfigError(
                    "unknown key(s) in section '%s': %s"
                    % (name, ", ".join(sorted(unknown)))
                )
            kwargs[name] = section_cls(**raw)
        cfg = cls(**kwargs)
        cfg.validate()
        return cfg

    @classmethod
    def load(cls, path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    @classmethod
    def load_or_default(cls, path: str) -> "Config":
        if os.path.exists(path):
            return cls.load(path)
        cfg = cls()
        cfg.validate()
        return cfg

    def save(self, path: str) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, sort_keys=False)
            fh.write("\n")
        os.replace(tmp, path)

    # -- validation ------------------------------------------------------

    def validate(self) -> "Config":
        m, l, b, a = self.midi, self.layout, self.behaviour, self.area

        if not 1 <= m.channel <= 16:
            raise ConfigError("midi.channel must be between 1 and 16")
        for name in ("cc_x", "cc_y", "button_cc_base"):
            value = getattr(m, name)
            if not 0 <= value <= 127:
                raise ConfigError("midi.%s must be between 0 and 127" % name)
        for name in ("button_on", "button_off"):
            if not 0 <= getattr(m, name) <= 127:
                raise ConfigError("midi.%s must be between 0 and 127" % name)
        if m.button_on == m.button_off:
            raise ConfigError("midi.button_on and midi.button_off must differ")

        if l.buttons < 1:
            raise ConfigError("layout.buttons must be at least 1")
        if not 0.0 < l.strip < 1.0:
            raise ConfigError("layout.strip must be strictly between 0 and 1")
        if l.strip_at not in ("bottom", "top"):
            raise ConfigError("layout.strip_at must be 'bottom' or 'top'")

        last = m.button_cc_base + l.buttons - 1
        if last > 127:
            raise ConfigError(
                "layout.buttons=%d starting at CC %d runs past CC 127"
                % (l.buttons, m.button_cc_base)
            )

        button_range = range(m.button_cc_base, last + 1)
        for name in ("cc_x", "cc_y"):
            if getattr(m, name) in button_range:
                raise ConfigError(
                    "midi.%s (CC %d) collides with the button range CC %d-%d"
                    % (name, getattr(m, name), m.button_cc_base, last)
                )
        if m.cc_x == m.cc_y:
            raise ConfigError("midi.cc_x and midi.cc_y must differ")

        if m.high_res:
            # The LSB of a 14-bit controller always lives at CC n+32, which
            # only exists for the first 32 controllers.
            for name in ("cc_x", "cc_y"):
                if getattr(m, name) > 31:
                    raise ConfigError(
                        "midi.high_res needs midi.%s to be 31 or below "
                        "(its LSB is sent on CC+32)" % name
                    )
            lsbs = {m.cc_x + 32, m.cc_y + 32}
            if lsbs & set(button_range):
                raise ConfigError(
                    "the 14-bit LSB controllers collide with the button range"
                )

        if b.xy_when not in ("hover", "tip"):
            raise ConfigError("behaviour.xy_when must be 'hover' or 'tip'")
        if not 0.0 <= b.smoothing < 1.0:
            raise ConfigError("behaviour.smoothing must be in [0, 1)")
        if b.toggle_debounce_ms < 0:
            raise ConfigError("behaviour.toggle_debounce_ms cannot be negative")

        for axis in ("x", "y"):
            lo = getattr(a, axis + "_min")
            hi = getattr(a, axis + "_max")
            if hi and hi <= lo:
                raise ConfigError(
                    "area.%s_max must be greater than area.%s_min" % (axis, axis)
                )
        return self


def default_config_path() -> str:
    """Where the configuration lives when the user does not say otherwise."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "TabletMidi", "config.json")
