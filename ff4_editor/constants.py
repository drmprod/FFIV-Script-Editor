"""
ff4_editor/constants.py
Shared constants: text limits, section tables and the small colour helpers.
"""

from typing import Any

from PySide6.QtCore import QT_TRANSLATE_NOOP
from PySide6.QtGui import QColor

# ── Text constants ─────────────────────────────────────────────────────────────
MAX_LINE_CHARS = 28
# A character can be renamed by the player to anything up to 6 characters, so every {Name}
# (and \charNN) is measured as the widest case: NAME_MAX_CHARS of NAME_WORST_CHAR ("WWWWWW").
# Fixed-length text fields (no terminator, no DTE): the JSON's itemLength can be stale for the
# Spanish build, which widened some fields in the assembly (item names: symbol + 23 letters).
FIXED_FIELD_OVERRIDES_ES = {"itemNames": 23}
# encode-ff4.js splits these sections when they have more entries than the first bank holds:
# entries past the split go to a second file/segment (eventDialog1 -> event_dlg1 + event_dlg3,
# mapDialog -> map_dlg1 + map_dlg2), so their capacity is the sum of both segments.
ENCODER_SPLITS = {"eventDialog1": (256, "eventDialog3")}

# Bytes a linker segment holds besides the section's text, which the JSON does not count.
# Pointer tables (2 bytes per entry) are derived from the JSON; these are fixed extras:
#   itemDescription: item_desc_id table ($ce-$f8, 43 bytes) in front of the text (item.asm).
SEGMENT_EXTRA_BYTES = {"itemDescription": 43}
# Sections whose pointer table was NOT confirmed to live inside the segment (checked against a real
# ld65 map: every other section matches exactly).  mapDialog is a list of lists and differs.
POINTER_OVERHEAD_UNVERIFIED = {"mapDialog"}
NAME_MAX_CHARS = 6
NAME_WORST_CHAR = "W"
# A \line separator is ONE character in the editor (so Backspace/Delete remove it whole); it is
# drawn as a dotted line by the canvas and its glyph is never shown.
BLANK_LINE_DISPLAY = "\u2504"

# ── Palette ────────────────────────────────────────────────────────────────────
C_WARN = QColor("#e0a030")
C_OVER = QColor("#e04040")
C_BLANK = QColor("#00d0c0")
C_RULER = QColor("#e02020")

# ── Section definitions ────────────────────────────────────────────────────────
DIALOG_SECTIONS = {
    "eventDialog1",
    "eventDialog2",
    "mapDialog",
    "battleDialog",
    "battleMessage",
    "itemDescription",
    "mapTitle",
}

# Sections drawn with the variable-width font in the game (field dialogue box)
VWF_PAGE_LINES = 4  # lineas por pagina de dialogo (caja de 4 lineas)
VWF_SECTIONS = {
    "eventDialog1",
    "eventDialog2",
    "eventDialog3",
    "mapDialog",
    "mapTitle",
    "battleDialog",
    "battleMessage",
    "itemDescription",
}
# Sections whose game box differs from the dialogue box: usable width in px and lines per 'page'.
# They are the defaults for that section; anything the user sets explicitly wins.
VWF_SECTION_LIMIT_PX = {"mapTitle": 176}
VWF_SECTION_PAGE_LINES = {"mapTitle": 2}


def page_lines_for(section: str | None) -> int:
    """Lines per dialogue page in the game box used by `section`."""
    return VWF_SECTION_PAGE_LINES.get(section or "", VWF_PAGE_LINES)


VWF_BOX_BG = "#14146e"  # dialogue window blue
VWF_INK = "#ffffff"

TEXT_SECTIONS: dict[str, Any] = {
    "attackNames": QT_TRANSLATE_NOOP("", "Nombres de ataques"),
    "battleCommandNames": QT_TRANSLATE_NOOP("", "Comandos de batalla"),
    "battleDialog": QT_TRANSLATE_NOOP("", "Diálogos de batalla"),
    "battleMessage": QT_TRANSLATE_NOOP("", "Mensajes de batalla"),
    "characterNames": QT_TRANSLATE_NOOP("", "Nombres de personajes"),
    "className": QT_TRANSLATE_NOOP("", "Clases"),
    "eventDialog1": QT_TRANSLATE_NOOP("", "Diálogos de eventos 1"),
    "eventDialog2": QT_TRANSLATE_NOOP("", "Diálogos de eventos 2"),
    "itemDescription": QT_TRANSLATE_NOOP("", "Descripciones de objetos"),
    "itemNames": QT_TRANSLATE_NOOP("", "Nombres de objetos"),
    "mapDialog": QT_TRANSLATE_NOOP("", "Diálogos de mapas"),
    "mapTitle": QT_TRANSLATE_NOOP("", "Títulos de mapas"),
    "monsterName": QT_TRANSLATE_NOOP("", "Nombres de monstruos"),
    "spellNames": QT_TRANSLATE_NOOP("", "Nombres de hechizos"),
    "statusName": QT_TRANSLATE_NOOP("", "Nombres de estados"),
}

DICT_KEY = {
    "itemNames": "itemName",
    "spellNames": "spellName",
}

# ── Colours: derived from the active Qt palette (default platform theme) ──────


def mix_colors(c1, c2, factor: float) -> str:
    """Blend two colours (QColor or '#rrggbb'); returns '#rrggbb'."""
    c1, c2 = QColor(c1), QColor(c2)

    r = int(c1.red() * (1 - factor) + c2.red() * factor)
    g = int(c1.green() * (1 - factor) + c2.green() * factor)
    b = int(c1.blue() * (1 - factor) + c2.blue() * factor)
    return QColor(r, g, b).name()


class PaletteColors:
    """Canvas colours taken from a QPalette, so the editor follows the platform theme."""

    def __init__(self, pal):
        from PySide6.QtGui import QPalette

        self.bg = pal.color(QPalette.ColorRole.Window)
        self.card = pal.color(QPalette.ColorRole.Base)
        self.text = pal.color(QPalette.ColorRole.Text)
        self.accent = pal.color(QPalette.ColorRole.Highlight)
        self.band0 = self.card
        self.band1 = QColor(mix_colors(self.card, self.text, 0.07))
