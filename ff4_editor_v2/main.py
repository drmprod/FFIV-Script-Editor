#!/usr/bin/env python3
r"""
FF4 Translation Editor v2.0
Modular PySide6 rewrite — painter-based canvas, no per-card widgets.

Usage:
    python3 main.py [--verbose] [ff4-en-data.json]

Workflow:
    1. make rip                        → produces ff4-en-data.json
    2. python3 main.py ff4-en-data.json
    3. make ff4-en                     → rebuilds the ROM
"""

import sys, os, argparse

# Allow running as  python3 main.py  from the repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore    import QTimer

from ff4_editor.constants      import QSS
from ff4_editor.ui_mainwindow  import FF4Editor


def main():
    parser = argparse.ArgumentParser(description="FF4 Translation Editor")
    parser.add_argument("file",    nargs="?", help="ff4-en-data.json to open")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print section load info to stdout")
    args, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName("FF4 Translation Editor")
    app.setStyleSheet(QSS)

    win = FF4Editor()
    win.verbose = args.verbose
    win.showMaximized()

    if args.file and os.path.isfile(args.file):
        QTimer.singleShot(0, lambda: win._load_file(args.file))

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
