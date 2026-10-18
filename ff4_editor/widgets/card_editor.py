"""
ff4_editor/widgets/card_editor.py
Handles the floating QTextEdit overlay for card editing.
Manages activation, deactivation, commit, and reflow.
"""

from PySide6.QtCore import QRect, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from ..util import display_to_json, json_to_display
from ..util.text_processing import (
    BLANK_LINE_DISPLAY,
    compute_reflow_limit,
    compute_reflow_measure,
    reflow_line,
)


class CardEditor:
    """Manages the single floating editor overlay for active card."""

    def __init__(self, canvas):
        self.canvas = canvas
        self._s = canvas.config

        self._overlay = QTextEdit(canvas)
        self._overlay.setVisible(False)
        self._overlay.setObjectName("cardOverlay")
        # scoped by selector: an unscoped rule is inherited by the context menu (transparent popup)
        self._overlay.setStyleSheet("QTextEdit#cardOverlay { background: transparent; border: none; }")
        self._overlay.document().setDocumentMargin(0)
        self._overlay.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._overlay.setTabChangesFocus(True)
        self._overlay.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overlay.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._overlay.document().contentsChanged.connect(self._on_content_changed)
        self._overlay.installEventFilter(canvas)  # canvas handles key events
        self._overlay.selectionChanged.connect(canvas.active_changed)
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
        return self.canvas.active_index >= 0

    def activate(self, index: int) -> bool:
        """Activate editor for card at index."""
        if index < 0 or index >= len(self.canvas.cards):
            return False
        if index == self.canvas.active_index:
            return True

        self.deactivate()
        self.canvas.active_index = index
        cd = self.canvas.cards[index]

        self._overlay.setFont(self._get_font())
        self._overlay.setGeometry(self._overlay_rect(index))

        self._overlay.document().blockSignals(True)
        self._overlay.setPlainText(json_to_display(cd.json_text) if cd.is_dialog else cd.json_text)

        fmt = self._block_format()

        cursor = self._overlay.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(fmt)

        self._overlay.document().blockSignals(False)

        from ..widgets.highlighter import FF4Highlighter

        self._drop_highlighter()
        self._hl = FF4Highlighter(self._overlay.document(), self._s, vwf=self.canvas.vwf_mode)
        self._last_block_count = self._overlay.document().blockCount()
        self._overlay.setVisible(True)
        self._overlay.setFocus()

        self.canvas.update()
        self.canvas.active_changed.emit()
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
        if self.canvas.active_index < 0:
            return
        self._flush()
        self._overlay.setVisible(False)
        self._drop_highlighter()
        self.canvas.active_index = -1
        self.canvas.update()
        self.canvas.active_changed.emit()

    def cancel(self):
        """Close the editor WITHOUT committing (the card changed underneath it)."""
        if self.canvas.active_index < 0:
            return
        self._overlay.setVisible(False)
        self._drop_highlighter()
        self.canvas.active_index = -1
        self.canvas.update()
        self.canvas.active_changed.emit()

    def _get_font(self) -> QFont:
        if self.canvas.vwf_mode:
            return self.canvas.vwf_qfont()
        return self._s.mono_font

    def _block_format(self) -> QTextBlockFormat:
        """Every line is exactly one pitch high, in both modes.  Without it a line holding only the
        \\line separator glyph (missing from the game font, so a fallback font is used) comes out
        taller and pushes the text below it out of line with the painted card."""
        fmt = QTextBlockFormat()
        fmt.setLineHeight(float(self._line_h()), QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        return fmt

    def _ensure_block_format(self) -> None:
        """Re-apply the fixed line height to blocks that lost it (text replaced, pasted...)."""
        doc = self._overlay.document()
        want = float(self._line_h())
        fixed = QTextBlockFormat.LineHeightTypes.FixedHeight.value
        block = doc.begin()
        while block.isValid():
            bf = block.blockFormat()
            if bf.lineHeightType() != fixed or bf.lineHeight() != want:
                break
            block = block.next()
        else:
            return
        doc.blockSignals(True)
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        cur.mergeBlockFormat(self._block_format())
        doc.blockSignals(False)
        doc.markContentsDirty(0, doc.characterCount())  # signals were blocked: force the relayout
        self._overlay.viewport().update()

    def _line_h(self) -> int:
        if self.canvas.vwf_mode:
            return self._s.vwf_line_pitch * self._s.vwf_scale
        return QFontMetrics(self._s.mono_font).height() + 2

    def _overlay_rect(self, index: int) -> QRect:
        ta = self.canvas.text_area_rect(index)
        return ta if self.canvas.vwf_mode else ta.adjusted(2, -1, 0, 0)

    # ── Commit / Flush ────────────────────────────────────────────────────────

    def _flush(self):
        if self.canvas.active_index < 0:
            return
        cd = self.canvas.cards[self.canvas.active_index]
        raw = self._overlay.toPlainText()
        jt = display_to_json(raw) if cd.is_dialog else raw
        self._commit(self.canvas.active_index, jt)

    def _commit(self, index: int, json_text: str):
        cd = self.canvas.cards[index]
        if cd.json_text == json_text:
            return
        bc = self.canvas.byte_cost(cd.section, json_text)
        cd.update(json_text, bc)
        self.canvas.card_committed.emit(cd.section, cd.idx, json_text)
        self.canvas.update()

    # ── Content Changed / Reflow ──────────────────────────────────────────────

    def _on_content_changed(self):
        if self._change_pending or self.canvas.active_index < 0:
            return
        self._change_pending = True

        def do():
            self._change_pending = False
            if self.canvas.active_index < 0:
                return
            cd = self.canvas.cards[self.canvas.active_index]
            if cd.is_dialog and self._s.auto_wrap:
                self._reflow_overlay()
            self._ensure_block_format()

            bc = self._overlay.document().blockCount()
            if bc != self._last_block_count:
                self._last_block_count = bc

            raw = self._overlay.toPlainText()
            jt = display_to_json(raw) if cd.is_dialog else raw
            self._commit(self.canvas.active_index, jt)

        QTimer.singleShot(0, do)

    def _reflow_overlay(self):
        ov = self._overlay
        cur = ov.textCursor()
        cb = cur.blockNumber()
        cc = cur.positionInBlock()
        lines = ov.toPlainText().split("\n")

        vwf = self.canvas.vwf if self.canvas.vwf_mode else None

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

            line = line.replace(BLANK_LINE_DISPLAY, "")
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

        new_text = "\n".join(new_lines)
        if new_text == ov.toPlainText():
            return

        ov.document().blockSignals(True)
        replace_cursor = QTextCursor(ov.document())
        replace_cursor.joinPreviousEditBlock()
        replace_cursor.select(QTextCursor.SelectionType.Document)
        replace_cursor.insertText(new_text)

        fmt = self._block_format()

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

    # ── \line separators behave as one character ─────────────────────────────

    @staticmethod
    def _is_blank(block) -> bool:
        return block.isValid() and block.text() == BLANK_LINE_DISPLAY

    def _remove_block(self, block) -> None:
        """Delete a whole separator line together with its line break."""
        cur = QTextCursor(block)
        cur.beginEditBlock()
        nxt, prv = block.next(), block.previous()
        if nxt.isValid():
            cur.setPosition(block.position())
            cur.setPosition(nxt.position(), QTextCursor.MoveMode.KeepAnchor)
        elif prv.isValid():
            cur.setPosition(prv.position() + prv.length() - 1)
            cur.setPosition(block.position() + block.length() - 1, QTextCursor.MoveMode.KeepAnchor)
        else:
            cur.setPosition(block.position())
            cur.setPosition(block.position() + block.length() - 1, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        cur.endEditBlock()

    def handle_key(self, event) -> bool:
        """Keys next to a \\line separator.  Backspace/Delete remove it in one stroke, and it
        cannot be typed into or glued to a neighbouring line.  True if the key was consumed."""
        if self.canvas.active_index < 0:
            return False
        cur = self._overlay.textCursor()
        if cur.hasSelection():
            return False
        blk, pos, key = cur.block(), cur.positionInBlock(), event.key()
        blank = self._is_blank(blk)
        if key == Qt.Key.Key_Backspace:
            if blank and pos == 1:
                self._remove_block(blk)
                return True
            if pos == 0 and self._is_blank(blk.previous()):
                self._remove_block(blk.previous())
                return True
            return blank and pos == 0
        if key == Qt.Key.Key_Delete:
            if blank and pos == 0:
                self._remove_block(blk)
                return True
            if pos == len(blk.text()) and self._is_blank(blk.next()):
                self._remove_block(blk.next())
                return True
            return blank and pos == 1
        mods = event.modifiers()
        typing = not (
            mods
            & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
            )
        )
        return blank and typing and bool(event.text()) and event.text().isprintable()

    # ── Toolbar Actions ──────────────────────────────────────────────────────

    def action_insert_blank_line(self):
        if self.canvas.active_index < 0:
            return
        cur = self._overlay.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.insertText(BLANK_LINE_DISPLAY + "\n")

    def action_centre_lines(self):
        if self.canvas.active_index < 0:
            return
        cur = self._overlay.textCursor()
        if cur.hasSelection():
            doc = self._overlay.document()
            sb = doc.findBlock(cur.selectionStart()).blockNumber()
            eb = doc.findBlock(cur.selectionEnd() - 1).blockNumber()
        else:
            sb = eb = cur.blockNumber()

        vwf = self.canvas.vwf if self.canvas.vwf_mode else None
        limit = compute_reflow_limit(self._s, vwf)
        measure = compute_reflow_measure(self._s, vwf)

        for bn in range(sb, eb + 1):
            blk = self._overlay.document().findBlockByNumber(bn)
            txt = blk.text()
            if txt == BLANK_LINE_DISPLAY:
                continue
            stripped = txt.lstrip(" ")
            w = measure(stripped)
            if w >= limit:
                continue
            pad = round(((limit - w) / 2) / max(1, vwf.adv(" "))) if vwf else (limit - w) // 2
            c2 = QTextCursor(blk)
            c2.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            c2.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            c2.insertText(" " * pad + stripped)

    def action_select_all(self):
        if self.canvas.active_index >= 0:
            self._overlay.selectAll()

    def action_cut(self):
        if self.canvas.active_index >= 0:
            self._overlay.cut()

    def action_copy(self):
        if self.canvas.active_index >= 0:
            self._overlay.copy()

    def action_paste(self):
        if self.canvas.active_index >= 0:
            self._overlay.paste()

    def action_copy_active(self):
        if self.canvas.active_index >= 0:
            QGuiApplication.clipboard().setText(self._overlay.toPlainText())
