"""
ff4_editor/util/text_processing.py
Pure-Python text helpers: json↔display conversion, line measurement, reflow.
No Qt imports.
"""

import contextlib
import re
from collections.abc import Callable
from typing import Any

from ..constants import BLANK_LINE_DISPLAY, MAX_LINE_CHARS, NAME_MAX_CHARS, NAME_WORST_CHAR
from ..errors import logger
from .patterns import ATOM, DISPLAY_CODE, NAME_SLOT, TOKEN

# ── Patterns ───────────────────────────────────────────────────────────────────
BOX_SPLIT_PAT = re.compile(r"(\\n|\\line)")
CTRL_PAT = DISPLAY_CODE
TOKEN_PAT = TOKEN


# ── Character Name Registry ────────────────────────────────────────────────────
class CharNameRegistry:
    """
    Thread-safe registry for character names with change notification.
    Replaces the global CHAR_NAMES dict with a proper encapsulated class.
    """

    def __init__(self) -> None:
        self._names: dict[int, str] = {}
        self._callbacks: list[Callable[[], None]] = []

    @property
    def names(self) -> dict[int, str]:
        """Get a copy of the character names dict."""
        return self._names.copy()

    def set_names(self, new_names: dict[int, str]) -> None:
        """Set character names and notify all callbacks."""
        self._names = {k: v for k, v in new_names.items() if isinstance(k, int) and isinstance(v, str)}
        self._notify()

    def get(self, idx: int) -> str | None:
        """Get a character name by index."""
        return self._names.get(idx)

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when names change."""
        self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """Unregister a callback."""
        with contextlib.suppress(ValueError):
            self._callbacks.remove(callback)

    def _notify(self) -> None:
        """Notify all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb()
            except Exception:  # noqa: BLE001 - one broken subscriber must not stop the rest
                logger.warning("CHAR_NAMES callback failed", exc_info=True)


# Global singleton instance
_char_names_registry: CharNameRegistry = CharNameRegistry()


# Public API for backward compatibility
def get_char_names() -> dict[int, str]:
    """Get a copy of the character names dict."""
    return _char_names_registry.names


def set_char_names(new_names: dict[int, str]) -> None:
    """Set CHAR_NAMES and notify callbacks."""
    _char_names_registry.set_names(new_names)


def get_char_name(idx: int) -> str | None:
    """Get a single character name by index."""
    return _char_names_registry.get(idx)


def register_char_names_changed(callback: Callable[[], None]) -> None:
    """Register a callback to be called when CHAR_NAMES changes."""
    _char_names_registry.register_callback(callback)


def unregister_char_names_changed(callback: Callable[[], None]) -> None:
    """Unregister a callback."""
    _char_names_registry.unregister_callback(callback)


def _ambiguous_names() -> set[str]:
    """Names used by more than one character index: {Name} could not be reverted safely."""
    seen: set[str] = set()
    dup: set[str] = set()
    for n in _char_names_registry.names.values():
        (dup if n in seen else seen).add(n)
    return dup


def apply_char_names(s: str) -> str:
    """Convert \\charNN codes to {Name} tokens using current CHAR_NAMES."""

    ambiguous = _ambiguous_names()

    def repl(m: re.Match[str]) -> str:
        # Only process \charNN patterns (group 1 exists)
        # The second alternative (\w+...) has no group 1
        if m.group(1) is not None:
            name = _char_names_registry.get(int(m.group(1)))
            if not name or name in ambiguous:
                return m.group(0)  # unknown, or shared by several characters: keep \\charNN
            return "{" + name + "}"
        return m.group(0)

    return CTRL_PAT.sub(repl, s)


def revert_char_names(s: str) -> str:
    """Convert {Name} tokens back to \\charNN codes."""
    dup = _ambiguous_names()
    rev = {name: f"\\char{idx:02d}" for idx, name in _char_names_registry.names.items() if name not in dup}
    for name in sorted(rev, key=len, reverse=True):
        s = s.replace("{" + name + "}", rev[name])
    return s


# ── JSON ↔ display ─────────────────────────────────────────────────────────────


def json_to_display(s: str) -> str:
    """Convert JSON-encoded FF4 string to editor display text."""
    tokens = BOX_SPLIT_PAT.split(s)
    rows: list[str] = []
    buf: list[str] = []
    last_tok: str | None = None
    for tok in tokens:
        if tok == r"\n":
            rows.append("".join(buf))
            buf = []
            last_tok = r"\n"
        elif tok == r"\line" and not "".join(buf):
            rows.append(BLANK_LINE_DISPLAY)
            buf = []
            last_tok = r"\line"
        else:
            buf.append(tok)
    tail = "".join(buf)
    if tail or last_tok == r"\n":
        rows.append(tail)
    return apply_char_names("\n".join(rows))


