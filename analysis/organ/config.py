"""Paramètres partagés par toute la chaîne d'analyse."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # --- analyse spectrale ---
    sr: int = 22050
    n_fft: int = 4096
    hop: int = 512

    # --- étendue transcrite (MIDI) : Do1 du pédalier -> Do7 des dessus ---
    midi_min: int = 24
    midi_max: int = 96

    # --- dictionnaire harmonique ---
    # multiples de 0.5 : le 0.5 capte un éventuel jeu de 16', les demi-entiers
    # suivants captent les harmoniques de ce 16'.
    harmonics: tuple = field(default=tuple(h / 2 for h in range(1, 33)))
    cents_tolerance: float = 12.0   # largeur du noyau spectral autour de chaque partiel

    # --- segmentation ---
    silence_db: float = -46.0       # sous ce niveau (dB rel. au max) : silence
    min_silence: float = 1.2        # s, durée mini d'un silence séparateur
    min_section: float = 3.0        # s, durée mini d'une section conservée

    # --- détection d'événements ---
    rel_onset: float = 0.16         # seuil d'attaque, relatif à la sonorité locale
    abs_floor: float = 0.020        # plancher absolu, en fraction du niveau global
    offset_ratio: float = 0.45      # seuil de relâche, relatif au seuil d'attaque
    prominence: float = 0.85        # saillance minimale face aux demi-tons voisins
    min_note: float = 0.070         # s
    max_gap: float = 0.075          # s, comble les micro-coupures d'une même note

    @property
    def frame_rate(self) -> float:
        return self.sr / self.hop


DEFAULT = Config()
