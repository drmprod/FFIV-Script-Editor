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
    assert caps["itemDescription"] == 0xB000 - 0xAE00  # 0x200, no el banco entero
    assert caps["battleMessage"] == 0x10000 - 0xB000  # hasta el fin del área ($0f8000+$8000)
    assert caps["eventDialog1"] == 0x10000  # único segmento: toda el área


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
    assert caps == {"mapDialog": 0x2000, "itemDescription": 0x230000 - 0x22A000}


def test_no_duplicate_definitions():
    import inspect
    import re

    assert len(re.findall(r"^def _lnk_path_for_json", inspect.getsource(linker), re.M)) == 1


MAP = """Modules list:
-------------
a.o:
    CODE              Offs=000000  Size=000010  Align=00001  Fill=0000

Segment list:
-------------
Name                   Start     End    Size  Align
----------------------------------------------------
battle_dlg            0E8000  0E8BFF  000C00  00200
battle_pal            0E9000  0E90FF  000100  00001
item_desc             0FAE00  0FAEFF  000100  00001
battle_msg            0FB000  0FB3FF  000400  00001


Exports list by name:
---------------------
"""


def test_parse_map_segments(tmp_path):
    p = tmp_path / "ff4-xx.map"
    p.write_text(MAP)
    segs = linker.parse_map_segments(str(p))
    assert segs["battle_dlg"] == (0xE8000, 0xC00)
    assert segs["item_desc"] == (0xFAE00, 0x100)
    assert "CODE" not in segs and len(segs) == 4


def test_map_gives_exact_capacities(lnk, tmp_path):
    p = tmp_path / "ff4-xx.map"
    p.write_text(MAP)
    caps = linker.capacities_from_map(lnk, str(p))
    assert caps["battleDialog"] == linker.Capacity(0x1000, True)  # real start $0e8000 -> battle_pal
    assert caps["itemDescription"] == linker.Capacity(0x200, True)
    assert caps["battleMessage"] == linker.Capacity(0x10000 - 0xB000, True)  # up to the area end


def test_lnk_capacity_is_flagged_inexact_when_a_start_is_implicit(lnk):
    caps = linker.parse_lnk_capacities(lnk)
    assert not caps["battleDialog"].exact  # no `start =`
    assert caps["itemDescription"].exact and caps["battleMessage"].exact
    assert not caps["eventDialog1"].exact  # alone in its area but without `start =`


def test_map_path_for_json():
    assert linker.map_path_for_json("/a/ff4-es-data.json") == "/a/rom/ff4-es.map"
    assert linker.map_path_for_json("/a/otro.json") is None
