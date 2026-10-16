"""
ff4_editor/widgets/card_canvas.py
CardCanvas — QPainter-based card grid.
- Zero child widgets per card.
- One QTextEdit floats over whichever card is active (managed by CardEditor).
- All inactive cards are pure paint calls.
- External QScrollBar wired via set_scrollbar().
"""

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QRect, Signal
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
)

from ..constants import (
    MAX_LINE_CHARS, BLANK_LINE_DISPLAY, C_WARN,
    C_OVER, C_RULER, mix_colors, PaletteColors, VWF_SECTIONS, VWF_PAGE_LINES,
)
from ..util.text_processing import visible_len
from .card_data import CardData
from .card_editor import CardEditor
from .vwf_painter import VWFPainter
from .card_layout import CardLayout
from ..config import EditorConfig


class CardCanvas(QWidget):
    card_committed = Signal(object, object, str)

    def __init__(self, config: EditorConfig, parent=None):
        super().__init__(parent)
        self._s = config
        self._cards: list[CardData] = []
        self._scroll_y = 0
        self._active = -1
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # VWF state (must be before sub-components)
        self._vwf = None
        self._vwf_family = None
        self._vwf_mode = False

        # Layout manager
        self._layout = CardLayout(config)

        # Sub-components
        self._editor = CardEditor(self)
        self._vwf_painter = VWFPainter(self)

        # DTE pair set for byte-cost calculation
        self.dte_set: set[str] = set()

        # External scrollbar
        self._vbar = None

    # ── Public API ────────────────────────────────────────────────────────────

    def set_scrollbar(self, vbar):
        self._vbar = vbar
        vbar.valueChanged.connect(self._on_scroll)

    def set_vwf(self, vwf, family):
        """Install (or remove, with None) the game font. Call load_cards() afterwards."""
        self._editor.deactivate()
        self._vwf, self._vwf_family = vwf, family
        self._vwf_painter = VWFPainter(self)  # Recreate with new font

    def _vwf_for(self, cards) -> bool:
        return bool(cards and self._vwf is not None and self._vwf_family
                    and getattr(self._s, 'vwf_enabled', False)
                    and cards[0].section in VWF_SECTIONS)

    def load_cards(self, cards: list[CardData]):
        """Replace the current card list and reset view state."""
        self._editor.deactivate()
        # Close old cards to unregister callbacks
        for cd in self._cards:
            cd.close()
        self._vwf_mode = self._vwf_for(cards)
        self._cards = cards
        self._scroll_y = 0
        self._active = -1
        if self._vbar:
            self._vbar.setValue(0)
        
        # Update layout manager
        self._layout.update_cards(cards, self._vwf_mode)
        self._layout.set_width(self.width())
        
        if self._vbar:
            self._vbar.setValue(0)
        self._update_scrollbar()
        self.update()

    def scroll_to_index(self, card_index: int):
        if 0 <= card_index < len(self._cards):
            y = self._layout.scroll_to_index(card_index)
            if self._vbar:
                self._vbar.setValue(y)

    def goto_entry(self, entry_idx: int) -> bool:
        """Scroll to the card whose entry index is `entry_idx` and open it for editing."""
        for i, cd in enumerate(self._cards):
            if cd.idx == entry_idx:
                self.scroll_to_index(i)
                return self._editor.activate(i)
        return False

    # ── VWFPainter public API ──────────────────────────────────────────────────

    def get_active_scroll(self) -> int:
        """Return the vertical scroll offset of the active editor overlay."""
        if self._active >= 0:
            return self._editor.overlay.verticalScrollBar().value()
        return 0

    def get_active_lines(self, cd: CardData) -> list[str]:
        """Return the current lines from the active editor overlay."""
        if self._active >= 0:
            return self._editor.overlay.toPlainText().split('\n')
        return cd.lines

    # ── Layout delegation ──────────────────────────────────────────────────────

    @property
    def _card_w(self) -> int:
        return self._layout.card_w

    @property
    def _card_h(self) -> int:
        return self._layout.card_h

    @property
    def _ncols(self) -> int:
        return self._layout.ncols

    def _text_area_rect(self, i: int) -> QRect:
        return self._layout.text_area_rect(i, self._scroll_y)

    def _overlay_rect(self, i: int) -> QRect:
        return self._layout.overlay_rect(i, self._scroll_y)

    def _line_h(self) -> int:
        if self._vwf_mode:
            return self._s.vwf_line_pitch * self._s.vwf_scale
        return QFontMetrics(self._s._mono_font).height() + 2

    def _vwf_qfont(self) -> QFont:
        """Get the VWF QFont for the editor overlay."""
        f = QFont(self._vwf_family)
        f.setFamilies([self._vwf_family, self._s._mono_font.family()])
        f.setPixelSize(8 * self._s.vwf_scale)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        f.setKerning(False)
        return f

    @property
    def _overlay(self):
        """Backward compat: overlay is now managed by CardEditor."""
        return self._editor.overlay

    def _update_scrollbar(self):
        if not self._vbar:
            return
        total = self._layout.total_height()
        vp_h = self.height()
        self._vbar.setRange(0, max(0, total - vp_h))
        self._vbar.setPageStep(vp_h)
        self._vbar.setSingleStep(self._layout.card_h + self._layout.CARD_PAD)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Base background
        pc = PaletteColors(self.palette())
        p.fillRect(self.rect(), pc.bg)

        if not self._cards:
            p.end()
            return

        fm = QFontMetrics(self._s._mono_font)
        line_h = self._line_h()
        hdr_h = fm.height() + 6
        vp_top = self._scroll_y
        vp_bot = self._scroll_y + self.height()

        small = self._s._mono_font.__class__(self._s._mono_font)
        small.setPointSize(max(7, self._s._mono_font.pointSize() - 2))

        # Dynamic colors
        c_border = QColor(mix_colors(pc.card, pc.text, 0.15))
        c_idx = QColor(mix_colors(pc.card, pc.text, 0.40))
        c_dim = QColor(mix_colors(pc.card, pc.text, 0.30))

        band0, band1 = pc.band0, pc.band1

        for i, cd in enumerate(self._cards):
            cr = self._layout.card_rect(i)
            if cr.bottom() < vp_top or cr.top() > vp_bot:
                continue
            vr = QRect(cr.x(), cr.y() - self._scroll_y, cr.width(), cr.height())
            is_active = (i == self._active)

            # Card background + border
            p.setBrush(QBrush(pc.card))
            p.setPen(QPen(pc.accent if is_active else c_border, 1.0))
            p.drawRoundedRect(vr.adjusted(0, 0, -1, -1), 5, 5)

            # Header
            p.setFont(small)
            hr = QRect(vr.x() + self._layout.CARD_INNER, vr.y() + self._layout.CARD_INNER,
                       vr.width() - self._layout.CARD_INNER * 2, hdr_h)
            p.setPen(c_idx)
            p.drawText(hr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       cd.header)
            p.setPen(C_OVER if cd.byte_count > 300
                     else C_WARN if cd.byte_count > 150 else c_dim)
            p.drawText(hr, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{cd.byte_count}B")

            # Text area
            tx = vr.x() + self._layout.CARD_INNER
            ty = vr.y() + self._layout.CARD_INNER + hdr_h + self._layout.CARD_INNER
            tw = vr.width() - self._layout.CARD_INNER * 2
            th = self._s.card_rows * line_h
            ta = QRect(tx, ty, tw, th)

            if self._vwf_mode:
                self._vwf_painter.paint_card(p, cd, is_active, tx, ty, tw, th, fm, c_dim)
                continue

            # Monospace mode
            p.fillRect(ta, pc.bg)

            p.setFont(self._s._mono_font)
            p.setClipRect(ta)

            # Page bands
            if self._s.show_bands:
                scroll_pixels = self._editor.overlay.verticalScrollBar().value() if is_active else 0
                first_doc_ln = scroll_pixels // line_h
                for ln in range(self._s.card_rows + 2):
                    doc_ln = first_doc_ln + ln
                    ly = ty + (doc_ln * line_h) - scroll_pixels
                    p.fillRect(QRect(tx, ly, tw, line_h),
                               band0 if (doc_ln // VWF_PAGE_LINES) % 2 == 0 else band1)

            # Character counter column background
            if self._s.show_bands:
                p.fillRect(QRect(tx + tw - 24, ty, 24, th), pc.card)

            # Inactive card text
            lines_to_paint = cd.lines
            active_scroll_offset = 0
            if is_active:
                lines_to_paint = self._editor.overlay.toPlainText().split('\n')
                active_scroll_offset = self._editor.overlay.verticalScrollBar().value()

            for ln, line in enumerate(lines_to_paint):
                if not is_active and ln >= self._s.card_rows:
                    break

                if line == BLANK_LINE_DISPLAY:
                    continue

                ly = ty + ln * line_h - active_scroll_offset

                # Draw the actual text line
                p.setPen(pc.text)
                p.drawText(tx + 2, ly + fm.ascent() + 1, line)

                vl = visible_len(line)
                count_str = str(vl)
                cw_count = fm.horizontalAdvance(count_str)
                p.setPen(C_OVER if vl >= self._s.over_chars else
                         C_WARN if vl >= self._s.warn_chars else c_dim)
                p.drawText(tx + tw - cw_count - 2, ly + fm.ascent() + 1, count_str)

            # Ruler
            if self._s.show_ruler:
                cw = fm.horizontalAdvance('M')
                ruler_col = getattr(self._s, 'ruler_chars', MAX_LINE_CHARS)
                rx = tx + 2 + cw * (ruler_col + 1)
                pen = QPen(C_RULER)
                pen.setWidthF(0.8)
                pen.setStyle(Qt.PenStyle.DotLine)
                p.setPen(pen)
                p.drawLine(rx, ty, rx, ty + th)

            p.setClipping(False)

        p.end()

    # ── Editor Integration ──────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            i = self._layout.card_at(event.position().toPoint(), self._scroll_y)
            if i >= 0:
                self._editor.activate(i)
            else:
                self._editor.deactivate()

    def wheelEvent(self, event):
        if self._vbar:
            self._vbar.setValue(self._vbar.value() - event.angleDelta().y() // 2)

    def _on_scroll(self, value: int):
        self._scroll_y = value
        if self._active >= 0:
            self._editor.overlay.setGeometry(self._layout.overlay_rect(self._active, self._scroll_y))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout.set_width(self.width())
        self._update_scrollbar()
        if self._active >= 0:
            self._editor.overlay.setGeometry(self._layout.overlay_rect(self._active, self._scroll_y))
        self.update()

    # ── Exposed for toolbar actions (delegated to editor) ──────────────────────

    def action_insert_blank_line(self):
        self._editor.action_insert_blank_line()

    def action_centre_lines(self):
        self._editor.action_centre_lines()

    def action_select_all(self):
        self._editor.action_select_all()

    def action_cut(self):
        self._editor.action_cut()

    def action_copy(self):
        self._editor.action_copy()

    def action_paste(self):
        self._editor.action_paste()

    def action_copy_active(self):
        self._editor.action_copy_active()