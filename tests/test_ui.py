"""Tests de la ventana principal (offscreen, datos sintéticos)."""

import os
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QSyntaxHighlighter
from PySide6.QtWidgets import QMessageBox

from ff4_editor.build_tools import find_rom, make_target
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

    monkeypatch.setattr(
        ui_mainwindow, "create_config_manager", lambda cfg: ConfigManager(cfg, str(tmp_path / "cfg.json"))
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Ok)
    shutil.copy(font_png, os.path.join(os.path.dirname(data_path), "font.png"))
    w = ui_mainwindow.FF4Editor()
    w.show()
    w.open_file(data_path)
    pump(qapp)
    yield w
    w._model.dirty_keys.clear()
    w.close()
    pump(qapp, 10)


def select(app, w, key):
    for i in range(w.section_list.count()):
        if w._item_key(w.section_list.item(i)) == key:
            w.section_list.setCurrentRow(i)
            pump(app, 10)
            return
    raise AssertionError(f"sección {key} no está en la lista")


def test_load_populates_sidebar_and_enables_buttons(qapp, win):
    keys = [win._item_key(win.section_list.item(i)) for i in range(win.section_list.count())]
    assert "battleDialog" in keys and "itemNames" in keys
    assert win.act_build.isEnabled() and win.act_run.isEnabled() and win.act_save.isEnabled()


def test_vwf_section_loads_cards_and_font(qapp, win):
    select(qapp, win, "battleDialog")
    assert len(win._canvas.cards) == 3
    assert win._canvas.vwf is not None


def test_activate_card_vwf_and_plain(qapp, win):
    ed = win._canvas.editor
    select(qapp, win, "battleDialog")
    assert ed.activate(0) is True
    ed.deactivate()
    select(qapp, win, "itemNames")  # sección no-VWF (usaba QFontMetrics sin importar)
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
    assert win._canvas.cards[0].json_text == old  # la tarjeta se recarga tras undo
    win.undo_stack.redo()
    pump(qapp)
    assert win._canvas.cards[0].json_text == "AA"


def test_undo_redo_actions_are_registered(qapp, win):
    from PySide6.QtGui import QKeySequence

    assert QKeySequence(QKeySequence.StandardKey.Undo) in win.act_undo.shortcuts()
    assert QKeySequence(QKeySequence.StandardKey.Redo) in win.act_redo.shortcuts()
    assert win.act_undo in win.actions() and win.act_redo in win.actions()


def test_save_writes_file_and_clears_dirty(qapp, win, data_path):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "AA")
    win._on_save()
    assert not win._model.dirty_keys
    assert '"AA"' in Path(data_path).read_text(encoding="utf-8")


def test_find_rom_prefers_sfc(qapp, win, data_path):
    assert find_rom(win._model.filepath) is None
    rom_dir = os.path.join(os.path.dirname(data_path), "rom")
    os.makedirs(rom_dir)
    Path(rom_dir, "ff4-xx.spc").touch()
    assert find_rom(win._model.filepath).endswith("ff4-xx.spc")
    Path(rom_dir, "ff4-xx.sfc").touch()
    assert find_rom(win._model.filepath).endswith("ff4-xx.sfc")


# ── Problemas conocidos (todo.md) ──────────────────────────────────────────────
def test_default_qt_theme_no_stylesheet(qapp, win):
    assert win.styleSheet() == ""
    assert win._canvas.grab().width() > 0  # la lona pinta con la paleta del sistema


def test_highlighters_do_not_accumulate(qapp, win):
    select(qapp, win, "battleDialog")
    ed = win._canvas.editor

    def count():
        return len([c for c in ed._overlay.document().children() if isinstance(c, QSyntaxHighlighter)])

    for n in range(3):
        ed.activate(n)
    pump(qapp, 10)  # deleteLater; the offscreen focus change may also deactivate
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


