"""
ff4_editor/util/text_processing.py
Pure-Python text helpers: json↔display conversion, line measurement, reflow.
No Qt imports.
"""

import re
from typing import Callable, Optional
from ..constants import MAX_LINE_CHARS, BLANK_LINE_DISPLAY

from ..errors import logger

# ── Patterns ───────────────────────────────────────────────────────────────────
BOX_SPLIT_PAT = re.compile(r'(\\n|\\line)')
CTRL_PAT: re.Pattern[str] = re.compile(r'\\(?:char(\d+)|\w+(?:\[.*?\])?)')
TOKEN_PAT: re.Pattern[str] = re.compile(r'\{[^}]+\}|\\[a-zA-Z0-9]+(?:\[.*?\])?|[^ ]+| ')


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
    
    def get(self, idx: int) -> Optional[str]:
        """Get a character name by index."""
        return self._names.get(idx)
    
    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when names change."""
        self._callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """Unregister a callback."""
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass
    
    def _notify(self) -> None:
        """Notify all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.debug(f"CHAR_NAMES callback failed: {e}")


# Global singleton instance
_char_names_registry: CharNameRegistry = CharNameRegistry()


# Public API for backward compatibility
def get_char_names() -> dict[int, str]:
    """Get a copy of the character names dict."""
    return _char_names_registry.names


def set_char_names(new_names: dict[int, str]) -> None:
    """Set CHAR_NAMES and notify callbacks."""
    _char_names_registry.set_names(new_names)


def get_char_name(idx: int) -> Optional[str]:
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
    def repl(m: re.Match[str]) -> str:
        # Only process \charNN patterns (group 1 exists)
        # The second alternative (\w+...) has no group 1
        if m.group(1) is not None:
            name = _char_names_registry.get(int(m.group(1)))
            if not name or name in _ambiguous_names():
                return m.group(0)        # unknown, or shared by several characters: keep \\charNN
            return '{' + name + '}'
        return m.group(0)
    return CTRL_PAT.sub(repl, s)


def revert_char_names(s: str) -> str:
    """Convert {Name} tokens back to \\charNN codes."""
    dup = _ambiguous_names()
    rev = {name: f'\\char{idx:02d}' for idx, name in _char_names_registry.names.items()
           if name not in dup}
    for name in sorted(rev, key=len, reverse=True):
        s = s.replace('{' + name + '}', rev[name])
    return s


# ── JSON ↔ display ─────────────────────────────────────────────────────────────

def json_to_display(s: str) -> str:
    """Convert JSON-encoded FF4 string to editor display text."""
    tokens = BOX_SPLIT_PAT.split(s)
    rows: list[str] = []
    buf: list[str] = []
    last_tok: Optional[str] = None
    for tok in tokens:
        if tok == r'\n':
            rows.append(''.join(buf))
            buf = []
            last_tok = r'\n'
        elif tok == r'\line' and not ''.join(buf):
            rows.append(BLANK_LINE_DISPLAY)
            buf = []
            last_tok = r'\line'
        else:
            buf.append(tok)
    tail = ''.join(buf)
    if tail or last_tok == r'\n':
        rows.append(tail)
    return apply_char_names('\n'.join(rows))


def display_to_json(s: str) -> str:
    """Convert editor display text back to JSON-encoded FF4 string."""
    s = revert_char_names(s)
    rows = s.split('\n')
    out: list[str] = []
    for i, row in enumerate(rows):
        if row == BLANK_LINE_DISPLAY:
            out.append(r'\line')
        else:
            out.append(row)
            if i < len(rows) - 1:
                out.append(r'\n')
    return ''.join(out)


# ── Visible length ─────────────────────────────────────────────────────────────

def visible_len(text: str, measure: Optional[Callable[[str], int]] = None) -> int:
    """Return visible character count, ignoring escape sequences and {Name} tokens.
    If `measure` is provided, it will be used to measure {Name} tokens; otherwise they
    are approximated as 6 characters."""
    s = CTRL_PAT.sub('', text)
    if measure:
        # Replace {Name} tokens with their measured width
        def repl(m):
            name = m.group(0)[1:-1]  # Remove { }
            return ' ' * measure('{' + name + '}')
        s = re.sub(r'\{[^}]+\}', repl, s)
    else:
        s = re.sub(r'\{[^}]+\}', '      ', s)   # {Name} ≈ 6 chars
    return len(s)


# ── Line reflow ────────────────────────────────────────────────────────────────

def reflow_line(
    line: str,
    limit: int = MAX_LINE_CHARS,
    measure: Optional[Callable[[str], int]] = None
) -> list[str]:
    """
    Wrap a single display line to fit within `limit` units.
    `measure(text) -> int` gives the width of a piece of text; by default it is the
    visible character count, with the VWF font it is the width in game pixels.
    Returns a list of wrapped lines (may be just [line] if already fits).
    """
    m: Callable[[str], int] = measure or visible_len
    if m(line) <= limit:
        return [line]
    sp = m(' ') or 1
    tokens = TOKEN_PAT.findall(line)
    result: list[str] = []
    cur = ''
    cvlen = 0

    def hard_cut(tok: str) -> int:
        """largest k such that tok[:k] + '-' fits in `limit` (at least 1)."""
        k = len(tok) - 1
        while k > 1 and m(tok[:k] + '-') > limit:
            k -= 1
        return max(1, k)

    for tok in tokens:
        if tok == ' ':
            if cvlen + sp <= limit:
                cur += ' '
                cvlen += sp
            continue
        tv = m(tok)
        if cvlen + tv <= limit:
            cur += tok
            cvlen += tv
            continue
        # Token doesn't fit - normal word wrap
        if cur.rstrip():
            result.append(cur.rstrip())
            cur = tok
            cvlen = tv
        else:
            # Word alone still too long - hard cut
            while m(tok) > limit and len(tok) > 1:
                k = hard_cut(tok)
                result.append(tok[:k] + '-')
                tok = tok[k:]
            cur = tok
            cvlen = m(tok)
    if cur.rstrip():
        result.append(cur.rstrip())
    return result if result else [line]


def compute_reflow_limit(config, vwf_font=None) -> int:
    """Get the character/pixel limit for reflow based on config and VWF font."""
    if vwf_font and config.vwf_enabled:
        return config.vwf_limit_px
    return getattr(config, 'char_limit', MAX_LINE_CHARS)


def compute_reflow_measure(config, vwf_font=None):
    """Get the measure function for reflow based on config and VWF font."""
    if vwf_font and config.vwf_enabled:
        return vwf_font.measure
    return visible_len