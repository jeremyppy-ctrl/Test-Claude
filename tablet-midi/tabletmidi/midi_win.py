"""MIDI output on Windows, through winmm.

Windows has no way to create a virtual MIDI port from user space -- that needs
a kernel driver -- so this opens a port someone else published. loopMIDI is
the usual choice: it creates a port the DAW sees as an input, and we write to
its output side.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import POINTER, Structure, byref, sizeof
from dataclasses import dataclass
from typing import List, Optional

from .mapping import MidiMsg

DWORD = ctypes.c_uint32
WORD = ctypes.c_uint16
HMIDIOUT = ctypes.c_void_p
UINT = ctypes.c_uint32

MMSYSERR_NOERROR = 0
CALLBACK_NULL = 0
MAXPNAMELEN = 32

#: Ports that exist but cannot carry our messages anywhere useful.
_USELESS = ("microsoft gs wavetable",)


class MidiUnavailable(RuntimeError):
    """Raised when no usable MIDI output port can be opened."""


class MIDIOUTCAPSW(Structure):
    """``MIDIOUTCAPSW`` from mmeapi.h.

    ``szPname`` is declared as raw UTF-16 code units rather than ``c_wchar``:
    a wide character is 2 bytes on Windows but 4 on Linux, and spelling it out
    keeps the structure exactly 84 bytes wherever the test suite runs.
    """

    _fields_ = [
        ("wMid", WORD),
        ("wPid", WORD),
        ("vDriverVersion", DWORD),
        ("szPname", WORD * MAXPNAMELEN),
        ("wTechnology", WORD),
        ("wVoices", WORD),
        ("wNotes", WORD),
        ("wChannelMask", WORD),
        ("dwSupport", DWORD),
    ]

    @property
    def name(self) -> str:
        units = []
        for unit in self.szPname:
            if unit == 0:
                break
            units.append(unit)
        return "".join(chr(u) for u in units) if units else ""


_winmm = None


def _load():
    global _winmm
    if _winmm is not None:
        return _winmm
    if sys.platform != "win32":
        raise MidiUnavailable(
            "MIDI output is implemented for Windows only (running on %s)"
            % sys.platform
        )
    winmm = ctypes.WinDLL("winmm")
    winmm.midiOutGetNumDevs.restype = UINT
    winmm.midiOutGetDevCapsW.argtypes = [ctypes.c_size_t, POINTER(MIDIOUTCAPSW), UINT]
    winmm.midiOutGetDevCapsW.restype = UINT
    winmm.midiOutOpen.argtypes = [
        POINTER(HMIDIOUT), UINT, ctypes.c_size_t, ctypes.c_size_t, DWORD
    ]
    winmm.midiOutOpen.restype = UINT
    winmm.midiOutShortMsg.argtypes = [HMIDIOUT, DWORD]
    winmm.midiOutShortMsg.restype = UINT
    winmm.midiOutReset.argtypes = [HMIDIOUT]
    winmm.midiOutReset.restype = UINT
    winmm.midiOutClose.argtypes = [HMIDIOUT]
    winmm.midiOutClose.restype = UINT
    winmm.midiOutGetErrorTextW.argtypes = [UINT, ctypes.c_wchar_p, UINT]
    winmm.midiOutGetErrorTextW.restype = UINT
    _winmm = winmm
    return winmm


@dataclass
class MidiPort:
    index: int
    name: str

    @property
    def looks_virtual(self) -> bool:
        low = self.name.lower()
        return any(k in low for k in ("loopmidi", "loopbe", "virtual", "rtpmidi"))


def _error_text(code: int) -> str:
    try:
        winmm = _load()
        buf = ctypes.create_unicode_buffer(256)
        if winmm.midiOutGetErrorTextW(code, buf, len(buf)) == MMSYSERR_NOERROR:
            return buf.value
    except Exception:
        pass
    return "MMSYSERR %d" % code


def list_ports() -> List[MidiPort]:
    """Every MIDI output Windows knows about, in device-id order."""
    winmm = _load()
    ports: List[MidiPort] = []
    for index in range(winmm.midiOutGetNumDevs()):
        caps = MIDIOUTCAPSW()
        if winmm.midiOutGetDevCapsW(index, byref(caps), sizeof(caps)) == MMSYSERR_NOERROR:
            ports.append(MidiPort(index, caps.name))
    return ports


def find_port(name: str, fallback: bool = True) -> Optional[MidiPort]:
    """Match a port by name.

    winmm truncates port names to 32 characters, so an exact match is not
    something we can rely on; prefix and substring matches are tried in turn.

    With ``fallback`` off, a name that matches nothing returns None instead of
    the next best port -- which is what ``doctor`` needs in order to say that
    the configured port is missing rather than quietly using another one.
    """
    ports = list_ports()
    needle = (name or "").strip().lower()
    if needle:
        for test in (
            lambda p: p.name.lower() == needle,
            lambda p: p.name.lower().startswith(needle),
            lambda p: needle in p.name.lower(),
        ):
            for port in ports:
                if test(port):
                    return port
        if not fallback:
            return None
    for port in ports:
        if port.looks_virtual:
            return port
    for port in ports:
        if not any(k in port.name.lower() for k in _USELESS):
            return port
    return None


class MidiOut:
    """An open MIDI output port."""

    def __init__(self, port: MidiPort) -> None:
        winmm = _load()
        self._winmm = winmm
        self.port = port
        handle = HMIDIOUT()
        rc = winmm.midiOutOpen(byref(handle), port.index, 0, 0, CALLBACK_NULL)
        if rc != MMSYSERR_NOERROR:
            raise MidiUnavailable(
                "could not open MIDI port '%s': %s" % (port.name, _error_text(rc))
            )
        self._handle = handle
        self._closed = False

    @classmethod
    def open_named(cls, name: str) -> "MidiOut":
        port = find_port(name)
        if port is None:
            raise MidiUnavailable(
                "no MIDI output port found. Install loopMIDI and create a "
                "port, then pick it here."
            )
        return cls(port)

    def send(self, msg: MidiMsg) -> None:
        if self._closed:
            return
        rc = self._winmm.midiOutShortMsg(self._handle, msg.packed())
        if rc != MMSYSERR_NOERROR:
            raise MidiUnavailable("midiOutShortMsg failed: %s" % _error_text(rc))

    def send_all(self, messages) -> None:
        for msg in messages:
            self.send(msg)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._winmm.midiOutReset(self._handle)
        self._winmm.midiOutClose(self._handle)

    def __enter__(self) -> "MidiOut":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
