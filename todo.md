# TODO — ff4_editor_vwf (open items only)

All P0 items and the P1 data-loss/config/capacity/reflow fixes from the first review are done (see CHANGES.md). The UI now follows desktop conventions (menus, toolbar, status bar, standard shortcuts, `[*]` title, unsaved-changes prompt, recent files, saved geometry, Spanish text, default Qt theme).

## Bugs / wrong behaviour
- [x] fixedLength sections (battleCommandNames, names, ...) now report the longest entry vs the slot size instead of a byte total (done; see CHANGES.md).
- [x] Byte counts come from a port of `text-codec.js` (`model/textcodec.py`). Check on the EN JSON: battleDialog 2967 vs range 2968, mapTitle 1232 vs 1231. Still unverified against a real build: `mapDialog` (assumes one terminator per inner string, as the encoder code does).
- [x] eventDialog1 capacity includes event_dlg3 when it has >256 entries (encoder split). Still open: per-part check (first 256 vs the rest) and `eventDialog3` as its own section.
- [ ] Linker capacities are approximate for segments without `start=`.
- [ ] Per-file config key is the JSON basename: two `ff4-es-data.json` in different folders share settings. Config file location is still next to the package; consider `QStandardPaths.AppConfigLocation`.
- [ ] `TOKEN_PAT` glues punctuation to tokens; three separate definitions of "control code" regexes.
- [ ] `isDirty` in the JSON is never cleared (probably intentional for the encoder; document it).

## Design
- [ ] Commit on every keystroke (now merged into one undo step per 1.5 s). The text widget's own undo still coexists with the model stack while an editor is open.
- [ ] `vwf_gap`, `vwf_space`, `vwf_line_pitch` have no control in Preferences.
- [ ] Item-name 8-letter-limit ASM work: abandoned, dormant.

## Possible UI follow-ups
- [ ] Replace one by one (today only "replace all", undoable as one step).
- [x] Interface localised with `tr` (see README, Idioma de la interfaz). Still literal: developer log messages, `typed_config` validation messages, Qt's own dialog buttons come from qtbase.

## Ideas from the last review (not done)
- [x] ui_mainwindow.py split into mixins (ui_actions, ui_windowstate, ui_sections)
- [ ] The overlay editor still has its own `QTextEdit` undo while open (standard text-field behaviour).
- [ ] Highlighter colours for codes (`#6fa8a0`) are fixed; derive from the palette for dark themes.
