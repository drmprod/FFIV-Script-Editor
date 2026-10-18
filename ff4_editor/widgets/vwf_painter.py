"""
ff4_editor/widgets/vwf_painter.py
VWF-specific painting logic extracted from CardCanvas.
Handles game-accurate dialogue box rendering with variable-width font.
"""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen

from ..constants import (
    BLANK_LINE_DISPLAY,
    C_BLANK,
    C_OVER,
    C_RULER,
    C_WARN,
    VWF_BOX_BG,
    VWF_INK,
    PaletteColors,
    mix_colors,
)
from ..util.patterns import ATOM_SPLIT


class VWFPainter:
    """Paints VWF-mode cards exactly like the game dialogue box."""

    def __init__(self, canvas):
        self.canvas = canvas
        self._s = canvas.config

    @property
    def _vwf(self):
        return self.canvas.vwf

    @property
    def _vwf_family(self):
        return self.canvas.vwf_family

    def paint_card(
        self,
        p: QPainter,
        cd,
        is_active: bool,
        tx: int,
        ty: int,
        tw: int,
        th: int,
        fm: QFontMetrics,
        c_dim: QColor,
    ):
        """Paint VWF text area for one card."""
        s = self._s
        sc = s.vwf_scale
        pitch = s.vwf_line_pitch * sc
        box_w = s.vwf_limit_px * sc
        ta = QRect(tx, ty, tw, th)

        pc = PaletteColors(self.canvas.palette())
        p.fillRect(ta, pc.card)
        p.setClipRect(ta)
        p.fillRect(QRect(tx, ty, box_w, th), QColor(VWF_BOX_BG))

        scroll = self.canvas.get_active_scroll() if is_active else 0

        # Page bands (one tint per dialogue page)
        if s.show_bands:
            tint = QColor(mix_colors(VWF_BOX_BG, "#ffffff", 0.07))
            first = scroll // pitch
            for k in range(s.card_rows + 2):
                ln = first + k
                if (ln // self.canvas.page_lines) % 2 == 1:
                    p.fillRect(QRect(tx, ty + ln * pitch - scroll, box_w, pitch), tint)

        lines = self.canvas.get_active_lines(cd) if is_active else cd.lines
        vfont = self.canvas.vwf_qfont()
        accent = pc.accent

        for ln, line in enumerate(lines):
            if not is_active and ln >= s.card_rows:
                break
            ly = ty + ln * pitch - scroll
            if ly + pitch < ty or ly > ty + th:
                continue

            if line == BLANK_LINE_DISPLAY:
                pen = QPen(C_BLANK)
                pen.setStyle(Qt.PenStyle.DotLine)
                p.setPen(pen)
                p.drawLine(tx + 4, ly + pitch * 3 // 4, tx + box_w - 4, ly + pitch * 3 // 4)
                continue

            if not is_active:
                self._draw_vwf_line(p, tx, ly + pitch, line, vfont, accent)

            # Pixel counter
            w = self._vwf.measure(line)
            p.setFont(self._s.mono_font)
            p.setPen(
                C_OVER
                if w > s.vwf_limit_px
                else C_WARN
                if w > s.vwf_limit_px - 2 * self._vwf.adv("a")
                else c_dim
            )
            base = ly + (pitch + fm.ascent() - fm.descent()) // 2
            p.drawText(tx + box_w + 6, base, f"{w}px")

        p.setClipping(False)

        # Ruler at line width boundary
        if s.show_ruler:
            pen = QPen(C_RULER)
            pen.setWidthF(0.8)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.drawLine(tx + box_w, ty, tx + box_w, ty + th)

    _SEG_PAT = ATOM_SPLIT

    def _draw_vwf_line(self, p: QPainter, x: int, y: int, line: str, vfont: QFont, accent: QColor):
        """Draw one line with syntax highlighting for {Names} and \\commands."""
        p.setFont(vfont)
        fm = QFontMetrics(vfont)
        for seg in self._SEG_PAT.split(line):
            if not seg:
                continue
            if seg[0] == "{":
                p.setPen(accent)
            elif seg[0] == "\\":
                p.setPen(QColor("#6fa8a0"))
            else:
                p.setPen(QColor(VWF_INK))
            p.drawText(x, y, seg)
            x += fm.horizontalAdvance(seg)
