"""
ff4_editor/widgets/card_canvas.py

CardCanvas — QPainter-based card grid.
- Zero child widgets per card.
- One QPlainTextEdit floats over whichever card is active.
- All inactive cards are pure paint calls.
- External QScrollBar wired via set_scrollbar().
"""

import math
from PySide6.QtWidgets import QWidget, QTextEdit, QApplication, QSizePolicy
from PySide6.QtCore    import Qt, QRect, QTimer, Signal
from PySide6.QtGui     import (
    QPainter, QPen, QBrush, QColor, QFontMetrics,
    QTextCursor, QTextBlockFormat, QGuiApplication,
)

from ..constants        import (
    MAX_LINE_CHARS, BLANK_LINE_DISPLAY, DIALOG_SECTIONS,
    C_BG, C_CARD_BG, C_CARD_BORDER,
    C_TV_BG, C_TEXT, C_DIM, C_IDX, C_WARN, C_OVER, C_BLANK, C_RULER,
)
from ..util             import (
    json_to_display, display_to_json, visible_len, reflow_line,
)
from .card_data         import CardData
from .highlighter       import FF4Highlighter
from ..config import EditorConfig

# Layout constants
CARD_PAD   = 6   # gap between cards
CARD_INNER = 6   # padding inside each card


class CardCanvas(QWidget):
    card_committed = Signal(object, object, str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._s = config
        self.dte_set: dict = {}
        self._cards: list[CardData] = []
        self._ncols  = 1
        self._card_h = 200
        self._card_w = 300
        self._scroll_y = 0
        self._active   = -1
        self._change_pending = False
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._overlay = QTextEdit(self)
        self._overlay.setVisible(False)
        self._overlay.setStyleSheet("QTextEdit { background: transparent; border: none; }")
        self._overlay.document().setDocumentMargin(0)
        self._overlay.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._overlay.setTabChangesFocus(True)
        self._overlay.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overlay.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overlay.document().contentsChanged.connect(self._on_content_changed)
        self._overlay.installEventFilter(self)
        self._overlay.verticalScrollBar().valueChanged.connect(self.update)
        self._hl: FF4Highlighter | None = None
        self._vbar = None
        self._last_block_count = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def set_scrollbar(self, vbar):
        self._vbar = vbar
        vbar.valueChanged.connect(self._on_scroll)

    def load_cards(self, cards: list[CardData]):
        """Replace the current card list and reset view state."""
        self._deactivate()
        self._cards    = cards
        self._scroll_y = 0
        self._active   = -1
        if self._vbar:
            self._vbar.setValue(0)
        self._recompute_layout()
        self._update_scrollbar()
        self.update()

    def scroll_to_index(self, card_index: int):
        if 0 <= card_index < len(self._cards):
            row = card_index // max(1, self._ncols)
            y   = CARD_PAD + row * (self._card_h + CARD_PAD)
            if self._vbar:
                self._vbar.setValue(max(0, y - 20))

    # ── Toolbar actions (called from main window) ─────────────────────────────

    def action_insert_blank_line(self):
        if self._active < 0:
            return
        cur = self._overlay.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.insertText(BLANK_LINE_DISPLAY + '\n')

    def action_centre_lines(self):
        if self._active < 0:
            return
        cur = self._overlay.textCursor()
        if cur.hasSelection():
            doc = self._overlay.document()
            sb  = doc.findBlock(cur.selectionStart()).blockNumber()
            eb  = doc.findBlock(cur.selectionEnd() - 1).blockNumber()
        else:
            sb = eb = cur.blockNumber()
        for bn in range(sb, eb + 1):
            blk     = self._overlay.document().findBlockByNumber(bn)
            txt     = blk.text()
            if txt == BLANK_LINE_DISPLAY:
                continue
            stripped = txt.lstrip(' ')
            vl       = visible_len(stripped)
            char_limit = getattr(self._s, 'char_limit', MAX_LINE_CHARS)
            if vl >= char_limit:
                continue
            pad = (char_limit - vl) // 2
            c2  = QTextCursor(blk)
            c2.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            c2.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                            QTextCursor.MoveMode.KeepAnchor)
            c2.insertText(' ' * pad + stripped)

    def action_select_all(self):
        if self._active >= 0:
            self._overlay.selectAll()

    def action_cut(self):
        if self._active >= 0:
            self._overlay.cut()

    def action_copy(self):
        if self._active >= 0:
            self._overlay.copy()

    def action_copy_active(self):
        if self._active >= 0:
            QGuiApplication.clipboard().setText(self._overlay.toPlainText())

    def action_paste(self):
        if self._active >= 0:
            self._overlay.paste()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _recompute_layout(self):
        fm           = QFontMetrics(self._s._mono_font)
        line_h       = fm.height() + 2
        hdr_h        = fm.height() + 6
        text_h       = self._s.card_rows * line_h + CARD_INNER * 2
        self._card_h = hdr_h + text_h + CARD_INNER * 2
        self._card_w = self._s.card_w
        avail        = max(self._card_w + CARD_PAD, self.width() - CARD_PAD)
        self._ncols  = max(1, avail // (self._card_w + CARD_PAD))

    def _total_height(self) -> int:
        if not self._cards:
            return 0
        nrows = math.ceil(len(self._cards) / self._ncols)
        return nrows * (self._card_h + CARD_PAD) + CARD_PAD

    def _card_rect(self, i: int) -> QRect:
        col = i % self._ncols
        row = i // self._ncols
        x   = CARD_PAD + col * (self._card_w + CARD_PAD)
        y   = CARD_PAD + row * (self._card_h + CARD_PAD)
        return QRect(x, y, self._card_w, self._card_h)

    def _card_rect_v(self, i: int) -> QRect:
        r = self._card_rect(i)
        return QRect(r.x(), r.y() - self._scroll_y, r.width(), r.height())

    def _text_area_rect(self, i: int) -> QRect:
        fm    = QFontMetrics(self._s._mono_font)
        hdr_h = fm.height() + 6
        line_h= fm.height() + 2
        vr    = self._card_rect_v(i)
        tx    = vr.x() + CARD_INNER
        ty    = vr.y() + CARD_INNER + hdr_h + CARD_INNER
        tw    = vr.width() - CARD_INNER * 2
        th    = self._s.card_rows * line_h
        return QRect(tx, ty, tw, th)

    def _card_at(self, pos) -> int:
        for i in range(len(self._cards)):
            if self._card_rect_v(i).contains(pos):
                return i
        return -1

    def _update_scrollbar(self):
        if not self._vbar:
            return
        total = self._total_height()
        vp_h  = self.height()
        self._vbar.setRange(0, max(0, total - vp_h))
        self._vbar.setPageStep(vp_h)
        self._vbar.setSingleStep(self._card_h + CARD_PAD)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), C_BG)

        if not self._cards:
            p.end()
            return

        fm     = QFontMetrics(self._s._mono_font)
        line_h = fm.height() + 2
        hdr_h  = fm.height() + 6
        vp_top = self._scroll_y
        vp_bot = self._scroll_y + self.height()

        mono  = self._s._mono_font
        small = mono.__class__(mono)
        small.setPointSize(max(7, mono.pointSize() - 2))

        band0 = QColor(self._s.band0_color)
        band1 = QColor(self._s.band1_color)

        for i, cd in enumerate(self._cards):
            cr = self._card_rect(i)
            if cr.bottom() < vp_top or cr.top() > vp_bot:
                continue
            vr        = QRect(cr.x(), cr.y() - self._scroll_y, cr.width(), cr.height())
            is_active = (i == self._active)

            # ── Card background + border ──────────────────────────────────────
            p.setBrush(QBrush(C_CARD_BG))
            p.setPen(QPen(QColor('#9070e0') if is_active else C_CARD_BORDER, 1.0))
            p.drawRoundedRect(vr.adjusted(0, 0, -1, -1), 5, 5)

            # ── Header ───────────────────────────────────────────────────────
            p.setFont(small)
            hr = QRect(vr.x() + CARD_INNER, vr.y() + CARD_INNER,
                       vr.width() - CARD_INNER * 2, hdr_h)
            p.setPen(C_IDX)
            p.drawText(hr, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       cd.header)
            p.setPen(C_OVER if cd.byte_count > 300
                     else C_WARN if cd.byte_count > 150 else C_DIM)
            p.drawText(hr, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{cd.byte_count}B")

            # ── Text area ─────────────────────────────────────────────────────
            tx = vr.x() + CARD_INNER
            ty = vr.y() + CARD_INNER + hdr_h + CARD_INNER
            tw = vr.width() - CARD_INNER * 2
            th = self._s.card_rows * line_h
            ta = QRect(tx, ty, tw, th)
            p.fillRect(ta, C_TV_BG)

            p.setFont(mono)
            p.setClipRect(ta)

            # --- Draw bands for ALL cards here so they sit behind the text ---
            if self._s.show_bands:
                # QTextEdit scrollbar value is in PIXELS
                scroll_pixels = self._overlay.verticalScrollBar().value() if is_active else 0

                first_doc_ln = scroll_pixels // line_h
                # Draw extra lines to handle partial shifts without leaving a gap
                for i in range(self._s.card_rows + 2):
                    doc_ln = first_doc_ln + i
                    ly = ty + (doc_ln * line_h) - scroll_pixels

                    # Calculate the color based on the actual document line
                    p.fillRect(QRect(tx, ly, tw, line_h),
                               band0 if (doc_ln // 4) % 2 == 0 else band1)



            # --- Draw vertical background column for character counters ---
            if self._s.show_bands:
                # We must account for the overlay's scroll when drawing the background for the active card
                scroll_pixels = self._overlay.verticalScrollBar().value() if is_active else 0

                count_bg_color = QColor(235, 235, 235, 210) # Light gray with transparency
                count_col_w = 35 # Fixed width for the column

                first_doc_ln = scroll_pixels // line_h

                # --- Draw vertical background column for character counters ---
                p.fillRect(QRect(tx + tw - 24, ty, 24, th), QColor('#1a1828'))


            # For the active card, only draw counters (overlay handles the text)
            lines_to_paint = cd.lines
            if not is_active:
                for ln, line in enumerate(lines_to_paint):
                    if ln >= self._s.card_rows:
                        break
                    ly = ty + ln * line_h

                    # Text colour
                    if line == BLANK_LINE_DISPLAY:
                        p.setPen(C_BLANK)
                    elif self._s.show_colors:
                        vl = visible_len(line)
                        p.setPen(C_OVER  if vl >= self._s.over_chars  else
                                 C_WARN  if vl >= self._s.warn_chars  else C_TEXT)
                    else:
                        p.setPen(C_TEXT)
                    p.drawText(tx + 2, ly + fm.ascent() + 1, line)

           # Character counters — drawn for both active and inactive cards
            # For the active card use live overlay content so counts stay current
            active_scroll_offset = 0
            if is_active:
                lines_to_paint = self._overlay.toPlainText().split('\n')
                # Grab the vertical scrollbar's value (it is already in pixels!)
                active_scroll_offset = self._overlay.verticalScrollBar().value()

            for ln, line in enumerate(lines_to_paint):
                # ONLY break at 8 lines if the card is inactive.
                # If active, process all lines and let the clipping rect hide the overflow.
                if not is_active and ln >= self._s.card_rows:
                    break

                if line == BLANK_LINE_DISPLAY:
                    continue

                # Subtract the scroll offset from the Y coordinate
                ly = ty + ln * line_h - active_scroll_offset

                vl = visible_len(line)
                count_str = str(vl)
                cw_count = fm.horizontalAdvance(count_str)
                p.setPen(C_OVER if vl >= self._s.over_chars else
                         C_WARN if vl >= self._s.warn_chars else C_DIM)
                p.drawText(tx + tw - cw_count - 2, ly + fm.ascent() + 1, count_str)
            p.setClipping(False)

            # Ruler line
            if self._s.show_ruler:
                cw  = fm.horizontalAdvance('M')
                ruler_col = getattr(self._s, 'ruler_chars', MAX_LINE_CHARS)
                rx  = tx + 2 + cw * (ruler_col + 1)
                pen = QPen(C_RULER)
                pen.setWidthF(0.8)
                pen.setStyle(Qt.PenStyle.DotLine)
                p.setPen(pen)
                p.drawLine(rx, ty, rx, ty + th)

        p.end()

    # ── Activation / deactivation ─────────────────────────────────────────────

    def _activate(self, i: int):
        if i == self._active:
            return
        self._deactivate()
        if i < 0 or i >= len(self._cards):
            return
        self._active = i
        cd = self._cards[i]

        # Position and populate overlay
        ta = self._text_area_rect(i)
        self._overlay.setFont(self._s._mono_font)
        self._overlay.setGeometry(ta.adjusted(2, -1, 0, 0))

        self._overlay.document().blockSignals(True)
        self._overlay.setPlainText(
            json_to_display(cd.json_text) if cd.is_dialog else cd.json_text)

        # Force QPlainTextEdit line height to match QPainter
        fm = QFontMetrics(self._s._mono_font)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(float(fm.height() + 2), 2) # 2 is FixedHeight

        cursor = self._overlay.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)

        self._apply_bands_to_overlay()
        self._overlay.document().blockSignals(False)

        self._hl = FF4Highlighter(self._overlay.document(), self._s)
        self._last_block_count = self._overlay.document().blockCount()
        self._overlay.setVisible(True)
        self._overlay.setFocus()

        self.update()

    def _deactivate(self):
        if self._active < 0:
            return
        self._flush()
        self._overlay.setVisible(False)
        self._hl = None
        self._active = -1
        self.update()

    def _flush(self):
        if self._active < 0:
            return
        cd  = self._cards[self._active]
        raw = self._overlay.toPlainText()
        jt  = display_to_json(raw) if cd.is_dialog else raw
        self._commit(self._active, jt)

    def _commit(self, i: int, json_text: str):
        from ..model.encoding import encode_size
        cd = self._cards[i]
        if cd.json_text == json_text:
            return
        bc = encode_size(json_text, self.dte_set)
        cd.update(json_text, bc)
        self.card_committed.emit(cd.section, cd.idx, json_text)
        self.update()

    def _apply_bands_to_overlay(self):
        '''
        if not self._s.show_bands:
            return
        doc = self._overlay.document()
        c0  = QColor(self._s.band0_color)
        c1  = QColor(self._s.band1_color)
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        blk = doc.begin()
        while blk.isValid():
            fmt = QTextBlockFormat()
            fmt.setBackground(c0 if (blk.blockNumber() // 4) % 2 == 0 else c1)
            cur.setPosition(blk.position())
            cur.setBlockFormat(fmt)
            blk = blk.next()
        cur.endEditBlock()
        '''
        pass
    # ── Editor change / reflow ─────────────────────────────────────────────────

    def _on_content_changed(self):
        if self._change_pending or self._active < 0:
            return
        self._change_pending = True

        def do():
            self._change_pending = False
            if self._active < 0:
                return
            cd = self._cards[self._active]
            if cd.is_dialog and self._s.auto_wrap and not getattr(self._s, 'hard_char_limit', False):
                self._reflow_overlay()
            # Reapply bands if line count changed
            bc = self._overlay.document().blockCount()
            if bc != self._last_block_count:
                self._last_block_count = bc
                self._apply_bands_to_overlay()
            raw = self._overlay.toPlainText()
            jt  = display_to_json(raw) if cd.is_dialog else raw
            self._commit(self._active, jt)

        QTimer.singleShot(0, do)

    def _reflow_overlay(self):
        ov  = self._overlay
        cur = ov.textCursor()
        cb  = cur.blockNumber()
        cc  = cur.positionInBlock()
        lines = ov.toPlainText().split('\n')

        new_lines = []; ln_out = 0; nb = cb; nc = cc
        for ln, line in enumerate(lines):
            if line == BLANK_LINE_DISPLAY:
                if ln == cb:
                    nb = ln_out
                new_lines.append(line); ln_out += 1
                continue
            _hyph = (getattr(self._s, 'auto_hyphenate', True)
                     and getattr(self._s, '_cur_section', None) in DIALOG_SECTIONS)
            char_limit = getattr(self._s, 'char_limit', MAX_LINE_CHARS)
            reflowed = reflow_line(line, limit=char_limit, hyphenate=_hyph)
            if ln == cb:
                col = cc
                for ri, rline in enumerate(reflowed):
                    if col <= len(rline):
                        nb = ln_out + ri; nc = col; break
                    col -= len(rline) + 1
                else:
                    nb = ln_out + len(reflowed) - 1
                    nc = len(reflowed[-1])
            elif ln < cb:
                nb += len(reflowed) - 1
            new_lines.extend(reflowed); ln_out += len(reflowed)

        # Enforce line limit
        line_limit = getattr(self._s, 'line_limit', 0)
        if line_limit > 0 and len(new_lines) > line_limit:
            new_lines = new_lines[:line_limit]
        new_text = '\n'.join(new_lines)
        if new_text == ov.toPlainText():
            return




        ov.document().blockSignals(True)

        # Replace text safely to preserve and merge undo history
        replace_cursor = QTextCursor(ov.document())
        replace_cursor.joinPreviousEditBlock()
        replace_cursor.select(QTextCursor.SelectionType.Document)
        replace_cursor.insertText(new_text)

        # Re-apply matching line height after replacement wipes it
        fm = QFontMetrics(self._s._mono_font)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(float(fm.height() + 2), 2)

        replace_cursor.select(QTextCursor.SelectionType.Document)
        replace_cursor.mergeBlockFormat(fmt)
        replace_cursor.endEditBlock()

        self._apply_bands_to_overlay()
        ov.document().blockSignals(False)



        '''
        ov.document().blockSignals(True)
        ov.setPlainText(new_text)

        # Re-apply matching line height after reflow wipes it
        fm = QFontMetrics(self._s._mono_font)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(float(fm.height() + 2), 2) # 2 is

        cursor = ov.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)

        self._apply_bands_to_overlay()
        ov.document().blockSignals(False)
        '''

        if self._hl:
            self._hl.rehighlight()

        doc  = ov.document()
        sb   = min(nb, doc.blockCount() - 1)
        blk  = doc.findBlockByNumber(sb)
        sc   = min(nc, max(0, blk.length() - 1))
        nc2  = QTextCursor(blk)
        nc2.movePosition(QTextCursor.MoveOperation.Right,
                         QTextCursor.MoveMode.MoveAnchor, sc)
        ov.setTextCursor(nc2)

    # ── Event filter ──────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is not self._overlay or event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)

        key = event.key()

        # Esc → close overlay
        if key == Qt.Key.Key_Escape:
            self._deactivate()
            self.setFocus()
            return True

        # Block Enter if at line_limit
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            line_limit = getattr(self._s, 'line_limit', 0)
            if line_limit > 0:
                cur = self._overlay.textCursor()
                if self._overlay.document().blockCount() >= line_limit:
                    return True  # block newline

        # Hard char limit — block printable input when current line is full
        if getattr(self._s, 'hard_char_limit', False):
            char_limit = getattr(self._s, 'char_limit', MAX_LINE_CHARS)
            txt = event.text()
            if char_limit > 0 and len(txt) == 1 and txt.isprintable():
                cur = self._overlay.textCursor()
                # Use same source as the painted counter: toPlainText split by line
                all_lines = self._overlay.toPlainText().split('\n')
                bn = cur.blockNumber()
                line_text = all_lines[bn] if bn < len(all_lines) else ''
                if cur.hasSelection():
                    blk_pos   = cur.block().position()
                    sel_start = max(0, cur.selectionStart() - blk_pos)
                    sel_end   = min(len(line_text), cur.selectionEnd() - blk_pos)
                    line_text = line_text[:sel_start] + line_text[sel_end:]
                if visible_len(line_text) >= char_limit:
                    return True

        # Backspace / Delete on BLANK_LINE row
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            cur = self._overlay.textCursor()
            cur.select(QTextCursor.SelectionType.LineUnderCursor)
            if cur.selectedText() == BLANK_LINE_DISPLAY:
                cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cur.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                                 QTextCursor.MoveMode.KeepAnchor)
                if not cur.atEnd():
                    cur.movePosition(QTextCursor.MoveOperation.NextCharacter,
                                     QTextCursor.MoveMode.KeepAnchor)
                elif cur.blockNumber() > 0:
                    cur.movePosition(QTextCursor.MoveOperation.PreviousCharacter,
                                     QTextCursor.MoveMode.KeepAnchor)
                cur.removeSelectedText()
                return True

        return super().eventFilter(obj, event)


    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            i = self._card_at(event.position().toPoint())
            if i >= 0:
                self._activate(i)
            else:
                self._deactivate()

    def wheelEvent(self, event):
        if self._vbar:
            self._vbar.setValue(
                self._vbar.value() - event.angleDelta().y() // 2)

    def _on_scroll(self, value: int):
        self._scroll_y = value
        if self._active >= 0:
            self._overlay.setGeometry(self._text_area_rect(self._active).adjusted(2, -1, 0, 0))
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute_layout()
        self._update_scrollbar()
        if self._active >= 0:
            self._overlay.setGeometry(self._text_area_rect(self._active))
        self.update()
