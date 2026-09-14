"""Entry point for the frozen executable.

PyInstaller cannot use ``tabletmidi/__main__.py`` directly: it runs the entry
script as ``__main__`` with no package around it, and the relative imports
inside the package would fail. This module imports the package properly
instead.
"""

import sys

from tabletmidi.cli import main

if __name__ == "__main__":
    sys.exit(main())
