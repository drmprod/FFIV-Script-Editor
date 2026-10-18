"""
ff4_editor/model/textcodec.py
Python port of the encoding half of romtools/text-codec.js, so byte counts match the build.

How the real encoder works (and what this reproduces):
  * The encoding table is the union of the charTables listed in textEncoding[<encoding>];
    later tables override earlier ones for the same value.  Keys are plain strings: single
    characters, DTE pairs, control codes such as "\\wait[" or "\\char03".
  * At every position the LONGEST key that is a prefix of the remaining text wins (no word
    boundaries: "\\charge" is not "\\char" + "ge" because "\\char" alone is not a key).
  * A key ending in "[" takes a 1-byte parameter up to "]" (2 bytes in total), "[[" a 2-byte one.
  * Text that matches nothing is skipped (the build prints "Invalid character"), "\\xNN" is a raw byte.
  * A terminator byte is appended when the tables define "\\0" and the data does not end with it.
No Qt imports.
"""

from collections.abc import Iterable
from typing import Any

# Python ints cannot be NaN: unparsable parameters follow the JS code path (n = 0, nothing consumed).


def _num(text: str) -> int | None:
    """JS Number() for the forms that occur here: decimal or 0x-prefixed hex."""
    text = text.strip()
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return None


class TextCodec:
    def __init__(self, definition: dict[str, Any], char_tables: dict[str, Any]) -> None:
        self.table: dict[str, int] = {}
        for key in definition.get("charTable", []):
            chars = char_tables.get(key, {}).get("char", {})
            for code, value in chars.items():
                n = _num(code)
                if n is not None:
                    self.table[value] = n
        self._max_key = max((len(k) for k in self.table), default=0)
        self.terminator: int | None = self.table.get("\\0")
        self.pad: int = self.table.get("\\pad", 0)

    def _longest(self, text: str, i: int) -> str | None:
        for length in range(min(self._max_key, len(text) - i), 0, -1):
            cand = text[i : i + length]
            if cand in self.table:
                return cand
        return None

    def encode(self, text: str) -> bytes:
        data = bytearray()
        i = 0
        while i < len(text):
            match = self._longest(text, i)
            if match is None:
                if text.startswith("\\x", i):
                    n = _num("0" + text[i + 1 : i + 4])
                    i += 4
                    if n is not None:
                        data.append(n & 0xFF)
                else:
                    i += 1
                continue
            if match == "\\0":
                break
            value = self.table[match]
            i += len(match)
            if match.endswith("[["):
                end = text.find("]]", i)
                n = _num(text[i:end]) if end >= 0 else None
                if n is None or n > 0xFFFF:
                    n, end = 0, i
                i = end + 2
                value = (value << 16) | n
            elif match.endswith("["):
                end = text.find("]", i)
                n = _num(text[i:end]) if end >= 0 else None
                if n is None or n > 0xFF:
                    n, end = 0, i
                i = end + 1
                value = (value << 8) | n
            if value > 0xFF:
                data.append((value >> 8) & 0xFF)
                data.append(value & 0xFF)
            else:
                data.append(value)
        if self.terminator is not None and (not data or data[-1] != self.terminator):
            data.append(self.terminator)
        return bytes(data)

    def size(self, text: str) -> int:
        return len(self.encode(text))


# Used when a JSON has charTable but no textEncoding section (older/minimal files).
DEFAULT_ENCODINGS: dict[str, dict[str, Any]] = {
    "dialog": {"charTable": ["text", "dte", "nullTerminated"]},
    "fixedLength": {"charTable": ["text", "fixedLength"]},
    "menuText": {"charTable": ["text", "menuText"]},
    "nullTerminated": {"charTable": ["text", "nullTerminated"]},
}


def shared_bytes(encoded: Iterable[bytes]) -> int:
    """Size of a 'shared array' (no terminator / itemLength in its definition).

    ROMEncoder stores each item once: if an item's bytes already occur anywhere in the data built
    so far (whole item or inside a longer one) its pointer reuses that offset (findSubarray)."""
    data = b""
    for item in encoded:
        if data.find(item) == -1:
            data += item
    return len(data)
