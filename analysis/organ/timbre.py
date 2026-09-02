"""Du profil harmonique brut à une registration d'orgue nommée."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import Config, DEFAULT

# Longueur nominale d'un rang d'orgue en fonction du rapport harmonique qu'il
# sonne au-dessus du 8 pieds (hauteur réelle du clavier).
RANKS: list[tuple[float, str]] = [
    (0.5, "16'"), (1.0, "8'"), (2.0, "4'"), (3.0, "2·2/3'"),
    (4.0, "2'"), (5.0, "1·3/5'"), (6.0, "1·1/3'"), (8.0, "1'"),
]


@dataclass
class Registration:
    index: int
    profile: list[float]                 # amplitudes harmoniques (max = 1)
    harmonics: list[float]
    name: str = ""
    family: str = ""
    stops: list[str] = field(default_factory=list)
    brightness: float = 0.0              # centroïde harmonique
    odd_even: float = 0.0                # équilibre impairs / pairs
    blocks: int = 0
    seconds: float = 0.0
    attack: float = 0.03
    release: float = 0.10

    def as_dict(self) -> dict:
        return {
            "index": self.index, "name": self.name, "family": self.family,
            "stops": self.stops, "brightness": round(self.brightness, 3),
            "oddEven": round(self.odd_even, 3), "seconds": round(self.seconds, 1),
            "attack": round(self.attack, 4), "release": round(self.release, 4),
            "harmonics": [round(h, 3) for h in self.harmonics],
            "profile": [round(v, 5) for v in self.profile],
        }


def _integer_part(profile: np.ndarray, harmonics: np.ndarray) -> dict[int, float]:
    out: dict[int, float] = {}
    for h, v in zip(harmonics, profile):
        if abs(h - round(h)) < 1e-6:
            out[int(round(h))] = float(v)
    return out


def describe(profile: np.ndarray, harmonics: np.ndarray) -> tuple[str, str, list[str], float, float]:
    """Nomme la registration d'après la forme de son spectre harmonique.

    Trois descripteurs suffisent à distinguer les familles de l'orgue :
      * la pente de décroissance des harmoniques (un bourdon s'éteint après le
        fondamental, un plein-jeu garde de l'énergie jusqu'au 16e partiel) ;
      * « l'anchité » : le poids des partiels 5, 7, 9, 11 — présents dans une
        anche, absents des rangs d'un plein-jeu qui ne sonnent qu'octaves et
        quintes ;
      * la présence effective de chaque rang (16', 8', 4', 2·2/3', 2', ...).
    """
    p = np.asarray(profile, dtype=float)
    h = np.asarray(harmonics, dtype=float)
    p = p / (p.max() + 1e-12)
    ints = _integer_part(p, h)

    tot = sum(ints.values()) + 1e-12
    brightness = sum(k * v for k, v in ints.items()) / tot
    odd = sum(v for k, v in ints.items() if k % 2 == 1 and k > 1)
    even = sum(v for k, v in ints.items() if k % 2 == 0)
    odd_even = float(odd / (even + 1e-12))

    ranks = np.mean([ints.get(k, 0.0) for k in (2, 3, 4, 6, 8)])
    reediness = float(np.mean([ints.get(k, 0.0) for k in (5, 7, 9, 11)]) / (ranks + 1e-9))

    ks = np.array([k for k, v in ints.items() if k >= 1 and v > 0.015])
    vs = np.array([ints[int(k)] for k in ks])
    if len(ks) >= 3:
        slope = -np.polyfit(np.log(ks), np.log(vs + 1e-9), 1)[0]
    else:
        slope = 6.0

    stops: list[str] = []
    for ratio, label in RANKS:
        if ratio < 1:
            v = float(p[int(np.argmin(np.abs(h - ratio)))])
            if v > 0.12:
                stops.append(label)
            continue
        # un rang tiré et une harmonique du 8' produisent le même partiel :
        # on rapporte donc honnêtement les hauteurs qui sonnent, pas une
        # composition de jeux qui serait une extrapolation.
        if ints.get(int(ratio), 0.0) > 0.10:
            stops.append(label)
    if "8'" not in stops:
        stops.insert(0 if "16'" not in stops else 1, "8'")

    if reediness > 0.55 and ints.get(7, 0.0) > 0.20:
        family, name = "reed", "Anche (Trompette / Cromorne)"
    elif slope > 2.8 and brightness < 2.2:
        family, name = "flute", "Bourdon / Flûte douce"
    elif ints.get(5, 0.0) > 0.26 and ints.get(3, 0.0) > 0.22:
        family, name = "cornet", "Cornet / Jeu de tierce"
    elif slope < 1.35 and ints.get(8, 0.0) > 0.9 * max(ints.get(2, 0.0), 1e-9):
        family, name = "mixture", "Plein-jeu / Fourniture"
    elif ints.get(3, 0.0) > 0.30 and ints.get(4, 0.0) < ints.get(3, 0.0):
        family, name = "nazard", "Nazard / Grand jeu"
    elif brightness > 2.4:
        family, name = "principal", "Principal / Montre"
    else:
        family, name = "flute", "Flûte / Fonds doux"
    return name, family, stops, float(brightness), odd_even


def cluster(profiles: np.ndarray, k: int, seed: int = 0,
            iters: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """k-moyennes sur les profils en dB : regroupe les blocs par registration."""
    X = 20 * np.log10(np.maximum(profiles, 1e-4))
    n = len(X)
    k = max(1, min(k, n))
    rng = np.random.default_rng(seed)
    # k-means++ : premier centre au hasard, les suivants loin des précédents
    centres = [X[rng.integers(n)]]
    for _ in range(k - 1):
        d = np.min([np.sum((X - c) ** 2, axis=1) for c in centres], axis=0)
        if d.sum() <= 0:
            centres.append(X[rng.integers(n)])
        else:
            centres.append(X[rng.choice(n, p=d / d.sum())])
    C = np.array(centres)
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        d = ((X[:, None, :] - C[None, :, :]) ** 2).sum(axis=2)
        new = d.argmin(axis=1)
        if np.array_equal(new, labels):
            break
        labels = new
        for j in range(k):
            m = labels == j
            if m.any():
                C[j] = X[m].mean(axis=0)
    return labels, 10 ** (C / 20)


def estimate_reverb(y: np.ndarray, cfg: Config = DEFAULT,
                    tails: list[tuple[float, float]] | None = None) -> float:
    """RT60 approché, mesuré sur les extinctions en fin de section."""
    if not tails:
        return 2.5
    hop = 256
    rts = []
    for t0, t1 in tails:
        a, b = int(t0 * cfg.sr), int(min(t1, t0 + 8.0) * cfg.sr)
        if b > len(y):
            b = len(y)
        seg = y[a:b]
        if len(seg) < hop * 30:
            continue
        n = len(seg) // hop
        env = 20 * np.log10(np.sqrt(np.array(
            [np.mean(seg[i * hop:(i + 1) * hop] ** 2) for i in range(n)]) + 1e-12) + 1e-12)
        peak = env[:int(0.5 * cfg.sr / hop) + 1].max()
        floor = float(np.median(env[-int(0.7 * cfg.sr / hop):]))
        # sans 30 dB de dynamique au-dessus du bruit de fond, la « décroissance »
        # mesurée est celle du plancher de bruit, pas celle de la salle
        if peak - floor < 30.0:
            continue
        idx = np.where(env <= peak - 5)[0]
        jdx = np.where(env <= peak - 25)[0]
        if idx.size and jdx.size and jdx[0] > idx[0]:
            slope = 20.0 / ((jdx[0] - idx[0]) * hop / cfg.sr)
            if slope > 0:
                rts.append(60.0 / slope)
    return float(np.clip(np.median(rts), 0.8, 6.0)) if rts else 2.5


def attack_release(y: np.ndarray, notes, cfg: Config = DEFAULT,
                   tuning_cents: float = 0.0, max_notes: int = 40
                   ) -> tuple[float, float]:
    """Temps d'attaque et de relâche moyens, mesurés sur des notes isolées.

    On filtre autour du fondamental de la note pour ne pas mesurer l'attaque
    des voisines, puis on relève la montée 10 %->90 % et la descente
    90 %->10 % de l'enveloppe.
    """
    import scipy.signal as ss

    if not notes:
        return 0.03, 0.10
    starts = np.array([n.start for n in notes])
    ends = np.array([n.end for n in notes])
    atk, rel = [], []
    order = np.argsort([-(n.end - n.start) for n in notes])
    for i in order:
        if len(atk) >= max_notes:
            break
        n = notes[i]
        if n.end - n.start < 0.45:
            continue
        # isolée : aucune autre note ne démarre dans +-120 ms
        near = np.abs(starts - n.start) < 0.12
        if near.sum() > 1:
            continue
        f0 = 440.0 * 2 ** ((n.pitch - 69) / 12.0) * 2 ** (tuning_cents / 1200.0)
        # bande large : un filtre étroit sonnerait plus longtemps que
        # l'attaque qu'on cherche à mesurer
        if not (150.0 < f0 < cfg.sr / 4):
            continue
        lo, hi = f0 * 0.75, min(f0 * 1.30, cfg.sr / 2 * 0.98)
        b, a = ss.butter(3, [lo / (cfg.sr / 2), hi / (cfg.sr / 2)], btype="band")
        s0 = int((n.start - 0.10) * cfg.sr)
        s1 = int(min(n.start + 0.40, n.end) * cfg.sr)
        if s0 < 0 or s1 <= s0 + 200:
            continue
        env = np.abs(ss.hilbert(ss.filtfilt(b, a, y[s0:s1])))
        env = ss.savgol_filter(env, min(101, len(env) // 2 * 2 - 1), 2)
        pk = env.max()
        if pk <= 0:
            continue
        i10 = np.argmax(env > 0.1 * pk)
        i90 = np.argmax(env > 0.9 * pk)
        if i90 > i10:
            atk.append((i90 - i10) / cfg.sr)

        e0 = int(n.end * cfg.sr)
        e1 = int(min((n.end + 0.6) * cfg.sr, len(y)))
        # pas de note qui démarre pendant la mesure de la relâche
        if e1 > e0 + 400 and not ((starts > n.end - 0.05) & (starts < n.end + 0.5)).any():
            env2 = np.abs(ss.hilbert(ss.filtfilt(b, a, y[e0:e1])))
            env2 = ss.savgol_filter(env2, min(101, len(env2) // 2 * 2 - 1), 2)
            p2 = env2[:200].max()
            if p2 > 0:
                below = np.where(env2 < 0.1 * p2)[0]
                if below.size:
                    rel.append(below[0] / cfg.sr)
    # La réverbération et les notes voisines ne peuvent qu'allonger une montée,
    # jamais la raccourcir : on lit donc un quantile bas, qui correspond aux
    # attaques les moins contaminées — celles du tuyau lui-même.
    a = float(np.percentile(atk, 20)) if atk else 0.04
    r = float(np.percentile(rel, 30)) if rel else 0.12
    return float(np.clip(a, 0.006, 0.16)), float(np.clip(r, 0.02, 0.40))
