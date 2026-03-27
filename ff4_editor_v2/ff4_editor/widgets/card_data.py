"""
ff4_editor/widgets/card_data.py
Lightweight data class representing one painted card on the canvas.
No Qt imports — safe to construct in bulk without widget overhead.
"""

from ..util.text_processing import json_to_display


class CardData:
    """
    Everything needed to paint one card and seed the editor overlay.

    Attributes
    ----------
    section     : str           — JSON key (e.g. 'eventDialog1')
    idx         : int|(int,int) — entry index; tuple (i,j) for mapDialog sub-strings
    header      : str           — label drawn above the text area
    lines       : list[str]     — display lines (result of json_to_display().split('\\n'))
    is_dialog   : bool          — True → multiline dialog entry; False → single-line name
    json_text   : str           — current JSON-encoded string (source of truth)
    byte_count  : int           — cached DTE-aware byte cost
    """

    __slots__ = ('section', 'idx', 'header', 'lines', 'is_dialog',
                 'json_text', 'byte_count')

    def __init__(self, section: str, idx, header: str,
                 is_dialog: bool, json_text: str, byte_count: int):
        self.section    = section
        self.idx        = idx
        self.header     = header
        self.is_dialog  = is_dialog
        self.json_text  = json_text
        self.byte_count = byte_count
        self.lines      = (json_to_display(json_text).split('\n')
                           if is_dialog else [json_text])

    def update(self, json_text: str, byte_count: int):
        """Update content after an edit commit."""
        self.json_text  = json_text
        self.byte_count = byte_count
        self.lines      = (json_to_display(json_text).split('\n')
                           if self.is_dialog else [json_text])
