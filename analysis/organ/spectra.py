"""Spectrogramme et dictionnaire harmonique paramétré par le timbre."""
from __future__ import annotations

import librosa
import numpy as np
import scipy.sparse as sp

from .config import Config, DEFAULT


def spectrogram(y: np.ndarray, cfg: Config = DEFAULT) -> np.ndarray:
    """Spectrogramme d'amplitude (linéaire) — base de toute la suite."""
    return np.abs(librosa.stft(y, n_fft=cfg.n_fft, hop_length=cfg.hop,
                               window="hann", center=True)).astype(np.float64)


def pitch_frequencies(cfg: Config = DEFAULT, tuning_cents: float = 0.0) -> np.ndarray:
    midi = np.arange(cfg.midi_min, cfg.midi_max + 1)
    return 440.0 * 2 ** ((midi - 69) / 12.0) * 2 ** (tuning_cents / 1200.0)


class HarmonicKernels:
    """Noyaux spectraux creux : un par (harmonique, hauteur).

    `mats[k]` est la matrice (n_freq x n_pitch) qui place, pour chaque hauteur,
    un lobe d'énergie à la fréquence `harmonics[k] * f0`. Le dictionnaire NMF
    s'écrit alors W = sum_k g[k] * mats[k], où g est le profil harmonique du
    timbre : c'est ce qui permet d'estimer notes et timbre conjointement.
    """

    def __init__(self, cfg: Config = DEFAULT, tuning_cents: float = 0.0):
        self.cfg = cfg
        self.freqs = librosa.fft_frequencies(sr=cfg.sr, n_fft=cfg.n_fft)
        self.f0s = pitch_frequencies(cfg, tuning_cents)
        self.harmonics = np.asarray(cfg.harmonics, dtype=float)
        n_freq, n_pitch = len(self.freqs), len(self.f0s)
        df = self.freqs[1] - self.freqs[0]
        nyq = cfg.sr / 2.0

        self.mats: list[sp.csr_matrix] = []
        for h in self.harmonics:
            rows, cols, vals = [], [], []
            for j, f0 in enumerate(self.f0s):
                fc = h * f0
                if fc < df or fc > nyq * 0.98:
                    continue
                sigma = np.hypot(1.1 * df, fc * cfg.cents_tolerance * 5.78e-4)
                lo = max(0, int(np.floor((fc - 3 * sigma) / df)))
                hi = min(n_freq - 1, int(np.ceil((fc + 3 * sigma) / df)))
                if hi <= lo:
                    lo, hi = max(0, lo - 1), min(n_freq - 1, hi + 1)
                bins = np.arange(lo, hi + 1)
                w = np.exp(-0.5 * ((self.freqs[bins] - fc) / sigma) ** 2)
                s = w.sum()
                if s <= 0:
                    continue
                w /= s
                rows.extend(bins.tolist())
                cols.extend([j] * len(bins))
                vals.extend(w.tolist())
            self.mats.append(
                sp.csr_matrix((vals, (rows, cols)), shape=(n_freq, n_pitch)))

        self.n_freq, self.n_pitch = n_freq, n_pitch

    def dictionary(self, g: np.ndarray) -> np.ndarray:
        """W (n_freq x n_pitch) pour un profil harmonique g donné."""
        W = np.zeros((self.n_freq, self.n_pitch))
        for gk, M in zip(g, self.mats):
            if gk > 0:
                W += gk * M.toarray()
        return W


def default_profile(cfg: Config = DEFAULT) -> np.ndarray:
    """Profil de départ : décroissance en 1/n sur les entiers, faible ailleurs."""
    h = np.asarray(cfg.harmonics, dtype=float)
    g = np.where(np.isclose(h % 1.0, 0.0), 1.0 / h, 0.15 / h)
    return g / g.max()
