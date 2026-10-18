import json
from pathlib import Path

import pytest

from ff4_editor.errors import FileLoadError, FileSaveError, safe_json_load, safe_json_save
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
    assert m.codec_for("battleDialog").table["AB"] == 0x9B


def test_load_builds_char_names(model):
    from ff4_editor.util.text_processing import get_char_names

    assert get_char_names() == {0: "Cecil", 1: "Kain", 3: "Rosa"}  # los vacíos se omiten


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
    codec = model.codec_for("battleDialog")
    texts = model._data["obj"]["battleDialog"]
    # battleDialog is a "shared array" in the synthetic data too: no duplicates here, so it is the sum
    assert model.used_bytes("battleDialog") == sum(codec.size(t) for t in texts)
    assert model.entry_byte_cost("ABAB", "battleDialog") == codec.size("ABAB") == 3  # 2 DTE + terminator


def test_json_range_is_inclusive(model):
    assert model.capacity("itemNames") == 0x900


def test_save_roundtrip(model, data_path):
    model.set_entry("battleDialog", 0, "CHANGED")
    model.save()
    assert not model.dirty_keys
    again = json.loads(Path(data_path).read_text(encoding="utf-8"))
    assert again["obj"]["battleDialog"][0] == "CHANGED"


def test_save_without_path_raises(qapp):
    with pytest.raises(FileSaveError):
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
    safe_json_save("rel.json", {"a": 1})
    assert json.loads(Path("rel.json").read_text(encoding="utf-8")) == {"a": 1}


def test_out_of_range_set_entry_is_not_dirty(model):
    model.set_entry("battleDialog", 999, "x")
    model.set_entry("battleDialog", -1, "x")
    assert not model.dirty_keys
    assert model.get_entry("battleDialog", 2) == "{Cecil} dice: AA"  # -1 no escribe en el último


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
    before = Path(data_path).read_bytes()
    model.save()
    assert Path(data_path).read_bytes() == before  # mismo formato que `make rip`


