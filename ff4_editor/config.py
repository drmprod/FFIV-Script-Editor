"""
ff4_editor/config.py
The live editor configuration: the persisted settings (see typed_config.EditorSettings,
the single list of fields and defaults) plus the QFont derived from them.
"""

from dataclasses import dataclass, field

from PySide6.QtGui import QFont

from .typed_config import EditorSettings


@dataclass
class EditorConfig(EditorSettings):
    _mono_font: QFont = field(default_factory=QFont)

    @property
    def mono_font(self) -> QFont:
        """Font used for cards and the overlay editor (rebuilt by apply_font)."""
        return self._mono_font

    def apply_font(self) -> None:
        f = QFont(self.card_font, self.font_size)
        if not f.exactMatch():
            f = QFont("Monospace", self.font_size)
            f.setStyleHint(QFont.StyleHint.Monospace)
        self._mono_font = f