# ── Interfaz estándar ──────────────────────────────────────────────────────────
def menu_titles(w):
    return [a.text().replace("&", "") for a in w.menuBar().actions()]


def test_menu_bar_layout(qapp, win):
    assert menu_titles(win) == ["Archivo", "Edición", "Ver", "Compilar", "Ayuda"]


def test_standard_shortcuts(qapp, win):
    from PySide6.QtGui import QKeySequence as K

    SK = K.StandardKey
    for act, std in (
        (win.act_open, SK.Open),
        (win.act_save, SK.Save),
        (win.act_find, SK.Find),
        (win.act_cut, SK.Cut),
        (win.act_copy, SK.Copy),
        (win.act_paste, SK.Paste),
    ):
        assert K(std) in act.shortcuts(), act.text()
    assert win.act_quit.shortcuts() and win.act_prefs.shortcuts()  # estándar de la plataforma o Ctrl+Q


def test_toolbar_has_main_actions(qapp, win):
    from PySide6.QtWidgets import QToolBar

    tb = win.findChild(QToolBar)
    acts = tb.actions()
    for a in (win.act_open, win.act_save, win.act_undo, win.act_redo, win.act_build, win.act_run):
        assert a in acts
    assert all(not a.icon().isNull() for a in (win.act_open, win.act_save, win.act_build))


def test_file_actions_disabled_without_file(qapp, tmp_path, monkeypatch):
    from ff4_editor import ui_mainwindow
    from ff4_editor.config_manager import ConfigManager

    monkeypatch.setattr(
        ui_mainwindow, "create_config_manager", lambda cfg: ConfigManager(cfg, str(tmp_path / "c.json"))
    )
    w = ui_mainwindow.FF4Editor()
    assert not w.act_save.isEnabled() and not w.act_build.isEnabled() and not w.filter_edit.isEnabled()
    assert w.windowTitle() == ui_mainwindow.APP_TITLE


def test_title_and_modified_flag(qapp, win):
    assert "[*]" in win.windowTitle() and "ff4-xx-data.json" in win.windowTitle()
    assert not win.isWindowModified()
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "AA")
    assert win.isWindowModified()
    win._on_save()
    assert not win.isWindowModified()


def test_edit_actions_follow_active_card(qapp, win):
    select(qapp, win, "battleDialog")
    win._update_edit_actions()
    assert not win.act_cut.isEnabled() and not win.act_paste.isEnabled()
    win._canvas.editor.activate(0)
    win._update_edit_actions()
    assert win.act_paste.isEnabled() and win.act_select_all.isEnabled()
    assert not win.act_copy.isEnabled()  # sin selección


def test_sidebar_uses_item_data_and_spanish_labels(qapp, win):
    it = win.section_list.item(0)
    assert win._item_key(it) in ("attackNames", "battleDialog", "characterNames", "itemNames", "mapDialog")
    assert "Diálogos de batalla" in [win.section_list.item(i).text() for i in range(win.section_list.count())]


def test_sidebar_modified_section_is_bold(qapp, win):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "AA")
    it = next(
        win.section_list.item(i)
        for i in range(win.section_list.count())
        if win._item_key(win.section_list.item(i)) == "battleDialog"
    )
    assert it.font().bold()
    win._on_save()
    assert not it.font().bold()


def test_budget_in_status_bar(qapp, win):
    select(qapp, win, "battleDialog")
    # the synthetic JSON only has a `range` (an estimate), so no free/over claim is made
    assert "capacidad estimada" in win.budget_lbl.text()
    assert "entradas" in win.count_lbl.text()


def test_filter_debounced_and_clear(qapp, win):
    select(qapp, win, "battleDialog")
    win.filter_edit.setText("Cecil")
    assert wait_until(qapp, lambda: len(win._canvas.cards) == 1)
    assert "mostradas" in win.count_lbl.text()
    win.filter_edit.clear()
    assert wait_until(qapp, lambda: len(win._canvas.cards) == 3)


