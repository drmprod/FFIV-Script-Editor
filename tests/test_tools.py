"""build_tools / game_font: pure helpers, no window needed."""

import pytest

from ff4_editor import build_tools as bt
from ff4_editor.game_font import GameFontError, build_game_font, find_font_png, load_overrides


def test_make_target_from_json_name():
    assert bt.make_target("/x/ff4-jp-data.json") == "ff4-jp"
    assert bt.make_target("/x/FF4-EN-DATA.JSON") == "FF4-EN"
    assert bt.make_target("/x/otro.json") == "ff4-es" and bt.make_target(None) == "ff4-es"


def test_find_rom_prefers_sfc_over_spc(tmp_path):
    js = str(tmp_path / "ff4-es-data.json")
    assert bt.find_rom(js) is None and bt.find_rom(None) is None
    (tmp_path / "rom").mkdir()
    (tmp_path / "rom" / "ff4-es.smc").touch()
    assert bt.find_rom(js).endswith("ff4-es.smc")
    (tmp_path / "rom" / "ff4-es.sfc").touch()
    assert bt.find_rom(js).endswith("ff4-es.sfc")


def test_find_mesen_uses_path(tmp_path, monkeypatch):
    exe = tmp_path / "mesen2"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert bt.find_mesen() == str(exe)
    monkeypatch.setenv("PATH", str(tmp_path / "nada"))
    assert bt.find_mesen() is None


def test_find_font_png_search_order(tmp_path):
    js = tmp_path / "sub" / "ff4-xx-data.json"
    (tmp_path / "sub" / "gfx").mkdir(parents=True)
    assert find_font_png("", str(js)) is None or find_font_png("", str(js)).endswith("font.png")
    (tmp_path / "sub" / "gfx" / "font.png").touch()
    assert find_font_png("", str(js)).endswith("gfx/font.png")
    explicit = tmp_path / "mi.png"
    explicit.touch()
    assert find_font_png(str(explicit), str(js)) == str(explicit)


def test_overrides_errors_are_readable(tmp_path):
    png = tmp_path / "font.png"
    png.touch()
    assert load_overrides(str(png)) == {}
    (tmp_path / "vwf_overrides.json").write_text("{roto")
    with pytest.raises(GameFontError):
        load_overrides(str(png))
    (tmp_path / "vwf_overrides.json").write_text("[1]")
    with pytest.raises(GameFontError):
        load_overrides(str(png))


def test_build_game_font_bad_png_raises_game_font_error(qapp, tmp_path):
    bad = tmp_path / "font.png"
    bad.write_bytes(b"no soy un png")
    with pytest.raises(GameFontError):
        build_game_font(str(bad), {}, 1, 4, 16)
