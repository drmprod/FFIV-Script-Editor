"""
ff4_editor/util/text_processing.py
Pure-Python text helpers: json↔display conversion, line measurement, reflow.
No Qt imports.
"""

import re
from ..constants import MAX_LINE_CHARS, BLANK_LINE_DISPLAY

# ── Spanish hyphenator ────────────────────────────────────────────────────────
try:
    import pyphen as _pyphen
    _es_dic = _pyphen.Pyphen(lang='es_ES')
except Exception:
    _es_dic = None


def _hyphen_break(word: str, space_left: int) -> tuple[str, str] | None:
    """
    Break `word` so that first_part + '-' fits within space_left chars.
    Uses pyphen Spanish syllable rules, falls back to hard break.
    Returns (first_part + '-', remainder) or None if impossible.

    pyphen.iterate() yields pairs longest-first, so the first match that
    fits is always the longest valid syllable break — no need to scan all.
    """
    if space_left < 2:
        return None
    if _es_dic is not None:
        for left, right in _es_dic.iterate(word):
            if len(left) + 1 <= space_left:
                return (left + '-', right)
    cut = space_left - 1
    if cut >= 1:
        return (word[:cut] + '-', word[cut:])
    return None

# ── Patterns ───────────────────────────────────────────────────────────────────
BOX_SPLIT_PAT = re.compile(r'(\\n|\\line)')
CTRL_PAT      = re.compile(r'\\(?:char\d+|\w+(?:\[.*?\])?)')
TOKEN_PAT     = re.compile(r'\{[^}]+\}|\\[a-zA-Z0-9]+(?:\[.*?\])?|[^ ]+| ')

# ── Character name substitution ───────────────────────────────────────────────
# Populated by model.json_model after loading data.
CHAR_NAMES: dict[int, str] = {}


def apply_char_names(s: str) -> str:
    def repl(m):
        name = CHAR_NAMES.get(int(m.group(1)))
        return '{' + name + '}' if name else m.group(0)
    return re.sub(r'\\char(\d+)', repl, s)


def revert_char_names(s: str) -> str:
    rev = {name: f'\\char{idx:02d}' for idx, name in CHAR_NAMES.items()}
    for name in sorted(rev, key=len, reverse=True):
        s = s.replace('{' + name + '}', rev[name])
    return s


# ── JSON ↔ display ─────────────────────────────────────────────────────────────

def json_to_display(s: str) -> str:
    """Convert JSON-encoded FF4 string to editor display text."""
    tokens = BOX_SPLIT_PAT.split(s)
    rows = []; buf = []; last_tok = None
    for tok in tokens:
        if tok == r'\n':
            rows.append(''.join(buf)); buf = []; last_tok = r'\n'
        elif tok == r'\line':
            rows.append(BLANK_LINE_DISPLAY); buf = []; last_tok = r'\line'
        else:
            buf.append(tok)
    tail = ''.join(buf)
    if tail or last_tok == r'\n':
        rows.append(tail)
    return apply_char_names('\n'.join(rows))


def display_to_json(s: str) -> str:
    """Convert editor display text back to JSON-encoded FF4 string."""
    s = revert_char_names(s)
    rows = s.split('\n'); out = []
    for i, row in enumerate(rows):
        if row == BLANK_LINE_DISPLAY:
            out.append(r'\line')
        else:
            out.append(row)
            if i < len(rows) - 1:
                out.append(r'\n')
    return ''.join(out)


# ── Visible length ─────────────────────────────────────────────────────────────

def visible_len(text: str) -> int:
    """Return visible character count, ignoring escape sequences and {Name} tokens."""
    s = re.sub(r'\\[a-zA-Z0-9]+(?:\[.*?\])?', '', text)
    s = re.sub(r'\{[^}]+\}', '      ', s)   # {Name} ≈ 6 chars
    return len(s)


# ── Line reflow ────────────────────────────────────────────────────────────────

def reflow_line(line: str, limit: int = MAX_LINE_CHARS,
                hyphenate: bool = False) -> list[str]:
    """
    Wrap a single display line to fit within `limit` visible characters.
    If `hyphenate` is True, attempts Spanish syllable-based hyphenation
    whenever a word doesn't fit on the current line (not just as last resort).
    Returns a list of wrapped lines (may be just [line] if already fits).
    """
    if visible_len(line) <= limit:
        return [line]
    tokens = TOKEN_PAT.findall(line)
    result = []; cur = ''; cvlen = 0
    for tok in tokens:
        if tok == ' ':
            if cvlen + 1 <= limit:
                cur += ' '; cvlen += 1
            continue
        tv = visible_len(tok)
        if cvlen + tv <= limit:
            cur += tok; cvlen += tv
            continue
        # Token doesn't fit on current line — try hyphenation first
        if hyphenate and cur.rstrip() \
                and not tok.startswith('\\') and not tok.startswith('{'):
            space_left = limit - cvlen
            broken = _hyphen_break(tok, space_left)
            if broken:
                first, rest = broken
                result.append((cur + first).rstrip())
                cur = rest; cvlen = visible_len(rest)
                continue
        # No hyphen break — normal word wrap
        if cur.rstrip():
            result.append(cur.rstrip())
            cur = tok; cvlen = tv
        else:
            # Word alone still too long — hard hyphenate
            if hyphenate and not tok.startswith('\\') and not tok.startswith('{'):
                while visible_len(tok) > limit:
                    broken = _hyphen_break(tok, limit)
                    if broken:
                        first, tok = broken
                        result.append(first)
                    else:
                        result.append(tok[:limit - 1] + '-')
                        tok = tok[limit - 1:]
            cur = tok; cvlen = visible_len(tok)
    if cur.rstrip():
        result.append(cur.rstrip())
    return result if result else [line]


def reflow_text(text: str, limit: int = MAX_LINE_CHARS) -> str:
    """
    Reflow a full multi-line display text (as in the editor).
    Preserves blank-line markers. Returns reflowed text.
    """
    lines = text.split('\n')
    out = []
    for line in lines:
        if line == BLANK_LINE_DISPLAY:
            out.append(line)
        else:
            out.extend(reflow_line(line, limit))
    return '\n'.join(out)