def test_goto_entry(qapp, win, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    select(qapp, win, "battleDialog")
    monkeypatch.setattr(QInputDialog, "getInt", lambda *a, **k: (2, True))
    win._on_goto()
    assert "#002" in win.statusBar().currentMessage()


def test_recent_files_menu(qapp, win, data_path):
    assert win.recent_menu.isEnabled()
    first = win.recent_menu.actions()[0]
    assert "ff4-xx-data.json" in first.text()
    win._clear_recent()
    assert not win.recent_menu.isEnabled()


def test_unsaved_changes_prompt_on_close_and_open(qapp, win, monkeypatch):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "AA")
    answers = []

    def fake(*a, **k):
        answers.append(1)
        return QMessageBox.Cancel

    monkeypatch.setattr(QMessageBox, "warning", fake)
    assert win._maybe_save() is False and win._model.dirty_keys
    from PySide6.QtGui import QCloseEvent

    ev = QCloseEvent()
    win.closeEvent(ev)
    assert not ev.isAccepted()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Discard)
    assert win._maybe_save() is True


def test_failed_save_keeps_window_open(qapp, win, monkeypatch):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "AA")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Save)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: QMessageBox.Ok)
    from ff4_editor.errors import FileSaveError

    monkeypatch.setattr(win._model, "save", lambda: (_ for _ in ()).throw(FileSaveError("x.json", "disk")))
    assert win._maybe_save() is False


def test_window_state_persisted(qapp, win):
    win._save_window_state()
    assert win._qsettings.value("window/geometry") is not None


# ── Diálogo de preferencias ────────────────────────────────────────────────────
def make_dialog(win, section="battleDialog", override=False):
    from ff4_editor.ui_view_dialog import ViewDialog

    return ViewDialog(
        win.config, section=section, section_label="Diálogos de batalla", has_section_override=override
    )


def test_prefs_dialog_standard_buttons(qapp, win):
    from PySide6.QtWidgets import QDialogButtonBox

    d = make_dialog(win)
    bb = d.findChild(QDialogButtonBox)
    assert bb.button(QDialogButtonBox.StandardButton.Ok) and bb.button(QDialogButtonBox.StandardButton.Cancel)


def test_prefs_dialog_no_change_gives_empty_result(qapp, win):
    d = make_dialog(win)
    d._on_apply()
    assert d.result_settings == {} and d.section_only is False


def test_prefs_dialog_collects_changes_and_scope(qapp, win):
    d = make_dialog(win)
    d.spin_rows.setValue(win.config.card_rows + 1)
    d.spin_vwf_limit.setValue(200)
    d.rb_section.setChecked(True)
    d._on_apply()
    assert d.result_settings == {"card_rows": win.config.card_rows + 1, "vwf_limit_px": 200}
    assert d.section_only is True


def test_prefs_dialog_clear_override_button(qapp, win):
    d = make_dialog(win, override=True)
    d.clr_btn.click()
    assert d.clear_section is True and d.result_settings == {}


def test_prefs_dialog_no_scope_without_section(qapp, win):
    d = make_dialog(win, section=None)
    assert not hasattr(d, "rb_section")
    d._on_apply()
    assert d.section_only is False


# ── Regresiones: editar no debe recargar la sección ───────────────────────────
def test_typing_keeps_editor_open_and_scroll(qapp, win):
    from PySide6.QtTest import QTest

    select(qapp, win, "battleDialog")
    ed = win._canvas.editor
    ed.activate(1)
    QTest.keyClicks(ed.overlay, "ab")
    assert wait_until(qapp, lambda: win.undo_stack.count() >= 1)
    assert win._canvas.active_index == 1 and ed.overlay.isVisible()


