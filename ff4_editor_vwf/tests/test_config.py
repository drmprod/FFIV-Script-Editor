import json

import pytest

from ff4_editor.config import EditorConfig
from ff4_editor.config_manager import ConfigManager
from ff4_editor.typed_config import ConfigKey, EditorSettings, SectionOverride, validate_config_dict


@pytest.fixture
def mgr(qapp, tmp_path):
    return ConfigManager(EditorConfig(), str(tmp_path / "cfg.json"))


def write_cfg(mgr, cfg):
    with open(mgr.config_path, "w") as f:
        json.dump(cfg, f)


# ── validate_config_dict ───────────────────────────────────────────────────────
def test_validate_drops_unknown_keys():
    assert validate_config_dict({"font_size": 12, "bogus": 1}) == {"font_size": 12}


def test_validate_coerces_types():
    out = validate_config_dict({"font_size": "13", "show_ruler": "false", "card_font": 5})
    assert out == {"font_size": 13, "show_ruler": False, "card_font": "5"}


def test_validate_drops_uncoercible():
    assert validate_config_dict({"font_size": "abc", "show_ruler": "maybe"}) == {}


def test_validate_rejects_out_of_range():
    assert "vwf_line_pitch" not in validate_config_dict({"vwf_line_pitch": 0})
    assert "font_size" not in validate_config_dict({"font_size": -3})


# ── EditorSettings / SectionOverride ───────────────────────────────────────────
def test_settings_dict_roundtrip():
    s = EditorSettings(font_size=14, card_font="X")
    assert EditorSettings.from_dict(s.to_dict()) == s


def test_settings_from_dict_ignores_unknown():
    assert EditorSettings.from_dict({"font_size": 9, "zzz": 1}).font_size == 9


def test_section_override_type_check():
    o = SectionOverride({})
    o.set(ConfigKey.FONT_SIZE, 12)
    assert o.get(ConfigKey.FONT_SIZE) == 12
    with pytest.raises(TypeError):
        o.set(ConfigKey.FONT_SIZE, "12")




# ── ConfigManager ──────────────────────────────────────────────────────────────
def test_load_missing_file_keeps_defaults(mgr):
    mgr.load()
    assert mgr.editor_config.font_size == 11


def test_load_corrupt_file_keeps_defaults(mgr):
    open(mgr.config_path, "w").write("{broken")
    mgr.load()
    assert mgr.editor_config.font_size == 11


def test_global_change_is_saved_in_global_layer(mgr):
    mgr.update_from_dialog({"font_size": 15}, None, section_only=False)
    mgr.save("/x/ff4-xx-data.json")
    cfg = json.load(open(mgr.config_path))
    assert cfg["global"]["font_size"] == 15
    assert "font_size" not in cfg["files"]["ff4-xx-data.json"]


def test_section_override_applies_and_clears(mgr):
    mgr.update_from_dialog({"font_size": 20}, "battleDialog", section_only=True)
    assert mgr.editor_config.font_size == 20
    mgr.apply_section_override("eventDialog1")
    assert mgr.editor_config.font_size == 11            # otra sección: sin override
    mgr.clear_section_override("battleDialog")
    mgr.apply_section_override("battleDialog")
    assert mgr.editor_config.font_size == 11


def test_show_bands_is_global_only(mgr):
    mgr.update_from_dialog({"show_bands": False}, "battleDialog", section_only=True)
    mgr.apply_section_override("battleDialog")
    assert mgr.editor_config.show_bands is True


def test_global_change_updates_base(mgr):
    mgr.update_from_dialog({"card_rows": 5}, "battleDialog", section_only=False)
    assert mgr._global == {"card_rows": 5}


def test_no_theme_settings_remain():
    from ff4_editor.typed_config import ConfigKey
    names = {k.value for k in ConfigKey}
    assert not {n for n in names if n.startswith("ui_") or n.endswith("_color")}


def test_global_config_is_restored(mgr):
    write_cfg(mgr, {"global": {"font_size": 17, "card_font": "GlobalFont"}, "files": {}})
    mgr.load()
    assert mgr.editor_config.font_size == 17


def test_file_settings_only_override_their_keys(mgr):
    write_cfg(mgr, {"global": {"warn_chars": 10}, "files": {"ff4-xx-data.json": {"font_size": 14}}})
    mgr.load("/x/ff4-xx-data.json")
    mgr.apply_section_override(None)
    assert (mgr.editor_config.font_size, mgr.editor_config.warn_chars) == (14, 10)


def test_section_override_does_not_leak_into_saved_config(mgr):
    mgr.update_from_dialog({"font_size": 20}, "battleDialog", section_only=True)
    mgr.save("/x/ff4-xx-data.json")
    saved = json.load(open(mgr.config_path))
    assert "font_size" not in saved["global"]
    assert "font_size" not in saved["files"]["ff4-xx-data.json"]
    assert saved["files"]["ff4-xx-data.json"]["section_overrides"] == {"battleDialog": {"font_size": 20}}


def test_validate_rejects_bool_inf_and_removed_keys():
    assert validate_config_dict({"font_size": True}) == {}
    assert validate_config_dict({"font_size": float("inf")}) == {}
    assert validate_config_dict({"ui_bg": "#abcdef"}) == {}        # claves de tema ya no existen


def test_global_apply_beats_stale_file_layer(mgr):
    write_cfg(mgr, {"global": {}, "files": {"ff4-xx-data.json": {"font_size": 14}}})
    mgr.load("/x/ff4-xx-data.json")
    assert mgr.editor_config.font_size == 14
    mgr.update_from_dialog({"font_size": 18}, "battleDialog", section_only=False)
    assert mgr.editor_config.font_size == 18


def test_font_and_vwf_changed_flags(mgr):
    assert mgr.update_from_dialog({"font_size": 12}, "a", False) == (True, False)
    assert mgr.update_from_dialog({"vwf_gap": 2}, "a", False) == (False, True)
    assert mgr.update_from_dialog({"font_size": 12}, "a", False) == (False, False)   # sin cambio real


def test_full_save_load_roundtrip_with_section_override(mgr):
    mgr.update_from_dialog({"font_size": 16}, "x", section_only=False)
    mgr.update_from_dialog({"card_rows": 4}, "battleDialog", section_only=True)
    mgr.save("/p/ff4-xx-data.json")
    m2 = ConfigManager(EditorConfig(), mgr.config_path)
    m2.load("/p/ff4-xx-data.json")
    assert m2.editor_config.font_size == 16 and m2.editor_config.card_rows == 8
    m2.apply_section_override("battleDialog")
    assert m2.editor_config.card_rows == 4


def test_loaded_section_override_is_validated_copy(mgr):
    write_cfg(mgr, {"files": {"f.json": {"section_overrides": {"s": {"font_size": 999, "card_rows": 3}}}}})
    mgr.load("/x/f.json")
    assert mgr._section_overrides["s"].to_dict() == {"card_rows": 3}


def test_save_is_atomic_no_tmp_left(mgr, tmp_path):
    mgr.save("/x/f.json")
    assert [p.name for p in tmp_path.iterdir()] == ["cfg.json"]


def test_default_config_path_env_and_location(monkeypatch, tmp_path):
    from ff4_editor.config_manager import default_config_path
    monkeypatch.setenv("FF4_EDITOR_CONFIG", str(tmp_path / "x.json"))
    assert default_config_path() == str(tmp_path / "x.json")
    monkeypatch.delenv("FF4_EDITOR_CONFIG")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert default_config_path().endswith("ff4_editor/config.json")
    assert "ff4_editor/ff4_editor_config.json" not in default_config_path()
