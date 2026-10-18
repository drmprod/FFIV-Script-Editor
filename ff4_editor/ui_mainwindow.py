"""
ff4_editor/ui_mainwindow.py
FF4Editor — QMainWindow with the usual desktop layout: menu bar, tool bar, section list,
card canvas and a status bar.  Follows the platform theme and standard shortcuts.
Owns: FF4Model, CardCanvas, settings, config I/O.
Delegates: all painting to CardCanvas, all data to FF4Model.
"""

import os

from PySide6.QtCore import QProcess, QSettings, Qt, QTimer
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollBar,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .build_tools import MESEN_NAMES, find_mesen, find_rom, make_target, rom_dir
from .config import EditorConfig
from .config_manager import create_config_manager
from .constants import TEXT_SECTIONS
from .errors import FF4Error
from .game_font import GameFontError, build_game_font, find_font_png, release_game_font
from .i18n import tr
from .model import FF4Model
from .model.commands import EditEntryCommand
from .theme import css_color, error_color, warning_color
from .ui_actions import ActionsMixin
from .ui_build_dialog import BuildDialog
from .ui_find_dialog import FindReplaceDialog
from .ui_sections import SectionsMixin
from .ui_view_dialog import ViewDialog
from .ui_windowstate import APP_TITLE, WindowStateMixin
from .util.vwf_font import FAMILY
from .widgets import CardCanvas