def test_commit_keeps_scroll_and_undo_reveals_the_card(qapp, win):
    select(qapp, win, "battleDialog")
    vb = win._canvas._vbar
    vb.setMaximum(1000)
    vb.setValue(50)
    win._on_card_committed("battleDialog", 0, "AA")
    assert vb.value() == 50
    win.undo_stack.undo()
    assert vb.value() == 0  # la tarjeta 0 no estaba a la vista: se la muestra
    assert win._model.get_entry("battleDialog", 0) != "AA"


def test_consecutive_edits_merge_into_one_undo_step(qapp, win):
    select(qapp, win, "battleDialog")
    for t in ("A", "AB", "ABC"):
        win._on_card_committed("battleDialog", 0, t)
    assert win.undo_stack.count() == 1
    win.undo_stack.undo()
    assert win._model.get_entry("battleDialog", 0) != "ABC"


def test_make_target_follows_json_name(qapp, win, monkeypatch):
    monkeypatch.setattr(type(win._model), "filepath", property(lambda s: "/x/ff4-jp-data.json"))
    assert make_target(win._model.filepath) == "ff4-jp"
    monkeypatch.setattr(type(win._model), "filepath", property(lambda s: "/x/otro.json"))
    assert make_target(win._model.filepath) == "ff4-es"


def test_config_save_failure_is_reported_not_silent(qapp, win, monkeypatch):
    from ff4_editor.errors import FileSaveError

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    monkeypatch.setattr(
        win.config_mgr, "save", lambda *a: (_ for _ in ()).throw(FileSaveError("c.json", "disco lleno"))
    )
    assert win._save_config() is False
    assert shown and "disco lleno" in shown[0]


def test_corrupt_config_warning_reaches_status_bar(qapp, win):
    win.config_mgr.warnings.append("config rota de prueba")
    win._show_config_warnings()
    assert "config rota de prueba" in win.statusBar().currentMessage()


def test_undo_refreshes_only_that_card(qapp, win):
    select(qapp, win, "battleDialog")
    before = win._canvas.cards[:]
    old = win._model.get_entry("battleDialog", 1)
    win._on_card_committed("battleDialog", 1, "NUEVO")
    win.undo_stack.undo()
    assert win._canvas.cards == before  # mismos objetos: no se recargó
    assert win._canvas.cards[1].json_text == old
    win.undo_stack.redo()
    assert win._canvas.cards[1].json_text == "NUEVO"


def test_undo_closes_stale_editor_without_recommitting(qapp, win):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 1, "NUEVO")
    win._canvas.editor.activate(1)
    n = win.undo_stack.count()
    win.undo_stack.undo()
    assert win._canvas.active_index == -1
    assert win.undo_stack.count() == n and win._model.get_entry("battleDialog", 1) != "NUEVO"


def test_undo_in_other_section_switches_to_it(qapp, win):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 1, "NUEVO")
    select(qapp, win, "itemNames")
    win.undo_stack.undo()
    assert win._cur_section == "battleDialog"
    assert win._canvas.cards[1].json_text != "NUEVO"


# ── Buscar y reemplazar / navegación ──────────────────────────────────────────
def make_find(win, text, **flags):
    win._on_find_replace()
    d = win._find_dlg
    d.find_edit.setText(text)
    d.chk_case.setChecked(flags.get("case", False))
    d.chk_regex.setChecked(flags.get("regex", False))
    d.chk_current.setChecked(flags.get("current", False))
    d.search()
    return d


def test_find_across_sections_and_current_only(qapp, win):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "zzmarca uno")
    win._on_card_committed("battleDialog", 1, "ZZMARCA dos")
    assert len(make_find(win, "zzmarca")._hits) == 2
    assert len(make_find(win, "zzmarca", case=True)._hits) == 1
    assert len(make_find(win, "zzmarca", current=True)._hits) == 2
    assert make_find(win, "zzmarca", current=True).results.topLevelItemCount() == 2


def test_find_bad_regex_and_empty_query_are_reported(qapp, win):
    d = make_find(win, "(", regex=True)
    assert "inválida" in d.status.text() and not d.btn_replace.isEnabled()
    d = make_find(win, "")
    assert "vacía" in d.status.text()


