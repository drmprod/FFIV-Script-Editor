"""
ff4_editor/build_tools.py
Where the build artefacts live, derived from the open JSON (no Qt, easy to test).

    <dir>/ff4-es-data.json  ->  make target "ff4-es"  ->  <dir>/rom/ff4-es.sfc
"""

import os
import re
import shutil

MESEN_NAMES = ("mesen", "Mesen", "mesen2", "Mesen2", "mesen-s", "Mesen-S")
ROM_EXTENSIONS = ("sfc", "spc", "smc")
DEFAULT_TARGET = "ff4-es"

_TARGET_RE = re.compile(r"(ff4-[A-Za-z0-9_]+?)-data\.json$", re.IGNORECASE)


def make_target(json_path: str | None) -> str:
    """`ff4-jp-data.json` -> `ff4-jp`; anything else falls back to ff4-es."""
    m = _TARGET_RE.match(os.path.basename(json_path or ""))
    return m.group(1) if m else DEFAULT_TARGET


def rom_dir(json_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(json_path)), "rom")


def find_rom(json_path: str | None) -> str | None:
    """The built ROM next to the JSON (rom/<target>.sfc|spc|smc), if it exists."""
    if not json_path:
        return None
    target = make_target(json_path)
    for ext in ROM_EXTENSIONS:
        candidate = os.path.join(rom_dir(json_path), f"{target}.{ext}")
        if os.path.isfile(candidate):
            return candidate
    return None


def find_mesen() -> str | None:
    """First Mesen executable found in PATH."""
    return next((p for p in (shutil.which(n) for n in MESEN_NAMES) if p), None)
