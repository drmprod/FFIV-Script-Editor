# Latest fixes
- Checked against a real ld65 map of the Spanish build: used text + pointer table equals the segment size exactly for battleDialog, battleMessage, eventDialog1 (each pool), eventDialog2 and statusName. Capacity now leaves room for the pointer table (2 bytes/entry) and for the item_desc_id table (43 bytes) that share the segment, so overflows are no longer under-reported by up to 1 KB; `status_name` is mapped from the map/lnk (it only holds its pointers and text). Not verified: mapDialog (list of lists; pointer overhead not applied) and mapTitle (the map is 393 bytes larger than the text).
- Sections the encoder splits (`eventDialog1` -> `event_dlg1` + `event_dlg3`) are checked per segment: the first 256 entries must fit `event_dlg1` and the rest `event_dlg3`, not just the total (`FF4Model.overflow_bytes`, used by sidebar and status bar; only for exact capacities).
- Command highlighting and status-bar warning colours come from the palette (`theme.py`), readable on dark and light themes.
- Capacity no longer reports false overflows: the JSON `range` is the original (English) layout and a linker-script estimate is inexact without `start=`, so only fixed-length slots and sizes from the build's `rom/<name>.map` (ld65 `-m`) are treated as exact. Anything else is shown as an informational 'estimated capacity' (sidebar, status bar) and never as an overflow.
- The `\line` row in VWF mode is exactly one line pitch high (the separator glyph no longer pulls in a taller fallback font), so the text below stays aligned with the painted card; every overlay block gets a fixed line height in both modes.
- Byte counts now use a port of `romtools/text-codec.js` (`model/textcodec.py`) instead of the old `encode_size` approximation: longest-prefix match over the encoding's charTables (per-section `textEncoding`: dialog uses DTE, nullTerminated and fixedLength do not), parameters (`\\wait[..]`, `\\song[..]`), `\\charNN`, unknown characters skipped, terminator only where the tables define `\\0`. Shared-array dedup works on the real bytes. `mapDialog` counts a terminator per string (the encoder terminates each string). `model/encoding.py` is gone; `FF4Model.codec_for(section)` replaces `dte_set`.
- The editor's context menu is no longer transparent: the overlay's stylesheet is scoped to `QTextEdit#cardOverlay` (an unscoped rule was inherited by the popup).
- `\line` is a single character in the editor (U+2504, never drawn) shown as a dotted line by the canvas in both modes; Backspace/Delete remove it in one stroke, it can't be typed into or glued to a neighbouring line, and a stray glyph is dropped when saving.
- Interface translation with Qt `tr`: `ff4_editor/i18n.py`, `translations/ff4_en.ts/.qm` (complete English catalogue), language selector in Preferences (applied on restart), `make i18n`, `tests/test_i18n.py` (catalogue complete, placeholders/mnemonics consistent, window really switches language). Spanish stays the source language.
- Section sizes follow `rom-encoder.js`: dialog/battle sections without terminator/itemLength are 'shared arrays' where equal item bytes are stored once (including tails of longer items), so `used_bytes` now deduplicates the same way; `eventDialog1` is sized as two pools (first 256 entries + the rest, matching the event_dlg1/event_dlg3 split). fixedLength slots confirmed: an entry longer than the slot makes the real encoder throw.
- Capacity of `eventDialog1` now adds the `event_dlg3` segment when the section has more than 256 entries, as `encode-ff4.js` splits it (the ES JSON has 512 entries; before, it was compared against `event_dlg1` alone).
- fixedLength sections (attack/battle command/character/class/item/monster/spell names) no longer count terminators or a byte total, which wrongly showed battleCommandNames over capacity. The sidebar, status bar and card counters now show the longest entry vs the slot size (itemLength - begin, never below the longest entry already in the file; Spanish item names allow 23). Entries longer than their slot are flagged.
- Widgets use the public `EditorConfig.mono_font` instead of reaching into the private `_mono_font`.
- `ui_mainwindow.py` split into `ui_actions.py`, `ui_windowstate.py`, `ui_sections.py` mixins (995 -> 561 lines), no behaviour change.
- Ctrl+Intro (insert `\line`) and Ctrl+E work on the first try: edit actions now refresh as soon as a card is opened/closed or the selection changes (new `CardCanvas.active_changed`), and the overlay handles those keys itself.
- `{Name}` / `\charNN` are measured as worst case (6 x "W") for auto line breaks and the pixel counter; a short name like Cid no longer lets lines overflow after a rename.

