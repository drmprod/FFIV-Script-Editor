import pytest

from ff4_editor.model import linker

LNK = """
memory {
    bank_0e: start = $0e8000, size = $8000, type = ro, fill = yes;
    bank_0f: start = $0f8000, size = $8000, type = ro, fill = yes;
    bank_20: start = $208000, size = $10000, type = ro;
}
segments {
    battle_prop: load = bank_0e, type = ro, align = $0100;
    battle_dlg: load = bank_0e, type = ro, align = $0200;
    battle_pal: load = bank_0e, type = ro, start = $0e9000;
    attack_name: load = bank_0f, type = ro, start = $0f8000;
    item_desc: load = bank_0f, type = ro, start = $0fae00;
    battle_msg: load = bank_0f, type = ro, start = $0fb000;
    event_dlg1: load = bank_20, type = ro;
}
"""


@pytest.fixture
def lnk(tmp_path):
    p = tmp_path / "ff4-xx.lnk"
    p.write_text(LNK)
    return str(p)


def test_lnk_path_for_json():
    assert linker._lnk_path_for_json("/a/b/ff4-es-data.json") == "/a/b/ff4-es.lnk"
    assert linker._lnk_path_for_json("/a/b/otro.json") is None


def test_missing_file_returns_empty(tmp_path):
    assert linker._parse_lnk(str(tmp_path / "nope.lnk")) == {}


def test_capacity_is_distance_to_next_segment(lnk):
    caps = linker._parse_lnk(lnk)
    assert caps["itemDescription"] == 0xB000 - 0xAE00     # 0x200, no el banco entero
    assert caps["battleMessage"] == 0x10000 - 0xB000      # hasta el fin del área ($0f8000+$8000)
    assert caps["eventDialog1"] == 0x10000                # único segmento: toda el área


def test_implicit_start_is_a_heuristic(lnk):
    # Los segmentos sin `start=` se asumen contiguos desde el último start conocido y se
    # ignoran tamaños/align: battle_dlg cuenta desde $0e8000 hasta battle_pal ($0e9000).
    # Para valores exactos hay que leer el .map de ld65 (ver README).
    assert linker._parse_lnk(lnk)["battleDialog"] == 0x1000


def test_segment_names_match_real_lnk(lnk):
    caps = linker._parse_lnk(lnk)
    assert {"battleDialog", "itemDescription", "battleMessage", "eventDialog1"} <= set(caps)


def test_shared_name_segments_are_not_mapped(lnk):
    # attack_name holds attack + item + magic names: its size is not "attackNames" capacity
    assert "attackNames" not in linker._parse_lnk(lnk)


def test_map_dlg_and_comments_and_attr_order(tmp_path):
    p = tmp_path / "x.lnk"
    p.write_text("""
memory { bank_22: size = $8000, start = $228000, type = ro; }
segments {
    # map_title: load = bank_22, type = ro, start = $229000;   (comentado: no cuenta)
    map_dlg: type = ro, load = bank_22, start = $228000;
    item_desc: type = ro, start = $22a000, load = bank_22;
}
""")
    caps = linker._parse_lnk(str(p))
    assert caps == {"mapDialog": 0x2000, "itemDescription": 0x230000 - 0x22a000}


def test_no_duplicate_definitions():
    import inspect, re
    assert len(re.findall(r"^def _lnk_path_for_json", inspect.getsource(linker), re.M)) == 1
