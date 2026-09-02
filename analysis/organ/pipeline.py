"""Chaîne complète : enregistrement -> notes, registrations, MIDI, JSON."""
from __future__ import annotations

import json
import os
import time

import numpy as np

from .audio import Section, estimate_tuning, load
from .content import music_spans
from .config import Config, DEFAULT
from .midiwrite import write as write_midi
from .nmf import factorize, noise_bases
from .notes import (Note, assign_velocities, contribution_scores, extract,
                    note_energy, split_hands)
from .spectra import HarmonicKernels, default_profile, spectrogram
from .timbre import Registration, attack_release, cluster, describe, estimate_reverb

BLOCK = 8.0        # s, fenêtre d'estimation du timbre
TIMBRE_PRIOR = 0.15  # poids de l'a priori « tuyau ordinaire » sur le timbre
CHUNK = 45.0       # s, fenêtre de transcription (bornée par la mémoire)
OVERLAP = 1.5      # s, recouvrement entre fenêtres de transcription

# programmes General MIDI par famille de jeux
GM = {"flute": 74, "principal": 19, "mixture": 19, "reed": 20,
      "cornet": 20, "nazard": 19}


def _blocks(sections: list[Section]) -> list[tuple[int, float, float]]:
    out = []
    for sec in sections:
        t = sec.start
        while t < sec.end - 0.5:
            t1 = min(t + BLOCK, sec.end)
            if sec.end - t1 < 3.0:
                t1 = sec.end
            out.append((sec.index, t, t1))
            t = t1
    return out


