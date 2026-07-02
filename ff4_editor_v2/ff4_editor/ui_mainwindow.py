"""
ff4_editor/ui_mainwindow.py
FF4Editor — QMainWindow.
Owns: FF4Model, CardCanvas, settings, config I/O.
Delegates: all painting to CardCanvas, all data to FF4Model.
"""

import os, json, sys

from PySide6.QtCore             import Qt, QTimer
from PySide6.QtGui              import QFont, QFontDatabase, QUndoStack
from PySide6.QtWidgets          import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QLabel, QLineEdit,
    QPushButton, QProgressBar, QFrame, QSizePolicy, QFileDialog,
    QMessageBox, QScrollBar, QComboBox,
)

from .model                     import FF4Model
from .model.encoding            import encode_size
from .util                      import json_to_display
from .util.text_processing      import validate_dependencies
from .widgets                   import CardCanvas, CardData
from .ui_view_dialog            import ViewDialog
from .config                    import EditorConfig
from .model.commands            import EditEntryCommand
from .constants                 import (
    TEXT_SECTIONS, DIALOG_SECTIONS, DICT_KEY,
    C_BAND0_DEF, C_BAND1_DEF,
)

CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ff4_editor.cfg")

class FF4Editor(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FF4 Translation Editor")

        # Validate critical dependencies before proceeding
        try:
            validate_dependencies()
        except RuntimeError as e:
            QMessageBox.critical(self, "Startup Error", str(e))
            sys.exit(1)

        # ── Settings Configuration Object ──────────
        self.config = EditorConfig()

        self.verbose      = False
        self._cur_map_idx = 0
        self._section_overrides: dict = {}  # section_key -> {setting: value, ...}

        self._load_cfg()
        self.config.apply_font()
        self._base_settings = self._snapshot_settings()

        # ── Model ─────────────────────────────────────────────────────────────
        self._model = FF4Model(self)
        self._model.loaded.connect(self._on_model_loaded)
        self._model.section_changed.connect(self._on_section_changed)
        self.undo_stack = QUndoStack(self)
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget(); root.setObjectName('root')
        self.setCentralWidget(root)
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # Toolbar
        tb = QWidget(); tb.setObjectName('toolbar')
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(14, 8, 14, 8)
        tbl.setSpacing(8)

        tbox = QWidget()
        tbl2 = QVBoxLayout(tbox)
        tbl2.setContentsMargins(0, 0, 0, 0)
        tbl2.setSpacing(0)
        tbl2.addWidget(self._make_label("FF4 TRANSLATION EDITOR", 'title_lbl'))
        tbl2.addWidget(self._make_label(
            "Final Fantasy IV · SNES · everything8215/ff4 disassembly", 'subtitle_lbl'))
        tbl.addWidget(tbox)
        tbl.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName('search_entry')
        self.search.setPlaceholderText("Filter strings…")
        self.search.textChanged.connect(self._on_search)
        tbl.addWidget(self.search)

        open_btn = QPushButton("Open JSON"); open_btn.setObjectName('open_btn')
        open_btn.clicked.connect(self._on_open)
        tbl.addWidget(open_btn)

        self.save_btn = QPushButton("Save"); self.save_btn.setObjectName('save_btn')
        self.save_btn.clicked.connect(self._on_save)
        self.save_btn.setEnabled(False)
        tbl.addWidget(self.save_btn)

        view_btn = QPushButton("⚙ View"); view_btn.setObjectName('view_btn')
        view_btn.clicked.connect(self._on_view_menu)
        tbl.addWidget(view_btn)

        rl.addWidget(tb)

        # Edit toolbar
        undo_action = self.undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcut("Ctrl+Z")
        redo_action = self.undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcut("Ctrl+Shift+Z")
        etb = QWidget(); etb.setObjectName('edit_toolbar')
        etbl = QHBoxLayout(etb)
        etbl.setContentsMargins(10, 4, 10, 4)
        etbl.setSpacing(2)

        def sep():
            s = QFrame()
            s.setFrameShape(QFrame.Shape.VLine)
            s.setStyleSheet('color: #2a2545;')
            etbl.addWidget(s)

        for label, tip, slot in [
            ("Select All",  "Select all text in active card (Ctrl+A)",
                lambda: self._canvas.action_select_all()),
        ]:
            btn = QPushButton(label); btn.setObjectName('edit_btn')
            btn.setToolTip(tip); btn.clicked.connect(slot)
            etbl.addWidget(btn)

        sep()

        for label, tip, slot in [
            ("Cut",   "Cut (Ctrl+X)", lambda: self._canvas.action_cut()),
            ("Copy",  "Copy (Ctrl+C)", lambda: self._canvas.action_copy()),
            ("Paste", "Paste (Ctrl+V)", lambda: self._canvas.action_paste()),
        ]:
            btn = QPushButton(label); btn.setObjectName('edit_btn')
            btn.setToolTip(tip); btn.clicked.connect(slot)
            etbl.addWidget(btn)

        sep()

        for label, tip, slot in [
            ("Insert \\line", "Insert page-break line at cursor",
                lambda: self._canvas.action_insert_blank_line()),
            ("Centre",        "Centre selected line(s)",
                lambda: self._canvas.action_centre_lines()),
        ]:
            btn = QPushButton(label); btn.setObjectName('edit_btn')
            btn.setToolTip(tip); btn.clicked.connect(slot)
            etbl.addWidget(btn)

        etbl.addStretch(1)
        rl.addWidget(etb)

        # Info bar
        ib = QWidget(); ib.setObjectName('infobar')
        ibl = QHBoxLayout(ib)
        ibl.setContentsMargins(0, 0, 0, 0)
        self.info_lbl = QLabel(
            "Tip: after saving, run  make ff4-en  in the repo to rebuild the ROM.")
        self.info_lbl.setObjectName('infobar_lbl')
        ibl.addWidget(self.info_lbl)
        rl.addWidget(ib)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        rl.addWidget(splitter, 1)

        # ── Sidebar ───────────────────────────────────────────────────────────
        sbw = QWidget(); sbw.setObjectName('sidebar'); sbw.setFixedWidth(220)
        sbl = QVBoxLayout(sbw); sbl.setContentsMargins(0, 0, 0, 0)
        self.section_list = QListWidget()
        sbl.addWidget(self.section_list)
        self.section_list.currentItemChanged.connect(self._on_section_selected)
        splitter.addWidget(sbw)

        # ── Right pane ────────────────────────────────────────────────────────
        right = QWidget(); right.setStyleSheet('background: #12111a;')
        rr = QVBoxLayout(right); rr.setContentsMargins(0, 0, 0, 0); rr.setSpacing(0)

        self.sec_title = QLabel("← Open a JSON file to begin")
        self.sec_title.setObjectName('sec_title')
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
        self._map_goto = QLineEdit(); self._map_goto.setObjectName('goto_entry')
        self._map_goto.setPlaceholderText("map…"); self._map_goto.setMaximumWidth(60)
        self._map_goto.returnPressed.connect(self._on_map_goto)
        mrl.addWidget(self._map_goto)
        self._map_row.setVisible(False)
        rr.addWidget(self._map_row)

        self.count_lbl = QLabel("")
        self.count_lbl.setObjectName('count_lbl')
        rr.addWidget(self.count_lbl)

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

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #2a2545;')
        rr.addWidget(sep)

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
        stb = QWidget(); stb.setObjectName('statusbar')
        stbl = QHBoxLayout(stb); stbl.setContentsMargins(0, 0, 0, 0)
        self.status_lbl = QLabel("No file loaded.")
        self.status_lbl.setObjectName('status_lbl')
        stbl.addWidget(self.status_lbl)
        rl.addWidget(stb)

    @staticmethod
    def _make_label(text, obj_name):
        lbl = QLabel(text); lbl.setObjectName(obj_name)
        return lbl

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _on_open(self, *_):
        p, _ = QFileDialog.getOpenFileName(
            self, "Open FF4 JSON", "", "JSON files (*.json)")
        if p:
            self._load_file(p)

    def _load_file(self, path: str):
        self.status_lbl.setText(f"Loading {path}…")
        try:
            self._model.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load:\n{e}")

    def _on_model_loaded(self):
        path = self._model.filepath
        self._load_cfg(path)
        self.config.apply_font()
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

    def _on_section_selected(self, current, previous):
        if current is None:
            return
        self._cur_section = current._section_key
        print(f"[section selected] {self._cur_section}")
        self._apply_section_override(self._cur_section)
        self._load_section(self._cur_section)

    # ── Section loading → CardData list ──────────────────────────────────────

    def _snapshot_settings(self) -> dict:
        """Capture all current settings into a dict."""
        return {k: getattr(self.config, k) for k in [
            'card_rows', 'card_w', 'show_ruler', 'show_colors',
            'warn_chars', 'over_chars', 'ruler_chars', 'auto_wrap',
            'auto_hyphenate', 'char_limit', 'line_limit', 'hard_char_limit',
            'card_font', 'font_size', 'show_bands',
            'band0_color', 'band1_color',
        ]}

    def _apply_section_override(self, key: str):
        """Restore base settings then apply section-specific overrides."""
        CASTS = {
            'card_rows': int, 'card_w': int, 'warn_chars': int,
            'over_chars': int, 'ruler_chars': int, 'font_size': int,
            'char_limit': int, 'line_limit': int, 'hard_char_limit': bool,
            'show_ruler': bool, 'show_colors': bool, 'auto_wrap': bool,
            'show_bands': bool, 'auto_hyphenate': bool,
            'card_font': str, 'band0_color': str, 'band1_color': str,
        }
        for attr, val in self._base_settings.items():
            setattr(self.config, attr, val)
        ov = self._section_overrides.get(key, {})
        for attr, val in ov.items():
            if attr in CASTS:
                setattr(self.config, attr, CASTS[attr](val))

        self.config.apply_font()

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
        has_override = cur in self._section_overrides if cur else False
        dlg = ViewDialog(self.config, section=cur, has_section_override=has_override, parent=self)
        if dlg.exec():
            changed      = dlg.result_settings
            section_only = dlg.section_only
            clear_section= dlg.clear_section
            if not changed and not clear_section:
                return
            if clear_section and cur:
                self._section_overrides.pop(cur, None)
                self._save_cfg()
                self._apply_section_override(cur)
                if cur:
                    self._load_section(cur)
                return
            font_changed = False
            if section_only and cur:
                # Save ALL changed settings as section override
                if changed:
                    self._section_overrides.setdefault(cur, {}).update(changed)
                font_changed = any(k in changed for k in ('card_font', 'font_size'))
                self._apply_section_override(cur)
            else:
                # Apply globally, update base, re-apply section override
                for k, v in changed.items():
                    setattr(self.config, k, v)
                    if k in ('card_font', 'font_size'):
                        font_changed = True
                self._base_settings = self._snapshot_settings()
                self._apply_section_override(cur) if cur else None
            if font_changed:
                self.config.apply_font()
            self._save_cfg()
            if cur:
                self._load_section(cur)
    # ── Config ────────────────────────────────────────────────────────────────

    def _cfg_defaults(self) -> dict:
        return {
            'card_rows':   self.config.card_rows,
            'card_w':      self.config.card_w,
            'show_ruler':  self.config.show_ruler,
            'show_colors': self.config.show_colors,
            'warn_chars':  self.config.warn_chars,
            'over_chars':  self.config.over_chars,
            'auto_wrap':   self.config.auto_wrap,
            'auto_hyphenate': self.config.auto_hyphenate,
            'char_limit':      self.config.char_limit,
            'line_limit':      self.config.line_limit,
            'hard_char_limit': self.config.hard_char_limit,
            'card_font':   self.config.card_font,
            'font_size':   self.config.font_size,
            'show_bands':  self.config.show_bands,
            'band0_color': self.config.band0_color,
            'band1_color': self.config.band1_color,
            'section_overrides': self._section_overrides,
        }

    def _apply_settings(self, s: dict):
        for attr, cast in [
            ('card_rows',   int),  ('card_w',      int),
            ('warn_chars',  int),  ('over_chars',  int),  ('font_size', int),
            ('show_ruler',  bool), ('show_colors', bool), ('auto_wrap', bool),
            ('show_bands',  bool), ('auto_hyphenate', bool),
            ('char_limit',  int),  ('line_limit',  int),
            ('hard_char_limit', bool),
            ('card_font',   str),  ('band0_color', str),  ('band1_color', str),
            ('ruler_chars', int),
        ]:
            if attr in s:
                setattr(self.config, attr, cast(s[attr]))

    def _load_cfg(self, filepath: str | None = None):
        try:
            with open(CFG_PATH) as f:
                cfg = json.load(f)
        except Exception:
            return
        self._apply_settings(cfg.get('global', {}))
        if filepath:
            file_cfg = cfg.get('files', {}).get(os.path.basename(filepath), {})
            self._apply_settings(file_cfg)
            self._section_overrides = file_cfg.get('section_overrides', {})
        # Update base values after loading
        self._base_settings = self._snapshot_settings()

    def _save_cfg(self):
        try:
            try:
                with open(CFG_PATH) as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {'global': {}, 'files': {}}
            cfg.setdefault('global', {}); cfg.setdefault('files', {})
            s = self._cfg_defaults()
            fp = self._model.filepath
            if fp:
                cfg['files'][os.path.basename(fp)] = s
            else:
                cfg['global'] = s
            with open(CFG_PATH, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass
