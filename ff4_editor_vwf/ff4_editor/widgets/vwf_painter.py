"""
ff4_editor/widgets/vwf_painter.py
VWF-specific painting logic extracted from CardCanvas.
Handles game-accurate dialogue box rendering with variable-width font.
"""

import re
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QFontMetrics
from PySide6.QtCore import Qt, QRect

from ..constants import (
    VWF_BOX_BG, VWF_INK, VWF_PAGE_LINES, C_BLANK, C_WARN, C_OVER, C_RULER,
    mix_colors, PaletteColors, BLANK_LINE_DISPLAY
)


class VWFPainter:
    """Paints VWF-mode cards exactly like the game dialogue box."""

    def __init__(self, canvas):
        self.canvas = canvas
        self._s = canvas._s

    @property
    def _vwf(self):
        return self.canvas._vwf

    @property
    def _vwf_family(self):
        return self.canvas._vwf_family

    def paint_card(self, p: QPainter, cd, is_active: bool, tx: int, ty: int, tw: int, th: int, fm: QFontMetrics, c_dim: QColor):
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
            tint = QColor(mix_colors(VWF_BOX_BG, '#ffffff', 0.07))
            first = scroll // pitch
            for k in range(s.card_rows + 2):
                ln = first + k
                if (ln // VWF_PAGE_LINES) % 2 == 1:
                    p.fillRect(QRect(tx, ty + ln * pitch - scroll, box_w, pitch), tint)

        lines = self.canvas.get_active_lines(cd) if is_active else cd.lines
        vfont = self._get_vwf_qfont()

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
                self._draw_vwf_line(p, tx, ly + pitch, line, vfont)

            # Pixel counter
            w = self._vwf.measure(line)
            p.setFont(self._s._mono_font)
            p.setPen(
                C_OVER if w > s.vwf_limit_px else
                C_WARN if w > s.vwf_limit_px - 2 * self._vwf.adv('a') else c_dim
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

    def _get_vwf_qfont(self) -> QFont:
        f = QFont(self._vwf_family)
        f.setFamilies([self._vwf_family, self._s._mono_font.family()])
        f.setPixelSize(8 * self._s.vwf_scale)
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        f.setKerning(False)
        return f

    _SEG_PAT = re.compile(r'(\\[a-zA-Z0-9]+(?:\[.*?\])?|\{[^}]+\})')

    def _draw_vwf_line(self, p: QPainter, x: int, y: int, line: str, vfont: QFont):
        """Draw one line with syntax highlighting for {Names} and \\commands."""
        p.setFont(vfont)
        fm = QFontMetrics(vfont)
        for seg in self._SEG_PAT.split(line):
            if not seg:
                continue
            if seg[0] == '{':
                p.setPen(PaletteColors(self.canvas.palette()).accent)
            elif seg[0] == '\\':
                p.setPen(QColor('#6fa8a0'))
            else:
                p.setPen(QColor(VWF_INK))
            p.drawText(x, y, seg)
            x += fm.horizontalAdvance(seg)