class FF4Editor(ActionsMixin, WindowStateMixin, SectionsMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1200, 780)

        # ── Settings Configuration Object ──────────
        self.config = EditorConfig()
        self.config_mgr = create_config_manager(self.config)

        self.verbose = False
        self._cur_map_idx = 0
        self._pushing = False
        self._vwf = None
        self._vwf_font_id: int | None = None
        self._find_dlg: FindReplaceDialog | None = None
        self._cur_section = None
        self._qsettings = QSettings("ff4_editor", "ff4_editor_vwf")

        self.config_mgr.load()
        self.config.apply_font()

        # ── Model ─────────────────────────────────────────────────────────────
        self._model = FF4Model(self)
        self._model.loaded.connect(self._on_model_loaded)
        self._model.section_changed.connect(self._on_section_changed)
        self._model.entry_changed.connect(self._on_entry_changed)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._on_undo_index_changed)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(200)
        self._filter_timer.timeout.connect(self._apply_filter)

        self._build_ui()
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._set_file_actions_enabled(False)
        self._restore_window_state()
        self.statusBar().showMessage(tr("Abrí un archivo ff4-xx-data.json (Ctrl+O)."))
        self._show_config_warnings()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)
        self._splitter = splitter

        # Section list
        self.section_list = QListWidget()
        self.section_list.setMinimumWidth(170)
        self.section_list.setAccessibleName("Secciones")
        self.section_list.currentItemChanged.connect(self._on_section_selected)
        splitter.addWidget(self.section_list)

        # Right pane: [map selector] + canvas
        right = QWidget()
        rr = QVBoxLayout(right)
        rr.setContentsMargins(0, 0, 0, 0)
        rr.setSpacing(0)

        self._map_row = QWidget()
        mrl = QHBoxLayout(self._map_row)
        mrl.setContentsMargins(8, 4, 8, 4)
        mrl.setSpacing(6)
        map_lbl = QLabel(tr("&Mapa:"))
        self._map_combo = QComboBox()
        self._map_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        map_lbl.setBuddy(self._map_combo)
        self._map_combo.currentIndexChanged.connect(self._on_map_combo_changed)
        mrl.addWidget(map_lbl)
        mrl.addWidget(self._map_combo, 1)
        self._map_row.setVisible(False)
        rr.addWidget(self._map_row)

        crow = QWidget()
        crl = QHBoxLayout(crow)
        crl.setContentsMargins(0, 0, 0, 0)
        crl.setSpacing(0)
        self._canvas = CardCanvas(self.config, self)
        self._canvas.card_committed.connect(self._on_card_committed)
        self._canvas.active_changed.connect(self._update_edit_actions)
        crl.addWidget(self._canvas, 1)
        vbar = QScrollBar(Qt.Orientation.Vertical)
        crl.addWidget(vbar)
        self._canvas.set_scrollbar(vbar)
        rr.addWidget(crow, 1)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 970])

        # Status bar: message on the left; entry count and byte budget on the right
        sb = self.statusBar()
        self.count_lbl = QLabel("")
        self.budget_lbl = QLabel("")
        self.budget_bar = QProgressBar()
        self.budget_bar.setRange(0, 1000)
        self.budget_bar.setTextVisible(False)
        self.budget_bar.setFixedWidth(130)
        self.budget_pct = QLabel("")
        self.budget_pct.setMinimumWidth(36)
        for w in (self.count_lbl, self.budget_lbl, self.budget_bar, self.budget_pct):
            sb.addPermanentWidget(w)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _maybe_save(self) -> bool:
        """Ask what to do with unsaved changes. True = it is safe to continue."""
        if not self._model.dirty_keys:
            return True
        r = QMessageBox.warning(
            self,
            "Cambios sin guardar",
            f"Hay {len(self._model.dirty_keys)} sección(es) modificada(s).\n¿Querés guardar los cambios?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if r == QMessageBox.StandardButton.Cancel:
            return False
        if r == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self._model.dirty_keys  # a failed save keeps the window open
        return True

    def _on_open(self, *_args):
        fp = self._model.filepath
        start = os.path.dirname(fp) if fp else ""
        p, _ = QFileDialog.getOpenFileName(
            self, tr("Abrir JSON de FF4"), start, tr("Archivos JSON (*.json);;Todos los archivos (*)")
        )
        if p:
            self._open_path(p)

    def _open_path(self, path: str):
        if not self._maybe_save():
            return
        self.open_file(path)

    def _on_run_mesen(self, *_):
        fp = self._model.filepath
        if not fp:
            return
        rom = find_rom(fp)
        if not rom:
            d = rom_dir(fp)
            QMessageBox.warning(
                self,
                "Mesen",
                f"No existe {make_target(self._model.filepath)}.sfc/.spc/.smc en:\n{d}\n\nCompilá primero (Compilar → Compilar).",
            )
            return
        exe = find_mesen()
        if not exe:
            QMessageBox.warning(
                self,
                "Mesen",
                tr("No encuentro Mesen en el PATH (probé: {names}).").format(names=", ".join(MESEN_NAMES)),
            )
            return
        ok = QProcess.startDetached(exe, [rom], os.path.dirname(rom))
        self.statusBar().showMessage(
            tr("Mesen: {rom}").format(rom=rom) if ok else tr("No se pudo lanzar Mesen")
        )

    def _on_build(self, *_):
        fp = self._model.filepath
        if not fp:
            return
        if self._model.dirty_keys:
            r = QMessageBox.question(
                self,
                tr("Compilar"),
                tr("Hay cambios sin guardar. ¿Guardar antes de compilar?"),
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if r == QMessageBox.StandardButton.Cancel:
                return
            if r == QMessageBox.StandardButton.Save:
                self._on_save()
        wd = os.path.dirname(os.path.abspath(fp))
        old = getattr(self, "_build_dlg", None)
        if old is not None and old.isVisible():
            old.raise_()
            old.activateWindow()
            return
        self._build_dlg = BuildDialog(wd, "make", [make_target(self._model.filepath)], self)
        self._build_dlg.show()
        self._build_dlg.start()

    def _on_about(self):
        QMessageBox.about(
            self,
            tr("Acerca de {title}").format(title=APP_TITLE),
            tr(
                "<b>{title}</b><br>Editor de texto para la traducción de Final Fantasy IV "
                "(SNES), con la fuente de ancho variable del juego.<br><br>"
                "Basado en el desensamblado everything8215/ff4."
            ).format(title=APP_TITLE),
        )

    def open_file(self, path: str):
        self.statusBar().showMessage(tr("Abriendo {path}…").format(path=path))
        try:
            self._model.load(path)
        except FF4Error as e:
            self.statusBar().showMessage(tr("No se pudo abrir el archivo."))
            QMessageBox.critical(
                self, tr("Error al abrir"), tr("No se pudo abrir el archivo:\n{err}").format(err=e)
            )

    def _on_model_loaded(self):
        path = self._model.filepath
        self.config_mgr.load(path)
        self._show_config_warnings()
        self.config.apply_font()
        self._setup_vwf()
        self._canvas.byte_cost = lambda section, text: self._model.entry_byte_cost(text, section)
        self.undo_stack.clear()
        self._populate_sidebar()
        self._set_file_actions_enabled(True)
        self._update_edit_actions()
        if path:
            self._add_recent(path)
        self._update_title()
        self.statusBar().showMessage(tr("Abierto: {path}").format(path=path), 5000)
        if self.verbose:
            print(f"[load] {path}  encodings: {self._model.encoding_names}")
        if self.section_list.count():
            self.section_list.setCurrentRow(0)

    # ── Game font (VWF) ───────────────────────────────────────────────────────

    def _setup_vwf(self):
        """Build the game font from font.png + charTable and hand it to the canvas."""
        release_game_font(self._vwf_font_id)
        self._vwf_font_id = None
        self._vwf = None
        png = find_font_png(self.config.vwf_font_png, self._model.filepath)
        if not png:
            self._canvas.set_vwf(None, None)
            self.statusBar().showMessage(
                tr(
                    "No se encontró font.png: fuente del juego desactivada (Edición → Preferencias → Fuente PNG)"
                )
            )
            return
        try:
            self._vwf, self._vwf_font_id = build_game_font(
                png,
                self._model.char_table_text,
                self.config.vwf_gap,
                self.config.vwf_space,
                self.config.vwf_line_pitch,
            )
        except GameFontError as e:
            self._canvas.set_vwf(None, None)
            self.statusBar().showMessage(tr("Fuente del juego desactivada: {err}").format(err=e))
            return
        self._canvas.set_vwf(self._vwf, FAMILY)

    # ── Card committed callback ───────────────────────────────────────────────

    def _on_card_committed(self, section, idx, json_text):
        old_text = self._model.get_entry(section, idx)

        if old_text == json_text:
            return  # Ignore focus loss without changes

        cmd = EditEntryCommand(self._model, section, idx, old_text, json_text)
        # The card already shows the new text: don't rebuild the section (that would
        # close the editor and jump to the top after every keystroke).
        self._pushing = True
        try:
            self.undo_stack.push(cmd)
        finally:
            self._pushing = False

    def _on_section_changed(self, key: str):
        self._refresh_budget(key)
        self._refresh_sidebar_item(key)
        self.setWindowModified(bool(self._model.dirty_keys))
        if self._model.dirty_keys:
            self.statusBar().showMessage(
                tr("{n} sección(es) con cambios sin guardar").format(n=len(self._model.dirty_keys)), 4000
            )

    def _on_entry_changed(self, key: str, idx):
        """Undo/redo wrote an entry: show it (switching section/map if needed).
        Edits coming from the editor itself are already on screen."""
        if self._pushing:
            return
        if key != self._cur_section:
            self._select_section(key)
        elif (
            key == "mapDialog"
            and isinstance(idx, tuple)
            and not self.filter_edit.text()
            and idx[0] != self._cur_map_idx
        ):
            self._map_combo.setCurrentIndex(idx[0])  # reloads the section
        text = self._model.get_entry(key, idx)
        if not self._canvas.refresh_card(key, idx, text, self._model.entry_byte_cost(text, key)):
            self._canvas.update()
            return
        self._canvas.ensure_visible(self._canvas.index_of(key, idx))

    def _on_undo_index_changed(self, _idx: int):
        if self._cur_section:
            self._refresh_budget(self._cur_section)

    def _select_section(self, key: str):
        for i in range(self.section_list.count()):
            if self._item_key(self.section_list.item(i)) == key:
                self.section_list.setCurrentRow(i)
                return

    # ── Budget (status bar) ───────────────────────────────────────────────────

    def _refresh_budget(self, key: str):
        cap = self._model.capacity(key)
        used = self._model.used_bytes(key)
        if cap == 0:
            self.budget_lbl.setText(tr("Sin información de capacidad"))
            self.budget_lbl.setStyleSheet("")
            self.budget_bar.setValue(0)
            self.budget_pct.setText("")
            return
        if self._model.is_fixed(key):
            bad = len(self._model.fixed_overflows(key))
            self.budget_bar.setValue(int(min(used / cap, 1.0) * 1000))
            self.budget_lbl.setText(
                tr("{bad} entradas exceden los {cap} caracteres").format(bad=bad, cap=cap)
                if bad
                else tr("Entrada más larga: {used} de {cap} caracteres").format(used=used, cap=cap)
            )
            self.budget_lbl.setStyleSheet(css_color(error_color()) if bad else "")
            self.budget_pct.setText("")
            return
        free = cap - used
        pct = min(used / cap, 1.0)
        self.budget_bar.setValue(int(pct * 1000))
        if not self._model.capacity_exact(key):
            self.budget_lbl.setText(
                tr("{used} B usados · capacidad estimada ≈ {cap} B").format(used=used, cap=cap)
            )
            self.budget_lbl.setToolTip(tr("Estimación: compilá para medir la capacidad real."))
            self.budget_lbl.setStyleSheet("")
            self.budget_pct.setText("")
            return
        self.budget_lbl.setToolTip("")
        over = self._model.overflow_bytes(key)
        self.budget_lbl.setText(
            tr("Excede por {n} bytes").format(n=over)
            if over
            else tr("{free} B libres de {cap} B").format(free=free, cap=cap)
        )
        # Only semantic warning colours; normal state uses the platform text colour.
        self.budget_lbl.setStyleSheet(
            css_color(error_color()) if over else (css_color(warning_color()) if pct > 0.90 else "")
        )
        self.budget_pct.setText(f"{pct * 100:.0f} %")

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_map_combo_changed(self, idx: int):
        if idx >= 0 and self._cur_section:
            self._cur_map_idx = idx
            self._load_section(self._cur_section)

    def _focus_filter(self):
        self.filter_edit.setFocus()
        self.filter_edit.selectAll()

    def _on_find_replace(self):
        if self._find_dlg is None:
            self._find_dlg = FindReplaceDialog(self._model, self._cur_section, self)
            self._find_dlg.goto_requested.connect(self._goto_entry)
            self._find_dlg.replace_requested.connect(self._apply_replacements)
        else:
            self._find_dlg._current = self._cur_section
            self._find_dlg.chk_current.setEnabled(bool(self._cur_section))
        self._find_dlg.show()
        self._find_dlg.raise_()
        self._find_dlg.activateWindow()
        self._find_dlg.find_edit.setFocus()
        self._find_dlg.find_edit.selectAll()

    def _goto_entry(self, key: str, idx):
        """Show entry (key, idx): switch section/map and open its card."""
        if key != self._cur_section:
            self._select_section(key)
        if key == "mapDialog" and isinstance(idx, tuple) and idx[0] != self._cur_map_idx:
            self.filter_edit.clear()
            self._map_combo.setCurrentIndex(idx[0])
        i = self._canvas.index_of(key, idx)
        if i < 0 and self.filter_edit.text():  # hidden by the filter
            self.filter_edit.clear()
            self._apply_filter()
            i = self._canvas.index_of(key, idx)
        if i >= 0:
            self._canvas.ensure_visible(i)
            self._canvas.editor.activate(i)

    def _apply_replacements(self, changes: list):
        """Apply [(key, idx, new_text)] as ONE undo step."""
        self._canvas.editor.deactivate()
        self._pushing = True
        self.undo_stack.beginMacro(tr("reemplazar en {n} entrada(s)").format(n=len(changes)))
        try:
            for key, idx, new in changes:
                old = self._model.get_entry(key, idx)
                if old != new:
                    self.undo_stack.push(EditEntryCommand(self._model, key, idx, old, new))
        finally:
            self.undo_stack.endMacro()
            self._pushing = False
        if self._cur_section:
            scroll = self._canvas.scroll_value
            self._load_section(self._cur_section)
            self._canvas.scroll_value = scroll
        self.statusBar().showMessage(tr("{n} entrada(s) modificada(s)").format(n=len(changes)), 6000)

    def _on_goto(self):
        key = self._cur_section
        if not key:
            return
        total = len(self._model.section_items(key))
        if total == 0:
            return
        is_map = key == "mapDialog"
        n, ok = QInputDialog.getInt(
            self,
            tr("Ir a…"),
            tr("Número de mapa:") if is_map else tr("Número de entrada (#NNN):"),
            self._cur_map_idx if is_map else 0,
            0,
            total - 1,
        )
        if not ok:
            return
        if is_map:
            self._cur_map_idx = n
            self._map_combo.blockSignals(True)
            self._map_combo.setCurrentIndex(n)
            self._map_combo.blockSignals(False)
            self._load_section(key)
            return
        if self.filter_edit.text():
            self.filter_edit.clear()
            self._apply_filter()
        if self._canvas.goto_entry(n):
            self.statusBar().showMessage(tr("Entrada #{n:03d}").format(n=n), 3000)

    def _apply_filter(self):
        self._filter_timer.stop()
        if self._cur_section:
            self._load_section(self._cur_section)

    # ── Save / close ──────────────────────────────────────────────────────────

    def _on_save(self, *_):
        if not self._model.filepath:
            return
        try:
            self._model.save()
        except FF4Error as e:
            QMessageBox.critical(self, tr("No se pudo guardar"), str(e))
            return
        self.setWindowModified(False)
        self.statusBar().showMessage(tr("Guardado: {path}").format(path=self._model.filepath), 5000)
        for i in range(self.section_list.count()):  # clear the "modified" marks
            key = self._item_key(self.section_list.item(i))
            if key:
                self._refresh_sidebar_item(key)

    def _save_config(self) -> bool:
        """Persist the preferences; tell the user if that is not possible."""
        try:
            self.config_mgr.save(self._model.filepath)
        except FF4Error as e:
            QMessageBox.warning(
                self,
                "Preferencias",
                f"Los cambios se aplican en esta sesión pero no se pudieron guardar:\n{e}",
            )
            return False
        return True

    def _show_config_warnings(self):
        for msg in self.config_mgr.take_warnings():
            self.statusBar().showMessage(msg, 12000)

    def closeEvent(self, event):
        if not self._maybe_save():
            event.ignore()
            return
        self._save_window_state()
        event.accept()

    # ── Preferences ───────────────────────────────────────────────────────────

    def _on_preferences(self):
        cur = self._cur_section
        has_override = self.config_mgr.has_section_override(cur)
        dlg = ViewDialog(
            self.config,
            section=cur,
            section_label=tr(TEXT_SECTIONS.get(cur, cur)) if cur else None,
            has_section_override=has_override,
            parent=self,
        )

        if dlg.exec():
            changed = dlg.result_settings
            section_only = dlg.section_only
            clear_section = dlg.clear_section

            if not changed and not clear_section:
                return

            if clear_section and cur:
                self.config_mgr.clear_section_override(cur)
                self._save_config()
                self._load_section(cur)
                self._canvas.update()
                return

            font_changed, vwf_changed = self.config_mgr.update_from_dialog(changed, cur, section_only)
            self._save_config()

            if font_changed:
                self.config.apply_font()
            if vwf_changed:
                self._setup_vwf()

            if cur:
                self._load_section(cur)
            self._canvas.update()
