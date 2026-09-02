"""Chargement audio et découpage en sections musicales."""
from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from .config import Config, DEFAULT


def load(path: str, cfg: Config = DEFAULT) -> np.ndarray:
    y, _ = librosa.load(path, sr=cfg.sr, mono=True)
    return y.astype(np.float32)


@dataclass
class Section:
    index: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def split_sections(y: np.ndarray, cfg: Config = DEFAULT) -> list[Section]:
    """Découpe le signal aux silences longs (changement de pièce ou de registration)."""
    hop = cfg.hop
    n = len(y) // hop
    rms = np.sqrt(np.array([np.mean(y[i * hop:(i + 1) * hop] ** 2) for i in range(n)]) + 1e-12)
    db = 20 * np.log10(rms + 1e-12)
    active = db > (db.max() + cfg.silence_db)

    # dilatation : un silence n'est séparateur que s'il dure min_silence
    min_sil = int(cfg.min_silence * cfg.frame_rate)
    runs, start = [], None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, n))

    merged: list[list[int]] = []
    for a, b in runs:
        if merged and a - merged[-1][1] < min_sil:
            merged[-1][1] = b
        else:
            merged.append([a, b])

    sections, k = [], 0
    for a, b in merged:
        t0, t1 = a / cfg.frame_rate, b / cfg.frame_rate
        if t1 - t0 < cfg.min_section:
            continue
        # marge : on récupère l'attaque et la queue de réverbération
        sections.append(Section(k, max(0.0, t0 - 0.25), min(len(y) / cfg.sr, t1 + 0.45)))
        k += 1
    return sections


def estimate_tuning(y: np.ndarray, cfg: Config = DEFAULT) -> float:
    """Écart d'accord de l'instrument en cents par rapport à La = 440 Hz.

    Moyenne circulaire pondérée de l'écart au demi-ton le plus proche, sur tous
    les pics spectraux saillants : robuste à la polyphonie et à la réverbération.
    """
    n_fft, hop = 8192, 4096
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=cfg.sr, n_fft=n_fft)
    df = freqs[1] - freqs[0]
    dev, wts = [], []
    for t in range(S.shape[1]):
        col = S[:, t]
        if col.max() < 1e-3:
            continue
        idx = np.where((col[1:-1] > col[:-2]) & (col[1:-1] > col[2:])
                       & (col[1:-1] > 0.08 * col.max()))[0] + 1
        for i in idx:
            a, b, c = (np.log(col[i - 1] + 1e-12), np.log(col[i] + 1e-12),
                       np.log(col[i + 1] + 1e-12))
            d = np.clip(0.5 * (a - c) / (a - 2 * b + c + 1e-12), -0.5, 0.5)
            f = freqs[i] + d * df
            if not (60.0 <= f <= 4000.0):
                continue
            m = 69 + 12 * np.log2(f / 440.0)
            dev.append((m - np.round(m)) * 100.0)
            wts.append(col[i])
    if not dev:
        return 0.0
    dev, wts = np.array(dev), np.array(wts)
    ang = np.sum(wts * np.exp(2j * np.pi * dev / 100.0))
    return float(np.angle(ang) / (2 * np.pi) * 100.0)
