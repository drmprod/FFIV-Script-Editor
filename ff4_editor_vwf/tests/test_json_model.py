import json

import pytest

from ff4_editor.errors import FileLoadError, safe_json_load, safe_json_save
from ff4_editor.model.json_model import FF4Model


@pytest.fixture
def model(qapp, data_path):
    m = FF4Model()
    m.load(data_path)
    return m


def test_load_and_signals(qapp, data_path):
    m = FF4Model()
    seen = []
    m.loaded.connect(lambda: seen.append(1))
    m.load(data_path)
    assert seen == [1] and m.filepath == data_path
    assert m.dte_set == {"AB", "BA"}


def test_load_builds_char_names(model):
    from ff4_editor.util.text_processing import get_char_names
    assert get_char_names() == {0: "Cecil", 1: "Kain", 3: "Rosa"}     # los vacíos se omiten


def test_get_and_set_entry(model):
    assert model.get_entry("battleDialog", 0) == r"ABAB\nAB"
    model.set_entry("battleDialog", 0, "XX")
    assert model.get_entry("battleDialog", 0) == "XX"
    assert "battleDialog" in model.dirty_keys
    assert model._data["assembly"]["battleDialog"]["isDirty"] is True


def test_dict_entries_and_tuple_index(model):
    assert model.get_entry("itemNames", 1) == "BBB"
    model.set_entry("itemNames", 1, "ZZZ")
    assert model._data["obj"]["itemNames"][1] == {"itemName": "ZZZ"}
    assert model.get_entry("mapDialog", (0, 1)) == "BA"
    model.set_entry("mapDialog", (0, 1), "AA")
    assert model.get_entry("mapDialog", (0, 1)) == "AA"


def test_section_changed_signal(model):
    got = []
    model.section_changed.connect(got.append)
    model.set_entry("battleDialog", 1, "x")
    assert got == ["battleDialog"]


def test_editing_character_names_rebuilds_registry(model):
    from ff4_editor.util.text_processing import get_char_name
    model.set_entry("characterNames", 2, "Rydia")
    assert get_char_name(2) == "Rydia"


def test_used_bytes_and_entry_cost(model):
    # se compara contra encode_size, que ya tiene tests propios
    from ff4_editor.model.encoding import encode_size
    expect = sum(encode_size(s, model.dte_set) for s in model._data["obj"]["battleDialog"])
    assert model.used_bytes("battleDialog") == expect
    assert model.entry_byte_cost("ABAB") == encode_size("ABAB", model.dte_set)



def test_json_range_is_inclusive(model):
    assert model.capacity("itemNames") == 0x900


def test_save_roundtrip(model, data_path):
    model.set_entry("battleDialog", 0, "CHANGED")
    model.save()
    assert not model.dirty_keys
    again = json.load(open(data_path, encoding="utf-8"))
    assert again["obj"]["battleDialog"][0] == "CHANGED"


def test_save_without_path_raises(qapp):
    with pytest.raises(RuntimeError):
        FF4Model().save()


def test_load_missing_or_invalid(qapp, tmp_path):
    with pytest.raises(FileLoadError):
        FF4Model().load(str(tmp_path / "no.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(FileLoadError):
        FF4Model().load(str(bad))


def test_load_json_with_bom(tmp_path):
    p = tmp_path / "bom.json"
    p.write_bytes(b"\xef\xbb\xbf" + b'{"a": 1}')
    assert safe_json_load(str(p)) == {"a": 1}


def test_save_relative_path_without_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert safe_json_save("rel.json", {"a": 1}) is True


def test_out_of_range_set_entry_is_not_dirty(model):
    model.set_entry("battleDialog", 999, "x")
    model.set_entry("battleDialog", -1, "x")
    assert not model.dirty_keys
    assert model.get_entry("battleDialog", 2) == "{Cecil} dice: AA"      # -1 no escribe en el último


def test_save_is_atomic_and_keeps_backup(model, data_path):
    import os
    model.save()
    assert os.path.exists(data_path + ".bak")
    assert not [f for f in os.listdir(os.path.dirname(data_path)) if f.endswith(".tmp")]


def test_unchanged_text_is_not_dirty(model):
    model.set_entry("battleDialog", 0, model.get_entry("battleDialog", 0))
    assert not model.dirty_keys
    assert model._data["assembly"]["battleDialog"]["isDirty"] is False


def test_save_unchanged_file_is_byte_identical(model, data_path):
    before = open(data_path, "rb").read()
    model.save()
    assert open(data_path, "rb").read() == before         # mismo formato que `make rip`


def test_failed_save_keeps_original(model, data_path, monkeypatch):
    before = open(data_path, "rb").read()
    monkeypatch.setattr(json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(RuntimeError):
        model.save()
    assert open(data_path, "rb").read() == before
    import os
    assert not [f for f in os.listdir(os.path.dirname(data_path)) if f.endswith(".tmp")]


# ── Integración opcional con el JSON real ──────────────────────────────────────
def test_real_json_roundtrip(qapp, real_data_path):
    """json -> display -> json no cambia ningún string (salvo los casos conocidos del todo.md)."""
    from ff4_editor.util.text_processing import display_to_json, json_to_display
    m = FF4Model()
    m.load(real_data_path)
    bad = []
    for key, items in m._data["obj"].items():
        for i, it in enumerate(items if isinstance(items, list) else []):
            strs = it if isinstance(it, list) else [it.get(next(iter(it))) if isinstance(it, dict) else it]
            for s in strs:
                if isinstance(s, str) and display_to_json(json_to_display(s)) != s:
                    bad.append((key, i))
    assert not bad, bad
