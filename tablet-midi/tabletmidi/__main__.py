"""``python -m tabletmidi`` -- opens the window unless a command is given."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
