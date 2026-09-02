"""NMF à dictionnaire harmonique paramétré : estime notes ET timbre ensemble.

Le spectrogramme V est modélisé par V ≈ W(g) · A + Wn · An, où
  * W(g) = Σ_k g_k B_k  : dictionnaire des hauteurs, entièrement déterminé par
    le profil harmonique g (le « timbre » de la registration jouée) ;
  * A                   : activations par hauteur et par trame (les notes) ;
  * Wn, An              : quelques bases larges qui absorbent le bruit de vent
    et la réverbération, pour qu'ils ne soient pas transformés en fausses notes.

g et A sont estimés en alternance par des mises à jour multiplicatives
(divergence de Kullback-Leibler), ce qui garantit la positivité et la
convergence monotone.
"""
from __future__ import annotations

import numpy as np

from .spectra import HarmonicKernels

EPS = 1e-10


def noise_bases(freqs: np.ndarray, n: int = 5) -> np.ndarray:
    """Bases spectrales larges, régulièrement réparties en fréquence log."""
    lo, hi = np.log(40.0), np.log(max(freqs[-1], 60.0))
    centres = np.exp(np.linspace(lo, hi, n))
    width = (hi - lo) / (n - 1) * 1.1
    f = np.log(np.maximum(freqs, 1.0))
    W = np.exp(-0.5 * ((f[:, None] - np.log(centres)[None, :]) / width) ** 2)
    return W / (W.sum(axis=0, keepdims=True) + EPS)


def factorize(V: np.ndarray, kern: HarmonicKernels, g0: np.ndarray,
              n_iter: int = 60, fit_timbre: bool = True,
              n_noise: int = 5, sparsity: float = 0.0,
              prior: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Renvoie (A, g, An) pour V (n_freq x n_frames)."""
    n_freq, T = V.shape
    g0 = np.maximum(np.array(g0, dtype=float), EPS)
    g = g0.copy()

    Wn = noise_bases(kern.freqs, n_noise)
    W = kern.dictionary(g)

    # initialisation par corrélation : bien plus stable qu'un tirage aléatoire
    A = np.maximum(W.T @ V, EPS)
    A *= V.sum() / max((W @ A).sum(), EPS)
    An = np.maximum(Wn.T @ V, EPS) * 0.05

    colsums = [np.asarray(M.sum(axis=0)).ravel() for M in kern.mats]
    ones_n = Wn.sum(axis=0)

    for it in range(n_iter):
        L = W @ A + Wn @ An + EPS
        R = V / L

        # --- activations des hauteurs ---
        # La parcimonie tranche l'ambiguïté fondamentale de la transcription :
        # « un son riche à f » et « des sons purs à f, 2f, 3f... » expliquent le
        # même spectre. Sans elle, le timbre estimé dégénère en sinusoïde et
        # chaque harmonique devient une fausse note. Le poids est mis à
        # l'échelle de la somme des colonnes du dictionnaire.
        pen = sparsity * float(W.sum(axis=0).mean())
        A *= (W.T @ R) / (W.sum(axis=0)[:, None] + pen + EPS)
        A = np.maximum(A, EPS)

        # --- activations du bruit ---
        L = W @ A + Wn @ An + EPS
        R = V / L
        An *= (Wn.T @ R) / (ones_n[:, None] + EPS)
        An = np.maximum(An, EPS)

        # --- profil harmonique (le timbre) ---
        if fit_timbre and it >= 5 and it % 2 == 0:
            L = W @ A + Wn @ An + EPS
            R = V / L
            a_rows = A.sum(axis=1)
            num = np.array([float(np.sum((M.T @ R) * A)) for M in kern.mats])
            den = np.array([float(cs @ a_rows) for cs in colsums])
            counts = g * num
            if prior > 0:
                # Pseudo-observations d'un tuyau « ordinaire » (harmoniques
                # décroissantes). Elles ne pèsent que là où les données sont
                # ambiguës — typiquement l'octave, où « une note riche à f » et
                # « deux notes pures à f et 2f » expliquent le même spectre.
                pri = g0 / max(g0.sum(), EPS)
                counts = counts + prior * counts.sum() * pri
            g = counts / np.maximum(den, EPS)
            g = np.maximum(g, 1e-6)
            scale = g.max()
            g /= scale
            A *= scale
            W = kern.dictionary(g)

    return A, g, An


def kl_divergence(V: np.ndarray, L: np.ndarray) -> float:
    L = L + EPS
    return float(np.sum(V * np.log((V + EPS) / L) - V + L))
