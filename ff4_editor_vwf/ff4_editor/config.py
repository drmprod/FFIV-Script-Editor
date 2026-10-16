# ff4_editor/config.py

from dataclasses import dataclass, field
from PySide6.QtGui import QFont

@dataclass
class EditorConfig:
    card_rows: int = 8
    card_w: int = 300
    show_ruler: bool = True
    warn_chars: int = 24
    over_chars: int = 26
    auto_wrap: bool = True
    card_font: str = 'Hack'
    font_size: int = 11
    show_bands: bool = True
    ruler_chars: int = 28
    char_limit: int = 28
    line_limit: int = 0
    hard_char_limit: bool = False

    # Variable-width font (same engine as the game: field/vwf.asm)
    vwf_enabled: bool = True        # use the game font in VWF sections
    vwf_scale: int = 2              # zoom (screen pixels per game pixel)
    vwf_limit_px: int = 224         # dialogue line width in game pixels (28 tiles)
    vwf_gap: int = 1                # must match vwf_gen.py --gap
    vwf_space: int = 4              # must match vwf_gen.py --space
    vwf_line_pitch: int = 16        # game pixels between lines (8 glyph + 8 spacer)
    vwf_font_png: str = ''          # path to font.png ('' = look next to the JSON)


    _mono_font: QFont = field(default_factory=QFont)

    def apply_font(self):
        f = QFont(self.card_font, self.font_size)
        if not f.exactMatch():
            f = QFont('Monospace', self.font_size)
            f.setStyleHint(QFont.StyleHint.Monospace)
        self._mono_font = f
