"""
ff4_editor/model/json_model.py
Loads, owns and mutates ff4-en-data.json.
Section capacities are read from the companion ff4-*.lnk linker script
(same directory as the JSON) for accuracy. Falls back to the JSON's
assembly[key].range field if the LNK is not found.
"""

import os, re, json
from PySide6.QtCore import QObject, Signal

from ..constants import TEXT_SECTIONS, DIALOG_SECTIONS, DICT_KEY
from ..util.text_processing import CHAR_NAMES
from .encoding import build_dte_set, encode_size


def _sanitize(obj):
    """Replace any raw \\ufeff BOM characters with the \\line escape."""
    if isinstance(obj, str):  return obj.replace('\ufeff', r'\line')
    if isinstance(obj, list): return [_sanitize(v) for v in obj]
    if isinstance(obj, dict): return {k: _sanitize(v) for k, v in obj.items()}
    return obj


# ── LNK parser ────────────────────────────────────────────────────────────────

# Maps ld65 segment names → our JSON section keys
_SEGMENT_TO_KEY = {
    'event_dlg1':    'eventDialog1',
    'event_dlg2':    'eventDialog2',
    'map_dlg':       'mapDialog',
    'battle_dlg':    'battleDialog',
    'battle_msg':    'battleMessage',
    'item_desc':     'itemDescription',
    'map_title':     'mapTitle',
    'attack_names':  'attackNames',
    'battle_cmd':    'battleCommandNames',
    'char_names':    'characterNames',
    'class_names':   'className',
    'item_names':    'itemNames',
    'monster_names': 'monsterName',
    'spell_names':   'spellNames',
    'status_names':  'statusName',
}


def _lnk_path_for_json(json_path: str) -> str | None:
    """
    Derive the LNK path from the JSON filename.
    ff4-en-data.json  →  ff4-en.lnk
    ff4-jp-data.json  →  ff4-jp.lnk
    """
    name = os.path.basename(json_path)           # ff4-en-data.json
    # strip '-data.json' suffix
    m = re.match(r'^(ff4-\w+)-data\.json$', name)
    if not m:
        return None
    lnk_name = m.group(1) + '.lnk'              # ff4-en.lnk
    return os.path.join(os.path.dirname(json_path), lnk_name)


def _parse_lnk(lnk_path: str) -> dict[str, int]:
    """
    Parse an ld65 linker script and return {section_key: byte_capacity}.

    Strategy:
      1. Read all MEMORY area definitions: name → size
         Some areas may be enlarged (e.g. bank_24 with size=$18000 covering
         3 banks) — we just read the declared size directly.
      2. Read all SEGMENTS definitions: segment_name → load_memory_area
      3. Cross-reference via _SEGMENT_TO_KEY to get section capacities.
    """
    try:
        text = open(lnk_path).read()
    except (FileNotFoundError, PermissionError):
        return {}

    # Parse memory areas: name -> declared size in bytes
    mem_sizes: dict[str, int] = {}
    for m in re.finditer(
        r'(\w+)\s*:\s*start\s*=\s*\$[0-9a-fA-F]+\s*,\s*size\s*=\s*\$([0-9a-fA-F]+)',
        text
    ):
        name = m.group(1)
        size = int(m.group(2), 16)
        # Keep largest declared size (in case of redeclaration)
        mem_sizes[name] = max(mem_sizes.get(name, 0), size)

    # Parse segments: segment_name -> load memory area name
    seg_to_mem: dict[str, str] = {}
    for m in re.finditer(
        r'(\w+)\s*:\s*load\s*=\s*(\w+)\s*,\s*type\s*=\s*ro',
        text
    ):
        seg_to_mem[m.group(1)] = m.group(2)

    # Build section capacities
    caps: dict[str, int] = {}
    for seg, key in _SEGMENT_TO_KEY.items():
        mem = seg_to_mem.get(seg)
        if mem and mem in mem_sizes:
            caps[key] = mem_sizes[mem]

    return caps


# ── Model ─────────────────────────────────────────────────────────────────────

