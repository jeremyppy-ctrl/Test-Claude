#!/usr/bin/env python3
"""Assemble l'application en un fichier unique.

Deux sorties, à partir de `app/index.html` et `app/data/orgue.json` :
  * `dist/orgue.html`  — page autonome, ouvrable par double-clic (les données
    sont injectées dans la page, il n'y a plus de requête réseau) ;
  * `dist/orgue-artifact.html` — le même contenu sans les balises `<!doctype>`,
    `<html>`, `<head>` et `<body>`, tel que l'attend la publication d'artefact.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build() -> tuple[str, str]:
    src = os.path.join(ROOT, "app", "index.html")
    data_path = os.path.join(ROOT, "app", "data", "orgue.json")
    html = open(src, encoding="utf-8").read()
    data = json.load(open(data_path, encoding="utf-8"))

    payload = ("<script>window.ORGUE_DATA=" +
               json.dumps(data, ensure_ascii=False, separators=(",", ":")) +
               ";</script>\n")
    standalone = html.replace('<div class="wrap" id="app"></div>',
                              '<div class="wrap" id="app"></div>\n' + payload, 1)

    # variante artefact : le service fournit lui-même l'enveloppe du document
    body = standalone
    head = re.search(r"<head>(.*?)</head>", body, re.S)
    inner = re.search(r"<body>(.*?)</body>", body, re.S)
    if not head or not inner:
        raise SystemExit("structure HTML inattendue")
    artifact = head.group(1).strip() + "\n" + inner.group(1).strip() + "\n"
    return standalone, artifact


def main() -> int:
    standalone, artifact = build()
    out = os.path.join(ROOT, "dist")
    os.makedirs(out, exist_ok=True)
    for name, content in (("orgue.html", standalone), ("orgue-artifact.html", artifact)):
        path = os.path.join(out, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"{path} — {len(content.encode('utf-8')) / 1024:.0f} Ko")
    return 0


if __name__ == "__main__":
    sys.exit(main())