# Changes in this round (against the 2nd zip)

Verified with `python3 -m pytest` (99 passed; the 18 former `xfail` bug markers are now plain regression tests) and an offscreen smoke run on the real `ff4-en-data.json` + `ff4-en.lnk` + `font.png` (all 15 sections load, cards activate, 0 errors).

## Main window (`ui_mainwindow.py`, `widgets/card_editor.py`)
- Removed the duplicated Save button.
- View changes are persisted again (`config_mgr.save` after `update_from_dialog`).
- Highlighters no longer accumulate: the previous one is detached and deleted on every `activate`/`deactivate`.
- `_reflow_overlay` no longer truncates to `line_limit` (it deleted text the user had just typed).

## Data (`errors.py`, `model/json_model.py`)
- `safe_json_load` reads `utf-8-sig` (BOM files load).
- `safe_json_save` is atomic (temp file in the same dir + fsync + `os.replace`), keeps `<file>.bak`, cleans its temp file on failure, and works for paths without a directory. Output format is unchanged: your real JSON re-serializes byte-for-byte, so no git noise.
- `set_entry` ignores out-of-range and negative indexes (negative used to write to the wrong entry), and does not mark dirty when the text did not change.
- JSON `range` capacity is inclusive (`e - s + 1`; itemNames 2303 -> 2304).

## Config (`config_manager.py`, `typed_config.py`)
- Rewritten as explicit layers: defaults < global < file < section override. Each layer stores only the keys set in it, and the effective config is recomputed from them. This fixes: global config never restored, file settings overwriting global with defaults, section overrides leaking into the saved file.
- "Apply globally" goes to the `global` layer (and drops the same key from the file layer so it does not shadow it); "this section only" goes to `section_overrides`.
- `font_changed` / `vwf_changed` are computed from the effective values before/after.
- `validate_config_dict`: range checks for every numeric key, valid colours only, rejects bool-as-int, inf/overflow; drops with a log line instead of raising. `SectionOverride.from_dict` validates and copies.
- Config file moved out of the package to `~/.config/ff4_editor/config.json` (override with `$FF4_EDITOR_CONFIG`); the legacy `ff4_editor/ff4_editor_config.json` is copied there on first run. Saves are atomic.
- Removed the unused and buggy `EditorSettings.merge`.

## Linker (`model/linker.py`)
- Line-based parser: ignores `#` comments, accepts attributes in any order.
- Removed the duplicate `_lnk_path_for_json`.
- Segment map now only contains segments that hold ONE text section (`event_dlg1/2/3`, `map_dlg`, `battle_dlg`, `battle_msg`, `item_desc`, `map_title`). `attack_name`, `char_name`, `status_name`, ... are intentionally NOT mapped: they also contain item/magic/class names, so using the whole segment would overstate each section's room. Those sections keep using the JSON `range`.
- Still a heuristic for segments without `start=` (documented in the module docstring); exact values need the ld65 `.map`.

