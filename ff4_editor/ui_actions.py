"""
ff4_editor/ui_actions.py
actions, menus, toolbar and their enabled state.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QLineEdit,
    QSizePolicy,
    QStyle,
    QToolBar,
    QWidget,
)

from .i18n import tr


class ActionsMixin:
    """Mixin of FF4Editor: actions, menus, toolbar and their enabled state."""

    def _icon(self, theme_name: str, fallback: QStyle.StandardPixmap) -> QIcon:
        return QIcon.fromTheme(theme_name, self.style().standardIcon(fallback))

    def _act(self, text, slot=None, keys=None, icon=None, tip=None) -> QAction:
        a = QAction(text, self)  # type: ignore[call-overload]
        if icon is not None:
            a.setIcon(icon)
        if keys is not None:
            a.setShortcuts(keys) if isinstance(keys, QKeySequence.StandardKey) else a.setShortcut(
                QKeySequence(keys)
            )
        if tip:
            a.setStatusTip(tip)
            a.setToolTip(tip)
        if slot is not None:
            a.triggered.connect(slot)
        return a

    def _create_actions(self):
        S = QStyle.StandardPixmap
        SK = QKeySequence.StandardKey
        c = self._canvas
        self.act_open = self._act(
            tr("&Abrir…"),
            self._on_open,
            SK.Open,
            self._icon("document-open", S.SP_DialogOpenButton),
            tr("Abrir un archivo ff4-xx-data.json"),
        )
        self.act_save = self._act(
            tr("&Guardar"),
            self._on_save,
            SK.Save,
            self._icon("document-save", S.SP_DialogSaveButton),
            tr("Guardar los cambios en el JSON (se deja una copia .bak)"),
        )
        self.act_quit = self._act(
            tr("&Salir"), self.close, SK.Quit, self._icon("application-exit", S.SP_DialogCloseButton)
        )
        if not self.act_quit.shortcuts():  # algunas plataformas no definen Quit
            self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))

        self.act_undo = self.undo_stack.createUndoAction(self, tr("Deshacer"))
        self.act_undo.setShortcuts(SK.Undo)
        self.act_undo.setIcon(self._icon("edit-undo", S.SP_ArrowBack))
        self.act_redo = self.undo_stack.createRedoAction(self, tr("Rehacer"))
        self.act_redo.setShortcuts(SK.Redo)
        self.act_redo.setIcon(self._icon("edit-redo", S.SP_ArrowForward))

        self.act_cut = self._act(tr("Cor&tar"), c.action_cut, SK.Cut, QIcon.fromTheme("edit-cut"))
        self.act_copy = self._act(tr("&Copiar"), c.action_copy, SK.Copy, QIcon.fromTheme("edit-copy"))
        self.act_paste = self._act(tr("&Pegar"), c.action_paste, SK.Paste, QIcon.fromTheme("edit-paste"))
        self.act_select_all = self._act(tr("Seleccionar &todo"), c.action_select_all, SK.SelectAll)
        self.act_insert_line = self._act(
            tr("Insertar línea en blanco (\\line)"),
            c.action_insert_blank_line,
            "Ctrl+Return",
            tip=tr("Inserta una línea separadora de página en el cursor"),
        )
        self.act_centre = self._act(
            tr("Cen&trar líneas"), c.action_centre_lines, "Ctrl+E", tip=tr("Centra las líneas seleccionadas")
        )
        self.act_find = self._act(
            tr("&Filtrar cadenas"),
            self._focus_filter,
            SK.Find,
            self._icon("edit-find", S.SP_FileDialogContentsView),
            tr("Filtrar las tarjetas por texto o número"),
        )
        self.act_replace = self._act(
            tr("Buscar y &reemplazar…"),
            self._on_find_replace,
            "Ctrl+H",
            tip=tr("Buscar y reemplazar en todas las secciones"),
        )
        self.act_next_card = self._act(
            tr("Tarjeta si&guiente"),
            lambda: self._canvas.step_card(+1),
            "Alt+Down",
            tip=tr("Editar la tarjeta siguiente"),
        )
        self.act_prev_card = self._act(
            tr("Tarjeta &anterior"),
            lambda: self._canvas.step_card(-1),
            "Alt+Up",
            tip=tr("Editar la tarjeta anterior"),
        )
        self.act_goto = self._act(
            tr("&Ir a entrada…"), self._on_goto, "Ctrl+G", tip=tr("Saltar a una entrada o mapa por número")
        )
        self.act_prefs = self._act(
            tr("Pre&ferencias…"),
            self._on_preferences,
            SK.Preferences,
            self._icon("preferences-system", S.SP_FileDialogDetailedView),
            tr("Fuente, tamaño de tarjetas, límites y fuente del juego"),
        )
        if not self.act_prefs.shortcuts():
            self.act_prefs.setShortcut(QKeySequence("Ctrl+,"))
        self.act_sidebar = self._act(tr("Barra de &secciones"), None, "F9")
        self.act_sidebar.setCheckable(True)
        self.act_sidebar.setChecked(True)
        self.act_sidebar.toggled.connect(self.section_list.setVisible)

        self.act_build = self._act(
            tr("&Compilar"),
            self._on_build,
            "Ctrl+B",
            self._icon("system-run", S.SP_MediaPlay),
            tr("Ejecutar «make ff4-es» en el directorio del JSON"),
        )
        self.act_run = self._act(
            tr("&Ejecutar en Mesen"),
            self._on_run_mesen,
            "F5",
            self._icon("media-playback-start", S.SP_MediaSeekForward),
            tr("Abrir la ROM compilada (rom/ff4-es.sfc junto al JSON) en Mesen"),
        )
        self.act_about = self._act(tr("&Acerca de…"), self._on_about)

        for a in (
            self.act_open,
            self.act_save,
            self.act_quit,
            self.act_undo,
            self.act_redo,
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_select_all,
            self.act_insert_line,
            self.act_centre,
            self.act_find,
            self.act_goto,
            self.act_replace,
            self.act_next_card,
            self.act_prev_card,
            self.act_prefs,
            self.act_sidebar,
            self.act_build,
            self.act_run,
        ):
            self.addAction(a)  # shortcuts work everywhere in the window

    def _create_menus(self):
        mb = self.menuBar()
        m = mb.addMenu(tr("&Archivo"))
        m.addAction(self.act_open)
        self.recent_menu = m.addMenu(tr("Abrir &reciente"))
        m.addSeparator()
        m.addAction(self.act_save)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = mb.addMenu(tr("&Edición"))
        for a in (
            self.act_undo,
            self.act_redo,
            None,
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_select_all,
            None,
            self.act_insert_line,
            self.act_centre,
            None,
            self.act_find,
            self.act_replace,
            self.act_goto,
            self.act_next_card,
            self.act_prev_card,
            None,
            self.act_prefs,
        ):
            m.addSeparator() if a is None else m.addAction(a)
        m.aboutToShow.connect(self._update_edit_actions)

        m = mb.addMenu(tr("&Ver"))
        m.addAction(self.act_sidebar)

        m = mb.addMenu(tr("&Compilar"))
        m.addAction(self.act_build)
        m.addAction(self.act_run)

        m = mb.addMenu(tr("A&yuda"))
        m.addAction(self.act_about)
        self._rebuild_recent_menu()

    def _create_toolbar(self):
        tb = QToolBar(tr("Principal"), self)  # type: ignore[call-overload]
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        for a in (
            self.act_open,
            self.act_save,
            None,
            self.act_undo,
            self.act_redo,
            None,
            self.act_build,
            self.act_run,
        ):
            tb.addSeparator() if a is None else tb.addAction(a)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(tr("Filtrar cadenas (Ctrl+F)"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMaximumWidth(280)
        self.filter_edit.setAccessibleName(tr("Filtrar cadenas"))
        self.filter_edit.textChanged.connect(lambda *_: self._filter_timer.start())
        tb.addWidget(self.filter_edit)
        self.addToolBar(tb)

    def _set_file_actions_enabled(self, on: bool):
        for a in (
            self.act_save,
            self.act_build,
            self.act_run,
            self.act_find,
            self.act_replace,
            self.act_goto,
            self.act_next_card,
            self.act_prev_card,
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_select_all,
            self.act_insert_line,
            self.act_centre,
        ):
            a.setEnabled(on)
        self.filter_edit.setEnabled(on)

    def _update_edit_actions(self):
        """Enable the text actions only when a card is being edited."""
        ed = self._canvas.editor
        active = bool(self._model.filepath) and ed.active
        has_sel = active and ed.overlay.textCursor().hasSelection()
        self.act_cut.setEnabled(bool(has_sel))
        self.act_copy.setEnabled(bool(has_sel))
        for a in (self.act_paste, self.act_select_all, self.act_insert_line, self.act_centre):
            a.setEnabled(bool(active))