class FF4Model(QObject):
    """
    Owns the parsed JSON data. All writes go through this class so that
    dirty-tracking and signal emission are centralised.

    Signals
    -------
    section_changed(key)   — emitted after any entry in `key` is mutated
    loaded()               — emitted after a successful file load
    """

    section_changed = Signal(str)
    loaded          = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data:     dict       = {}
        self._filepath: str | None = None
        self._dte_set:  set[str]   = set()
        self._caps:     dict       = {}   # section -> byte capacity
        self._caps_source: str     = ''   # 'lnk' or 'json'
        self.dirty_keys: set[str]  = set()

    # ── File I/O ──────────────────────────────────────────────────────────────

    def load(self, path: str):
        with open(path, encoding='utf-8') as f:
            self._data = _sanitize(json.load(f))
        self._filepath = path
        self._dte_set  = build_dte_set(self._data)
        self.dirty_keys.clear()
        self._compute_capacities()
        self._build_char_names()
        self.loaded.emit()

    def save(self):
        if not self._filepath:
            raise RuntimeError("No filepath set")
        with open(self._filepath, 'w', encoding='utf-8') as f:
            json.dump(_sanitize(self._data), f, ensure_ascii=False, indent=2)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def filepath(self) -> str | None:
        return self._filepath

    @property
    def dte_set(self) -> set[str]:
        return self._dte_set

    @property
    def caps_source(self) -> str:
        """'lnk' if capacities came from the LNK file, 'json' if fallback."""
        return self._caps_source

    def capacity(self, key: str) -> int:
        return self._caps.get(key, 0)

    def section_items(self, key: str) -> list:
        return self._data.get('obj', {}).get(key, [])

    def map_properties(self) -> list:
        return self._data.get('obj', {}).get('mapProperties', [])

    def map_titles(self) -> list:
        return self._data.get('obj', {}).get('mapTitle', [])

    # ── Writes ────────────────────────────────────────────────────────────────

    def set_entry(self, key: str, idx, json_text: str):
        """
        Write json_text into data[key][idx].
        idx is an int for normal entries, or (i, j) for mapDialog sub-strings.
        """
        items = self._data.get('obj', {}).get(key, [])
        dk    = DICT_KEY.get(key)

        if isinstance(idx, tuple):
            i, j = idx
            if i < len(items) and isinstance(items[i], list):
                if j < len(items[i]):
                    items[i][j] = json_text
        elif idx < len(items):
            if dk and isinstance(items[idx], dict):
                items[idx][dk] = json_text
            else:
                items[idx] = json_text

        # Mark assembly dirty
        asm = self._data.get('assembly', {}).get(key)
        if asm:
            asm['isDirty'] = True

        self.dirty_keys.add(key)
        self.section_changed.emit(key)

    # ── Byte budget ───────────────────────────────────────────────────────────

    def used_bytes(self, key: str) -> int:
        items = self.section_items(key)
        dk    = DICT_KEY.get(key)
        total = 0
        for item in items:
            if isinstance(item, list):
                for s in item:
                    if isinstance(s, str):
                        total += encode_size(s, self._dte_set)
            elif isinstance(item, dict):
                total += encode_size(item.get(dk, ''), self._dte_set)
            elif isinstance(item, str):
                total += encode_size(item, self._dte_set)
        return total

    def entry_byte_cost(self, json_text: str) -> int:
        return encode_size(json_text, self._dte_set)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _compute_capacities(self):
        """
        Try to read capacities from the companion LNK file first.
        Falls back to assembly[key].range in the JSON if LNK not found
        or a section isn't listed in the LNK.
        """
        self._caps = {}
        self._caps_source = 'json'

        # Attempt LNK parse
        lnk_path = _lnk_path_for_json(self._filepath) if self._filepath else None
        lnk_caps: dict[str, int] = {}
        if lnk_path:
            lnk_caps = _parse_lnk(lnk_path)
            if lnk_caps:
                self._caps_source = 'lnk'

        # JSON fallback capacities
        json_caps: dict[str, int] = {}
        for key in TEXT_SECTIONS:
            a = self._data.get('assembly', {}).get(key, {})
            r = a.get('range', '')
            if '-' in r:
                try:
                    s, e = [int(x, 16) for x in r.split('-')]
                    json_caps[key] = e - s
                except ValueError:
                    pass

        # Merge: LNK takes priority, JSON fills gaps
        for key in TEXT_SECTIONS:
            if key in lnk_caps:
                self._caps[key] = lnk_caps[key]
            elif key in json_caps:
                self._caps[key] = json_caps[key]

    def _build_char_names(self):
        CHAR_NAMES.clear()
        for i, name in enumerate(
                self._data.get('obj', {}).get('characterNames', [])):
            if isinstance(name, str) and name.strip():
                CHAR_NAMES[i] = name.strip()
