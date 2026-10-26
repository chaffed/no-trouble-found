#!/usr/bin/env python3
"""Entry point for the packaged app.

Double-clicked (no arguments) -> graphical interface.
Any arguments               -> the command-line interface.

This is the PyInstaller entry script for all three platforms.
"""

import sys


def main():
    if len(sys.argv) > 1:
        import modem_capture
        return modem_capture.main()
    try:
        import gui
    except ImportError as e:
        print("The graphical interface needs tkinter, which is missing from "
              f"this Python install ({e}).")
        print("Run the command-line version instead:")
        print("    python3 modem_capture.py --probe")
        return 1
    return gui.run()


if __name__ == "__main__":
    sys.exit(main())
