"""
ff4_editor/model/encoding.py
DTE-aware byte-cost calculation for FF4 encoded strings.
No Qt imports.
"""

import re
from collections.abc import Iterable, Iterator

from ..util.patterns import JSON_CODE as CTRL_PAT

_CHAR_CODE = re.compile(r"\\char\d+")  # \charNN costs 2 bytes; \charge is an ordinary code


def build_dte_set(data: dict) -> set[str]:
    """Extract the DTE pair set from a loaded ff4-en-data.json dict."""
    return set(data.get("charTable", {}).get("dte", {}).get("char", {}).values())


def _units(s: str, dte_set: set[str]) -> Iterator[str]:
    """One item per ROM byte the string encodes to (greedy left-to-right DTE pairing, codes
    cost 1 byte, or 2 for \\charNN and codes with an argument).  Items are comparable keys,
    not real byte values."""
    i = 0
    while i < len(s):
        if s[i] == "\\":
            m = CTRL_PAT.match(s, i)
            if m:
                tok = m.group()
                yield tok
                if _CHAR_CODE.fullmatch(tok) or "[" in tok:
                    yield tok + "#"
                i += len(tok)
                continue
        if i + 1 < len(s) and s[i : i + 2] in dte_set:
            yield s[i : i + 2]
            i += 2
        else:
            yield s[i]
            i += 1


def encode_size(s: str, dte_set: set[str], add_terminator: bool = True) -> int:
    """
    Return the number of ROM bytes this string will occupy when encoded,
    optionally including the terminator byte.
    """
    return sum(1 for _ in _units(s, dte_set)) + (1 if add_terminator else 0)


class _SymbolTable:
    """Maps encoded units to single characters so byte strings can be searched with str.find."""

    def __init__(self) -> None:
        self._ids: dict[str, str] = {}

    def symbol(self, unit: str) -> str:
        sym = self._ids.get(unit)
        if sym is None:
            sym = self._ids[unit] = chr(0xE000 + len(self._ids))  # private-use area
        return sym


def shared_size(strings: Iterable[str], dte_set: set[str]) -> int:
    """Bytes of a 'shared array' section (no terminator / itemLength in its definition).

    ROMEncoder stores each item once: if an item's bytes already occur anywhere in the data built
    so far (as a whole item or inside a longer one), the pointer just reuses that offset."""
    table = _SymbolTable()
    data = ""
    for text in strings:
        item = "".join(table.symbol(u) for u in _units(text, dte_set)) + "\x00"
        if data.find(item) == -1:
            data += item
    return len(data)