## Text (`util/text_processing.py`)
- `\line` in the middle of a row (after text) is kept as literal `\line` in the display instead of silently dropping the text before it. This makes `json -> display -> json` lossless for all 7556 strings of the real JSON (it was 1 mismatch, mapDialog #65). Only that one string displays differently.
- Character names shared by several indexes stay as `\charNN` in the display (a `{Name}` could not be reverted safely).
- `reflow_text` never drops text; it takes `measure` instead of `line_limit`.

## Cleanup
- Unused imports removed (autoflake, `__init__` re-exports left alone), dead `safe_execute` branch, `.todo.md.kate-swp` deleted (it is in the new `.gitignore`).

## Dead code removed (vulture + manual check; tests and a run on the real JSON still pass)
- Theme (all of it): `ui_theme_dialog.py`, `ConfigManager.apply_theme/get_stylesheet`, `generate_stylesheet`, every `setStyleSheet`/`setObjectName` used for styling, and the `ui_bg`, `ui_card_bg`, `ui_text`, `ui_accent`, `band0_color`, `band1_color`, `show_colors` settings. The window uses the default Qt theme; the card canvas and highlighter take their colours from the active `QPalette` (`PaletteColors` in `constants.py`). Old config files with those keys still load (unknown keys are ignored). The game-accurate dialogue box colours (`VWF_BOX_BG`, `VWF_INK`) stay fixed on purpose.
- `errors.py`: `FileSaveError`, `FontError`, `ValidationError`, `get_logger`, `log_exception`, `handle_error`, `safe_execute`, `validate_dir_exists`, `safe_open_image`.
- `typed_config.py`: `ConfigKey.all_keys`, `EditorSettings.apply_to_config`, `EditorSettings.section_overrides` field, `SectionOverride.merge`.
- `text_processing.py`: the `CHAR_NAMES` proxy, `_notify_char_names_changed`, `reflow_text` (the app only uses `reflow_line`).
- `card_canvas.py`: `_total_height`, `_card_rect`, `_card_rect_v`, `_card_at` (compat wrappers nobody called); `card_layout.py`: `CardGeometry`, unused `scrollbar` parameter; `VWFFont.has`; `BuildDialog._workdir`; `WARN_LINE_CHARS`; the unconditional `[section selected]` debug print.
- Kept on purpose: `VWF_SECTION_LIMIT_PX` / `VWF_SECTION_PAGE_LINES` in `constants.py` are defined but nothing reads them yet (mapTitle should use 176 px and 2 lines); that looks like an unfinished feature, not dead code.

## Not done (still open in todo.md)
- `hard_char_limit` / `char_limit` options do nothing; `vwf_gap/space/line_pitch` have no control in ViewDialog.
- `eventDialog3` missing from `TEXT_SECTIONS` / `DIALOG_SECTIONS`.
- `encode_size` is not validated against the real encoder (`encode-ff4.js`); `used_bytes` for mapDialog is approximate.
- Three separate definitions of "control code" regexes; `TOKEN_PAT` punctuation gluing; `ViewDialog._on_apply` comparison against the effective config and `card_w` rounding.
- `isDirty` in the JSON is never cleared (probably intentional, for the encoder).
- Per-file config key is still the JSON basename.
- Observation: `battleCommandNames` shows used 149 > capacity 148 on the EN JSON; worth checking whether that is a real overflow or an off-by-one in `used_bytes`.


## Interface redesign (desktop conventions, Spanish UI)
- Main window rebuilt around `QMenuBar` (Archivo/Edición/Ver/Compilar/Ayuda), a `QToolBar` with standard icons (`QIcon.fromTheme` with `QStyle` fallback), a real `QStatusBar` (entry count, free bytes, usage bar) and standard shortcuts via `QKeySequence.StandardKey` (Ctrl+Q / Ctrl+, fallbacks where the platform has none). The old Open/Save/Build/Mesen/View/Ir a # buttons are gone.
- Window title uses `[*]` + `setWindowModified`; `_maybe_save()` asks Save/Discard/Cancel on close and on opening another file; a failed save keeps the window open.
- Recent files submenu; window geometry, splitter sizes and sidebar visibility stored in `QSettings`.
- Sidebar: `Qt.UserRole` key (`_item_key`) instead of a monkey-patched `_section_key`; bold for dirty sections, warning/error icons by capacity.
- Preferences dialog: grouped boxes, `QFormLayout`, `QDialogButtonBox` OK/Cancel, scope radio (all sections / this section) and "clear section overrides". The `hard_char_limit` checkbox was removed from the dialog (the setting still exists in config but does nothing).
- Everything user-visible is Spanish, including section names (`TEXT_SECTIONS`) and undo texts; `main.py` installs the Qt base translations for the system locale.
- Goto-entry moved to Ctrl+G (QInputDialog); the filter lives in the toolbar (Ctrl+F).
- Tests: 112 passed, 1 skipped; QSettings are isolated through `XDG_CONFIG_HOME` in `tests/conftest.py`.

## Second review: bugs found and fixed
- Typing one character closed the editor and scrolled to the top: every commit pushed an undo command whose `indexChanged` rebuilt the whole section. Now a push from the editor only refreshes the budget; undo/redo reload the section but keep the scroll position. Tests added.
- Consecutive edits of the same entry within 1.5 s merge into one undo step (`EditEntryCommand.mergeWith`).
- Compile and Mesen always used `ff4-es`; the target (and ROM name) now come from the open JSON (`ff4-jp-data.json` → `ff4-jp`).
- The build dialog decoded UTF-8 per chunk and could corrupt multibyte characters split across reads; it now uses an incremental decoder.


## Third pass: robustness, structure, tooling
- Errors: `safe_json_save` / `FF4Model.save` / `ConfigManager.save` raise `FileSaveError` (no more `False` / `RuntimeError`); loading raises `FileLoadError` with the cause chained; blind `except Exception` replaced by concrete exceptions (kept, documented, only where a plugin-like boundary needs it: callbacks, optional game font). A failed config save now warns the user; a corrupt config file is moved to `<config>.corrupt` and reported in the status bar instead of being silently overwritten.
- Undo/redo: the model emits `entry_changed(key, idx)`; undo/redo refresh only that card (no section rebuild), switch to the right section/map if needed, scroll only if the card is off screen, and close a stale editor without committing it.
- Canvas/editor API: the main window and tests no longer reach into private attributes (`cards`, `active_index`, `editor`, `scroll_value`, `refresh_card`, `index_of`, `ensure_visible`, `step_card`); dead `eventFilter` hook now implements Esc-to-close.
- Refactors: `_load_section` split (map selector / per-entry cards / filter), `paintEvent` split (frame / monospace text), `VWFFont.__init__` and `ttf_bytes` split into glyph loading, drop handling, glyph plan and drawing helpers (the generated glyph/cmap/metrics tables are identical to before; checked against the real font.png). Build dialog uses the right enum scopes and an incremental UTF-8 decoder.
- Types: mypy is clean (strict `disallow_untyped_defs` in `model/`, config, errors, typed_config, text_processing). Checking against the real PySide6 stubs also removed all short-form Qt enums that were deprecated.
- Tooling: `pyproject.toml` (ruff lint + format), `mypy.ini`, `Makefile` (`make check`), GitHub Actions workflow, `requirements-dev.txt` with ruff/mypy. Whole code base formatted with `ruff format`.
- New: find & replace across all sections (Ctrl+H) as one undo step; Alt+Down/Alt+Up to move between cards; Esc closes the editor.
- Verified on the real JSON: replace-all + undo + save reproduces the original text exactly (only the encoder's `isDirty` flags differ, by design).


## Fourth pass: review
Bugs fixed
- Reflow: a word longer than a whole line was only cut when it started the line; after other text it stayed over the limit. It could also split `\charNN`, `\wait[2x4]` or `{Name}` in two when cutting. Fixed (codes and names are atomic); fuzz-tested for width, idempotence and no text loss.
- `encode_size` charged 2 bytes to any code containing the substring "char" (`\charge`); only `\charNN` (and codes with arguments) cost 2.
- The "NNNpx" label on VWF cards was clipped; the card now reserves the measured width.
- `line_limit` (Preferences > "Límite de líneas") did nothing; a card over the limit now shows `n/limit líneas` in red.
- `VWF_SECTION_LIMIT_PX` / `VWF_SECTION_PAGE_LINES` were defined but unused: mapTitle now uses its 176 px, 2-line box as the section default (anything the user sets explicitly wins); page bands follow the section.
- Control codes and {Names} are now highlighted in monospace mode too (they only were in VWF mode).
- `hard_char_limit` removed (no UI, no effect). Old config files that contain it still load.
- `main.py` silently ignored a file argument that did not exist; it now says so (stderr + status bar).
Structure
- One definition of the code/name regexes (`util/patterns.py`); `EditorConfig` now extends `EditorSettings` (single list of settings), `_KEY_TYPES` derived from it, plus a test that keeps `ConfigKey` in sync.
- `used_bytes` is cached and updated incrementally on every edit (was re-encoding the whole section several times per keystroke).
- Game font loading moved out of the 1000-line window into `game_font.py`; make target / ROM / Mesen lookup into `build_tools.py` (both testable without a window). `open_file` is public.
- Removed dead members and inline imports; painter reuses one palette/font per paint.
Tests: 148 passed (reflow properties, tools, game font, config sync, find/replace, etc.).
