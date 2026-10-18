#!/usr/bin/env python3
r"""
FFIV Script Editor Translation Tool v2.0
Modular PySide6 rewrite — painter-based canvas, no per-card widgets.

Usage:
    python3 main.py [--verbose] [ff4-en-data.json]

Workflow:
    1. make rip                        → produces ff4-en-data.json
    2. python3 main.py ff4-en-data.json
    3. make ff4-en                     → rebuilds the ROM
"""

import argparse
import os
import sys

# Allow running as  python3 main.py  from the repo root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTimer, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ff4_editor.i18n import install_language, tr
from ff4_editor.ui_mainwindow import FF4Editor


def main():
    parser = argparse.ArgumentParser(description="FFIV Script Editor Translation Tool")
    parser.add_argument("file", nargs="?", help="ff4-##-data.json to open")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print section load info to stdout")
    args, qt_args = parser.parse_known_args()

    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName("FFIV Script Editor Translation Tool")

    # Standard dialog buttons (Save/Discard/Cancel...) in the system language
    translator = QTranslator()
    if translator.load(QLocale(), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)

    # Interface language (Preferences > Idioma); 'auto' follows the system locale
    install_language(str(QSettings("ff4_editor", "ff4_editor_vwf").value("ui/language", "auto")))

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    app.setWindowIcon(QIcon(icon_path))

    app.setDesktopFileName("FFIV Script Editor.desktop")

    win = FF4Editor()
    win.verbose = args.verbose
    win.show()

    if args.file:
        if os.path.isfile(args.file):
            QTimer.singleShot(0, lambda: win.open_file(args.file))
        else:
            print(tr("Error: no existe el archivo {path}").format(path=args.file), file=sys.stderr)
            win.statusBar().showMessage(tr("No existe el archivo: {path}").format(path=args.file), 15000)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
