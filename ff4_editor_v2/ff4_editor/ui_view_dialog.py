"""
ff4_editor/ui_view_dialog.py
"View Settings" dialog. Reads current settings from an FF4Editor instance,
returns a dict of changed values via accepted signal / return value.
"""

from PySide6.QtWidgets import (
    QDialog, QGridLayout, QLabel, QSpinBox, QCheckBox,
    QComboBox, QPushButton, QColorDialog,
)
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import Qt
from PySide6.QtGui  import QColor


class ViewDialog(QDialog):
    """
    Modal settings dialog.
    Call exec(); if accepted, read .result_settings for changed values.
    """

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("View Settings")
        self.setModal(True)
        self._s = settings
        self.result_settings: dict = {}
        self._build()

    def _build(self):
        grid = QGridLayout(self)
        grid.setSpacing(10)
        grid.setContentsMargins(16, 16, 16, 16)

        def add_row(label, widget, r):
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, r, 0)
            grid.addWidget(widget, r, 1)

        # Card rows
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(2, 64)
        self.spin_rows.setValue(self._s.card_rows)
        add_row("Card rows:", self.spin_rows, 0)

        # Card width
        self.spin_w = QSpinBox()
        self.spin_w.setRange(260, 800)
        self.spin_w.setSingleStep(10)
        self.spin_w.setValue(self._s.card_w)
        add_row("Card width (px):", self.spin_w, 1)

        # Show ruler
        self.chk_ruler = QCheckBox()
        self.chk_ruler.setChecked(self._s.show_ruler)
        add_row("Show ruler:", self.chk_ruler, 2)

        # Ruler position
        self.spin_ruler_chars = QSpinBox()
        self.spin_ruler_chars.setRange(1, 80)
        self.spin_ruler_chars.setValue(getattr(self._s, 'ruler_chars', 28))
        add_row("Ruler at col:", self.spin_ruler_chars, 3)

        # Font family
        all_fonts = sorted(QFontDatabase.families(), key=str.lower)
        self.font_combo = QComboBox()
        self.font_combo.addItems(all_fonts)
        try:
            self.font_combo.setCurrentIndex(all_fonts.index(self._s.card_font))
        except ValueError:
            pass
        add_row("Font:", self.font_combo, 3)

        # Font size
        self.spin_fsize = QSpinBox()
        self.spin_fsize.setRange(6, 32)
        self.spin_fsize.setValue(self._s.font_size)
        add_row("Font size:", self.spin_fsize, 4)

        # Text colouring
        self.chk_colors = QCheckBox()
        self.chk_colors.setChecked(self._s.show_colors)
        add_row("Text colouring:", self.chk_colors, 5)

        # Warn / over thresholds
        self.spin_warn = QSpinBox()
        self.spin_warn.setRange(1, 80)
        self.spin_warn.setValue(self._s.warn_chars)
        add_row("Orange from col:", self.spin_warn, 6)

        self.spin_over = QSpinBox()
        self.spin_over.setRange(1, 80)
        self.spin_over.setValue(self._s.over_chars)
        add_row("Red from col:", self.spin_over, 7)

        # Auto wrap
        self.chk_wrap = QCheckBox()
        self.chk_wrap.setChecked(self._s.auto_wrap)
        add_row("Auto line-break:", self.chk_wrap, 8)

        # Page bands
        self.chk_bands = QCheckBox()
        self.chk_bands.setChecked(self._s.show_bands)
        add_row("Page bands:", self.chk_bands, 9)

        # Band colour A
        self._b0 = [self._s.band0_color]
        self.b0_btn = QPushButton()
        self.b0_btn.setFixedSize(40, 22)
        self._refresh_swatch(self.b0_btn, self._b0[0])
        self.b0_btn.clicked.connect(lambda: self._pick_color(self._b0, self.b0_btn))
        add_row("Band A:", self.b0_btn, 10)

        # Band colour B
        self._b1 = [self._s.band1_color]
        self.b1_btn = QPushButton()
        self.b1_btn.setFixedSize(40, 22)
        self._refresh_swatch(self.b1_btn, self._b1[0])
        self.b1_btn.clicked.connect(lambda: self._pick_color(self._b1, self.b1_btn))
        add_row("Band B:", self.b1_btn, 11)

        # Apply button
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName('apply_btn')
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply)
        grid.addWidget(apply_btn, 13, 1, Qt.AlignmentFlag.AlignRight)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _refresh_swatch(btn, color_str):
        btn.setStyleSheet(f'background: {color_str}; border: 1px solid #3a3060;')

    def _pick_color(self, holder, btn):
        c = QColorDialog.getColor(QColor(holder[0]), self)
        if c.isValid():
            holder[0] = c.name()
            self._refresh_swatch(btn, holder[0])

    def _on_apply(self):
        s = self._s
        r = {}

        nf = self.font_combo.currentText()
        ns = self.spin_fsize.value()
        if nf != s.card_font: r['card_font']  = nf
        if ns != s.font_size: r['font_size']  = ns

        nr = self.spin_rows.value()
        nw = max(260, self.spin_w.value())
        if nr != s.card_rows: r['card_rows'] = nr
        if nw != s.card_w:    r['card_w']    = nw

        for attr, widget in [
            ('show_ruler',  self.chk_ruler),
            ('show_colors', self.chk_colors),
            ('auto_wrap',   self.chk_wrap),
            ('show_bands',  self.chk_bands),
        ]:
            if widget.isChecked() != getattr(s, attr):
                r[attr] = widget.isChecked()

        for attr, val in [
            ('warn_chars', self.spin_warn.value()),
            ('over_chars', self.spin_over.value()),
        ]:
            if val != getattr(s, attr):
                r[attr] = val

        if self._b0[0] != s.band0_color: r['band0_color'] = self._b0[0]
        if self._b1[0] != s.band1_color: r['band1_color'] = self._b1[0]
        rc = self.spin_ruler_chars.value()
        if rc != getattr(s, 'ruler_chars', 28): r['ruler_chars'] = rc

        self.result_settings = r
        self.accept()