def display_to_json(s: str) -> str:
    """Convert editor display text back to JSON-encoded FF4 string."""
    s = revert_char_names(s)
    rows = s.split("\n")
    out: list[str] = []
    for i, row in enumerate(rows):
        if row == BLANK_LINE_DISPLAY:
            out.append(r"\line")
        else:
            out.append(row.replace(BLANK_LINE_DISPLAY, ""))  # a stray separator glyph is not text
            if i < len(rows) - 1:
                out.append(r"\n")
    return "".join(out)


# ── Visible length ─────────────────────────────────────────────────────────────


def visible_len(text: str, measure: Callable[[str], int] | None = None) -> int:
    """Visible character count: codes take no room, and every {Name} / \\charNN counts as a
    worst-case name (NAME_MAX_CHARS wide, see constants) because the player can rename characters.
    If `measure` is given, names are as wide as measure() says, but never narrower than the
    worst case."""
    slot = NAME_MAX_CHARS
    if measure:
        slot = measure(NAME_WORST_CHAR * NAME_MAX_CHARS)

    def repl(m: re.Match[str]) -> str:
        width = slot
        if measure and m.group(1) is not None:
            width = max(measure("{" + m.group(1) + "}"), slot)
        return " " * width

    return len(CTRL_PAT.sub("", NAME_SLOT.sub(repl, text)))


# ── Line reflow ────────────────────────────────────────────────────────────────


def _cut_points(tok: str) -> list[int]:
    """Indices where `tok` may be split: never inside a {Name} or a backslash code."""
    inside: set[int] = set()
    for m in ATOM.finditer(tok):
        inside.update(range(m.start() + 1, m.end()))
    return [i for i in range(1, len(tok)) if i not in inside]


def _hard_cut(tok: str, limit: int, m: Callable[[str], int]) -> int:
    """Largest cut k such that tok[:k] + '-' fits in `limit`; at least the first allowed
    point (so progress is always made). Codes and {Names} are never split."""
    points = _cut_points(tok)
    if not points:
        return len(tok)
    fitting = [k for k in points if m(tok[:k] + "-") <= limit]
    return fitting[-1] if fitting else points[0]


def reflow_line(
    line: str, limit: int = MAX_LINE_CHARS, measure: Callable[[str], int] | None = None
) -> list[str]:
    """
    Wrap a single display line to fit within `limit` units.
    `measure(text) -> int` gives the width of a piece of text; by default it is the
    visible character count, with the VWF font it is the width in game pixels.
    Words longer than a whole line are cut with a hyphen; {Names} and backslash codes are
    never split.  Returns a list of wrapped lines (just [line] if it already fits).
    """
    m: Callable[[str], int] = measure or visible_len
    if m(line) <= limit:
        return [line]
    sp = m(" ") or 1
    result: list[str] = []
    cur = ""
    cvlen = 0

    for tok in TOKEN_PAT.findall(line):
        if tok == " ":
            if cvlen + sp <= limit:
                cur += " "
                cvlen += sp
            continue
        tv = m(tok)
        if cvlen + tv <= limit:
            cur += tok
            cvlen += tv
            continue
        if cur.rstrip():  # start a new line with this word
            result.append(cur.rstrip())
        while tv > limit and len(_cut_points(tok)) > 0:  # a word wider than a whole line
            k = _hard_cut(tok, limit, m)
            if k >= len(tok):
                break
            result.append(tok[:k] + "-")
            tok = tok[k:]
            tv = m(tok)
        cur, cvlen = tok, tv
    if cur.rstrip():
        result.append(cur.rstrip())
    return result if result else [line]


def compute_reflow_limit(config: Any, vwf_font: Any = None) -> int:
    """Get the character/pixel limit for reflow based on config and VWF font."""
    if vwf_font and config.vwf_enabled:
        return config.vwf_limit_px
    return getattr(config, "char_limit", MAX_LINE_CHARS)


def compute_reflow_measure(config: Any, vwf_font: Any = None) -> Callable[[str], int]:
    """Get the measure function for reflow based on config and VWF font."""
    if vwf_font and config.vwf_enabled:
        return vwf_font.measure
    return visible_len
