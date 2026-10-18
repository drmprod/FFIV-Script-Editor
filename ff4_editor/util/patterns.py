"""
ff4_editor/util/patterns.py
The text-code regular expressions, defined once.

A *code* is a backslash command in the stored JSON text: ``\\wait[2x4]``, ``\\char03``,
``\\n``, ``\\line``...  Two flavours exist on purpose:

* ``JSON_CODE``    - for stored text, where ``\\n`` and ``\\line`` must win over a following word
                     (``\\nHello`` is a newline followed by "Hello", not a code named "nHello").
* ``DISPLAY_CODE`` - for editor text, where newlines are already real newlines, so any
                     ``\\name`` or ``\\name[args]`` is a code.
"""

import re

JSON_CODE = re.compile(r"\\(?:n|line|char\d+|\w+(?:\[.*?\])?)")
DISPLAY_CODE = re.compile(r"\\(?:char(\d+)|\w+(?:\[.*?\])?)")
NAME_TOKEN = re.compile(r"\{[^}]+\}")  # {Cecil}
# A character name as it will print in game: {Cecil}, or an unresolved \char03 (group 1 = the name)
NAME_SLOT = re.compile(r"\{([^}]+)\}|\\char\d+")
# What may not be split by wrapping: {Name} and codes (display flavour, ASCII names)
ASCII_CODE = re.compile(r"\\[a-zA-Z0-9]+(?:\[.*?\])?")  # \wait[2x4], \char03
ATOM = re.compile(NAME_TOKEN.pattern + "|" + ASCII_CODE.pattern)
# Reflow tokens: atoms, any other run of non-space characters, or a single space
TOKEN = re.compile(ATOM.pattern + "|[^ ]+| ")

# Splits a line into plain text and atoms (the atoms are kept: capture group)
ATOM_SPLIT = re.compile("(" + ATOM.pattern + ")")
