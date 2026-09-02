"""Passage des activations NMF à des événements de notes."""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
from scipy.ndimage import maximum_filter1d, median_filter, uniform_filter1d

from .config import Config, DEFAULT


@dataclass
class Note:
    pitch: int          # numéro MIDI
    start: float        # s, absolu dans l'enregistrement
    end: float          # s
    velocity: int       # 1..127, dérivé de l'amplitude estimée
    amp: float          # amplitude linéaire estimée
    section: int = 0
    voice: int = 0      # 0 = manuel, 1 = pédale (déduit ensuite)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["start"] = round(d["start"], 4)
        d["end"] = round(d["end"], 4)
        d["amp"] = round(d["amp"], 6)
        return d


def note_energy(A: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Énergie spectrale portée par chaque hauteur (compense la troncature
    des harmoniques au-delà de Nyquist pour les notes aiguës)."""
    return A * W.sum(axis=0)[:, None]


def detection_threshold(Es: np.ndarray, cfg: Config, rel_onset: float,
                        abs_floor: float, floor_level: float | None = None) -> np.ndarray:
    """Seuil d'attaque adaptatif, trame par trame.

    Le niveau de référence suit la sonorité locale (nombre de jeux tirés, boîte
    expressive) : sans cela un même seuil absolu sur-détecte dans les tutti et
    manque les notes dans les passages doux.
    """
    fr = cfg.frame_rate
    top = np.sort(Es, axis=0)[-3:, :].mean(axis=0)
    local = maximum_filter1d(top, size=max(3, int(0.7 * fr)), mode="nearest")
    local = uniform_filter1d(local, size=max(3, int(0.5 * fr)), mode="nearest")
    # Le plancher doit se référer à tout l'enregistrement : mesuré sur la seule
    # fenêtre courante, il descendrait au niveau du bruit dans les passages
    # doux et transformerait la réverbération en notes.
    if floor_level is None:
        floor_level = float(np.percentile(top, 90)) if top.size else 0.0
    return np.maximum(abs_floor * floor_level, rel_onset * local)


def extract(E: np.ndarray, cfg: Config = DEFAULT, t0: float = 0.0,
            section: int = 0, rel_onset: float | None = None,
            abs_floor: float | None = None,
            prominence: float | None = None,
            floor_level: float | None = None) -> list[Note]:
    """Suivi par hystérésis sur la matrice énergie (n_pitch x n_frames)."""
    rel_onset = cfg.rel_onset if rel_onset is None else rel_onset
    abs_floor = cfg.abs_floor if abs_floor is None else abs_floor
    prominence = cfg.prominence if prominence is None else prominence

    fr = cfg.frame_rate
    Es = median_filter(E, size=(1, 5), mode="nearest")
    Es = uniform_filter1d(Es, size=3, axis=1, mode="nearest")
    if Es.max() <= 0:
        return []

    thr_on = detection_threshold(Es, cfg, rel_onset, abs_floor, floor_level)
    thr_off = thr_on * cfg.offset_ratio

    # saillance sur l'axe des hauteurs : une vraie note domine ses voisines d'un
    # demi-ton, contrairement à l'étalement dû à la réverbération
    pad = np.pad(Es, ((1, 1), (0, 0)), mode="constant")
    neigh = np.maximum(pad[:-2], pad[2:])
    salient = Es >= prominence * neigh if prominence > 0 else np.ones_like(Es, bool)

    min_len = max(1, int(cfg.min_note * fr))
    max_gap = int(cfg.max_gap * fr)

    notes: list[Note] = []
    for j in range(E.shape[0]):
        row = Es[j]
        active = row > thr_off
        seeds = (row > thr_on) & salient[j]
        runs, s = [], None
        for i, a in enumerate(active):
            if a and s is None:
                s = i
            elif not a and s is not None:
                runs.append((s, i))
                s = None
        if s is not None:
            runs.append((s, len(active)))
        runs = [(a, b) for a, b in runs if seeds[a:b].any()]

        merged: list[list[int]] = []
        for a, b in runs:
            if merged and a - merged[-1][1] <= max_gap:
                merged[-1][1] = b
            else:
                merged.append([a, b])

        pitch = cfg.midi_min + j
        for a, b in merged:
            if b - a < min_len:
                continue
            amp = float(np.percentile(row[a:b], 75))
            notes.append(Note(pitch=pitch, start=t0 + a / fr, end=t0 + b / fr,
                              velocity=0, amp=amp, section=section))
    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes


def assign_velocities(notes: list[Note], lo: int = 55, hi: int = 118) -> None:
    """L'orgue n'est pas sensible au toucher : la vélocité encode ici le poids
    spectral de la note (registration + place dans la texture), ce qui restitue
    l'équilibre sonore à la réécoute."""
    if not notes:
        return
    amps = np.array([n.amp for n in notes])
    ref = np.percentile(amps, 92) or amps.max()
    for n, a in zip(notes, amps):
        db = 20 * np.log10(max(a, 1e-9) / max(ref, 1e-9))
        x = float(np.clip((db + 30.0) / 30.0, 0.0, 1.0))
        n.velocity = int(round(lo + (hi - lo) * x))


def split_hands(notes: list[Note], pedal_max: int = 55, gap: int = 7) -> None:
    """Sépare pédale et manuel : notes graves nettement détachées du reste."""
    for n in notes:
        n.voice = 0
    by_time: dict[int, list[Note]] = {}
    for n in notes:
        by_time.setdefault(int(n.start * 4), []).append(n)
    for n in notes:
        if n.pitch > pedal_max:
            continue
        # simultanées (recouvrement temporel)
        others = [m for m in notes
                  if m is not n and m.start < n.end - 0.05 and m.end > n.start + 0.05]
        above = [m.pitch for m in others if m.pitch > n.pitch]
        if not others or (above and min(above) - n.pitch >= gap):
            n.voice = 1


def contribution_scores(notes: list[Note], A: np.ndarray, W: np.ndarray,
                        V: np.ndarray, An: np.ndarray, Wn: np.ndarray,
                        cfg: Config = DEFAULT, t0: float = 0.0) -> np.ndarray:
    """Gain d'explication apporté par chaque note (divergence KL par trame).

    On retire une note du modèle et on mesure de combien la reconstruction du
    spectrogramme se dégrade. Une note réellement jouée fait nettement remonter
    la divergence ; un artefact de réverbération ou un fantôme harmonique, non.
    """
    fr = cfg.frame_rate
    L = W @ A + Wn @ An + 1e-10
    scores = np.zeros(len(notes))
    for i, n in enumerate(notes):
        a = max(0, int(round((n.start - t0) * fr)))
        b = min(A.shape[1], int(round((n.end - t0) * fr)) + 1)
        if b <= a:
            continue
        j = n.pitch - cfg.midi_min
        Lw = L[:, a:b]
        drop = np.outer(W[:, j], A[j, a:b])
        Lp = np.maximum(Lw - drop, 1e-10)
        Vw = V[:, a:b]
        d = np.sum(Vw * np.log(Lw / Lp) + (Lp - Lw))
        scores[i] = d / (b - a)
    return scores
