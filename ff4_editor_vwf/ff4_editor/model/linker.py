"""
ff4_editor/model/linker.py

Reads the ld65 linker script (ff4-xx.lnk) to estimate how many bytes each text section
may occupy.  Capacity of a segment = distance from its start to the next segment in the
same memory area (or to the end of the area for the last one).

Limitation: segments without an explicit `start =` are assumed to begin where the
previous segment began (sizes and `align` are unknown from the script alone), so their
capacity can be over-estimated.  Exact values need the ld65 map file.
"""
import os
import re

from ..errors import logger

# ld65 segment name -> JSON section key.  Only segments that hold exactly ONE text section
# are mapped.  Name tables (attack_name, char_name, status_name, ...) are deliberately left
# out: those segments also contain item/magic names, class names, etc., so the whole segment
# size would overstate the room for a single section; they use the JSON `range` instead.
_SEGMENT_TO_KEY = {
    'event_dlg1':     'eventDialog1',
    'event_dlg2':     'eventDialog2',
    'event_dlg3':     'eventDialog3',
    'map_dlg':        'mapDialog',
    'map_dlg1':       'mapDialog',
    'map_dlg2':       'mapDialog',
    'battle_dlg':     'battleDialog',
    'battle_msg':     'battleMessage',
    'item_desc':      'itemDescription',
    'map_title':      'mapTitle',
}

_BLOCK_PAT = re.compile(r'\b(memory|segments)\s*\{(.*?)\}', re.S | re.I)


def _lnk_path_for_json(json_path: str) -> str | None:
    """
    Derive the LNK path from the JSON filename.
    ff4-en-data.json -> ff4-en.lnk
    ff4-jp-data.json -> ff4-jp.lnk
    """
    name = os.path.basename(json_path)
    m = re.match(r'^(ff4-\w+)-data\.json$', name)
    if not m:
        return None
    return os.path.join(os.path.dirname(json_path), m.group(1) + '.lnk')


def _num(v: str):
    v = v.strip()
    if v.startswith('$'):
        return int(v[1:], 16)
    if v.lower().startswith('0x'):
        return int(v, 16)
    try:
        return int(v)
    except ValueError:
        return v


def _parse_blocks(text: str) -> dict[str, list[tuple[str, dict]]]:
    """{'memory': [(name, {attr: value})...], 'segments': [...]}, in file order.
    Comments (# to end of line) are ignored; attributes may come in any order."""
    text = re.sub(r'#[^\n]*', '', text)
    out: dict[str, list[tuple[str, dict]]] = {'memory': [], 'segments': []}
    for m in _BLOCK_PAT.finditer(text):
        for entry in m.group(2).split(';'):
            if ':' not in entry:
                continue
            name, rest = entry.split(':', 1)
            attrs = {}
            for pair in rest.split(','):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    attrs[k.strip().lower()] = _num(v)
            name = name.strip()
            if name:
                out[m.group(1).lower()].append((name, attrs))
    return out


def _parse_lnk(lnk_path: str) -> dict[str, int]:
    """Parse an ld65 linker script and return {section_key: byte_capacity}."""
    try:
        with open(lnk_path, encoding='utf-8') as f:
            text = f.read()
    except FileNotFoundError:
        logger.warning(f"Linker file not found: {lnk_path}")
        return {}
    except Exception as e:
        logger.error(f"Failed to read linker file {lnk_path}: {e}")
        return {}

    blocks = _parse_blocks(text)
    areas = {}
    for name, a in blocks['memory']:
        if isinstance(a.get('start'), int) and isinstance(a.get('size'), int):
            areas[name] = {'start': a['start'], 'end': a['start'] + a['size']}

    by_area: dict[str, list[dict]] = {}
    for name, a in blocks['segments']:
        load = a.get('load')
        if load in areas:
            start = a.get('start')
            by_area.setdefault(load, []).append(
                {'name': name, 'start': start if isinstance(start, int) else None})

    caps: dict[str, int] = {}
    for area_name, segs in by_area.items():
        area = areas[area_name]
        pos = area['start']
        for seg in segs:                       # file order; never go backwards
            seg['start'] = max(seg['start'], pos) if seg['start'] is not None else pos
            pos = seg['start']
        segs.sort(key=lambda s: s['start'])    # stable: ties keep file order
        for i, seg in enumerate(segs):
            end = segs[i + 1]['start'] if i + 1 < len(segs) else area['end']
            key = _SEGMENT_TO_KEY.get(seg['name'])
            if key:
                caps[key] = caps.get(key, 0) + (end - seg['start'])
    return caps
