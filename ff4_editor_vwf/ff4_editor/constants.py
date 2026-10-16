"""
ff4_editor/constants.py
Shared constants, palette QColors, and Qt stylesheet.
"""

from PySide6.QtGui import QColor

# ── Text constants ─────────────────────────────────────────────────────────────
MAX_LINE_CHARS     = 28
BLANK_LINE_DISPLAY = '─' * 28

# ── Palette ────────────────────────────────────────────────────────────────────
C_WARN        = QColor('#e0a030')
C_OVER        = QColor('#e04040')
C_BLANK       = QColor('#00d0c0')
C_RULER       = QColor('#e02020')

# ── Section definitions ────────────────────────────────────────────────────────
DIALOG_SECTIONS = {
    'eventDialog1', 'eventDialog2', 'mapDialog',
    'battleDialog', 'battleMessage', 'itemDescription',
    'mapTitle',
   }

# Sections drawn with the variable-width font in the game (field dialogue box)
VWF_PAGE_LINES = 4          # lineas por pagina de dialogo (caja de 4 lineas)
VWF_SECTIONS = {'eventDialog1', 'eventDialog2', 'eventDialog3', 'mapDialog', 'mapTitle',
                'battleDialog', 'battleMessage', 'itemDescription'}
# secciones con caja distinta de la de dialogo: ancho util en px y lineas por 'pagina'
VWF_SECTION_LIMIT_PX   = {'mapTitle': 176, 'battleDialog': 224, 'battleMessage': 224, 'itemDescription': 224}
VWF_SECTION_PAGE_LINES = {'mapTitle': 2}
VWF_BOX_BG   = '#14146e'     # dialogue window blue
VWF_INK      = '#ffffff'

TEXT_SECTIONS = {
    'attackNames':        'Attack Names',
    'battleCommandNames': 'Battle Command Names',
    'battleDialog':       'Battle Dialogue',
    'battleMessage':      'Battle Messages',
    'characterNames':     'Character Names',
    'className':          'Class Names',
    'eventDialog1':       'Event Dialogue 1',
    'eventDialog2':       'Event Dialogue 2',
    'itemDescription':    'Item Descriptions',
    'itemNames':          'Item Names',
    'mapDialog':          'Map Dialogue',
    'mapTitle':           'Map Titles',
    'monsterName':        'Monster Names',
    'spellNames':         'Spell Names',
    'statusName':         'Status Names',
}

DICT_KEY = {
    'itemNames':  'itemName',
    'spellNames': 'spellName',
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
        self.bg = pal.color(QPalette.Window)
        self.card = pal.color(QPalette.Base)
        self.text = pal.color(QPalette.Text)
        self.accent = pal.color(QPalette.Highlight)
        self.band0 = self.card
        self.band1 = QColor(mix_colors(self.card, self.text, 0.07))