def test_replace_all_is_one_undo_step_and_updates_cards(qapp, win):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "foo bar foo")
    win._on_card_committed("battleDialog", 1, "FOO")
    win.undo_stack.clear()
    d = make_find(win, "foo")
    d.replace_edit.setText("x")
    d.replace_all()
    assert win._model.get_entry("battleDialog", 0) == "x bar x"
    assert win._model.get_entry("battleDialog", 1) == "x"
    assert win._canvas.cards[0].json_text == "x bar x"
    assert win.undo_stack.count() == 1
    win.undo_stack.undo()
    assert win._model.get_entry("battleDialog", 0) == "foo bar foo"
    assert win._model.get_entry("battleDialog", 1) == "FOO"


def test_replace_regex_backreference_and_literal_backslash(qapp, win):
    select(qapp, win, "battleDialog")
    win._on_card_committed("battleDialog", 0, "ab12")
    d = make_find(win, r"([a-z]+)(\d+)", regex=True, current=True)
    d.replace_edit.setText(r"\2\1")
    d.replace_all()
    assert win._model.get_entry("battleDialog", 0) == "12ab"
    d = make_find(win, "12", current=True)
    d.replace_edit.setText(r"\wait")  # literal: sin interpretar la barra
    d.replace_all()
    assert win._model.get_entry("battleDialog", 0) == r"\waitab"


def test_goto_from_find_result_opens_card(qapp, win):
    select(qapp, win, "itemNames")
    win._goto_entry("battleDialog", 2)
    assert win._cur_section == "battleDialog"
    assert win._canvas.active_index == win._canvas.index_of("battleDialog", 2)