def test_failed_save_keeps_original(model, data_path, monkeypatch):
    before = Path(data_path).read_bytes()
    monkeypatch.setattr(json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(FileSaveError):
        model.save()
    assert True
    assert Path(data_path).read_bytes() == before
    import os

    assert not [f for f in os.listdir(os.path.dirname(data_path)) if f.endswith(".tmp")]


# ── Integración opcional con el JSON real ──────────────────────────────────────
def test_real_json_roundtrip(qapp, real_data_path):
    """json -> display -> json no cambia ningún string (salvo los casos conocidos del todo.md)."""
    from ff4_editor.util.text_processing import display_to_json, json_to_display

    m = FF4Model()
    m.load(real_data_path)

    def strings(it):
        if isinstance(it, list):
            return it
        return [it.get(next(iter(it))) if isinstance(it, dict) else it]

    bad = [
        (key, i)
        for key, items in m._data["obj"].items()
        for i, it in enumerate(items if isinstance(items, list) else [])
        for s in strings(it)
        if isinstance(s, str) and display_to_json(json_to_display(s)) != s
    ]
    assert not bad, bad


def test_failed_load_keeps_previous_data(model, tmp_path):
    before = model.section_items("battleDialog")[:]
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(FileLoadError):
        model.load(str(bad))
    assert model.section_items("battleDialog") == before


def test_save_unserialisable_data_raises(model):
    model._data["obj"]["battleDialog"][0] = {1, 2}
    with pytest.raises(FileSaveError):
        model.save()


def test_used_bytes_cache_follows_edits(model):
    import random

    rnd = random.Random(3)
    for key in ("battleDialog", "itemNames", "mapDialog"):
        items = model.section_items(key)
        if not items:
            continue
        model.used_bytes(key)  # fill the cache
        for _ in range(30):
            i = rnd.randrange(len(items))
            idx = (i, 0) if isinstance(items[i], list) and items[i] else i
            if isinstance(idx, int) and isinstance(items[i], list):
                continue
            model.set_entry(key, idx, "".join(rnd.choice("abc\\n x") for _ in range(rnd.randint(0, 12))))
            assert model.used_bytes(key) == model._compute_used_bytes(key)


# ── fixedLength sections: slot size, not a byte total ─────────────────────────
def _add_fixed_section(model, key="characterNames", item_length=6):
    model._data["assembly"][key] = {
        "assembly": {"type": "text", "encoding": "fixedLength"},
        "itemLength": item_length,
        "range": "0x000000-0x0000FF",
    }
    model._data["obj"][key] = ["Cid", "Rosa", "Kain"]
    model._compute_capacities()


def test_fixed_length_uses_slot_size_and_longest_entry(model):
    _add_fixed_section(model)
    assert model.is_fixed("characterNames")
    assert model.capacity("characterNames") == 6
    assert model.used_bytes("characterNames") == 4  # longest entry, no terminator
    assert model.fixed_overflows("characterNames") == []
    model.set_entry("characterNames", 0, "Tellah7")
    assert model.used_bytes("characterNames") == 7
    assert model.fixed_overflows("characterNames") == [0]


def test_fixed_length_limit_never_below_existing_data(model):
    _add_fixed_section(model, item_length=3)  # stale JSON: "Rosa" is already 4 and builds fine
    assert model.capacity("characterNames") == 4
    assert model.fixed_overflows("characterNames") == []


def test_fixed_length_card_cost_has_no_terminator(model):
    _add_fixed_section(model)
    assert model.entry_byte_cost("Cid", "characterNames") == 3
    assert model.entry_byte_cost("Cid") == 4  # sections with terminator keep counting it


def test_non_fixed_sections_are_unchanged(model):
    assert not model.is_fixed("battleDialog")


def test_event_dialog1_capacity_includes_event_dlg3_when_split(model, tmp_path, monkeypatch):
    import ff4_editor.model.json_model as jm
    from ff4_editor.model.linker import Capacity

    monkeypatch.setattr(
        jm,
        "parse_lnk_capacities",
        lambda p: {"eventDialog1": Capacity(1000, True), "eventDialog3": Capacity(500, True)},
    )
    monkeypatch.setattr(jm, "_lnk_path_for_json", lambda p: str(tmp_path / "x.lnk"))
    model._data["obj"]["eventDialog1"] = ["a"] * 256
    model._data["assembly"].setdefault("eventDialog1", {})
    model._compute_capacities()
    assert model.capacity("eventDialog1") == 1000  # encoder does not split at 256 entries
    model._data["obj"]["eventDialog1"] = ["a"] * 257
    model._compute_capacities()
    assert model.capacity("eventDialog1") == 1500  # 257+ entries: event_dlg1 + event_dlg3


def test_split_section_is_checked_per_segment(model, tmp_path, monkeypatch):
    import ff4_editor.model.json_model as jm
    from ff4_editor.model.linker import Capacity

    monkeypatch.setattr(
        jm,
        "parse_lnk_capacities",
        lambda p: {"eventDialog1": Capacity(100, True), "eventDialog3": Capacity(5000, True)},
    )
    monkeypatch.setattr(jm, "_lnk_path_for_json", lambda p: str(tmp_path / "x.lnk"))
    model._data["assembly"]["eventDialog1"] = {"type": "array"}
    model._data["obj"]["eventDialog1"] = [f"t{i:03d}" for i in range(300)]
    model._used.pop("eventDialog1", None)
    model._compute_capacities()
    assert model.used_bytes("eventDialog1") < model.capacity("eventDialog1")  # total fits...
    assert model.overflow_bytes("eventDialog1") > 0  # ...but the first pool does not fit event_dlg1


def test_capacity_leaves_room_for_pointer_table_and_extras(model, tmp_path, monkeypatch):
    import ff4_editor.model.json_model as jm
    from ff4_editor.model.linker import Capacity

    monkeypatch.setattr(
        jm,
        "parse_lnk_capacities",
        lambda p: {"battleDialog": Capacity(1000, True), "itemDescription": Capacity(500, True)},
    )
    monkeypatch.setattr(jm, "_lnk_path_for_json", lambda p: str(tmp_path / "x.lnk"))
    model._data["assembly"]["battleDialog"] = {"type": "array", "pointerTable": {"range": "0x0-0x1"}}
    model._data["obj"]["battleDialog"] = ["a"] * 10
    model._data["assembly"]["itemDescription"] = {"type": "array", "terminator": 0}
    model._compute_capacities()
    assert model.capacity("battleDialog") == 1000 - 2 * 10  # 2-byte pointer per entry
    assert model.capacity("itemDescription") == 500 - 43  # item_desc_id table in front of the text
