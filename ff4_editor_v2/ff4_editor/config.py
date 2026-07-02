# ff4_editor/config.py

from dataclasses import dataclass, field
from PySide6.QtGui import QFont
from .constants import C_BAND0_DEF, C_BAND1_DEF

@dataclass
class EditorConfig:
    card_rows: int = 8
    card_w: int = 300
    show_ruler: bool = True
    show_colors: bool = True
    warn_chars: int = 24
    over_chars: int = 26
    auto_wrap: bool = True
    card_font: str = 'Hack'
    font_size: int = 11
    show_bands: bool = True
    band0_color: str = C_BAND0_DEF
    band1_color: str = C_BAND1_DEF
    ruler_chars: int = 28
    char_limit: int = 28
    line_limit: int = 0
    hard_char_limit: bool = False
    auto_hyphenate: bool = False
    _mono_font: QFont = field(default_factory=QFont)

    def apply_font(self):
        f = QFont(self.card_font, self.font_size)
        if not f.exactMatch():
            f = QFont('Monospace', self.font_size)
            f.setStyleHint(QFont.StyleHint.Monospace)
        self._mono_font = f