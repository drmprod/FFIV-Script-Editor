"""
ff4_editor/widgets/highlighter.py
QSyntaxHighlighter for the single active QPlainTextEdit overlay.
"""

from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QPalette, QGuiApplication
from ..constants import BLANK_LINE_DISPLAY, C_BLANK, VWF_INK
from ..util.text_processing import CTRL_PAT, TOKEN_PAT


class FF4Highlighter(QSyntaxHighlighter):

    def __init__(self, document, settings, vwf=False):
        super().__init__(document)
        self._settings = settings
        self._vwf = vwf

        pal = QGuiApplication.palette()
        self._fmt_normal = QTextCharFormat()
        self._fmt_normal.setForeground(QColor(VWF_INK) if vwf else pal.color(QPalette.Text))

        self._fmt_blank = QTextCharFormat()
        # in VWF mode the separator line is painted by the canvas, hide the dashes
        self._fmt_blank.setForeground(QColor(0, 0, 0, 0) if vwf else C_BLANK)

        self._fmt_name = QTextCharFormat()
        self._fmt_name.setForeground(pal.color(QPalette.Highlight))
        self._fmt_cmd = QTextCharFormat()
        self._fmt_cmd.setForeground(QColor('#6fa8a0'))

    def highlightBlock(self, text: str):
        if text == BLANK_LINE_DISPLAY:
            self.setFormat(0, len(text), self._fmt_blank)
            return

        self.setFormat(0, len(text), self._fmt_normal)
        if self._vwf:
            for m in CTRL_PAT.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), self._fmt_cmd)
            for m in TOKEN_PAT.finditer(text):
                if m.group(0).startswith('{'):
                    self.setFormat(m.start(), m.end() - m.start(), self._fmt_name)