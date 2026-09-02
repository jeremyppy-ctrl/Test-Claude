"""Séparation parole / musique.

L'enregistrement est une démonstration commentée : les extraits joués alternent
avec de longs passages parlés. Transcrire la parole produit des dizaines de
fausses notes par seconde — il faut donc l'écarter avant toute autre analyse.

Trois traits mesurés par fenêtre courte suffisent :
  * le **niveau** — la voix, prise à distance dans la nef, reste très en dessous
    des jeux de l'orgue ; c'est ici le trait décisif ;
  * la **tenue** — similarité du spectre à 0,12 s d'intervalle : un tuyau tient
    sa note, la parole change de spectre à chaque phonème ;
  * le **contraste pic/vallée** — l'orgue produit des raies harmoniques
    étroites et des vallées profondes, la voix des formants larges.

Le niveau seul suffit aux passages francs ; les deux autres rattrapent les
extraits joués en jeux doux, qui sinon passeraient pour de la parole.
"""
from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from .config import Config, DEFAULT

WIN = 0.5             # s, pas d'analyse
LEVEL_STRONG = 0.10   # au-dessus de cette fraction du niveau global : musique
LEVEL_WEAK = 0.035    # en dessous : rien d'exploitable
SUSTAIN_MIN = 0.785   # tenue minimale pour rattraper un jeu doux
CONTRAST_MIN = 24.0   # dB entre pics et vallées du spectre
MIN_RUN = 2.0         # s, durée mini d'un passage
MARGIN = 0.35         # s, marge conservée autour de la musique (attaques, queues)


@dataclass
class Span:
    start: float
    end: float
    music: bool

    @property
    def duration(self) -> float:
        return self.end - self.start


def features(y: np.ndarray, cfg: Config = DEFAULT) -> dict:
    n_fft, hop = 4096, 512
    S = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop))
    fr = cfg.sr / hop
    freqs = librosa.fft_frequencies(sr=cfg.sr, n_fft=n_fft)

    band = (freqs > 250) & (freqs < 4000)
    Lb = 20 * np.log10(S[band] + 1e-5)
    contrast = np.percentile(Lb, 92, axis=0) - np.percentile(Lb, 40, axis=0)

    d = max(1, int(0.12 * fr))
    A, B = S[:, :-d], S[:, d:]
    sustain = (A * B).sum(0) / (np.linalg.norm(A, axis=0) * np.linalg.norm(B, axis=0) + 1e-9)
    sustain = np.pad(sustain, (0, d), mode="edge")

    level = S.sum(0)
    return {"contrast": contrast, "sustain": sustain, "level": level,
            "frame_rate": fr, "global": float(np.percentile(level, 90))}


def analyse(y: np.ndarray, cfg: Config = DEFAULT) -> tuple[list[Span], dict]:
    f = features(y, cfg)
    fr, G = f["frame_rate"], f["global"]
    step = max(1, int(WIN * fr))
    n = len(f["level"])

    spans: list[Span] = []
    for i in range(0, n, step):
        sl = slice(i, min(i + step, n))
        lvl = float(np.percentile(f["level"][sl], 90)) / max(G, 1e-9)
        sus = float(np.median(f["sustain"][sl]))
        con = float(np.median(f["contrast"][sl]))
        music = lvl > LEVEL_STRONG or (
            lvl > LEVEL_WEAK and sus > SUSTAIN_MIN and con > CONTRAST_MIN)
        t0, t1 = i / fr, min((i + step) / fr, len(y) / cfg.sr)
        if spans and spans[-1].music == music:
            spans[-1].end = t1
        else:
            spans.append(Span(t0, t1, music))

    spans = _despeckle(spans)
    stats = {"music": sum(s.duration for s in spans if s.music),
             "speech": sum(s.duration for s in spans if not s.music),
             "globalLevel": G}
    return spans, stats


def _despeckle(spans: list[Span]) -> list[Span]:
    """Absorbe les fragments trop courts pour être une prise ou une phrase."""
    while len(spans) > 1:
        short = [i for i, s in enumerate(spans) if s.duration < MIN_RUN]
        if not short:
            break
        i = short[0]
        s = spans[i]
        if i == 0:
            spans[1].start = s.start
        elif i == len(spans) - 1:
            spans[-2].end = s.end
        else:
            spans[i - 1].end = spans[i + 1].start = (s.start + s.end) / 2
        spans.pop(i)
        merged: list[Span] = []
        for sp in spans:
            if merged and merged[-1].music == sp.music:
                merged[-1].end = sp.end
            else:
                merged.append(sp)
        spans = merged
    return spans


def music_spans(y: np.ndarray, cfg: Config = DEFAULT) -> tuple[list[Span], dict]:
    spans, stats = analyse(y, cfg)
    total = len(y) / cfg.sr
    out = [Span(max(0.0, s.start - MARGIN), min(total, s.end + MARGIN), True)
           for s in spans if s.music]
    return out, stats
