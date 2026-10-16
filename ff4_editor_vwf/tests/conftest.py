"""Fixtures compartidas. Todo corre offscreen y con datos sintéticos (no hace falta el JSON real)."""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from PIL import Image

from ff4_editor.util.vwf_font import PALETTE

# ── font.png sintético ─────────────────────────────────────────────────────────
# 16x16 tiles de 8x8, rejilla de 1 px: imagen de 145x145 (cell=9, scale=1).
# 'A' (0x42) ocupa 5 columnas de tinta -> avance 5+gap = 6 px; 'B' (0x43) 3 columnas -> 4 px.
GLYPH_COLS = {0x42: 5, 0x43: 3, 0x44: 7}   # A, B, C (código -> columnas de tinta)


def make_font_png(path):
    img = Image.new("RGB", (145, 145), PALETTE[0])
    for code, ncols in GLYPH_COLS.items():
        ox, oy = 1 + (code % 16) * 9, 1 + (code // 16) * 9
        for y in range(8):
            for x in range(ncols):
                img.putpixel((ox + x, oy + y), PALETTE[2])
    img.save(path)
    return str(path)


@pytest.fixture(scope="session")
def font_png(tmp_path_factory):
    return make_font_png(tmp_path_factory.mktemp("font") / "font.png")


# ── JSON de datos mínimo ───────────────────────────────────────────────────────
def mini_data():
    return {
        "type": "rom",
        "key": "ff4-xx",
        "charTable": {
            "text": {"char": {"0x42": "A", "0x43": "B", "0x44": "C", "0xFF": " "}},
            "dte": {"char": {"0x01": "AB", "0x02": "BA"}},
        },
        "assembly": {
            "battleDialog": {"range": "0x0E8000-0x0E80FF", "isDirty": False},
            "itemNames": {"range": "0x0F8000-0x0F88FF", "isDirty": False},
            "characterNames": {"range": "0x0F9000-0x0F90FF", "isDirty": False},
        },
        "obj": {
            "characterNames": ["Cecil", "Kain", "", "Rosa"],
            "battleDialog": ["ABAB\\nAB", "AAAA\\line BBBB", "{Cecil} dice: AA"],
            "itemNames": [{"itemName": "AAA"}, {"itemName": "BBB"}],
            "mapDialog": [["AB", "BA"], ["AA"]],
        },
    }


@pytest.fixture
def data_path(tmp_path):
    """ff4-xx-data.json + ff4-xx.lnk en un directorio temporal."""
    p = tmp_path / "ff4-xx-data.json"
    p.write_text(json.dumps(mini_data(), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


@pytest.fixture(autouse=True)
def _reset_char_names():
    from ff4_editor.util.text_processing import set_char_names
    set_char_names({})
    yield
    set_char_names({})


# ── Integración opcional con el JSON real ──────────────────────────────────────
@pytest.fixture(scope="session")
def real_data_path():
    p = os.environ.get("FF4_DATA_JSON", "")
    if not p or not os.path.isfile(p):
        pytest.skip("definí FF4_DATA_JSON=/ruta/a/ff4-xx-data.json para correr los tests de integración")
    return p


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
