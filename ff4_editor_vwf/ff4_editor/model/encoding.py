"""
ff4_editor/model/encoding.py
DTE-aware byte-cost calculation for FF4 encoded strings.
No Qt imports.
"""

import re

CTRL_PAT = re.compile(r'\\(?:n|line|char\d+|\w+(?:\[.*?\])?)')


def build_dte_set(data: dict) -> set[str]:
    """Extract the DTE pair set from a loaded ff4-en-data.json dict."""
    return set(data.get('charTable', {}).get('dte', {}).get('char', {}).values())


def encode_size(s: str, dte_set: set[str], add_terminator: bool = True) -> int:
    """
    Return the number of ROM bytes this string will occupy when encoded,
    optionally including the terminator byte.
    """
    cost = 0; i = 0
    while i < len(s):
        if s[i] == '\\':
            m = CTRL_PAT.match(s, i)
            if m:
                tok = m.group()
                cost += 2 if ('char' in tok or '[' in tok) else 1
                i += len(tok)
                continue
        if i + 1 < len(s) and s[i:i+2] in dte_set:
            cost += 1; i += 2
        else:
            cost += 1; i += 1
    return cost + (1 if add_terminator else 0)
