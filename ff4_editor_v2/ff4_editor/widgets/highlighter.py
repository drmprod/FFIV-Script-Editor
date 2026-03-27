"""
ff4_editor/widgets/highlighter.py
QSyntaxHighlighter for the single active QPlainTextEdit overlay.
Colours lines by visible length: normal / warn / over / blank.
"""

import re
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QFont

from ..constants import BLANK_LINE_DISPLAY, C_TEXT, C_WARN, C_OVER, C_BLANK


class FF4Highlighter(QSyntaxHighlighter):

    # Class-level formats — built once, shared across all instances
    _fmt_normal = QTextCharFormat()
    _fmt_warn   = QTextCharFormat()
    _fmt_over   = QTextCharFormat()
    _fmt_blank  = QTextCharFormat()
    _initialised = False

    @classmethod
    def _init_formats(cls):
        if cls._initialised:
            return
        cls._fmt_normal.setForeground(C_TEXT)
        cls._fmt_warn.setForeground(C_WARN)
        cls._fmt_over.setForeground(C_OVER)
        cls._fmt_over.setFontWeight(QFont.Weight.Bold)
        cls._fmt_blank.setForeground(C_BLANK)
        cls._initialised = True

    def __init__(self, document, settings):
        """
        Parameters
        ----------
        document : QTextDocument
        settings : object with .show_colors, .warn_chars, .over_chars attributes
        """
        super().__init__(document)
        self._init_formats()
        self._settings = settings

    def highlightBlock(self, text: str):
        if text == BLANK_LINE_DISPLAY:
            self.setFormat(0, len(text), self._fmt_blank)
            return

        if not self._settings.show_colors:
            self.setFormat(0, len(text), self._fmt_normal)
            return

        # Strip escapes/tokens to measure visible length
        v = re.sub(r'\\[a-zA-Z0-9]+(?:\[.*?\])?', '', text)
        v = re.sub(r'\{[^}]+\}', '      ', v)
        n = len(v)

        if n >= self._settings.over_chars:
            self.setFormat(0, len(text), self._fmt_over)
        elif n >= self._settings.warn_chars:
            self.setFormat(0, len(text), self._fmt_warn)
        else:
            self.setFormat(0, len(text), self._fmt_normal)