def _smooth_labels(labels: np.ndarray, blocks, width: int = 3) -> np.ndarray:
    """Un changement de registration dure plusieurs blocs : on lisse par
    vote majoritaire, à l'intérieur de chaque section seulement."""
    out = labels.copy()
    secs = np.array([b[0] for b in blocks])
    for i in range(len(labels)):
        m = (secs == secs[i]) & (np.abs(np.arange(len(labels)) - i) <= width // 2)
        vals, counts = np.unique(labels[m], return_counts=True)
        out[i] = vals[counts.argmax()]
    return out


def run(path: str, out_dir: str, cfg: Config = DEFAULT, n_reg: int = 8,
        sensitivity: float = 1.0, contribution: float = 0.05,
        verbose: bool = True) -> dict:
    t_start = time.time()

    def log(msg: str) -> None:
        if verbose:
            print(f"[{time.time() - t_start:6.1f}s] {msg}", flush=True)

    os.makedirs(out_dir, exist_ok=True)
    y = load(path, cfg)
    log(f"audio chargé : {len(y) / cfg.sr:.1f} s à {cfg.sr} Hz")

    spans, content = music_spans(y, cfg)
    sections = [Section(i, sp.start, sp.end) for i, sp in enumerate(spans)]
    log(f"parole écartée : {content['speech']:.0f} s ; "
        f"{len(sections)} extraits joués, {content['music']:.0f} s de musique")

    # le diapason se mesure sur la musique seule — la voix le fausserait
    played = np.concatenate([y[int(s.start * cfg.sr):int(s.end * cfg.sr)]
                             for s in sections]) if sections else y
    tuning = estimate_tuning(played, cfg)
    log(f"diapason : La4 = {440 * 2 ** (tuning / 1200):.2f} Hz ({tuning:+.1f} cents)")

    kern = HarmonicKernels(cfg, tuning)
    Wn = noise_bases(kern.freqs, 5)
    g0 = default_profile(cfg)

    # --- passe 1 : un profil harmonique par bloc -------------------------
    blocks = _blocks(sections)
    log(f"passe 1 : timbre sur {len(blocks)} blocs de {BLOCK:.0f} s")
    profiles = []
    for i, (sec, a, b) in enumerate(blocks):
        V = spectrogram(y[int(a * cfg.sr):int(b * cfg.sr)], cfg)
        _, g, _ = factorize(V, kern, g0, n_iter=45, fit_timbre=True, prior=TIMBRE_PRIOR)
        profiles.append(g)
        if verbose and (i + 1) % 20 == 0:
            log(f"   {i + 1}/{len(blocks)} blocs")
    profiles = np.array(profiles)

    # --- regroupement en registrations -----------------------------------
    labels, centres = cluster(profiles, n_reg)
    labels = _smooth_labels(labels, blocks)
    used = sorted(set(labels.tolist()))
    remap = {old: i for i, old in enumerate(used)}
    labels = np.array([remap[v] for v in labels])
    centres = centres[used]
    log(f"passe 1 terminée : {len(used)} registrations distinctes")

    # --- segments de registration ----------------------------------------
    segments: list[tuple[int, int, float, float]] = []   # (section, reg, t0, t1)
    for (sec, a, b), lab in zip(blocks, labels):
        if segments and segments[-1][0] == sec and segments[-1][1] == lab \
                and abs(segments[-1][3] - a) < 1e-6:
            segments[-1] = (sec, lab, segments[-1][2], b)
        else:
            segments.append((sec, lab, a, b))
    log(f"{len(segments)} segments homogènes")

    # --- passe 2 : transcription à timbre fixé ----------------------------
    all_notes: list[Note] = []
    for si, (sec, lab, a, b) in enumerate(segments):
        g = centres[lab]
        W = kern.dictionary(g)
        cursor = a
        seg_notes: list[Note] = []
        while cursor < b - 0.2:
            end = min(cursor + CHUNK, b)
            V = spectrogram(y[int(cursor * cfg.sr):int(end * cfg.sr)], cfg)
            A, _, An = factorize(V, kern, g, n_iter=55, fit_timbre=False)
            E = note_energy(A, W)
            cand = extract(E, cfg, t0=cursor, section=si,
                           rel_onset=cfg.rel_onset / max(sensitivity, 1e-3),
                           floor_level=content["globalLevel"])
            if cand and contribution > 0:
                sc = contribution_scores(cand, A, W, V, An, Wn, cfg, t0=cursor)
                ref = max(float(np.percentile(sc, 97)), 1e-9)
                cand = [n for n, s in zip(cand, sc) if s / ref > contribution]
            seg_notes.extend(cand)
            cursor = end - OVERLAP if end < b - 0.2 else end
        all_notes.extend(_merge_overlaps(seg_notes, cfg))
        if verbose and (si + 1) % 5 == 0:
            log(f"   passe 2 : {si + 1}/{len(segments)} segments, {len(all_notes)} notes")

    all_notes.sort(key=lambda n: (n.start, n.pitch))
    assign_velocities(all_notes)
    split_hands(all_notes)
    log(f"passe 2 terminée : {len(all_notes)} notes")

    # --- description des registrations ------------------------------------
    regs: list[Registration] = []
    for k in range(len(centres)):
        secs_time = sum(b - a for (s, lab, a, b) in segments if lab == k)
        name, family, stops, brightness, oddeven = describe(centres[k], np.array(cfg.harmonics))
        notes_k = [n for n in all_notes
                   if segments[n.section][1] == k]
        atk, rel = attack_release(y, notes_k[:400], cfg, tuning)
        regs.append(Registration(
            index=k, profile=[float(v) for v in centres[k]],
            harmonics=[float(h) for h in cfg.harmonics], name=name, family=family,
            stops=stops, brightness=brightness, odd_even=oddeven,
            blocks=int((labels == k).sum()), seconds=secs_time,
            attack=atk, release=rel))
        log(f"   registration {k}: {name} — {', '.join(stops)} "
            f"({secs_time:.0f} s, attaque {atk * 1000:.0f} ms)")

    tails = [(s.end - 1.2, s.end + 3.5) for s in sections]
    rt60 = estimate_reverb(y, cfg, tails)
    log(f"réverbération estimée : RT60 ≈ {rt60:.2f} s")

    # --- sorties -----------------------------------------------------------
    names = {i: f"{regs[lab].name} [{sec}]" for i, (sec, lab, a, b) in enumerate(segments)}
    progs = {i: GM.get(regs[lab].family, 19) for i, (sec, lab, a, b) in enumerate(segments)}
    midi_path = os.path.join(out_dir, "orgue.mid")
    write_midi(midi_path, all_notes, bpm=100.0, track_names=names, programs=progs)

    data = {
        "source": os.path.basename(path),
        "duration": round(len(y) / cfg.sr, 3),
        "tuningCents": round(tuning, 2),
        "a4": round(440 * 2 ** (tuning / 1200), 2),
        "rt60": round(rt60, 2),
        "musicSeconds": round(content["music"], 1),
        "speechSeconds": round(content["speech"], 1),
        "harmonics": [float(h) for h in cfg.harmonics],
        "registrations": [r.as_dict() for r in regs],
        "segments": [{"index": i, "section": sec, "registration": int(lab),
                      "start": round(a, 3), "end": round(b, 3)}
                     for i, (sec, lab, a, b) in enumerate(segments)],
        "sections": [{"index": s.index, "start": round(s.start, 3),
                      "end": round(s.end, 3)} for s in sections],
        "notes": [n.as_dict() for n in all_notes],
    }
    json_path = os.path.join(out_dir, "orgue.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    log(f"écrit : {midi_path} et {json_path}")
    return data


def _merge_overlaps(notes: list[Note], cfg: Config) -> list[Note]:
    """Recolle les notes coupées par une frontière de fenêtre."""
    notes.sort(key=lambda n: (n.pitch, n.start))
    out: list[Note] = []
    for n in notes:
        if out and out[-1].pitch == n.pitch and n.start - out[-1].end <= cfg.max_gap:
            prev = out[-1]
            prev.end = max(prev.end, n.end)
            prev.amp = max(prev.amp, n.amp)
        else:
            out.append(n)
    return out
