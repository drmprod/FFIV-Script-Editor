"""
ff4_editor/model/linker.py

Encapsulates ld65 linker script parsing for memory capacity computation.
"""
import os
import re

# Maps ld65 segment names -> our JSON section keys
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
    ff4-en-data.json -> ff4-en.lnk
    ff4-jp-data.json -> ff4-jp.lnk
    """
    name = os.path.basename(json_path)
    # strip '-data.json' suffix
    m = re.match(r'^(ff4-\w+)-data\.json$', name)
    if not m:
        return None
    
    lnk_name = m.group(1) + '.lnk'
    return os.path.join(os.path.dirname(json_path), lnk_name)

def _parse_lnk(lnk_path: str) -> dict[str, int]:
    """
    Parse an ld65 linker script and return {section_key: byte_capacity}.
    Strategy:
      1. Read all MEMORY area definitions: name -> size
         Some areas may be enlarged (e.g. bank_24 with size=$18000 covering
         3 banks) -> we just read the declared size directly.
      2. Read all SEGMENTS definitions: segment_name -> load_memory_area
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