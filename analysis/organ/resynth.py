"""Resynthèse additive à partir des notes et du profil harmonique extraits.

Sert à deux choses : mesurer objectivement la qualité de la transcription en
comparant la resynthèse à l'original, et servir de référence exacte au moteur
Web Audio de l'application (mêmes harmoniques, même enveloppe).
"""
from __future__ import annotations

import numpy as np

from .config import Config, DEFAULT
from .notes import Note


def render(notes: list[Note], profiles: dict[int, np.ndarray], harmonics,
           cfg: Config = DEFAULT, duration: float | None = None,
           tuning_cents: float = 0.0, attack: float = 0.030,
           release: float = 0.090, t0: float = 0.0) -> np.ndarray:
    """Somme de partiels, un jeu d'harmoniques par section (registration)."""
    harmonics = np.asarray(harmonics, dtype=float)
    if duration is None:
        duration = max((n.end for n in notes), default=0.0) - t0 + release + 0.5
    out = np.zeros(int(duration * cfg.sr) + 1, dtype=np.float64)
    nyq = cfg.sr / 2.0

    for n in notes:
        g = profiles.get(n.section)
        if g is None:
            continue
        s = int((n.start - t0) * cfg.sr)
        e = int((n.end - t0 + release) * cfg.sr)
        s, e = max(0, s), min(len(out), e)
        if e <= s:
            continue
        m = e - s
        t = np.arange(m) / cfg.sr

        env = np.ones(m)
        na = max(1, int(attack * cfg.sr))
        env[:min(na, m)] = np.linspace(0.0, 1.0, min(na, m)) ** 2
        nr = max(1, int(release * cfg.sr))
        hold = max(0, int((n.end - n.start) * cfg.sr))
        if hold < m:
            k = m - hold
            env[hold:] *= np.exp(-np.arange(k) / (nr / 3.0))

        f0 = 440.0 * 2 ** ((n.pitch - 69) / 12.0) * 2 ** (tuning_cents / 1200.0)
        sig = np.zeros(m)
        for h, gh in zip(harmonics, g):
            f = h * f0
            if gh < 1e-3 or f >= nyq * 0.98:
                continue
            sig += gh * np.sin(2 * np.pi * f * t + np.random.uniform(0, 2 * np.pi))
        out[s:e] += n.amp * sig * env

    peak = np.abs(out).max()
    return (out / peak * 0.9).astype(np.float32) if peak > 0 else out.astype(np.float32)


def log_spectral_distance(a: np.ndarray, b: np.ndarray, cfg: Config = DEFAULT) -> float:
    """Distance log-spectrale moyenne (dB) entre deux signaux, après
    normalisation d'énergie : mesure la ressemblance de contenu, pas de niveau."""
    import librosa
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    A = np.abs(librosa.stft(a, n_fft=2048, hop_length=512))
    B = np.abs(librosa.stft(b, n_fft=2048, hop_length=512))
    A = A / (A.sum() + 1e-12)
    B = B / (B.sum() + 1e-12)
    la, lb = np.log10(A + 1e-7), np.log10(B + 1e-7)
    return float(20 * np.sqrt(np.mean((la - lb) ** 2)))