def test_alt_arrows_step_between_cards_and_esc_closes(qapp, win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    select(qapp, win, "battleDialog")
    c = win._canvas
    assert c.step_card(+1) and c.active_index == 0
    assert c.step_card(+1) and c.active_index == 1
    assert c.step_card(-1) and c.active_index == 0
    c.step_card(-1)
    assert c.active_index == 0  # no pasa del primero
    QTest.keyClick(c.editor.overlay, Qt.Key.Key_Escape)
    assert c.active_index == -1


def test_step_card_commits_previous_edit(qapp, win):
    select(qapp, win, "battleDialog")
    c = win._canvas
    c.step_card(+1)
    c.editor.overlay.setPlainText("CAMBIADO")
    qapp.processEvents()
    c.step_card(+1)
    assert win._model.get_entry("battleDialog", 0) == "CAMBIADO"


def test_run_mesen_reports_missing_rom_and_missing_emulator(qapp, win, monkeypatch):
    from ff4_editor import ui_mainwindow

    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    win._on_run_mesen()
    assert "ff4-xx" in shown[-1]  # no hay ROM compilada
    monkeypatch.setattr(ui_mainwindow, "find_rom", lambda fp: "/tmp/x.sfc")
    monkeypatch.setattr(ui_mainwindow, "find_mesen", lambda: None)
    win._on_run_mesen()
    assert "Mesen" in shown[-1] and "PATH" in shown[-1]


def test_vwf_card_is_wide_enough_for_pixel_counter(qapp, win):
    from PySide6.QtGui import QFontMetrics

    select(qapp, win, "battleDialog")
    lay = win._canvas._layout
    box = win.config.vwf_limit_px * win.config.vwf_scale
    room = lay.card_w - 2 * lay.CARD_INNER - box - 6
    assert room >= QFontMetrics(win.config.mono_font).horizontalAdvance("999px")


# ── Regresión: Ctrl+Intro (insertar \line) debe funcionar a la primera ────────
def test_edit_actions_enabled_without_opening_edit_menu(qapp, win):
    select(qapp, win, "battleDialog")
    assert not win.act_insert_line.isEnabled()
    win._canvas.editor.activate(0)  # sin llamar a _update_edit_actions ni abrir el menú
    assert win.act_insert_line.isEnabled() and win.act_centre.isEnabled()
    win._canvas.editor.deactivate()
    assert not win.act_insert_line.isEnabled()


def test_ctrl_return_inserts_exactly_one_blank_line_first_try(qapp, win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    select(qapp, win, "battleDialog")
    ed = win._canvas.editor
    ed.activate(0)
    before = ed.overlay.document().blockCount()
    QTest.keyClick(ed.overlay, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert ed.overlay.document().blockCount() == before + 1
    # con la acción deshabilitada a mano (estado "viejo") sigue funcionando, una sola vez
    win.act_insert_line.setEnabled(False)
    QTest.keyClick(ed.overlay, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert ed.overlay.document().blockCount() == before + 2


def test_preferences_saves_ui_language(qapp, win):
    from PySide6.QtCore import QSettings

    from ff4_editor.ui_view_dialog import ViewDialog

    dlg = ViewDialog(win.config)
    assert dlg.combo_lang.currentData() == "auto"
    dlg.combo_lang.setCurrentIndex(dlg.combo_lang.findData("en"))
    dlg._on_apply()
    assert QSettings("ff4_editor", "ff4_editor_vwf").value("ui/language") == "en"
    QSettings("ff4_editor", "ff4_editor_vwf").remove("ui/language")


# ── Idioma de la interfaz ─────────────────────────────────────────────────────
def test_main_window_uses_the_selected_language(qapp, win):
    from ff4_editor import i18n

    assert win.act_open.text() == "&Abrir…"
    i18n.install_language("en")
    try:
        from ff4_editor import ui_mainwindow

        w2 = ui_mainwindow.FF4Editor()
        assert [a.text() for a in w2.menuBar().actions()] == ["&File", "&Edit", "&View", "&Build", "&Help"]
        assert w2.act_open.text() == "&Open…"
        w2.close()
    finally:
        i18n.install_language("es")


# ── \line es un solo carácter y el menú contextual no es transparente ─────────
def _open_blank_card(qapp, win, text="AB\nCD"):
    from ff4_editor.constants import BLANK_LINE_DISPLAY

    select(qapp, win, "battleDialog")
    ed = win._canvas.editor
    ed.activate(0)
    ed.overlay.setPlainText(text.replace("|", BLANK_LINE_DISPLAY))
    return ed


def _key(ed, key):
    from PySide6.QtTest import QTest

    QTest.keyClick(ed.overlay, key)


def _cursor_at(ed, block, pos):
    from PySide6.QtGui import QTextCursor

    blk = ed.overlay.document().findBlockByNumber(block)
    cur = QTextCursor(blk)
    cur.setPosition(blk.position() + pos)
    ed.overlay.setTextCursor(cur)


def test_line_separator_is_one_character(qapp):
    from ff4_editor.constants import BLANK_LINE_DISPLAY

    assert len(BLANK_LINE_DISPLAY) == 1


def test_separator_row_has_the_same_height_as_a_text_row(qapp, win):
    ed = _open_blank_card(qapp, win, "AB\n|\nCD\nEF")
    for _ in range(5):
        qapp.processEvents()
    doc = ed.overlay.document()
    lay = doc.documentLayout()
    heights = {
        round(lay.blockBoundingRect(doc.findBlockByNumber(i)).height(), 1) for i in range(doc.blockCount())
    }
    assert heights == {float(ed._line_h())}


def test_backspace_after_separator_removes_it_whole(qapp, win):
    ed = _open_blank_card(qapp, win, "AB\n|\nCD")
    _cursor_at(ed, 1, 1)
    _key(ed, Qt.Key.Key_Backspace)
    assert ed.overlay.toPlainText() == "AB\nCD"


def test_backspace_below_separator_removes_it_whole(qapp, win):
    ed = _open_blank_card(qapp, win, "AB\n|\nCD")
    _cursor_at(ed, 2, 0)
    _key(ed, Qt.Key.Key_Backspace)
    assert ed.overlay.toPlainText() == "AB\nCD"


def test_delete_removes_separator_whole(qapp, win):
    ed = _open_blank_card(qapp, win, "AB\n|\nCD")
    _cursor_at(ed, 1, 0)
    _key(ed, Qt.Key.Key_Delete)
    assert ed.overlay.toPlainText() == "AB\nCD"
    ed = _open_blank_card(qapp, win, "AB\n|\nCD")
    _cursor_at(ed, 0, 2)
    _key(ed, Qt.Key.Key_Delete)  # end of the line above
    assert ed.overlay.toPlainText() == "AB\nCD"


def test_last_separator_and_only_separator(qapp, win):
    ed = _open_blank_card(qapp, win, "AB\n|")
    _cursor_at(ed, 1, 1)
    _key(ed, Qt.Key.Key_Backspace)
    assert ed.overlay.toPlainText() == "AB"
    ed = _open_blank_card(qapp, win, "|")
    _cursor_at(ed, 0, 1)
    _key(ed, Qt.Key.Key_Backspace)
    assert ed.overlay.toPlainText() == ""


def test_cannot_type_into_or_glue_to_a_separator(qapp, win):
    from PySide6.QtTest import QTest

    ed = _open_blank_card(qapp, win, "AB\n|\nCD")
    _cursor_at(ed, 1, 1)
    QTest.keyClicks(ed.overlay, "xyz")
    assert ed.overlay.toPlainText() == "AB\n┄\nCD"
    ed.overlay.setPlainText("AB\n┄\nCD")
    _cursor_at(ed, 1, 0)
    _key(ed, Qt.Key.Key_Backspace)
    assert ed.overlay.toPlainText() == "AB\n┄\nCD"


def test_separator_roundtrip_and_stray_glyph(qapp):
    from ff4_editor.util.text_processing import display_to_json, json_to_display

    assert json_to_display(r"AB\n\lineCD") == "AB\n┄\nCD"
    assert display_to_json("AB\n┄\nCD") == r"AB\n\lineCD"
    assert display_to_json("A┄B") == "AB"  # a glyph glued to text is not a separator


def test_overlay_context_menu_is_not_transparent(qapp, win):
    from PySide6.QtCore import QPoint

    ed = _open_blank_card(qapp, win)
    menu = ed.overlay.createStandardContextMenu()
    menu.popup(ed.overlay.mapToGlobal(QPoint(5, 5)))
    pump(qapp, 20)
    bg = menu.palette().window().color()
    assert menu.styleSheet() == ""
    assert win._canvas.editor.overlay.styleSheet().startswith("QTextEdit#cardOverlay")
    img = menu.grab().toImage()
    px = img.pixelColor(img.width() // 2, 2)
    assert px.alpha() == 255 and bg.alpha() == 255
    menu.close()


def test_estimated_capacity_never_claims_an_overflow(qapp, win):
    select(qapp, win, "battleDialog")
    m = win._model
    m._caps["battleDialog"], m._caps_exact["battleDialog"] = 1, False
    m._used["battleDialog"] = 50
    win._refresh_budget("battleDialog")
    assert "Excede" not in win.budget_lbl.text() and win.budget_lbl.styleSheet() == ""
    win._refresh_sidebar_item("battleDialog")
    item = next(
        win.section_list.item(i)
        for i in range(win.section_list.count())
        if win._item_key(win.section_list.item(i)) == "battleDialog"
    )
    assert item.icon().isNull() and "estimada" in item.toolTip()


def test_exact_capacity_still_reports_an_overflow(qapp, win):
    select(qapp, win, "battleDialog")
    m = win._model
    m._caps["battleDialog"], m._caps_exact["battleDialog"] = 1, True
    m._used["battleDialog"] = 50
    win._refresh_budget("battleDialog")
    assert "Excede por 49" in win.budget_lbl.text()
