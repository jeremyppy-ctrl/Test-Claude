"""Écriture d'un fichier MIDI type 1, sans dépendance externe."""
from __future__ import annotations

import struct

from .notes import Note

TICKS = 480


def _vlq(n: int) -> bytes:
    if n == 0:
        return b"\x00"
    out = bytearray()
    while n:
        out.insert(0, n & 0x7F)
        n >>= 7
    for i in range(len(out) - 1):
        out[i] |= 0x80
    return bytes(out)


def _track(events: list[tuple[int, bytes]]) -> bytes:
    events.sort(key=lambda e: e[0])
    data, prev = bytearray(), 0
    for tick, payload in events:
        data += _vlq(tick - prev) + payload
        prev = tick
    data += _vlq(0) + b"\xff\x2f\x00"
    return b"MTrk" + struct.pack(">I", len(data)) + bytes(data)


def _text(kind: int, s: str) -> bytes:
    b = s.encode("utf-8")[:127]
    return bytes([0xFF, kind, len(b)]) + b


def write(path: str, notes: list[Note], bpm: float = 100.0,
          track_names: dict[int, str] | None = None,
          programs: dict[int, int] | None = None,
          title: str = "Transcription d'orgue") -> None:
    """Une piste par section : chaque registration reste identifiable."""
    track_names = track_names or {}
    programs = programs or {}
    spt = 60.0 / bpm / TICKS      # secondes par tick

    def tick(t: float) -> int:
        return max(0, int(round(t / spt)))

    tracks = [_track([(0, _text(0x03, title)),
                      (0, b"\xff\x51\x03" + struct.pack(">I", int(60e6 / bpm))[1:]),
                      (0, b"\xff\x58\x04\x04\x02\x18\x08")])]

    sections = sorted({n.section for n in notes})
    for ch, sec in enumerate(sections):
        chan = ch % 16
        if chan == 9:                      # on saute le canal percussif
            chan = (ch + 1) % 16
        evs: list[tuple[int, bytes]] = [
            (0, _text(0x03, track_names.get(sec, f"Section {sec}")))]
        evs.append((0, bytes([0xC0 | chan, programs.get(sec, 19) & 0x7F])))
        for n in notes:
            if n.section != sec:
                continue
            s, e = tick(n.start), max(tick(n.end), tick(n.start) + 1)
            evs.append((s, bytes([0x90 | chan, n.pitch & 0x7F, max(1, min(127, n.velocity))])))
            evs.append((e, bytes([0x80 | chan, n.pitch & 0x7F, 0])))
        tracks.append(_track(evs))

    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), TICKS)
    with open(path, "wb") as f:
        f.write(header + b"".join(tracks))
