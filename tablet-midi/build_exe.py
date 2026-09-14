"""Build TabletMidi.exe.

Run on Windows with a Python that has tkinter (the python.org installers do):

    python build_exe.py

The executable lands in dist/TabletMidi.exe and needs nothing installed on the
machine it runs on.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"]
        )


def main() -> int:
    if sys.platform != "win32":
        print("A Windows .exe has to be built on Windows.")
        print("Push the branch instead: the GitHub Actions workflow builds it")
        print("and attaches TabletMidi.exe to the run as an artifact.")
        return 1

    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("This Python has no tkinter, so the window could not be bundled.")
        print("Use a python.org installer build, which includes it.")
        return 1

    ensure_pyinstaller()
    for stale in ("build", "dist"):
        shutil.rmtree(os.path.join(HERE, stale), ignore_errors=True)

    rc = subprocess.call(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "TabletMidi.spec"],
        cwd=HERE,
    )
    if rc != 0:
        return rc

    built = os.path.join(HERE, "dist", "TabletMidi.exe")
    if not os.path.exists(built):
        print("PyInstaller reported success but produced no executable.")
        return 1
    print("\nBuilt %s (%.1f MB)" % (built, os.path.getsize(built) / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
