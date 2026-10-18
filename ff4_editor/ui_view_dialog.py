"""
ff4_editor/ui_view_dialog.py
Preferences dialog.  Reads the current settings from an EditorConfig and, when accepted,
exposes the changed values in `result_settings`.

Scope (radio buttons): all sections, or only the current one (stored as a section override).
"""

from typing import Any

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import i18n
from .config import EditorConfig
from .i18n import tr
from .typed_config import ConfigKey


class ViewDialog(QDialog):
    """
    Modal preferences dialog.
    Call exec(); if accepted, read .result_settings (changed values), .section_only and
    .clear_section.
    """

    def __init__(
        self,
        config: EditorConfig,
        section: str | None = None,
        has_section_override: bool = False,
        parent=None,
        section_label: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("Preferencias"))
        self.setModal(True)

        self._config = config
        self._section = section
        self._section_label = section_label or section
        self._has_override = has_section_override

        self.result_settings: dict = {}
        self.section_only: bool = False
        self.clear_section: bool = False

        self._build()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        c = self._config
        root = QVBoxLayout(self)

        # Cards
        box = QGroupBox(tr("Tarjetas"))
        f = QFormLayout(box)
        self.spin_rows = QSpinBox()
        self.spin_rows.setRange(2, 64)
        self.spin_rows.setValue(c.card_rows)
        f.addRow(tr("&Filas visibles:"), self.spin_rows)

        self.spin_w = QSpinBox()
        self.spin_w.setRange(10, 60)
        self.spin_w.setSuffix(tr(" caracteres"))
        fm = QFontMetrics(QFont(c.card_font, c.font_size))
        char_w = fm.horizontalAdvance("A") or 1
        self.spin_w.setValue(max(10, (c.card_w - 12) // char_w))  # 12 px = canvas padding
        f.addRow(tr("&Ancho (modo monoespaciado):"), self.spin_w)

        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(c.card_font))
        f.addRow(tr("F&uente:"), self.font_combo)

        self.spin_fsize = QSpinBox()
        self.spin_fsize.setRange(6, 32)
        self.spin_fsize.setSuffix(tr(" pt"))
        self.spin_fsize.setValue(c.font_size)
        f.addRow(tr("&Tamaño:"), self.spin_fsize)
        root.addWidget(box)

        # Text limits
        box = QGroupBox(tr("Texto (modo monoespaciado)"))
        f = QFormLayout(box)
        self.chk_wrap = QCheckBox(tr("Cortar líneas automáticamente al llegar al límite"))
        self.chk_wrap.setChecked(c.auto_wrap)
        f.addRow(self.chk_wrap)

        self.chk_ruler = QCheckBox(tr("Mostrar regla"))
        self.chk_ruler.setChecked(c.show_ruler)
        f.addRow(self.chk_ruler)
        self.spin_ruler_chars = QSpinBox()
        self.spin_ruler_chars.setRange(1, 80)
        self.spin_ruler_chars.setValue(c.ruler_chars)
        f.addRow(tr("Regla en la &columna:"), self.spin_ruler_chars)
        self.chk_ruler.toggled.connect(self.spin_ruler_chars.setEnabled)
        self.spin_ruler_chars.setEnabled(c.show_ruler)

        self.spin_char_limit = QSpinBox()
        self.spin_char_limit.setRange(0, 80)
        self.spin_char_limit.setSpecialValueText(tr("sin límite"))
        self.spin_char_limit.setValue(c.char_limit)
        f.addRow(tr("&Límite de caracteres por línea:"), self.spin_char_limit)

        self.spin_line_limit = QSpinBox()
        self.spin_line_limit.setRange(0, 64)
        self.spin_line_limit.setSpecialValueText(tr("sin límite"))
        self.spin_line_limit.setValue(c.line_limit)
        f.addRow(tr("Límite de &líneas:"), self.spin_line_limit)

        self.spin_warn = QSpinBox()
        self.spin_warn.setRange(1, 80)
        self.spin_warn.setValue(c.warn_chars)
        f.addRow(tr("Aviso (naranja) desde la columna:"), self.spin_warn)
        self.spin_over = QSpinBox()
        self.spin_over.setRange(1, 80)
        self.spin_over.setValue(c.over_chars)
        f.addRow(tr("Exceso (rojo) desde la columna:"), self.spin_over)
        root.addWidget(box)

        # Game font
        box = QGroupBox(tr("Fuente del juego (ancho variable)"))
        f = QFormLayout(box)
        self.chk_vwf = QCheckBox(tr("Dibujar el diálogo con la fuente del juego (font.png)"))
        self.chk_vwf.setToolTip(
            tr(
                "Mide el texto en píxeles del juego, igual que field/vwf.asm.\nLas demás secciones no se ven afectadas."
            )
        )
        self.chk_vwf.setChecked(c.vwf_enabled)
        f.addRow(self.chk_vwf)

        self.spin_vwf_scale = QSpinBox()
        self.spin_vwf_scale.setRange(1, 4)
        self.spin_vwf_scale.setPrefix("×")
        self.spin_vwf_scale.setValue(c.vwf_scale)
        f.addRow(tr("&Zoom:"), self.spin_vwf_scale)

        self.spin_vwf_limit = QSpinBox()
        self.spin_vwf_limit.setRange(32, 448)
        self.spin_vwf_limit.setSuffix(tr(" px"))
        self.spin_vwf_limit.setValue(c.vwf_limit_px)
        self.spin_vwf_limit.setToolTip(tr("Ancho de línea del diálogo en píxeles del juego (28 tiles = 224)"))
        f.addRow(tr("&Ancho de línea:"), self.spin_vwf_limit)

        png_row = QWidget()
        pl = QHBoxLayout(png_row)
        pl.setContentsMargins(0, 0, 0, 0)
        self.edit_png = QLineEdit(c.vwf_font_png)
        self.edit_png.setPlaceholderText(tr("(automático: font.png junto al JSON)"))
        browse = QPushButton(tr("Examinar…"))
        browse.clicked.connect(self._browse_png)
        pl.addWidget(self.edit_png, 1)
        pl.addWidget(browse)
        f.addRow(tr("Archivo &font.png:"), png_row)

        for w in (self.spin_vwf_scale, self.spin_vwf_limit, png_row):
            self.chk_vwf.toggled.connect(w.setEnabled)
            w.setEnabled(c.vwf_enabled)
        root.addWidget(box)

        # Language
        self.combo_lang = QComboBox()
        self.combo_lang.addItem(tr("Automático (sistema)"), "auto")
        for code, name in i18n.LANGUAGES.items():
            self.combo_lang.addItem(name, code)
        cur_lang = str(self._settings().value("ui/language", "auto"))
        idx = self.combo_lang.findData(cur_lang)
        self.combo_lang.setCurrentIndex(max(0, idx))
        lang_box = QWidget()
        ll = QVBoxLayout(lang_box)
        ll.setContentsMargins(0, 0, 0, 0)
        lang_row = QFormLayout()
        lang_row.addRow(tr("Idioma de la interfaz:"), self.combo_lang)
        ll.addLayout(lang_row)
        note = QLabel(tr("El cambio de idioma se aplica al reiniciar el editor."))
        note.setWordWrap(True)
        ll.addWidget(note)
        root.addWidget(lang_box)

        # Scope
        if self._section:
            box = QGroupBox(tr("Aplicar a"))
            sl = QVBoxLayout(box)
            self.rb_all = QRadioButton(tr("Todas las secciones"))
            self.rb_section = QRadioButton(
                tr("Solo «{section}»").format(section=tr(self._section_label or ""))
            )
            self.rb_all.setChecked(True)
            sl.addWidget(self.rb_all)
            sl.addWidget(self.rb_section)
            if self._has_override:
                self.clr_btn = QPushButton(tr("Quitar los ajustes propios de esta sección"))
                self.clr_btn.clicked.connect(self._on_clear_section)
                sl.addWidget(self.clr_btn)
            root.addWidget(box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ── Actions ───────────────────────────────────────────────────────────────

    @staticmethod
    def _settings() -> QSettings:
        return QSettings("ff4_editor", "ff4_editor_vwf")

    def _browse_png(self):
        p, _ = QFileDialog.getOpenFileName(
            self, tr("Elegir font.png"), self.edit_png.text(), tr("Imágenes PNG (*.png)")
        )
        if p:
            self.edit_png.setText(p)

    def _on_clear_section(self):
        """Tell the main window to drop this section's override."""
        self.clear_section = True
        self.result_settings = {}
        self.accept()

    def _on_apply(self):
        c = self._config
        r: dict[str, Any] = {}
        self.section_only = bool(self._section) and self.rb_section.isChecked()

        nf = self.font_combo.currentFont().family()
        ns = self.spin_fsize.value()
        if nf != c.card_font:
            r[ConfigKey.CARD_FONT.value] = nf
        if ns != c.font_size:
            r[ConfigKey.FONT_SIZE.value] = ns

        fm = QFontMetrics(QFont(nf, ns))
        nw = self.spin_w.value() * fm.horizontalAdvance("A") + 12  # chars * width + padding
        nr = self.spin_rows.value()
        if nr != c.card_rows:
            r[ConfigKey.CARD_ROWS.value] = nr
        if nw != c.card_w and self.spin_w.value() != self._initial_chars():
            r[ConfigKey.CARD_W.value] = nw

        for attr, widget in [
            ("show_ruler", self.chk_ruler),
            ("auto_wrap", self.chk_wrap),
            ("vwf_enabled", self.chk_vwf),
        ]:
            if widget.isChecked() != getattr(c, attr):
                r[attr] = widget.isChecked()

        values = {
            "warn_chars": self.spin_warn.value(),
            "over_chars": self.spin_over.value(),
            "char_limit": self.spin_char_limit.value(),
            "line_limit": self.spin_line_limit.value(),
            "ruler_chars": self.spin_ruler_chars.value(),
            "vwf_scale": self.spin_vwf_scale.value(),
            "vwf_limit_px": self.spin_vwf_limit.value(),
            "vwf_font_png": self.edit_png.text().strip(),
        }
        r.update({attr: val for attr, val in values.items() if val != getattr(c, attr)})

        self._settings().setValue("ui/language", self.combo_lang.currentData())

        self.result_settings = r
        self.accept()

    def _initial_chars(self) -> int:
        c = self._config
        char_w = QFontMetrics(QFont(c.card_font, c.font_size)).horizontalAdvance("A") or 1
        return max(10, (c.card_w - 12) // char_w)
