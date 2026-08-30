#!/usr/bin/env python3
"""Render tools/preview.html against the exported table and screenshot it.

    ./gradlew :engine:exportTable && python3 tools/preview.py

Writes tools/out/preview.html (self-contained) and tools/out/preview.png.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tools", "out")
data = os.path.join(OUT, "slick_chick.json")
if not os.path.exists(data):
    sys.exit("run ./gradlew :engine:exportTable first")

table = open(data).read()
html = open(os.path.join(ROOT, "tools", "preview.html")).read()
page = html.replace("<script>", "<script>window.TABLE=%s;</script>\n<script>" % table, 1)
page_path = os.path.join(OUT, "preview.html")
open(page_path, "w").write(page)

chromium = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium")
if not os.path.exists(chromium):
    chromium = "chromium"
subprocess.run([
    chromium, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
    "--force-device-scale-factor=1", "--window-size=2256,2120",
    "--screenshot=" + os.path.join(OUT, "preview.png"),
    "--virtual-time-budget=3000", "file://" + page_path,
], check=True, capture_output=True)
print("wrote", os.path.join(OUT, "preview.png"))
