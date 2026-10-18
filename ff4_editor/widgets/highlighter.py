"""
ff4_editor/widgets/highlighter.py
QSyntaxHighlighter for the single active QPlainTextEdit overlay.
"""

from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette, QSyntaxHighlighter, QTextCharFormat

from ..constants import BLANK_LINE_DISPLAY, VWF_INK
from ..theme import command_color
from ..util.patterns import DISPLAY_CODE as CTRL_PAT
from ..util.patterns import NAME_TOKEN


class FF4Highlighter(QSyntaxHighlighter):
    def __init__(self, document, settings, vwf=False):
        super().__init__(document)
        self._settings = settings
        self._vwf = vwf

        pal = QGuiApplication.palette()
        self._fmt_normal = QTextCharFormat()
        self._fmt_normal.setForeground(QColor(VWF_INK) if vwf else pal.color(QPalette.ColorRole.Text))

        self._fmt_blank = QTextCharFormat()
        # in VWF mode the separator line is painted by the canvas, hide the dashes
        self._fmt_blank.setForeground(QColor(0, 0, 0, 0))  # the dotted line is painted by the canvas
        # the glyph is missing from the game font; no font merging keeps a fallback font from making the row taller
        blank_font = QFont(document.defaultFont())
        blank_font.setStyleStrategy(QFont.StyleStrategy.NoFontMerging)
        self._fmt_blank.setFont(blank_font)

        self._fmt_name = QTextCharFormat()
        self._fmt_name.setForeground(pal.color(QPalette.ColorRole.Highlight))
        self._fmt_cmd = QTextCharFormat()
        self._fmt_cmd.setForeground(QColor("#6fa8a0") if vwf else command_color(pal))

    def highlightBlock(self, text: str):
        if text == BLANK_LINE_DISPLAY:
            self.setFormat(0, len(text), self._fmt_blank)
            return

        self.setFormat(0, len(text), self._fmt_normal)
        for i, ch in enumerate(text):  # a separator glyph pasted into a text line stays invisible
            if ch == BLANK_LINE_DISPLAY:
                self.setFormat(i, 1, self._fmt_blank)
        for m in CTRL_PAT.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_cmd)
        for m in NAME_TOKEN.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._fmt_name)
