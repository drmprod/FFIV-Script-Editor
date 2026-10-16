"""
ff4_editor/ui_mainwindow.py
FF4Editor — QMainWindow.
Owns: FF4Model, CardCanvas, settings, config I/O.
Delegates: all painting to CardCanvas, all data to FF4Model.
"""

import os, shutil, json

from PySide6.QtCore             import Qt, QProcess
from PySide6.QtGui              import QUndoStack
from PySide6.QtWidgets          import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QLabel, QLineEdit,
    QPushButton, QProgressBar, QFrame, QSizePolicy, QFileDialog,
    QMessageBox, QScrollBar, QComboBox,
)

from .model                     import FF4Model
from .widgets                   import CardCanvas, CardData
from .ui_view_dialog            import ViewDialog
from .config                    import EditorConfig
from .config_manager            import create_config_manager
from .model.commands            import EditEntryCommand
from .ui_build_dialog           import BuildDialog
from .constants                 import (
    TEXT_SECTIONS, DIALOG_SECTIONS, DICT_KEY
)

class FF4Editor(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FF4 Translation Editor")

        # ── Settings Configuration Object ──────────
        self.config = EditorConfig()
        self.config_mgr = create_config_manager(self.config)

        self.verbose      = False
        self._cur_map_idx = 0

        self.config_mgr.load()
        self.config.apply_font()

        # ── Model ─────────────────────────────────────────────────────────────
        self._model = FF4Model(self)
        self._model.loaded.connect(self._on_model_loaded)
        self._model.section_changed.connect(self._on_section_changed)
        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._on_undo_index_changed)
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # Toolbar
        tb = QWidget()
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(14, 8, 14, 8)
        tbl.setSpacing(8)

        tbox = QWidget()
        tbl2 = QVBoxLayout(tbox)
        tbl2.setContentsMargins(0, 0, 0, 0)
        tbl2.setSpacing(0)
        tbl2.addWidget(QLabel("FF4 TRANSLATION EDITOR"))
        tbl2.addWidget(QLabel("Final Fantasy IV · SNES · everything8215/ff4 disassembly"))
        tbl.addWidget(tbox)
        tbl.addStretch(1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter strings…")
        self.search.textChanged.connect(self._on_search)
        tbl.addWidget(self.search)

        open_btn = QPushButton("Open JSON")
        open_btn.clicked.connect(self._on_open)
        tbl.addWidget(open_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setEnabled(False)
        tbl.addWidget(self.save_btn)

        view_btn = QPushButton("⚙ View")
        view_btn.clicked.connect(self._on_view_menu)
        tbl.addWidget(view_btn)

        self.build_btn = QPushButton("Compilar")
        self.build_btn.setToolTip("make ff4-es en el directorio del JSON abierto")
        self.build_btn.clicked.connect(self._on_build)
        self.build_btn.setEnabled(False)
        tbl.addWidget(self.build_btn)

        self.run_btn = QPushButton("Mesen")
        self.run_btn.setToolTip("Abrir la ROM compilada (rom/ff4-es.sfc junto al JSON) en Mesen")
        self.run_btn.clicked.connect(self._on_run_mesen)
        self.run_btn.setEnabled(False)
        tbl.addWidget(self.run_btn)

        rl.addWidget(tb)

        # Edit toolbar
        undo_action = self.undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcut("Ctrl+Z")
        self.addAction(undo_action)
        redo_action = self.undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcut("Ctrl+Shift+Z")
        self.addAction(redo_action)
        etb = QWidget()
        etbl = QHBoxLayout(etb)
        etbl.setContentsMargins(10, 4, 10, 4)
        etbl.setSpacing(2)

        def sep():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.VLine)
            etbl.addWidget(s)

        for label, tip, slot in [
            ("Select All",  "Select all text in active card (Ctrl+A)",
                lambda: self._canvas.action_select_all()),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip); btn.clicked.connect(slot)
            etbl.addWidget(btn)

        sep()

        for label, tip, slot in [
            ("Cut",   "Cut (Ctrl+X)", lambda: self._canvas.action_cut()),
            ("Copy",  "Copy (Ctrl+C)", lambda: self._canvas.action_copy()),
            ("Paste", "Paste (Ctrl+V)", lambda: self._canvas.action_paste()),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip); btn.clicked.connect(slot)
            etbl.addWidget(btn)

        sep()

        for label, tip, slot in [
            ("Insert \\line", "Insert page-break line at cursor",
                lambda: self._canvas.action_insert_blank_line()),
            ("Centre",        "Centre selected line(s)",
                lambda: self._canvas.action_centre_lines()),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip); btn.clicked.connect(slot)
            etbl.addWidget(btn)

        etbl.addStretch(1)
        rl.addWidget(etb)

        # Info bar
        ib = QWidget()
        ibl = QHBoxLayout(ib)
        ibl.setContentsMargins(0, 0, 0, 0)
        self.info_lbl = QLabel(
            "Tip: after saving, run  make ff4-en  in the repo to rebuild the ROM.")
        ibl.addWidget(self.info_lbl)
        rl.addWidget(ib)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        rl.addWidget(splitter, 1)

        # ── Sidebar ───────────────────────────────────────────────────────────
        sbw = QWidget(); sbw.setFixedWidth(220)
        sbl = QVBoxLayout(sbw); sbl.setContentsMargins(0, 0, 0, 0)
        self.section_list = QListWidget()
        sbl.addWidget(self.section_list)
        self.section_list.currentItemChanged.connect(self._on_section_selected)
        splitter.addWidget(sbw)

        # ── Right pane ────────────────────────────────────────────────────────
        right = QWidget()
        rr = QVBoxLayout(right); rr.setContentsMargins(0, 0, 0, 0); rr.setSpacing(0)

        self.sec_title = QLabel("← Open a JSON file to begin")
        rr.addWidget(self.sec_title)

        # Map selector row
        self._map_row = QWidget()
        mrl = QHBoxLayout(self._map_row)
        mrl.setContentsMargins(6, 2, 6, 2); mrl.setSpacing(6)
        self._map_combo = QComboBox()
        self._map_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._map_combo.currentIndexChanged.connect(self._on_map_combo_changed)
        mrl.addWidget(self._map_combo, 1)
        mrl.addWidget(QLabel("Go #"))
        self._map_goto = QLineEdit()
        self._map_goto.setPlaceholderText("map…"); self._map_goto.setMaximumWidth(60)
        self._map_goto.returnPressed.connect(self._on_map_goto)
        mrl.addWidget(self._map_goto)
        self._map_row.setVisible(False)
        rr.addWidget(self._map_row)

        # Entry goto row (every section except mapDialog, which has its own map selector)
        self._entry_row = QWidget()
        erl = QHBoxLayout(self._entry_row)
        erl.setContentsMargins(6, 2, 6, 2); erl.setSpacing(6)
        self.count_lbl = QLabel("")
        erl.addWidget(self.count_lbl, 1)
        self._goto_lbl = QLabel("Ir a #")
        erl.addWidget(self._goto_lbl)
        self._entry_goto = QLineEdit()
        self._entry_goto.setPlaceholderText("entrada…"); self._entry_goto.setMaximumWidth(80)
        self._entry_goto.setToolTip("Número de entrada (el #NNN de cada tarjeta) + Enter. "
                                    "Quita el filtro si la entrada está oculta.")
        self._entry_goto.returnPressed.connect(self._on_entry_goto)
        erl.addWidget(self._entry_goto)
        rr.addWidget(self._entry_row)

        # Budget bar
        brow = QWidget()
        brl = QHBoxLayout(brow)
        brl.setContentsMargins(14, 4, 14, 8); brl.setSpacing(8)
        self.budget_lbl = QLabel(""); self.budget_lbl.setMinimumWidth(220)
        brl.addWidget(self.budget_lbl)
        self.budget_bar = QProgressBar()
        self.budget_bar.setRange(0, 1000); self.budget_bar.setValue(0)
        self.budget_bar.setTextVisible(False); self.budget_bar.setFixedHeight(8)
        brl.addWidget(self.budget_bar, 1)
        self.budget_pct = QLabel(""); self.budget_pct.setMinimumWidth(40)
        brl.addWidget(self.budget_pct)
        rr.addWidget(brow)

        sep_h = QFrame(); sep_h.setFrameShape(QFrame.Shape.HLine)
        rr.addWidget(sep_h)

        # Canvas + scrollbar
        crow = QWidget()
        crl = QHBoxLayout(crow)
        crl.setContentsMargins(0, 0, 0, 0); crl.setSpacing(0)
        self._canvas = CardCanvas(self.config, self)
        self._canvas.card_committed.connect(self._on_card_committed)
        crl.addWidget(self._canvas, 1)
        vbar = QScrollBar(Qt.Orientation.Vertical)
        crl.addWidget(vbar)
        self._canvas.set_scrollbar(vbar)
        rr.addWidget(crow, 1)

        splitter.addWidget(right)
        splitter.setSizes([220, 1000])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # Status bar
        stb = QWidget()
        stbl = QHBoxLayout(stb); stbl.setContentsMargins(0, 0, 0, 0)
        self.status_lbl = QLabel("No file loaded.")
        stbl.addWidget(self.status_lbl)
        rl.addWidget(stb)

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _on_open(self, *_):
        p, _ = QFileDialog.getOpenFileName(
            self, "Open FF4 JSON", "", "JSON files (*.json)")
        if p:
            self._load_file(p)

    MESEN_NAMES = ("mesen", "Mesen", "mesen2", "Mesen2", "mesen-s", "Mesen-S")

    def _find_rom(self):
        """<dir del JSON>/rom/ff4-es.sfc (o .spc, tal como se pidio)."""
        fp = self._model.filepath
        if not fp:
            return None
        d = os.path.join(os.path.dirname(os.path.abspath(fp)), "rom")
        for ext in ("sfc", "spc", "smc"):
            c = os.path.join(d, "ff4-es." + ext)
            if os.path.isfile(c):
                return c
        return None

    def _on_run_mesen(self, *_):
        rom = self._find_rom()
        if not rom:
            d = os.path.join(os.path.dirname(os.path.abspath(self._model.filepath)), "rom")
            QMessageBox.warning(self, "Mesen",
                                f"No existe ff4-es.sfc/.spc en:\n{d}\n\nCompila primero.")
            return
        exe = next((p for p in (shutil.which(n) for n in self.MESEN_NAMES) if p), None)
        if not exe:
            QMessageBox.warning(self, "Mesen",
                                "No encuentro Mesen en el PATH (probe: "
                                + ", ".join(self.MESEN_NAMES) + ").")
            return
        ok = QProcess.startDetached(exe, [rom], os.path.dirname(rom))
        self.status_lbl.setText(f"Mesen: {rom}" if ok else "No se pudo lanzar Mesen")

    def _on_build(self, *_):
        fp = self._model.filepath
        if not fp:
            return
        if self._model.dirty_keys:
            r = QMessageBox.question(
                self, "Compilar",
                "Hay cambios sin guardar. ¿Guardar antes de compilar?",
                QMessageBox.Save | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Save)
            if r == QMessageBox.Cancel:
                return
            if r == QMessageBox.Save:
                self._on_save()
        wd = os.path.dirname(os.path.abspath(fp))
        old = getattr(self, '_build_dlg', None)
        if old is not None and old.isVisible():
            old.raise_(); old.activateWindow()
            return
        self._build_dlg = BuildDialog(wd, "make", ["ff4-es"], self)
        self._build_dlg.show()
        self._build_dlg.start()

    def _load_file(self, path: str):
        self.status_lbl.setText(f"Loading {path}…")
        try:
            self._model.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load:\n{e}")

    def _on_model_loaded(self):
        path = self._model.filepath
        self.build_btn.setEnabled(bool(path))
        self.run_btn.setEnabled(bool(path))
        self.config_mgr.load(path)
        self.config.apply_font()
        self._setup_vwf()
        self._canvas.dte_set = self._model.dte_set
        self.undo_stack.clear()
        self._populate_sidebar()
        self.save_btn.setEnabled(True)
        name = os.path.basename(path)
        self.status_lbl.setText(f"Loaded: {name}")
        self.setWindowTitle(f"FF4 Translation Editor — {name}")
        repo = os.path.dirname(path)
        self.info_lbl.setText(f"After saving → cd {repo} && make ff4-en")
        if self.verbose:
            print(f"[load] {path}  DTE: {len(self._model.dte_set)}")

    # ── Game font (VWF) ───────────────────────────────────────────────────────

    def _find_font_png(self) -> str | None:
        c = self.config
        cands = []
        if c.vwf_font_png:
            cands.append(c.vwf_font_png)
        fp = self._model.filepath
        if fp:
            d = os.path.dirname(os.path.abspath(fp))
            cands += [os.path.join(d, 'font.png'),
                      os.path.join(d, 'gfx', 'font.png'),
                      os.path.join(d, 'tools', 'font.png'),
                      os.path.join(os.path.dirname(d), 'font.png')]
        here = os.path.dirname(os.path.abspath(__file__))
        cands += [os.path.join(os.path.dirname(here), 'font.png')]
        return next((p for p in cands if os.path.isfile(p)), None)

    def _setup_vwf(self):
        """Build the game font from font.png + charTable and hand it to the canvas."""
        from PySide6.QtGui import QFontDatabase
        from .util.vwf_font import VWFFont, text_codes_from_json, FAMILY
        old = getattr(self, '_vwf_font_id', None)
        if old is not None:
            QFontDatabase.removeApplicationFont(old)
            self._vwf_font_id = None
        self._vwf = None
        png = self._find_font_png()
        if not png:
            self._canvas.set_vwf(None, None)
            self.status_lbl.setText('font.png not found: game font disabled '
                                    '(set it in View → Font PNG)')
            return
        try:
            ov = {}
            ovp = os.path.join(os.path.dirname(png), 'vwf_overrides.json')
            if os.path.isfile(ovp):
                with open(ovp, encoding='utf-8') as f:
                    ov = json.load(f)
            codes = text_codes_from_json(self._model.char_table_text)
            self._vwf = VWFFont(png, codes, self.config.vwf_gap, self.config.vwf_space, ov)
            fid = QFontDatabase.addApplicationFontFromData(self._vwf.ttf_bytes(self.config.vwf_line_pitch))
            if fid < 0:
                raise RuntimeError('Qt rejected the generated font')
            self._vwf_font_id = fid
        except Exception as e:
            self._vwf = None
            self._canvas.set_vwf(None, None)
            self.status_lbl.setText(f'Game font disabled: {e}')
            return
        self._canvas.set_vwf(self._vwf, FAMILY)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _populate_sidebar(self):
        self.section_list.clear()
        for key in TEXT_SECTIONS:
            if not self._model.section_items(key):
                continue
            item = QListWidgetItem()
            item._section_key = key
            self.section_list.addItem(item)
            self._refresh_sidebar_item(key, item)

    def _refresh_sidebar_item(self, key: str, item=None):
        if item is None:
            for i in range(self.section_list.count()):
                it = self.section_list.item(i)
                if getattr(it, '_section_key', None) == key:
                    item = it; break
        if item is None:
            return
        name  = TEXT_SECTIONS.get(key, key)
        dirty = ' ✎' if key in self._model.dirty_keys else ''
        cap   = self._model.capacity(key)
        used  = self._model.used_bytes(key)
        pct   = used / cap if cap else 1.0
        dot   = '🔴' if pct > 0.95 else ('🟡' if pct > 0.75 else '⚫')
        item.setText(f"{name}{dirty}  {dot}")

    def _on_section_selected(self, current, _previous=None):
        if current is None:
            return
        self._cur_section = current._section_key
        self.config_mgr.apply_section_override(self._cur_section)
        self._load_section(self._cur_section)

    # ── Section loading → CardData list ──────────────────────────────────────

    def _load_section(self, key: str):
        items  = self._model.section_items(key)
        filt   = self.search.text().lower()
        is_dlg = key in DIALOG_SECTIONS
        self.sec_title.setText(TEXT_SECTIONS.get(key, key))

        # Map selector
        entry_labels: dict[int, str] = {}
        if key == 'mapDialog':
            mp = self._model.map_properties()
            mt = self._model.map_titles()
            for li in range(len(items)):
                tidx = (mp[li].get('title', 0)
                        if li < len(mp) and isinstance(mp[li], dict) else 0)
                entry_labels[li] = mt[tidx] if tidx < len(mt) else ''
            self._map_combo.blockSignals(True)
            self._map_combo.clear()
            for li, name in entry_labels.items():
                self._map_combo.addItem(f'#{li:03d}  {name}')
            self._cur_map_idx = max(0, min(self._cur_map_idx, len(items) - 1))
            self._map_combo.setCurrentIndex(self._cur_map_idx)
            self._map_combo.blockSignals(False)
            self._map_row.setVisible(True)
        else:
            self._map_row.setVisible(False)
            self._cur_map_idx = 0
        self._goto_lbl.setVisible(key != 'mapDialog')
        self._entry_goto.setVisible(key != 'mapDialog')

        cards: list[CardData] = []
        dk = DICT_KEY.get(key)

        for i, item in enumerate(items):

            # mapDialog: list of sub-strings per map
            if isinstance(item, list):
                label    = entry_labels.get(i, '')
                all_text = ' '.join(s for s in item if isinstance(s, str))
                if key == 'mapDialog':
                    if filt:
                        if (filt not in all_text.lower()
                                and filt not in str(i)
                                and filt not in label.lower()):
                            continue
                    elif i != self._cur_map_idx:
                        continue
                elif filt and filt not in all_text.lower() and filt not in str(i):
                    continue
                n   = len(item)
                hdr = f"#{i:03d}  {label}  ({n})" if label else f"#{i:03d}  ({n})"
                for j, sub in enumerate(item):
                    if not isinstance(sub, str):
                        continue
                    bc = self._model.entry_byte_cost(sub)
                    cards.append(CardData(key, (i, j), f"{hdr} .{j:02d}",
                                          True, sub, bc))
                continue

            # Normal entry (string or dict)
            json_text = (item.get(dk, '') if (dk and isinstance(item, dict))
                         else (item if isinstance(item, str) else str(item)))
            if filt and filt not in json_text.lower() and filt not in str(i):
                continue
            bc = self._model.entry_byte_cost(json_text)
            cards.append(CardData(key, i, f"#{i:03d}", is_dlg, json_text, bc))

        self._canvas.load_cards(cards)
        self._refresh_budget(key)
        self.count_lbl.setText(
            f"{len(items)} entries"
            + (f"  ·  {len(cards)} shown" if filt else ""))
        if self.verbose:
            print(f"[section] {TEXT_SECTIONS.get(key, key)}: "
                  f"{len(items)} entries, {len(cards)} cards")

    # ── Card committed callback ───────────────────────────────────────────────

    def _on_card_committed(self, section, idx, json_text):
        old_text = self._model.get_entry(section, idx)

        if old_text == json_text:
            return  # Ignore focus loss without changes

        cmd = EditEntryCommand(self._model, section, idx, old_text, json_text)
        self.undo_stack.push(cmd)

    def _on_section_changed(self, key: str):
        self._refresh_budget(key)
        self._refresh_sidebar_item(key)
        if not self._model.dirty_keys:
            return
        if not self.windowTitle().startswith('*'):
            self.setWindowTitle('* ' + self.windowTitle())
        self.status_lbl.setText(
            f"Unsaved changes · {len(self._model.dirty_keys)} section(s) marked dirty")

    def _on_undo_index_changed(self, _idx: int):
        """Refresh the current section when undo/redo happens."""
        if hasattr(self, '_cur_section') and self._cur_section:
            self._load_section(self._cur_section)
            self._refresh_budget(self._cur_section)
            self._refresh_sidebar_item(self._cur_section)
            self._canvas.update()

    # ── Budget bar ────────────────────────────────────────────────────────────

    def _refresh_budget(self, key: str):
        cap  = self._model.capacity(key)
        used = self._model.used_bytes(key)
        if cap == 0:
            self.budget_lbl.setText("No ROM range info")
            self.budget_bar.setValue(0)
            self.budget_pct.setText("")
            return
        free  = cap - used
        pct   = min(used / cap, 1.0)
        color = '#e04040' if free < 0 else ('#c08020' if pct > 0.90 else '#5a5080')
        self.budget_bar.setValue(int(pct * 1000))
        self.budget_lbl.setText(
            f"⚠ OVER by {-free} bytes!" if free < 0 else f"{free}B free / {cap}B cap")
        self.budget_lbl.setStyleSheet(f'color: {color};')
        self.budget_pct.setText(f"{pct * 100:.0f}%")
        self.budget_pct.setStyleSheet(f'color: {color};')

    # ── Map controls ──────────────────────────────────────────────────────────

    def _on_map_combo_changed(self, idx: int):
        if idx >= 0:
            self._cur_map_idx = idx
            self._load_section(self._cur_section)

    def _on_map_goto(self):
        try:
            idx = int(self._map_goto.text().strip())
        except ValueError:
            return
        items = self._model.section_items(self._cur_section)
        if 0 <= idx < len(items):
            self._cur_map_idx = idx
            self._map_combo.blockSignals(True)
            self._map_combo.setCurrentIndex(idx)
            self._map_combo.blockSignals(False)
            self._load_section(self._cur_section)
        self._map_goto.clear()

    def _on_entry_goto(self):
        txt = self._entry_goto.text().strip().lstrip('#')
        try:
            n = int(txt)
        except ValueError:
            return
        key = getattr(self, '_cur_section', None)
        if not key or key == 'mapDialog':
            return
        total = len(self._model.section_items(key))
        if not 0 <= n < total:
            self.status_lbl.setText(f"Entrada #{n} fuera de rango (0–{total - 1})")
            return
        if self.search.text():
            self.search.clear()          # reloads the section without a filter
        if self._canvas.goto_entry(n):
            self._entry_goto.clear()
            self.status_lbl.setText(f"Entrada #{n:03d}")

    def _on_search(self, *_):
        if hasattr(self, '_cur_section') and self._cur_section:
            self._load_section(self._cur_section)

    # ── Save / close ──────────────────────────────────────────────────────────

    def _on_save(self, *_):
        if not self._model.filepath:
            return
        try:
            self._model.save()
            t = f"FF4 Translation Editor — {os.path.basename(self._model.filepath)}"
            self.setWindowTitle(t)
            self.status_lbl.setText(f"Saved: {self._model.filepath}")

            # Refresh all sidebar items to clear the dirty icons
            for key in TEXT_SECTIONS:
                self._refresh_sidebar_item(key)

        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def closeEvent(self, event):
        if self._model.dirty_keys:
            r = QMessageBox.warning(
                self, "Unsaved changes",
                f"{len(self._model.dirty_keys)} section(s) modified. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Save:
                self._on_save()
            elif r == QMessageBox.StandardButton.Cancel:
                event.ignore(); return
        event.accept()

    # ── View menu ─────────────────────────────────────────────────────────────

    def _on_view_menu(self):
        cur = getattr(self, '_cur_section', None)
        has_override = cur in self.config_mgr._section_overrides if cur else False
        dlg = ViewDialog(self.config, section=cur, has_section_override=has_override, parent=self)

        if dlg.exec():
            changed      = dlg.result_settings
            section_only = dlg.section_only
            clear_section= dlg.clear_section

            if not changed and not clear_section:
                return

            if clear_section and cur:
                self.config_mgr.clear_section_override(cur)
                self.config_mgr.save(self._model.filepath)
                self._load_section(cur)
                self._canvas.update()
                return

            font_changed, vwf_changed = self.config_mgr.update_from_dialog(changed, cur, section_only)
            self.config_mgr.save(self._model.filepath)

            if font_changed:
                self.config.apply_font()
            if vwf_changed:
                self._setup_vwf()

            if cur:
                self._load_section(cur)
            self._canvas.update()
