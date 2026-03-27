"""
ff4_editor/constants.py
Shared constants, palette QColors, and Qt stylesheet.
"""

from PySide6.QtGui import QColor

# ── Text constants ─────────────────────────────────────────────────────────────
MAX_LINE_CHARS     = 28
WARN_LINE_CHARS    = 26
BLANK_LINE_DISPLAY = '─' * 28

# ── Palette ────────────────────────────────────────────────────────────────────
C_BG          = QColor('#12111a')
C_CARD_BG     = QColor('#1a1828')
C_CARD_BORDER = QColor('#2a2545')
C_TV_BG       = QColor('#100f1a')
C_TEXT        = QColor('#e0d0ff')
C_DIM         = QColor('#504070')
C_IDX         = QColor('#6050a0')
C_WARN        = QColor('#e0a030')
C_OVER        = QColor('#e04040')
C_BLANK       = QColor('#00d0c0')
C_RULER       = QColor('#e02020')

C_BAND0_DEF = '#100f1a'
C_BAND1_DEF = '#1c1830'

# ── Section definitions ────────────────────────────────────────────────────────
DIALOG_SECTIONS = {
    'eventDialog1', 'eventDialog2', 'mapDialog',
    'battleDialog', 'battleMessage', 'itemDescription',
   }

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

# ── Qt stylesheet ──────────────────────────────────────────────────────────────
QSS = """
QMainWindow, QWidget { background: #12111a; color: #e0d0ff; }
QWidget#sidebar { background: #1a1828; border-right: 2px solid #2a2545; }
QListWidget { background: #1a1828; border: none; color: #9090b0; outline: none; }
QListWidget::item { padding: 6px 10px; border-radius: 4px; margin: 1px 4px; }
QListWidget::item:selected { background: #2e2060; color: #c0a0ff; }
QListWidget::item:hover:!selected { background: #221e38; color: #d0c0ff; }
QWidget#toolbar { background: #0e0d17; border-bottom: 2px solid #2a2545; }
QWidget#infobar { background: #1a1428; border-bottom: 1px solid #2a2545; }
QLabel#infobar_lbl  { color: #806090; font-size: 10px; padding: 4px 14px; }
QLabel#title_lbl    { color: #c0a0ff; font-size: 15px; font-weight: bold; }
QLabel#subtitle_lbl { color: #504070; font-size: 10px; }
QLabel#sec_title    { color: #e0d0ff; font-size: 13px; font-weight: bold; padding: 10px 14px 2px; }
QLabel#count_lbl    { color: #504070; font-size: 11px; padding: 0 14px 4px; }
QLabel#status_lbl   { color: #504070; font-size: 11px; padding: 3px 12px; }
QPushButton#save_btn {
    background: #5030c0; color: #fff; border: none;
    border-radius: 5px; padding: 6px 20px; font-weight: bold;
}
QPushButton#save_btn:hover    { background: #6040d0; }
QPushButton#save_btn:pressed  { background: #4020a0; }
QPushButton#save_btn:disabled { background: #2a2060; color: #706090; }
QPushButton#open_btn, QPushButton#view_btn {
    background: #1e1c30; color: #c0b0f0;
    border: 1px solid #3a3060; border-radius: 5px;
    padding: 6px 18px; font-weight: bold;
}
QPushButton#open_btn:hover, QPushButton#view_btn:hover { background: #2a2545; }
QLineEdit#search_entry {
    background: #100f1a; color: #e0d0ff;
    border: 1px solid #3a3060; border-radius: 4px;
    padding: 4px 10px; min-width: 190px;
}
QLineEdit#search_entry:focus { border-color: #9070e0; }
QLineEdit#goto_entry {
    background: #100f1a; color: #e0d0ff;
    border: 1px solid #3a3060; border-radius: 3px;
    padding: 3px 6px; max-width: 60px;
}
QProgressBar {
    background: #1a1828; border: 1px solid #2a2545;
    border-radius: 3px; max-height: 8px;
}
QProgressBar::chunk { background: #5030c0; border-radius: 2px; }
QComboBox {
    background: #100f1a; color: #e0d0ff;
    border: 1px solid #3a3060; border-radius: 3px; padding: 3px 8px;
}
QComboBox:focus { border-color: #9070e0; }
QComboBox QAbstractItemView {
    background: #1a1828; color: #e0d0ff;
    border: 1px solid #3a3060; selection-background-color: #2e2060;
}
QScrollBar:vertical { background: #12111a; width: 10px; }
QScrollBar::handle:vertical { background: #2a2545; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QDialog { background: #1a1828; }
QDialog QLabel { color: #c0b0f0; }
QDialog QSpinBox, QDialog QComboBox {
    background: #100f1a; color: #e0d0ff;
    border: 1px solid #3a3060; border-radius: 3px; padding: 2px 6px;
}
QDialog QCheckBox { color: #c0b0f0; }
QDialog QCheckBox::indicator {
    width: 14px; height: 14px; border: 1px solid #3a3060;
    background: #100f1a; border-radius: 2px;
}
QDialog QCheckBox::indicator:checked { background: #5030c0; border-color: #9070e0; }
QPushButton#apply_btn {
    background: #5030c0; color: #fff; border: none;
    border-radius: 4px; padding: 5px 16px; font-weight: bold;
}
QPushButton#apply_btn:hover { background: #6040d0; }
QPlainTextEdit {
    background: #100f1a; color: #e0d0ff;
    border: 1px solid #3a3060; border-radius: 3px;
    selection-background-color: #3a2080;
}
QPlainTextEdit:focus { border-color: #9070e0; }
QWidget#statusbar { background: #0e0d17; border-top: 1px solid #2a2545; }

QWidget#edit_toolbar {
    background: #16152a;
    border-bottom: 1px solid #2a2545;
}
QPushButton#edit_btn {
    background: #1e1c30; color: #c0b0f0;
    border: 1px solid #2a2545; border-radius: 3px;
    padding: 3px 10px; font-size: 11px;
}
QPushButton#edit_btn:hover   { background: #2a2545; color: #e0d0ff; border-color: #6040b0; }
QPushButton#edit_btn:pressed { background: #3a3060; }
"""
