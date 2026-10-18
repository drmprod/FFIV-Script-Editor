"""
ff4_editor/widgets/card_canvas.py
CardCanvas — QPainter-based card grid.
- Zero child widgets per card.
- One QTextEdit floats over whichever card is active (managed by CardEditor).
- All inactive cards are pure paint calls.
- External QScrollBar wired via set_scrollbar().
"""

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..config import EditorConfig
from ..constants import (
    BLANK_LINE_DISPLAY,
    C_BLANK,
    C_OVER,
    C_RULER,
    C_WARN,
    MAX_LINE_CHARS,
    VWF_PAGE_LINES,
    VWF_SECTIONS,
    PaletteColors,
    mix_colors,
    page_lines_for,
)
from ..i18n import tr
from ..util.text_processing import visible_len
from .card_data import CardData
from .card_editor import CardEditor
from .card_layout import CardLayout
from .vwf_painter import VWFPainter


@dataclass
class _CardColors:
    """Colours derived once per paint from the palette."""

    border: QColor
    idx: QColor
    dim: QColor
    pc: PaletteColors


class CardCanvas(QWidget):
    card_committed = Signal(object, object, str)
    active_changed = Signal()  # a card was opened/closed for editing, or its selection changed

    def __init__(self, config: EditorConfig, parent=None):
        super().__init__(parent)
        self._s = config
        self.cards: list[CardData] = []
        self._scroll_y = 0
        self.active_index = -1
        self.page_lines = VWF_PAGE_LINES
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # VWF state (must be before sub-components)
        self.vwf = None
        self.vwf_family = None
        self.vwf_mode = False

        # Layout manager
        self._layout = CardLayout(config)

        # Sub-components
        self.editor = CardEditor(self)
        self._vwf_painter = VWFPainter(self)

        # (section, json_text) -> ROM bytes; the main window plugs in the model's real encoder
        self.byte_cost: Callable[[str, str], int] = lambda _section, text: len(text)

        # External scrollbar
        self._vbar = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def config(self) -> EditorConfig:
        return self._s

    @property
    def scroll_value(self) -> int:
        """Current vertical scroll (pixels)."""
        return self._vbar.value() if self._vbar else self._scroll_y

    @scroll_value.setter
    def scroll_value(self, value: int) -> None:
        if self._vbar:
            self._vbar.setValue(value)

    def set_scrollbar(self, vbar):
        self._vbar = vbar
        vbar.valueChanged.connect(self._on_scroll)

    def set_vwf(self, vwf, family):
        """Install (or remove, with None) the game font. Call load_cards() afterwards."""
        self.editor.deactivate()
        self.vwf, self.vwf_family = vwf, family
        self._vwf_painter = VWFPainter(self)  # Recreate with new font

    def _vwf_for(self, cards) -> bool:
        return bool(
            cards
            and self.vwf is not None
            and self.vwf_family
            and getattr(self._s, "vwf_enabled", False)
            and cards[0].section in VWF_SECTIONS
        )

    def load_cards(self, cards: list[CardData]):
        """Replace the current card list and reset view state."""
        self.editor.deactivate()
        # Close old cards to unregister callbacks
        for cd in self.cards:
            cd.close()
        self.vwf_mode = self._vwf_for(cards)
        self.page_lines = page_lines_for(cards[0].section if cards else None)
        self.cards = cards
        self._scroll_y = 0
        self.active_index = -1
        if self._vbar:
            self._vbar.setValue(0)

        # Update layout manager
        self._layout.update_cards(cards, self.vwf_mode)
        self._layout.set_width(self.width())

        if self._vbar:
            self._vbar.setValue(0)
        self._update_scrollbar()
        self.update()

    def scroll_to_index(self, card_index: int):
        if 0 <= card_index < len(self.cards):
            y = self._layout.scroll_to_index(card_index)
            if self._vbar:
                self._vbar.setValue(y)

    def ensure_visible(self, card_index: int):
        """Scroll only if the card is not (fully) on screen."""
        if not (0 <= card_index < len(self.cards)):
            return
        r = self._layout.card_rect(card_index)
        top = self.scroll_value
        if r.top() < top or r.bottom() > top + self.height():
            self.scroll_to_index(card_index)

    def step_card(self, delta: int) -> bool:
        """Open the editor on the next/previous card (Alt+Down / Alt+Up)."""
        if not self.cards:
            return False
        i = self.active_index + delta if self.active_index >= 0 else (0 if delta > 0 else len(self.cards) - 1)
        i = max(0, min(len(self.cards) - 1, i))
        self.ensure_visible(i)
        return self.editor.activate(i)

    def eventFilter(self, obj, event):
        """Keys typed in the editor overlay: Esc closes it (committing)."""
        if obj is self.editor.overlay and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.editor.deactivate()
                self.setFocus()
                return True
            ctrl_only = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier == (
                Qt.KeyboardModifier.ControlModifier
            )
            # Handled here so they work the first time, independent of QAction enabled state
            if ctrl_only and key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.editor.action_insert_blank_line()
                return True
            if ctrl_only and key == Qt.Key.Key_E:
                self.editor.action_centre_lines()
                return True
            if self.editor.handle_key(event):
                return True
        return super().eventFilter(obj, event)

    def index_of(self, section: str, idx) -> int:
        """Position of the card for (section, idx) in the current list, or -1."""
        for i, cd in enumerate(self.cards):
            if cd.section == section and cd.idx == idx:
                return i
        return -1

    def refresh_card(self, section: str, idx, json_text: str, byte_count: int) -> bool:
        """Show new text for one card (model changed through undo/redo). Closes the editor
        if it was open on that card, without committing its stale content."""
        i = self.index_of(section, idx)
        if i < 0:
            return False
        if i == self.active_index:
            self.editor.cancel()
        self.cards[i].update(json_text, byte_count)
        self.update()
        return True

    def goto_entry(self, entry_idx: int) -> bool:
        """Scroll to the card whose entry index is `entry_idx` and open it for editing."""
        for i, cd in enumerate(self.cards):
            if cd.idx == entry_idx:
                self.scroll_to_index(i)
                return self.editor.activate(i)
        return False

    # ── VWFPainter public API ──────────────────────────────────────────────────

    def get_active_scroll(self) -> int:
        """Return the vertical scroll offset of the active editor overlay."""
        if self.active_index >= 0:
            return self.editor.overlay.verticalScrollBar().value()
        return 0

    def get_active_lines(self, cd: CardData) -> list[str]:
        """Return the current lines from the active editor overlay."""
        if self.active_index >= 0:
            return self.editor.overlay.toPlainText().split("\n")
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

    def text_area_rect(self, i: int) -> QRect:
        return self._layout.text_area_rect(i, self._scroll_y)

    def _overlay_rect(self, i: int) -> QRect:
        return self._layout.overlay_rect(i, self._scroll_y)

    def _line_h(self) -> int:
        if self.vwf_mode:
            return self._s.vwf_line_pitch * self._s.vwf_scale
        return QFontMetrics(self._s.mono_font).height() + 2

    def vwf_qfont(self) -> QFont:
        """Get the VWF QFont for the editor overlay."""
        f = QFont(self.vwf_family or "")
        f.setFamilies([self.vwf_family or "", self._s.mono_font.family()])
        f.setPixelSize(8 * self._s.vwf_scale)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        f.setKerning(False)
        return f

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
        pc = PaletteColors(self.palette())
        p.fillRect(self.rect(), pc.bg)
        if not self.cards:
            p.end()
            return

        fm = QFontMetrics(self._s.mono_font)
        hdr_h = fm.height() + 6
        small = QFont(self._s.mono_font)
        small.setPointSize(max(7, self._s.mono_font.pointSize() - 2))
        colors = _CardColors(
            border=QColor(mix_colors(pc.card, pc.text, 0.15)),
            idx=QColor(mix_colors(pc.card, pc.text, 0.40)),
            dim=QColor(mix_colors(pc.card, pc.text, 0.30)),
            pc=pc,
        )
        inner = self._layout.CARD_INNER
        vp_top, vp_bot = self._scroll_y, self._scroll_y + self.height()

        for i, cd in enumerate(self.cards):
            cr = self._layout.card_rect(i)
            if cr.bottom() < vp_top or cr.top() > vp_bot:
                continue
            vr = QRect(cr.x(), cr.y() - self._scroll_y, cr.width(), cr.height())
            is_active = i == self.active_index
            self._paint_card_frame(p, cd, vr, is_active, small, hdr_h, colors)

            tx = vr.x() + inner
            ty = vr.y() + inner + hdr_h + inner
            tw = vr.width() - inner * 2
            th = self._s.card_rows * self._line_h()
            if self.vwf_mode:
                self._vwf_painter.paint_card(p, cd, is_active, tx, ty, tw, th, fm, colors.dim)
            else:
                self._paint_mono_text(p, cd, is_active, QRect(tx, ty, tw, th), fm, colors)
        p.end()

    def _paint_card_frame(self, p, cd, vr, is_active, small, hdr_h, c):
        """Card background, border and the header line (entry label + byte count)."""
        inner = self._layout.CARD_INNER
        p.setBrush(QBrush(c.pc.card))
        p.setPen(QPen(c.pc.accent if is_active else c.border, 1.0))
        p.drawRoundedRect(vr.adjusted(0, 0, -1, -1), 5, 5)
        p.setFont(small)
        hr = QRect(vr.x() + inner, vr.y() + inner, vr.width() - inner * 2, hdr_h)
        p.setPen(c.idx)
        p.drawText(hr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, cd.header)
        over_lines = bool(self._s.line_limit) and len(cd.lines) > self._s.line_limit
        p.setPen(C_OVER if over_lines or cd.byte_count > 300 else C_WARN if cd.byte_count > 150 else c.dim)
        label = (
            tr("{n}/{limit} líneas · ").format(n=len(cd.lines), limit=self._s.line_limit)
            if over_lines
            else ""
        )
        p.drawText(
            hr, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{label}{cd.byte_count}B"
        )

    def _paint_mono_text(self, p, cd, is_active, ta, fm, c):
        """Monospace mode: page bands, per-line character counters, text and ruler."""
        s, pc = self._s, c.pc
        tx, ty, tw, th = ta.x(), ta.y(), ta.width(), ta.height()
        line_h = self._line_h()
        p.fillRect(ta, pc.bg)
        p.setFont(s.mono_font)
        p.setClipRect(ta)

        overlay_scroll = self.editor.overlay.verticalScrollBar().value() if is_active else 0
        if s.show_bands:
            first_doc_ln = overlay_scroll // line_h
            for ln in range(s.card_rows + 2):
                doc_ln = first_doc_ln + ln
                ly = ty + (doc_ln * line_h) - overlay_scroll
                p.fillRect(
                    QRect(tx, ly, tw, line_h), pc.band0 if (doc_ln // self.page_lines) % 2 == 0 else pc.band1
                )
            p.fillRect(QRect(tx + tw - 24, ty, 24, th), pc.card)  # counter column

        lines = self.editor.overlay.toPlainText().split("\n") if is_active else cd.lines
        for ln, line in enumerate(lines):
            if not is_active and ln >= s.card_rows:
                break
            ly = ty + ln * line_h - overlay_scroll
            if line == BLANK_LINE_DISPLAY:
                pen = QPen(C_BLANK)
                pen.setStyle(Qt.PenStyle.DotLine)
                p.setPen(pen)
                y = ly + line_h // 2
                p.drawLine(tx + 4, y, tx + tw - 28, y)
                continue
            p.setPen(pc.text)
            p.drawText(tx + 2, ly + fm.ascent() + 1, line)
            vl = visible_len(line)
            count_str = str(vl)
            p.setPen(C_OVER if vl >= s.over_chars else C_WARN if vl >= s.warn_chars else c.dim)
            p.drawText(tx + tw - fm.horizontalAdvance(count_str) - 2, ly + fm.ascent() + 1, count_str)

        if s.show_ruler:
            cw = fm.horizontalAdvance("M")
            rx = tx + 2 + cw * (getattr(s, "ruler_chars", MAX_LINE_CHARS) + 1)
            pen = QPen(C_RULER)
            pen.setWidthF(0.8)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.drawLine(rx, ty, rx, ty + th)
        p.setClipping(False)

    # ── Editor Integration ──────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            i = self._layout.card_at(event.position().toPoint(), self._scroll_y)
            if i >= 0:
                self.editor.activate(i)
            else:
                self.editor.deactivate()

    def wheelEvent(self, event):
        if self._vbar:
            self._vbar.setValue(self._vbar.value() - event.angleDelta().y() // 2)

    def _on_scroll(self, value: int):
        self._scroll_y = value
        if self.active_index >= 0:
            self.editor.overlay.setGeometry(self._layout.overlay_rect(self.active_index, self._scroll_y))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout.set_width(self.width())
        self._update_scrollbar()
        if self.active_index >= 0:
            self.editor.overlay.setGeometry(self._layout.overlay_rect(self.active_index, self._scroll_y))
        self.update()

    # ── Exposed for toolbar actions (delegated to editor) ──────────────────────

    def action_insert_blank_line(self):
        self.editor.action_insert_blank_line()

    def action_centre_lines(self):
        self.editor.action_centre_lines()

    def action_select_all(self):
        self.editor.action_select_all()

    def action_cut(self):
        self.editor.action_cut()

    def action_copy(self):
        self.editor.action_copy()

    def action_paste(self):
        self.editor.action_paste()

    def action_copy_active(self):
        self.editor.action_copy_active()
