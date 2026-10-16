"""Tests de la ventana principal (offscreen, datos sintéticos)."""
import os
import shutil

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QAction, QSyntaxHighlighter
from PySide6.QtWidgets import QMessageBox, QPushButton

from ff4_editor.ui_build_dialog import BuildDialog


def pump(app, ms=30):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(app, cond, timeout_ms=5000):
    waited = 0
    while not cond() and waited < timeout_ms:
        pump(app, 20)
        waited += 20
    return cond()


@pytest.fixture
def win(qapp, data_path, font_png, tmp_path, monkeypatch):
    """FF4Editor con config en un directorio temporal y el JSON sintético ya cargado."""
    from ff4_editor import ui_mainwindow
    from ff4_editor.config_manager import ConfigManager
    monkeypatch.setattr(ui_mainwindow, "create_config_manager",
                        lambda cfg: ConfigManager(cfg, str(tmp_path / "cfg.json")))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    shutil.copy(font_png, os.path.join(os.path.dirname(data_path), "font.png"))
    w = ui_mainwindow.FF4Editor()
    w.show()
    w._load_file(data_path)
    pump(qapp)
    yield w
    w._model.dirty_keys.clear()
    w.close()
    pump(qapp, 10)


def select(app, w, key):
    for i in range(w.section_list.count()):
        if w.section_list.item(i)._section_key == key:
            w.section_list.setCurrentRow(i)
            pump(app, 10)
            return
    raise AssertionError(f"sección {key} no está en la lista")


def test_load_populates_sidebar_and_enables_buttons(qapp, win):
    keys = [win.section_list.item(i)._section_key for i in range(win.section_list.count())]
    assert "battleDialog" in keys and "itemNames" in keys
    assert win.build_btn.isEnabled() and win.run_btn.isEnabled()


def test_vwf_section_loads_cards_and_font(qapp, win):
    select(qapp, win, "battleDialog")
    assert len(win._canvas._cards) == 3
    assert win._canvas._vwf is not None


def test_activate_card_vwf_and_plain(qapp, win):
    ed = win._canvas._editor
    select(qapp, win, "battleDialog")
    assert ed.activate(0) is True
    ed.deactivate()
    select(qapp, win, "itemNames")                 # sección no-VWF (usaba QFontMetrics sin importar)
    assert ed.activate(0) is True
    ed.deactivate()


def test_commit_marks_dirty_and_pushes_undo(qapp, win):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "AA")
    assert win._model.get_entry("battleDialog", 0) == "AA"
    assert win.undo_stack.count() == 1 and "battleDialog" in win._model.dirty_keys


def test_undo_redo_restore_model_and_card(qapp, win):
    select(qapp, win, "battleDialog")
    old = win._model.get_entry("battleDialog", 0)
    win._on_card_committed("battleDialog", 0, "AA")
    win.undo_stack.undo()
    pump(qapp)
    assert win._model.get_entry("battleDialog", 0) == old
    assert win._canvas._cards[0].json_text == old          # la tarjeta se recarga tras undo
    win.undo_stack.redo()
    pump(qapp)
    assert win._canvas._cards[0].json_text == "AA"


def test_undo_redo_actions_are_registered(qapp, win):
    acts = [a for a in win.actions() if isinstance(a, QAction)]
    assert len(acts) >= 2
    assert {a.shortcut().toString() for a in acts} >= {"Ctrl+Z", "Ctrl+Shift+Z"}


def test_save_writes_file_and_clears_dirty(qapp, win, data_path):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "AA")
    win._on_save()
    assert not win._model.dirty_keys
    assert '"AA"' in open(data_path, encoding="utf-8").read()


def test_find_rom_prefers_sfc(qapp, win, data_path):
    assert win._find_rom() is None
    rom_dir = os.path.join(os.path.dirname(data_path), "rom")
    os.makedirs(rom_dir)
    open(os.path.join(rom_dir, "ff4-es.spc"), "w").close()
    assert win._find_rom().endswith("ff4-es.spc")
    open(os.path.join(rom_dir, "ff4-es.sfc"), "w").close()
    assert win._find_rom().endswith("ff4-es.sfc")


# ── Problemas conocidos (todo.md) ──────────────────────────────────────────────
def test_default_qt_theme_no_stylesheet(qapp, win):
    assert win.styleSheet() == ""
    assert win._canvas.grab().width() > 0          # la lona pinta con la paleta del sistema


def test_single_save_button(qapp, win):
    assert len([b for b in win.findChildren(QPushButton) if b.text() == "Save"]) == 1


def test_highlighters_do_not_accumulate(qapp, win):
    select(qapp, win, "battleDialog")
    ed = win._canvas._editor

    def count():
        return len([c for c in ed._overlay.document().children()
                    if isinstance(c, QSyntaxHighlighter)])
    for n in range(3):
        ed.activate(n)
    pump(qapp, 10)                       # deleteLater; the offscreen focus change may also deactivate
    assert count() == (1 if ed.active else 0)
    ed.deactivate()
    pump(qapp, 10)
    assert count() == 0


# ── BuildDialog ────────────────────────────────────────────────────────────────
def run_dialog(app, tmp_path, cmd, args):
    d = BuildDialog(str(tmp_path), cmd, args)
    d.start()
    assert wait_until(app, lambda: d._rerun_btn.isEnabled())
    return d


def test_build_dialog_success(qapp, tmp_path):
    d = run_dialog(qapp, tmp_path, "sh", ["-c", "echo hola; echo err >&2"])
    text = d._out.toPlainText()
    assert "hola" in text and "err" in text and "[OK]" in text
    assert d._status.text() == "Compilacion correcta"


def test_build_dialog_runs_in_workdir(qapp, tmp_path):
    d = run_dialog(qapp, tmp_path, "sh", ["-c", "pwd"])
    assert os.path.realpath(str(tmp_path)) in d._out.toPlainText()


def test_build_dialog_failure_code(qapp, tmp_path):
    d = run_dialog(qapp, tmp_path, "sh", ["-c", "exit 3"])
    assert "[ERROR]" in d._out.toPlainText() and "3" in d._status.text()


def test_build_dialog_missing_command(qapp, tmp_path):
    d = BuildDialog(str(tmp_path), "no_existe_este_comando_xyz", [])
    d.start()
    assert wait_until(qapp, lambda: d._status.text() == "No se pudo iniciar")


def test_build_dialog_strips_ansi(qapp, tmp_path):
    d = run_dialog(qapp, tmp_path, "sh", ["-c", r"printf '\033[31mrojo\033[0m\n'"])
    assert "rojo" in d._out.toPlainText() and "\x1b" not in d._out.toPlainText()


def test_build_dialog_stop_kills_process(qapp, tmp_path):
    d = BuildDialog(str(tmp_path), "sh", ["-c", "sleep 30"])
    d.start()
    pump(qapp, 100)
    d._stop()
    assert wait_until(qapp, lambda: d._rerun_btn.isEnabled())
    assert "[ERROR]" in d._out.toPlainText()
