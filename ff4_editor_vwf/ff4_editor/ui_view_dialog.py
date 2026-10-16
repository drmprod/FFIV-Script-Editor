"""
ff4_editor/ui_view_dialog.py
"View Settings" dialog. Reads current settings from an EditorConfig instance,
returns a dict of changed values via accepted signal / return value.
"""

from PySide6.QtWidgets import (
    QDialog, QGridLayout, QLabel, QSpinBox, QCheckBox,
    QComboBox, QPushButton, QMessageBox, QHBoxLayout, QWidget,
    QLineEdit, QFileDialog
)
from PySide6.QtGui import QFontDatabase, QFont, QFontMetrics
from PySide6.QtCore import Qt

from .config import EditorConfig
from .typed_config import ConfigKey


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
            'Disable when using auto line-break.')
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

        # Warn / over thresholds
        self.spin_warn = QSpinBox()
        self.spin_warn.setRange(1, 80)
        self.spin_warn.setValue(self._config.warn_chars)
        add_row("Orange from col:", self.spin_warn, 9)

        self.spin_over = QSpinBox()
        self.spin_over.setRange(1, 80)
        self.spin_over.setValue(self._config.over_chars)
        add_row("Red from col:", self.spin_over, 10)

        # Auto wrap
        self.chk_wrap = QCheckBox()
        self.chk_wrap.setChecked(self._config.auto_wrap)
        add_row("Auto line-break:", self.chk_wrap, 11)

        # ── Variable-width font (game accurate) ──────────────────────────────
        self.chk_vwf = QCheckBox()
        self.chk_vwf.setChecked(self._config.vwf_enabled)
        self.chk_vwf.setToolTip(
            'Draw field dialogue with the game font (font.png) and measure it in\n'
            'game pixels, exactly like field/vwf.asm. Other sections are unaffected.')
        add_row('Game font (VWF):', self.chk_vwf, 12)

        self.spin_vwf_scale = QSpinBox()
        self.spin_vwf_scale.setRange(1, 4)
        self.spin_vwf_scale.setValue(self._config.vwf_scale)
        add_row('VWF zoom:', self.spin_vwf_scale, 13)

        self.spin_vwf_limit = QSpinBox()
        self.spin_vwf_limit.setRange(32, 448)
        self.spin_vwf_limit.setSuffix(' px')
        self.spin_vwf_limit.setValue(self._config.vwf_limit_px)
        self.spin_vwf_limit.setToolTip('Dialogue line width in game pixels (28 tiles = 224)')
        add_row('VWF line width:', self.spin_vwf_limit, 14)

        png_row = QWidget()
        png_l = QHBoxLayout(png_row)
        png_l.setContentsMargins(0, 0, 0, 0)
        self.edit_png = QLineEdit(self._config.vwf_font_png)
        self.edit_png.setPlaceholderText('(auto: font.png next to the JSON)')
        browse = QPushButton('…')
        browse.clicked.connect(self._browse_png)
        png_l.addWidget(self.edit_png, 1)
        png_l.addWidget(browse)
        add_row('Font PNG:', png_row, 15)

        # Buttons row
        btn_row = QWidget()
        btn_l = QHBoxLayout(btn_row)
        btn_l.setContentsMargins(0, 0, 0, 0)
        btn_l.setSpacing(6)

        if self._section:
            sec_label = self._section
            self.sec_btn = QPushButton(f"Apply for '{sec_label}' only")
            self.sec_btn.setToolTip(
                "Save all current settings for this section only.\n"
                "Other sections keep the global values.")
            self.sec_btn.clicked.connect(self._on_apply_section)
            btn_l.addWidget(self.sec_btn)

            if self._has_override:
                self.clr_btn = QPushButton(f"Clear '{sec_label}' override")
                self.clr_btn.setToolTip("Remove per-section settings, revert to global.")
                self.clr_btn.clicked.connect(self._on_clear_section)
                btn_l.addWidget(self.clr_btn)

        btn_l.addStretch(1)
        apply_btn = QPushButton("Apply globally")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._on_apply_global)
        btn_l.addWidget(apply_btn)

        # Finally, add the fully constructed button row to the grid
        grid.addWidget(btn_row, 17, 0, 1, 2)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _browse_png(self):
        p, _ = QFileDialog.getOpenFileName(self, 'Select font.png', self.edit_png.text(),
                                           'PNG images (*.png)')
        if p:
            self.edit_png.setText(p)

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
        if nf != c.card_font: r[ConfigKey.CARD_FONT.value]  = nf
        if ns != c.font_size: r[ConfigKey.FONT_SIZE.value]  = ns

        # Calculate new card width in pixels based on character width
        fm = QFontMetrics(QFont(nf, ns))
        char_w = fm.horizontalAdvance('A')
        nw = (self.spin_w.value() * char_w) + 12 # chars * width + padding

        nr = self.spin_rows.value()
        if nr != c.card_rows: r[ConfigKey.CARD_ROWS.value] = nr
        if nw != c.card_w:    r[ConfigKey.CARD_W.value]    = nw

        for attr, widget in [
            ('show_ruler',     self.chk_ruler),
            ('auto_wrap',      self.chk_wrap),
            ('hard_char_limit',self.chk_hard_limit),
            ('vwf_enabled',    self.chk_vwf),
        ]:
            if widget.isChecked() != getattr(c, attr):
                r[attr] = widget.isChecked()

        for attr, val in [
            ('warn_chars',  self.spin_warn.value()),
            ('over_chars',  self.spin_over.value()),
            ('char_limit',  self.spin_char_limit.value()),
            ('line_limit',  self.spin_line_limit.value()),
            ('ruler_chars', self.spin_ruler_chars.value()),
            ('vwf_scale',   self.spin_vwf_scale.value()),
            ('vwf_limit_px',self.spin_vwf_limit.value()),
            ('vwf_font_png',self.edit_png.text().strip()),
        ]:
            if val != getattr(c, attr): r[attr] = val

        self.result_settings = r
        self.accept()
