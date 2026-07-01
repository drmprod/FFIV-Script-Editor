"""
ff4_editor/ui_view_dialog.py
"View Settings" dialog. Reads current settings from an EditorConfig instance,
returns a dict of changed values via accepted signal / return value.
"""

from PySide6.QtWidgets import (
    QDialog, QGridLayout, QLabel, QSpinBox, QCheckBox,
    QComboBox, QPushButton, QColorDialog, QMessageBox, QHBoxLayout, QWidget
)
from PySide6.QtGui import QFontDatabase, QFont, QFontMetrics, QColor
from PySide6.QtCore import Qt

from .config import EditorConfig


class ViewDialog(QDialog):
    """
    Modal settings dialog.
    Call exec(); if accepted, read .result_settings for changed values.
    """

    def __init__(self, config: EditorConfig, section: str | None = None, has_section_override: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("View Settings")
        self.setModal(True)

        self._config = config
        self._section = section
        self._has_override = has_section_override

        self.result_settings: dict = {}
        self.section_only: bool = False
        self.clear_section: bool = False

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
        self.spin_rows.setValue(self._config.card_rows)
        add_row("Card rows:", self.spin_rows, 0)

        # Card width
        self.spin_w = QSpinBox()
        self.spin_w.setRange(10, 60)

        # Estimate the current value in characters using the current font settings
        fm = QFontMetrics(QFont(self._config.card_font, self._config.font_size))
        char_w = fm.horizontalAdvance('A') or 1
        # Subtract 12px to account for the canvas padding before dividing
        current_chars = max(10, (self._config.card_w - 12) // char_w)

        self.spin_w.setValue(current_chars)
        add_row("Card width (chars):", self.spin_w, 1)

        # Show ruler
        self.chk_ruler = QCheckBox()
        self.chk_ruler.setChecked(self._config.show_ruler)
        add_row("Show ruler:", self.chk_ruler, 2)

        # Ruler position
        self.spin_ruler_chars = QSpinBox()
        self.spin_ruler_chars.setRange(1, 80)
        self.spin_ruler_chars.setValue(self._config.ruler_chars)
        add_row("Ruler at col:", self.spin_ruler_chars, 3)

        # Char limit
        self.spin_char_limit = QSpinBox()
        self.spin_char_limit.setRange(0, 80)
        self.spin_char_limit.setSpecialValueText('no limit')
        self.spin_char_limit.setValue(self._config.char_limit)
        add_row('Char limit:', self.spin_char_limit, 4)

        # Line limit
        self.spin_line_limit = QSpinBox()
        self.spin_line_limit.setRange(0, 64)
        self.spin_line_limit.setSpecialValueText('no limit')
        self.spin_line_limit.setValue(self._config.line_limit)
        add_row('Line limit:', self.spin_line_limit, 5)

        # Hard char limit
        self.chk_hard_limit = QCheckBox()
        self.chk_hard_limit.setChecked(self._config.hard_char_limit)
        self.chk_hard_limit.setToolTip(
            'Block keypresses that would exceed char limit.\n'
            'Disable when using auto line-break or hyphenation.')
        add_row('Hard char limit:', self.chk_hard_limit, 6)

        # Font family
        all_fonts = sorted(QFontDatabase.families(), key=str.lower)
        self.font_combo = QComboBox()
        self.font_combo.addItems(all_fonts)
        try:
            self.font_combo.setCurrentIndex(all_fonts.index(self._config.card_font))
        except ValueError:
            pass
        add_row("Font:", self.font_combo, 7)

        # Font size
        self.spin_fsize = QSpinBox()
        self.spin_fsize.setRange(6, 32)
        self.spin_fsize.setValue(self._config.font_size)
        add_row("Font size:", self.spin_fsize, 8)

        # Text colouring
        self.chk_colors = QCheckBox()
        self.chk_colors.setChecked(self._config.show_colors)
        add_row("Text colouring:", self.chk_colors, 9)

        # Warn / over thresholds
        self.spin_warn = QSpinBox()
        self.spin_warn.setRange(1, 80)
        self.spin_warn.setValue(self._config.warn_chars)
        add_row("Orange from col:", self.spin_warn, 10)

        self.spin_over = QSpinBox()
        self.spin_over.setRange(1, 80)
        self.spin_over.setValue(self._config.over_chars)
        add_row("Red from col:", self.spin_over, 11)

        # Auto wrap
        self.chk_wrap = QCheckBox()
        self.chk_wrap.setChecked(self._config.auto_wrap)
        add_row("Auto line-break:", self.chk_wrap, 12)

        # Spanish hyphenation
        self.chk_hyphenate = QCheckBox()
        self.chk_hyphenate.setChecked(self._config.auto_hyphenate)
        add_row("Spanish hyphenation:", self.chk_hyphenate, 13)

        # Page bands
        self.chk_bands = QCheckBox()
        self.chk_bands.setChecked(self._config.show_bands)
        add_row("Page bands:", self.chk_bands, 14)

        # Band colour A
        self._b0 = [self._config.band0_color]
        self.b0_btn = QPushButton()
        self.b0_btn.setFixedSize(40, 22)
        self._refresh_swatch(self.b0_btn, self._b0[0])
        self.b0_btn.clicked.connect(lambda: self._pick_color(self._b0, self.b0_btn))
        add_row("Band A:", self.b0_btn, 15)

        # Band colour B
        self._b1 = [self._config.band1_color]
        self.b1_btn = QPushButton()
        self.b1_btn.setFixedSize(40, 22)
        self._refresh_swatch(self.b1_btn, self._b1[0])
        self.b1_btn.clicked.connect(lambda: self._pick_color(self._b1, self.b1_btn))
        add_row("Band B:", self.b1_btn, 16)

        # Buttons row
        btn_row = QWidget()
        btn_l = QHBoxLayout(btn_row)
        btn_l.setContentsMargins(0, 0, 0, 0)
        btn_l.setSpacing(6)

        if self._section:
            sec_label = self._section
            self.sec_btn = QPushButton(f"Apply for '{sec_label}' only")
            self.sec_btn.setObjectName('apply_btn')
            self.sec_btn.setToolTip(
                "Save all current settings for this section only.\n"
                "Other sections keep the global values.")
            self.sec_btn.clicked.connect(self._on_apply_section)
            btn_l.addWidget(self.sec_btn)

            if self._has_override:
                self.clr_btn = QPushButton(f"Clear '{sec_label}' override")
                self.clr_btn.setObjectName('open_btn')
                self.clr_btn.setToolTip("Remove per-section settings, revert to global.")
                self.clr_btn.clicked.connect(self._on_clear_section)
                btn_l.addWidget(self.clr_btn)

        btn_l.addStretch(1)
        apply_btn = QPushButton("Apply globally")
        apply_btn.setObjectName('apply_btn')
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply_global)
        btn_l.addWidget(apply_btn)
        grid.addWidget(btn_row, 17, 0, 1, 2)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _refresh_swatch(btn, color_str):
        btn.setStyleSheet(f'background: {color_str}; border: 1px solid #3a3060;')

    def _pick_color(self, holder, btn):
        c = QColorDialog.getColor(QColor(holder[0]), self)
        if c.isValid():
            holder[0] = c.name()
            self._refresh_swatch(btn, holder[0])

    def _on_apply_global(self):
        """Ask confirmation then apply globally."""
        msg = 'Apply these settings globally?'
        if self._section:
            msg += f'\n\nThis will override any saved settings for \'{self._section}\'.'
        r = QMessageBox.question(self, 'Apply globally', msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if r == QMessageBox.StandardButton.Yes:
            self._on_apply()

    def _on_apply_section(self):
        """Apply only section-overridable settings for current section."""
        self.section_only = True
        self._on_apply()

    def _on_clear_section(self):
        """Signal main window to clear the section override."""
        self.clear_section = True
        self.result_settings = {}
        self.accept()

    def _on_apply(self):
        c = self._config
        r = {}

        nf = self.font_combo.currentText()
        ns = self.spin_fsize.value()
        if nf != c.card_font: r['card_font']  = nf
        if ns != c.font_size: r['font_size']  = ns

        # Calculate new card width in pixels based on character width
        fm = QFontMetrics(QFont(nf, ns))
        char_w = fm.horizontalAdvance('A')
        nw = (self.spin_w.value() * char_w) + 12 # chars * width + padding

        nr = self.spin_rows.value()
        if nr != c.card_rows: r['card_rows'] = nr
        if nw != c.card_w:    r['card_w']    = nw

        for attr, widget in [
            ('show_ruler',     self.chk_ruler),
            ('show_colors',    self.chk_colors),
            ('auto_wrap',      self.chk_wrap),
            ('auto_hyphenate', self.chk_hyphenate),
            ('show_bands',     self.chk_bands),
            ('hard_char_limit',self.chk_hard_limit),
        ]:
            if widget.isChecked() != getattr(c, attr):
                r[attr] = widget.isChecked()

        for attr, val in [
            ('warn_chars',  self.spin_warn.value()),
            ('over_chars',  self.spin_over.value()),
            ('char_limit',  self.spin_char_limit.value()),
            ('line_limit',  self.spin_line_limit.value()),
            ('ruler_chars', self.spin_ruler_chars.value()),
        ]:
            if val != getattr(c, attr): r[attr] = val

        if self._b0[0] != c.band0_color: r['band0_color'] = self._b0[0]
        if self._b1[0] != c.band1_color: r['band1_color'] = self._b1[0]

        self.result_settings = r
        self.accept()
