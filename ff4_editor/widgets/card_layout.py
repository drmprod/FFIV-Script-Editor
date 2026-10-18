"""
ff4_editor/widgets/card_layout.py
Layout computation for card grid. Pure logic, no Qt widget dependencies.
"""

import math
from dataclasses import dataclass

from PySide6.QtCore import QRect
from PySide6.QtGui import QFontMetrics

from ..config import EditorConfig


@dataclass
class CardLayout:
    """Handles all layout calculations for the card grid."""

    # Layout constants
    CARD_PAD = 6
    CARD_INNER = 6
    VWF_COUNTER_W = 44

    def __init__(self, config: EditorConfig):
        self._s = config
        self._cards: list = []  # List of CardData
        self._ncols = 1
        self._card_h = 200
        self._card_w = 300
        self._vwf_mode = False

    def update_cards(self, cards: list, vwf_mode: bool):
        """Update card list and VWF mode, recompute layout."""
        self._cards = cards
        self._vwf_mode = vwf_mode
        self._recompute()

    def _recompute(self):
        """Recompute all layout dimensions."""

        fm = QFontMetrics(self._s.mono_font)
        line_h = self._line_h()
        hdr_h = fm.height() + 6
        text_h = self._s.card_rows * line_h + self.CARD_INNER * 2
        self._card_h = hdr_h + text_h + self.CARD_INNER * 2

        if self._vwf_mode:
            counter_w = max(
                self.VWF_COUNTER_W, fm.horizontalAdvance("999px") + 12
            )  # the "NNNpx" label must fit
            self._card_w = self._s.vwf_limit_px * self._s.vwf_scale + counter_w + self.CARD_INNER * 2
        else:
            self._card_w = self._s.card_w

        avail = max(self._card_w + self.CARD_PAD, 1)  # width will be set later
        self._ncols = max(1, avail // (self._card_w + self.CARD_PAD))

    def set_width(self, width: int):
        """Update column count based on available width."""
        avail = max(self._card_w + self.CARD_PAD, width - self.CARD_PAD)
        self._ncols = max(1, avail // (self._card_w + self.CARD_PAD))

    def _line_h(self) -> int:
        if self._vwf_mode:
            return self._s.vwf_line_pitch * self._s.vwf_scale

        return QFontMetrics(self._s.mono_font).height() + 2

    def total_height(self) -> int:
        if not self._cards:
            return 0

        nrows = math.ceil(len(self._cards) / self._ncols)
        return nrows * (self._card_h + self.CARD_PAD) + self.CARD_PAD

    def card_rect(self, i: int):
        """Get card rectangle in content coordinates (not scrolled)."""

        col = i % self._ncols
        row = i // self._ncols
        x = self.CARD_PAD + col * (self._card_w + self.CARD_PAD)
        y = self.CARD_PAD + row * (self._card_h + self.CARD_PAD)
        return QRect(x, y, self._card_w, self._card_h)

    def card_rect_v(self, i: int, scroll_y: int):
        """Get card rectangle in viewport coordinates (scrolled)."""

        r = self.card_rect(i)
        return QRect(r.x(), r.y() - scroll_y, r.width(), r.height())

    def text_area_rect(self, i: int, scroll_y: int):
        """Get text area rectangle in viewport coordinates."""
        from PySide6.QtGui import QFontMetrics

        fm = QFontMetrics(self._s.mono_font)
        hdr_h = fm.height() + 6
        line_h = self._line_h()
        vr = self.card_rect_v(i, scroll_y)
        tx = vr.x() + self.CARD_INNER
        ty = vr.y() + self.CARD_INNER + hdr_h + self.CARD_INNER
        tw = vr.width() - self.CARD_INNER * 2
        th = self._s.card_rows * line_h
        return QRect(tx, ty, tw, th)

    def overlay_rect(self, i: int, scroll_y: int):
        """Get editor overlay rectangle in viewport coordinates."""
        ta = self.text_area_rect(i, scroll_y)
        return ta if self._vwf_mode else ta.adjusted(2, -1, 0, 0)

    def card_at(self, pos, scroll_y: int) -> int:
        """Find card index at viewport position."""
        for i in range(len(self._cards)):
            if self.card_rect_v(i, scroll_y).contains(pos):
                return i
        return -1

    def scroll_to_index(self, card_index: int) -> int:
        """Calculate scrollbar value to show card at index."""
        if 0 <= card_index < len(self._cards):
            row = card_index // max(1, self._ncols)
            y = self.CARD_PAD + row * (self._card_h + self.CARD_PAD)
            return max(0, y - 20)
        return 0

    @property
    def card_w(self) -> int:
        return self._card_w

    @property
    def card_h(self) -> int:
        return self._card_h

    @property
    def ncols(self) -> int:
        return self._ncols

    @property
    def vwf_mode(self) -> bool:
        return self._vwf_mode
