"""Turn a graphics tablet into a virtual MIDI controller.

The pen's position drives two continuous controllers, and a strip of toggle
buttons along the bottom edge of the active area is hit by putting the tip
down. The tablet is hidden from Windows entirely, so the mouse never moves.

Only :mod:`tabletmidi.mapping` and :mod:`tabletmidi.config` are portable; the
rest wraps Windows APIs and raises on other platforms.
"""

__version__ = "1.0.0"
