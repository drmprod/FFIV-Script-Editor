"""
ff4_editor/ui_find_dialog.py
Buscar y reemplazar en todas las secciones (o solo en la actual).

El diálogo no toca el modelo: emite `goto_requested` (doble clic en un resultado) y
`replace_requested` (lista de cambios) y la ventana principal los aplica con el deshacer.
Busca en el texto guardado en el JSON, así que los códigos (\\wait, \\char03...) también se encuentran.
"""

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .constants import TEXT_SECTIONS
from .i18n import tr
from .model.json_model import FF4Model

MAX_RESULTS = 2000


def replace_text(pattern: re.Pattern, replacement: str, text: str, regex: bool) -> str:
    """Replace every match. Literal mode inserts `replacement` as typed; regex mode allows \\1."""
    if regex:
        return pattern.sub(replacement, text)
    return pattern.sub(lambda _m: replacement, text)


class FindReplaceDialog(QDialog):
    goto_requested = Signal(str, object)  # key, idx
    replace_requested = Signal(list)  # [(key, idx, new_text)]

    def __init__(self, model: FF4Model, current_section: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Buscar y reemplazar"))
        self.resize(720, 480)
        self._model = model
        self._current = current_section
        self._hits: list[tuple[str, int | tuple[int, int], str]] = []
        self._pattern: re.Pattern | None = None

        root = QVBoxLayout(self)
        form = QFormLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setClearButtonEnabled(True)
        self.replace_edit = QLineEdit()
        form.addRow(tr("&Buscar:"), self.find_edit)
        form.addRow(tr("&Reemplazar por:"), self.replace_edit)
        root.addLayout(form)

        opts = QHBoxLayout()
        self.chk_case = QCheckBox(tr("Distinguir &mayúsculas"))
        self.chk_regex = QCheckBox(tr("Expresión re&gular"))
        self.chk_current = QCheckBox(tr("Solo la sección &actual"))
        self.chk_current.setEnabled(bool(current_section))
        for c in (self.chk_case, self.chk_regex, self.chk_current):
            opts.addWidget(c)
        opts.addStretch(1)
        root.addLayout(opts)

        self.results = QTreeWidget()
        self.results.setHeaderLabels([tr("Sección"), tr("Entrada"), tr("Texto")])
        self.results.setRootIsDecorated(False)
        self.results.setUniformRowHeights(True)
        self.results.setColumnWidth(0, 190)
        self.results.setColumnWidth(1, 80)
        self.results.itemActivated.connect(self._on_item_activated)
        root.addWidget(self.results, 1)

        row = QHBoxLayout()
        self.status = QLabel("")
        row.addWidget(self.status, 1)
        self.btn_find = QPushButton(tr("Buscar"))
        self.btn_find.setDefault(True)
        self.btn_replace = QPushButton(tr("Reemplazar todo"))
        self.btn_replace.setEnabled(False)
        self.btn_close = QPushButton(tr("Cerrar"))
        for b in (self.btn_find, self.btn_replace, self.btn_close):
            row.addWidget(b)
        root.addLayout(row)

        self.btn_find.clicked.connect(self.search)
        self.find_edit.returnPressed.connect(self.search)
        self.btn_replace.clicked.connect(self.replace_all)
        self.btn_close.clicked.connect(self.close)
        self.find_edit.setFocus()

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self) -> None:
        self.results.clear()
        self._hits = []
        self.btn_replace.setEnabled(False)
        try:
            self._pattern = self._model.make_matcher(
                self.find_edit.text(), self.chk_case.isChecked(), self.chk_regex.isChecked()
            )
        except ValueError as e:
            self.status.setText(str(e))
            return
        keys = [self._current] if (self.chk_current.isChecked() and self._current) else None
        hits = self._model.find_all(self._pattern, keys)
        self._hits = hits
        for key, idx, text in hits[:MAX_RESULTS]:
            n = f"#{idx[0]:03d}.{idx[1]:02d}" if isinstance(idx, tuple) else f"#{idx:03d}"
            item = QTreeWidgetItem([tr(TEXT_SECTIONS.get(key, key)), n, text.replace("\n", " ")[:200]])
            item.setData(0, Qt.ItemDataRole.UserRole, (key, idx))
            self.results.addTopLevelItem(item)
        if len(hits) > MAX_RESULTS:
            msg = tr("{n} entrada(s) con coincidencias (se muestran {shown})").format(
                n=len(hits), shown=MAX_RESULTS
            )
        else:
            msg = tr("{n} entrada(s) con coincidencias").format(n=len(hits))
        self.status.setText(msg)
        self.btn_replace.setEnabled(bool(hits))

    def _on_item_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        key, idx = item.data(0, Qt.ItemDataRole.UserRole)
        self.goto_requested.emit(key, idx)

    # ── Replace ───────────────────────────────────────────────────────────────

    def compute_changes(self) -> list[tuple[str, int | tuple[int, int], str]]:
        """New text for every hit whose text actually changes."""
        if self._pattern is None:
            return []
        repl = self.replace_edit.text()
        regex = self.chk_regex.isChecked()
        out: list[tuple[str, int | tuple[int, int], str]] = []
        for key, idx, text in self._hits:
            new = replace_text(self._pattern, repl, text, regex)
            if new != text:
                out.append((key, idx, new))
        return out

    def replace_all(self) -> None:
        try:
            changes = self.compute_changes()
        except (re.error, IndexError) as e:
            self.status.setText(tr("Reemplazo inválido: {err}").format(err=e))
            return
        if not changes:
            self.status.setText(tr("No hay nada que cambiar."))
            return
        self.replace_requested.emit(changes)
        self.status.setText(
            tr("{n} entrada(s) modificada(s). Se puede deshacer de una vez (Ctrl+Z).").format(n=len(changes))
        )
        self.search()
