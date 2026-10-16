"""
ff4_editor/widgets/card_editor.py
Handles the floating QTextEdit overlay for card editing.
Manages activation, deactivation, commit, and reflow.
"""

from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt, QTimer, QRect
from PySide6.QtGui import QFont, QTextCursor, QTextBlockFormat, QGuiApplication, QFontMetrics

from ..util import json_to_display, display_to_json
from ..util.text_processing import (
    reflow_line, compute_reflow_limit, compute_reflow_measure, visible_len,
    BLANK_LINE_DISPLAY
)


class CardEditor:
    """Manages the single floating editor overlay for active card."""

    def __init__(self, canvas):
        self.canvas = canvas
        self._s = canvas._s

        self._overlay = QTextEdit(canvas)
        self._overlay.setVisible(False)
        self._overlay.setStyleSheet("background: transparent; border: none;")
        self._overlay.document().setDocumentMargin(0)
        self._overlay.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._overlay.setTabChangesFocus(True)
        self._overlay.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overlay.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overlay.document().contentsChanged.connect(self._on_content_changed)
        self._overlay.installEventFilter(canvas)  # canvas handles key events
        self._overlay.verticalScrollBar().valueChanged.connect(canvas.update)

        self._hl = None
        self._last_block_count = 0
        self._change_pending = False

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def overlay(self) -> QTextEdit:
        return self._overlay

    @property
    def active(self) -> bool:
        return self.canvas._active >= 0

    def activate(self, index: int) -> bool:
        """Activate editor for card at index."""
        if index < 0 or index >= len(self.canvas._cards):
            return False
        if index == self.canvas._active:
            return True

        self.deactivate()
        self.canvas._active = index
        cd = self.canvas._cards[index]

        self._overlay.setFont(self._get_font())
        self._overlay.setGeometry(self._overlay_rect(index))

        self._overlay.document().blockSignals(True)
        self._overlay.setPlainText(
            json_to_display(cd.json_text) if cd.is_dialog else cd.json_text
        )

        fmt = QTextBlockFormat()
        if not self.canvas._vwf_mode:
            fmt.setLineHeight(float(self._line_h()), 2)

        cursor = self._overlay.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)

        self._overlay.document().blockSignals(False)

        from ..widgets.highlighter import FF4Highlighter
        self._drop_highlighter()
        self._hl = FF4Highlighter(self._overlay.document(), self._s, vwf=self.canvas._vwf_mode)
        self._last_block_count = self._overlay.document().blockCount()
        self._overlay.setVisible(True)
        self._overlay.setFocus()

        self.canvas.update()
        return True

    def _drop_highlighter(self):
        """Detach and destroy the current highlighter (it is a child of the document,
        so just forgetting the reference would leave one more attached per activation)."""
        if self._hl is not None:
            self._hl.setDocument(None)
            self._hl.deleteLater()
            self._hl = None

    def deactivate(self):
        """Deactivate editor, committing any pending changes."""
        if self.canvas._active < 0:
            return
        self._flush()
        self._overlay.setVisible(False)
        self._drop_highlighter()
        self.canvas._active = -1
        self.canvas.update()

    def _get_font(self) -> QFont:
        if self.canvas._vwf_mode:
            return self.canvas._vwf_qfont()
        return self._s._mono_font

    def _line_h(self) -> int:
        if self.canvas._vwf_mode:
            return self._s.vwf_line_pitch * self._s.vwf_scale
        return QFontMetrics(self._s._mono_font).height() + 2

    def _overlay_rect(self, index: int) -> QRect:
        ta = self.canvas._text_area_rect(index)
        return ta if self.canvas._vwf_mode else ta.adjusted(2, -1, 0, 0)

    # ── Commit / Flush ────────────────────────────────────────────────────────

    def _flush(self):
        if self.canvas._active < 0:
            return
        cd = self.canvas._cards[self.canvas._active]
        raw = self._overlay.toPlainText()
        jt = display_to_json(raw) if cd.is_dialog else raw
        self._commit(self.canvas._active, jt)

    def _commit(self, index: int, json_text: str):
        from ..model.encoding import encode_size
        cd = self.canvas._cards[index]
        if cd.json_text == json_text:
            return
        bc = encode_size(json_text, self.canvas.dte_set)
        cd.update(json_text, bc)
        self.canvas.card_committed.emit(cd.section, cd.idx, json_text)
        self.canvas.update()

    # ── Content Changed / Reflow ──────────────────────────────────────────────

    def _on_content_changed(self):
        if self._change_pending or self.canvas._active < 0:
            return
        self._change_pending = True

        def do():
            self._change_pending = False
            if self.canvas._active < 0:
                return
            cd = self.canvas._cards[self.canvas._active]
            if cd.is_dialog and self._s.auto_wrap and not getattr(self._s, 'hard_char_limit', False):
                self._reflow_overlay()

            bc = self._overlay.document().blockCount()
            if bc != self._last_block_count:
                self._last_block_count = bc

            raw = self._overlay.toPlainText()
            jt = display_to_json(raw) if cd.is_dialog else raw
            self._commit(self.canvas._active, jt)

        QTimer.singleShot(0, do)

    def _reflow_overlay(self):
        ov = self._overlay
        cur = ov.textCursor()
        cb = cur.blockNumber()
        cc = cur.positionInBlock()
        lines = ov.toPlainText().split('\n')

        vwf = self.canvas._vwf if self.canvas._vwf_mode else None

        new_lines = []
        ln_out = 0
        nb = cb
        nc = cc

        for ln, line in enumerate(lines):
            if line == BLANK_LINE_DISPLAY:
                if ln == cb:
                    nb = ln_out
                new_lines.append(line)
                ln_out += 1
                continue

            limit = compute_reflow_limit(self._s, vwf)
            measure = compute_reflow_measure(self._s, vwf)
            reflowed = reflow_line(line, limit, measure)

            if ln == cb:
                col = cc
                for ri, rline in enumerate(reflowed):
                    if col <= len(rline):
                        nb = ln_out + ri
                        nc = col
                        break
                    col -= len(rline) + 1
                else:
                    nb = ln_out + len(reflowed) - 1
                    nc = len(reflowed[-1])
            elif ln < cb:
                nb += len(reflowed) - 1

            new_lines.extend(reflowed)
            ln_out += len(reflowed)

        # NOTE: no truncation to `line_limit` here: dropping lines would delete text the user
        # just typed.  Going over the limit is reported by the budget/warning display instead.

        new_text = '\n'.join(new_lines)
        if new_text == ov.toPlainText():
            return

        ov.document().blockSignals(True)
        replace_cursor = QTextCursor(ov.document())
        replace_cursor.joinPreviousEditBlock()
        replace_cursor.select(QTextCursor.SelectionType.Document)
        replace_cursor.insertText(new_text)

        fmt = QTextBlockFormat()
        if not self.canvas._vwf_mode:
            fmt.setLineHeight(float(self._line_h()), 2)

        replace_cursor.select(QTextCursor.SelectionType.Document)
        replace_cursor.mergeBlockFormat(fmt)
        replace_cursor.endEditBlock()

        ov.document().blockSignals(False)

        if self._hl:
            self._hl.rehighlight()

        doc = ov.document()
        sb = min(nb, doc.blockCount() - 1)
        blk = doc.findBlockByNumber(sb)
        sc = min(nc, max(0, blk.length() - 1))
        nc2 = QTextCursor(blk)
        nc2.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, sc)
        ov.setTextCursor(nc2)

    # ── Toolbar Actions ──────────────────────────────────────────────────────

    def action_insert_blank_line(self):
        if self.canvas._active < 0:
            return
        cur = self._overlay.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.insertText(BLANK_LINE_DISPLAY + '\n')

    def action_centre_lines(self):
        if self.canvas._active < 0:
            return
        cur = self._overlay.textCursor()
        if cur.hasSelection():
            doc = self._overlay.document()
            sb = doc.findBlock(cur.selectionStart()).blockNumber()
            eb = doc.findBlock(cur.selectionEnd() - 1).blockNumber()
        else:
            sb = eb = cur.blockNumber()

        vwf = self.canvas._vwf if self.canvas._vwf_mode else None
        limit = compute_reflow_limit(self._s, vwf)
        measure = compute_reflow_measure(self._s, vwf)

        for bn in range(sb, eb + 1):
            blk = self._overlay.document().findBlockByNumber(bn)
            txt = blk.text()
            if txt == BLANK_LINE_DISPLAY:
                continue
            stripped = txt.lstrip(' ')
            w = measure(stripped) if measure else visible_len(stripped)
            if w >= limit:
                continue
            pad = round(((limit - w) / 2) / max(1, vwf.adv(' '))) if vwf else (limit - w) // 2
            c2 = QTextCursor(blk)
            c2.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            c2.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            c2.insertText(' ' * pad + stripped)

    def action_select_all(self):
        if self.canvas._active >= 0:
            self._overlay.selectAll()

    def action_cut(self):
        if self.canvas._active >= 0:
            self._overlay.cut()

    def action_copy(self):
        if self.canvas._active >= 0:
            self._overlay.copy()

    def action_paste(self):
        if self.canvas._active >= 0:
            self._overlay.paste()

    def action_copy_active(self):
        if self.canvas._active >= 0:
            QGuiApplication.clipboard().setText(self._overlay.toPlainText())