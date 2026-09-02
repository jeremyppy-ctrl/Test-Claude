#!/usr/bin/env python3
"""Rend la transcription en audio, avec les timbres et l'acoustique relevés.

    python analysis/render.py app/data/orgue.json -o rendu.wav

Sert à écouter le relevé sans passer par l'application, et à le comparer
objectivement à l'enregistrement d'origine.
"""
from __future__ import annotations

import argparse
import json

import numpy as np


def impulse(rt60: float, sr: int, seed: int = 7) -> np.ndarray:
    """Réponse impulsionnelle synthétique : bruit décroissant amorti dans l'aigu."""
    rng = np.random.default_rng(seed)
    n = int(sr * min(rt60, 6.0) * 1.05)
    t = np.arange(n) / sr
    ir = rng.normal(0, 1, n) * 10 ** (-60 * t / rt60 / 20)
    ir *= 0.15 + 0.85 * np.minimum(1.0, t / 0.05)
    # amortissement progressif de l'aigu, un pôle dont la constante suit le temps
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        a = 0.72 - 0.45 * min(1.0, t[i] / rt60)
        acc += (ir[i] - acc) * a
        out[i] = acc
    for k, dt in enumerate((0.017, 0.029, 0.041, 0.063, 0.088)):
        i = int(dt * sr)
        if i < n:
            out[i] += (-1) ** k * 0.42 / (k + 1)
    return out / (np.abs(out).max() + 1e-9)


def render(data: dict, sr: int = 44100, wet: float = 0.38,
           start: float = 0.0, end: float | None = None) -> np.ndarray:
    end = data["duration"] if end is None else end
    notes = [n for n in data["notes"] if n["end"] > start and n["start"] < end]
    seg_reg = {s["index"]: s["registration"] for s in data["segments"]}
    profiles = [np.asarray(r["profile"], float) for r in data["registrations"]]
    harmonics = np.asarray(data["harmonics"], float)
    cents = data.get("tuningCents", 0.0)
    nyq = sr / 2
    rng = np.random.default_rng(3)

    out = np.zeros(int((end - start) * sr) + sr, dtype=np.float64)
    for n in notes:
        reg = seg_reg.get(n["section"], 0)
        g = profiles[reg]
        r = data["registrations"][reg]
        atk = float(np.clip(r.get("attack", 0.04), 0.006, 0.16))
        rel = float(np.clip(r.get("release", 0.12), 0.02, 0.4))
        s = int((n["start"] - start) * sr)
        hold = max(1, int((n["end"] - n["start"]) * sr))
        tail = int(rel * 3.2 * sr)
        e = min(len(out), s + hold + tail)
        s = max(0, s)
        if e <= s:
            continue
        m = e - s
        t = np.arange(m) / sr

        env = np.ones(m)
        na = min(max(1, int(atk * sr)), m)
        env[:na] = np.linspace(0, 1, na) ** 1.6
        if hold < m:
            env[hold:] = np.exp(-np.arange(m - hold) / (rel * sr / 3.2))

        f0 = 440.0 * 2 ** ((n["pitch"] - 69) / 12.0) * 2 ** (cents / 1200.0)
        f0 *= 2 ** (rng.uniform(-3.2, 3.2) / 1200)      # aucun tuyau parfaitement juste
        sig = np.zeros(m)
        for h, gh in zip(harmonics, g):
            f = h * f0
            if gh < 5e-3 or f >= nyq * 0.98:
                continue
            sig += gh * np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi))
        amp = (max(1, min(127, n["velocity"])) / 127.0) ** 1.7 / max(1.0, np.sqrt(g.sum() * 1.6))
        out[s:e] += amp * sig * env

    peak = np.abs(out).max()
    if peak > 0:
        out /= peak
    if wet > 0:
        from scipy.signal import fftconvolve
        ir = impulse(float(data.get("rt60", 2.5)), sr)
        rev = fftconvolve(out, ir)[:len(out)]
        rev /= (np.abs(rev).max() + 1e-9)
        out = (1 - wet * 0.45) * out + wet * rev
    return (out / (np.abs(out).max() + 1e-9) * 0.89).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("json", help="fichier orgue.json produit par transcribe.py")
    ap.add_argument("-o", "--out", default="rendu.wav")
    ap.add_argument("--sr", type=int, default=44100)
    ap.add_argument("--wet", type=float, default=0.38, help="dose de réverbération (0-1)")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()

    data = json.load(open(args.json, encoding="utf-8"))
    y = render(data, args.sr, args.wet, args.start, args.end)
    import soundfile as sf
    sf.write(args.out, y, args.sr)
    print(f"{args.out} — {len(y) / args.sr:.1f} s, {len(data['notes'])} notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
