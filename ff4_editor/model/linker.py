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
from dataclasses import dataclass

from ..errors import logger

# ld65 segment name -> JSON section key.  Only segments that hold exactly ONE text section
# are mapped.  Name tables (attack_name, char_name, ...) are deliberately left
# out: those segments also contain item/magic names, class names, etc., so the whole segment
# size would overstate the room for a single section; they use the JSON `range` instead.
_SEGMENT_TO_KEY = {
    "event_dlg1": "eventDialog1",
    "event_dlg2": "eventDialog2",
    "event_dlg3": "eventDialog3",
    "map_dlg": "mapDialog",
    "map_dlg1": "mapDialog",
    "map_dlg2": "mapDialog",
    "battle_dlg": "battleDialog",
    "battle_msg": "battleMessage",
    "item_desc": "itemDescription",
    "status_name": "statusName",  # pointer table + text only (btlgfx_data.asm)
    "map_title": "mapTitle",
}

_BLOCK_PAT = re.compile(r"\b(memory|segments)\s*\{(.*?)\}", re.S | re.I)


def _lnk_path_for_json(json_path: str) -> str | None:
    """
    Derive the LNK path from the JSON filename.
    ff4-en-data.json -> ff4-en.lnk
    ff4-jp-data.json -> ff4-jp.lnk
    """
    name = os.path.basename(json_path)
    m = re.match(r"^(ff4-\w+)-data\.json$", name)
    if not m:
        return None
    return os.path.join(os.path.dirname(json_path), m.group(1) + ".lnk")


def _num(v: str) -> int | str:
    v = v.strip()
    if v.startswith("$"):
        return int(v[1:], 16)
    if v.lower().startswith("0x"):
        return int(v, 16)
    try:
        return int(v)
    except ValueError:
        return v


def _parse_blocks(text: str) -> dict[str, list[tuple[str, dict]]]:
    """{'memory': [(name, {attr: value})...], 'segments': [...]}, in file order.
    Comments (# to end of line) are ignored; attributes may come in any order."""
    text = re.sub(r"#[^\n]*", "", text)
    out: dict[str, list[tuple[str, dict]]] = {"memory": [], "segments": []}
    for m in _BLOCK_PAT.finditer(text):
        for entry in m.group(2).split(";"):
            if ":" not in entry:
                continue
            name, rest = entry.split(":", 1)
            attrs = {}
            for pair in rest.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    attrs[k.strip().lower()] = _num(v)
            name = name.strip()
            if name:
                out[m.group(1).lower()].append((name, attrs))
    return out


@dataclass(frozen=True)
class Capacity:
    """Room for one section.  `exact` is False when it is only an estimate: a segment without
    `start =` (its position/size is unknown to the script) or a neighbour in that situation."""

    bytes: int
    exact: bool


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"Linker file not found: {path}")
    except (OSError, UnicodeDecodeError) as e:
        logger.error(f"Failed to read linker file {path}: {e}")
    return None


def _layout(text: str) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """({area: {start, end}}, {area: [segment dicts in file order]}) of an ld65 script."""
    blocks = _parse_blocks(text)
    areas = {}
    for name, a in blocks["memory"]:
        if isinstance(a.get("start"), int) and isinstance(a.get("size"), int):
            areas[name] = {"start": a["start"], "end": a["start"] + a["size"]}
    by_area: dict[str, list[dict]] = {}
    for name, a in blocks["segments"]:
        load = a.get("load")
        if load in areas:
            start = a.get("start")
            by_area.setdefault(load, []).append(
                {"name": name, "start": start if isinstance(start, int) else None}
            )
    return areas, by_area


def parse_lnk_capacities(lnk_path: str) -> dict[str, Capacity]:
    """Capacity of every mapped text section from the ld65 script alone (see module docstring)."""
    text = _read(lnk_path)
    if text is None:
        return {}
    areas, by_area = _layout(text)
    caps: dict[str, Capacity] = {}
    for area_name, segs in by_area.items():
        area = areas[area_name]
        pos = area["start"]
        for seg in segs:  # file order; never go backwards
            seg["explicit"] = seg["start"] is not None
            seg["start"] = max(seg["start"], pos) if seg["start"] is not None else pos
            pos = seg["start"]
        segs.sort(key=lambda s: s["start"])  # stable: ties keep file order
        for i, seg in enumerate(segs):
            last = i + 1 == len(segs)
            end = area["end"] if last else segs[i + 1]["start"]
            exact = seg["explicit"] and (last or segs[i + 1]["explicit"])
            key = _SEGMENT_TO_KEY.get(seg["name"])
            if key:
                prev = caps.get(key)
                size = (end - seg["start"]) + (prev.bytes if prev else 0)
                caps[key] = Capacity(size, exact and (prev.exact if prev else True))
    return caps


def _parse_lnk(lnk_path: str) -> dict[str, int]:
    """Parse an ld65 linker script and return {section_key: byte_capacity} (estimates included)."""
    return {k: c.bytes for k, c in parse_lnk_capacities(lnk_path).items()}


# ── ld65 map file (written by `ld65 -m`, e.g. rom/ff4-es.map) ──────────────────────────────
_MAP_ROW = re.compile(r"^(\S+)\s+([0-9A-Fa-f]{6})\s+([0-9A-Fa-f]{6})\s+([0-9A-Fa-f]{6})\s+[0-9A-Fa-f]+\s*$")


def map_path_for_json(json_path: str) -> str | None:
    """ff4-es-data.json -> <dir>/rom/ff4-es.map (where the Makefile writes it)."""
    lnk = _lnk_path_for_json(json_path)
    if lnk is None:
        return None
    return os.path.join(os.path.dirname(lnk), "rom", os.path.basename(lnk)[: -len(".lnk")] + ".map")


def parse_map_segments(map_path: str) -> dict[str, tuple[int, int]]:
    """{segment: (start, size)} from the 'Segment list' of an ld65 map file."""
    try:
        with open(map_path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    segs: dict[str, tuple[int, int]] = {}
    in_list = False
    for line in lines:
        if line.startswith("Segment list:"):
            in_list = True
        elif in_list and line and not line.startswith(("Name", "-")):
            m = _MAP_ROW.match(line)
            if m:
                segs[m.group(1)] = (int(m.group(2), 16), int(m.group(4), 16))
            else:
                break  # next section of the map
    return segs


def capacities_from_map(lnk_path: str, map_path: str) -> dict[str, Capacity]:
    """Exact capacities: where each segment really starts (from the build) up to the next one,
    or the end of its memory area.  Only valid for a map newer than the script."""
    segs = parse_map_segments(map_path)
    text = _read(lnk_path)
    if not segs or text is None:
        return {}
    areas, _ = _layout(text)
    starts = sorted({st for st, _ in segs.values()})
    caps: dict[str, Capacity] = {}
    for name, (start, _size) in segs.items():
        key = _SEGMENT_TO_KEY.get(name)
        if not key:
            continue
        later = [st for st in starts if st > start]
        bounds = [a["end"] for a in areas.values() if a["start"] <= start < a["end"]]
        end = min(later[:1] + bounds, default=None)
        if end is None:
            continue
        prev = caps.get(key)
        caps[key] = Capacity((end - start) + (prev.bytes if prev else 0), True)
    return caps
