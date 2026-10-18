"""
ff4_editor/ui_windowstate.py
window geometry, recent files and the title bar.
"""

import contextlib
import os

from .i18n import tr

APP_TITLE = "FF4 Script Editor"
MAX_RECENT = 8


class WindowStateMixin:
    """Mixin of FF4Editor: window geometry, recent files and the title bar."""

    # ── Window state / recent files ──────────────────────────────────────────

    def _restore_window_state(self):
        st = self._qsettings
        geo = st.value("window/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        sizes = st.value("window/splitter")
        if sizes:
            with contextlib.suppress(TypeError, ValueError):
                self._splitter.setSizes([int(x) for x in sizes])
        vis = st.value("window/sidebar_visible", True)
        self.act_sidebar.setChecked(str(vis).lower() not in ("false", "0"))

    def _save_window_state(self):
        st = self._qsettings
        st.setValue("window/geometry", self.saveGeometry())
        st.setValue("window/splitter", self._splitter.sizes())
        st.setValue("window/sidebar_visible", self.act_sidebar.isChecked())

    def _recent_files(self) -> list[str]:
        raw = self._qsettings.value("recent/files", [])
        paths = raw if isinstance(raw, list) else ([raw] if raw else [])
        return [p for p in paths if isinstance(p, str)]

    def _add_recent(self, path: str):
        path = os.path.abspath(path)
        files = [path] + [p for p in self._recent_files() if p != path]
        self._qsettings.setValue("recent/files", files[:MAX_RECENT])
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        files = [p for p in self._recent_files() if os.path.isfile(p)]
        for i, p in enumerate(files):
            a = self.recent_menu.addAction(f"&{i + 1}  {os.path.basename(p)}")
            a.setStatusTip(p)
            a.triggered.connect(lambda _=False, path=p: self._open_path(path))
        if files:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction(tr("Borrar lista"), self._clear_recent)
        self.recent_menu.setEnabled(bool(files))

    def _clear_recent(self):
        self._qsettings.setValue("recent/files", [])
        self._rebuild_recent_menu()

    def _update_title(self):
        fp = self._model.filepath
        if fp:
            self.setWindowTitle(f"{os.path.basename(fp)}[*] — {APP_TITLE}")
        else:
            self.setWindowTitle(APP_TITLE)
        self.setWindowModified(bool(self._model.dirty_keys))
