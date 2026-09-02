#!/usr/bin/env python3
"""Extrait les notes et les timbres d'un enregistrement d'orgue.

    python analysis/transcribe.py enregistrement.m4a -o app/data

Produit `orgue.mid` (transcription jouable) et `orgue.json` (notes +
registrations + acoustique) que l'application web charge directement.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from organ.config import Config, DEFAULT      # noqa: E402
from organ.pipeline import run                # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", help="fichier audio source (m4a, wav, mp3...)")
    ap.add_argument("-o", "--out", default="app/data", help="dossier de sortie")
    ap.add_argument("-r", "--registrations", type=int, default=8,
                    help="nombre de registrations à distinguer (défaut : 8)")
    ap.add_argument("-s", "--sensitivity", type=float, default=1.0,
                    help=">1 détecte plus de notes, <1 n'en garde que les plus sûres")
    ap.add_argument("-c", "--contribution", type=float, default=0.05,
                    help="seuil d'élagage des notes peu explicatives (0 = aucun)")
    ap.add_argument("--start", type=float, default=None, help="début de l'extrait (s)")
    ap.add_argument("--end", type=float, default=None, help="fin de l'extrait (s)")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    src = args.audio
    if args.start is not None or args.end is not None:
        import subprocess
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), "organ_excerpt.wav")
        cmd = ["ffmpeg", "-v", "error", "-y"]
        if args.start:
            cmd += ["-ss", str(args.start)]
        cmd += ["-i", src]
        if args.end:
            cmd += ["-t", str(args.end - (args.start or 0))]
        cmd += ["-ac", "1", "-ar", str(DEFAULT.sr), tmp]
        subprocess.run(cmd, check=True)
        src = tmp

    data = run(src, args.out, Config(), n_reg=args.registrations,
               sensitivity=args.sensitivity, contribution=args.contribution,
               verbose=not args.quiet)
    print(f"\n{len(data['notes'])} notes, {len(data['registrations'])} registrations, "
          f"La4 = {data['a4']} Hz, RT60 = {data['rt60']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
