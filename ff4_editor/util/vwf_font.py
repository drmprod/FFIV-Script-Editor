"""
ff4_editor/util/vwf_font.py

Fuente de ancho variable del juego (la misma que field/vwf.asm):
  - lee font.png (tiles de 8x8, 16 por fila, rejilla de 1 px entre celdas),
  - recorta cada glifo a la izquierda y calcula el avance = ancho de tinta + gap
    (los codigos que no son texto -- iconos -- avanzan 8 px; el espacio avanza `space`),
  - mide texto en pixeles del juego,
  - genera una fuente TrueType en memoria (cada pixel = 1 unidad) para que Qt
    dibuje y mida el texto exactamente como el juego.

Debe mantenerse identica a tools/vwf_gen.py (tablas ROM).  Sin imports de Qt.
"""

import hashlib
import io

from ..constants import NAME_MAX_CHARS, NAME_WORST_CHAR
from ..errors import logger
from .patterns import ASCII_CODE, NAME_SLOT

PALETTE = [(12, 10, 26), (80, 80, 80), (255, 255, 255), (180, 180, 180)]
FAMILY = "FF4 VWF"
UNIT = 8  # unidades de fuente por pixel del juego (FreeType exige unitsPerEm >= 16)

# esquema de codigos del proyecto; se usa si el JSON no trae charTable.text
DEFAULT_TEXT = {}
for _i in range(26):
    DEFAULT_TEXT[0x42 + _i] = chr(65 + _i)
    DEFAULT_TEXT[0x5C + _i] = chr(97 + _i)
for _i in range(10):
    DEFAULT_TEXT[0x80 + _i] = str(_i)
for _i, _c in enumerate("¡¿ÁÉÍÓÚáéíóúñü"):
    DEFAULT_TEXT[0x8A + _i] = _c
for _i, _c in enumerate("'.-…!?%/:,"):
    DEFAULT_TEXT[0xC0 + _i] = _c
DEFAULT_TEXT[0xFF] = " "


# Glyphs for characters the game cannot print (editor syntax such as \\wait[2x4]).  They
# exist only so that Qt never falls back to another font (which would change the line
# height); 5x7 pixels, advance 8.
_EXTRA = {
    "\\": ["#....", ".#...", ".#...", "..#..", "..#..", "...#.", "...#."],
    "[": ["###..", "#....", "#....", "#....", "#....", "#....", "###.."],
    "]": ["..###", "....#", "....#", "....#", "....#", "....#", "..###"],
    "(": ["..#..", ".#...", "#....", "#....", "#....", ".#...", "..#.."],
    ")": ["..#..", "...#.", "....#", "....#", "....#", "...#.", "..#.."],
    '"': ["#.#..", "#.#..", ".....", ".....", ".....", ".....", "....."],
    ";": [".....", "..#..", ".....", ".....", "..#..", "..#..", ".#..."],
    "+": [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    "=": [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    "*": [".....", "#.#.#", ".###.", "#####", ".###.", "#.#.#", "....."],
    "<": ["...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."],
    ">": [".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."],
    "_": [".....", ".....", ".....", ".....", ".....", ".....", "#####"],
    "#": [".#.#.", "#####", ".#.#.", ".#.#.", "#####", ".#.#.", "....."],
    "&": [".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"],
    "@": [".###.", "#...#", "#.###", "#.#.#", "#.###", "#....", ".###."],
    "|": ["..#..", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "~": [".....", ".....", ".##.#", "#.##.", ".....", ".....", "....."],
    "^": ["..#..", ".#.#.", "#...#", ".....", ".....", ".....", "....."],
    "`": [".#...", "..#..", ".....", ".....", ".....", ".....", "....."],
    "$": ["..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."],
}
_TOFU = ["#####", "#...#", "#...#", "#...#", "#...#", "#...#", "#####"]


def text_codes_from_json(char_table_text: dict | None) -> dict[int, str]:
    """charTable.text.char ({'0x42': 'A', ...}) -> {codigo: caracter} (solo 1 caracter, <= $FF)."""
    if not char_table_text:
        return dict(DEFAULT_TEXT)
    m = {}
    for k, v in char_table_text.items():
        try:
            code = int(k, 16)
        except ValueError:
            continue
        if code <= 0xFF and len(v) == 1:
            m[code] = v
    m[0xFF] = " "
    return m


def _load_tiles(png_path):
    from PIL import Image

    img = Image.open(png_path).convert("RGB")
    cell = (img.width - 1) // 16
    scale = (cell - 1) // 8
    tiles = []
    for t in range(256):
        ox, oy = 1 + (t % 16) * cell, 1 + (t // 16) * cell
        rows = []
        for y in range(8):
            row = []
            for x in range(8):
                px = img.getpixel((ox + x * scale + scale // 2, oy + y * scale + scale // 2))
                assert isinstance(px, tuple)
                row.append(
                    min(
                        range(4),
                        key=lambda i: sum((a - b) ** 2 for a, b in zip(tuple(px), PALETTE[i], strict=True)),
                    )
                )
            rows.append(row)
        tiles.append(rows)
    return tiles


def _rect(pen, x0: int, y0: int, x1: int, y1: int) -> None:
    """Closed rectangle in font units from pixel coordinates."""
    x0, y0, x1, y1 = x0 * UNIT, y0 * UNIT, x1 * UNIT, y1 * UNIT
    pen.moveTo((x0, y0))
    pen.lineTo((x0, y1))
    pen.lineTo((x1, y1))
    pen.lineTo((x1, y0))
    pen.closePath()


def _draw_rows(pen, rows, top: int) -> None:
    """One rectangle per horizontal run of ink; row r spans y = top-r .. top-r+1."""
    for r, row in enumerate(rows):
        y = top - r
        x = 0
        while x < len(row):
            if row[x]:
                start = x
                while x < len(row) and row[x]:
                    x += 1
                _rect(pen, start, y, x, y + 1)
            else:
                x += 1


class VWFFont:
    """Anchos y glifos del juego.  `code_to_char` = {codigo: caracter} del charTable de texto."""

    def __init__(self, png_path, code_to_char=None, gap=1, space=4, overrides=None):
        self.code_to_char = dict(code_to_char) if code_to_char else dict(DEFAULT_TEXT)
        self.char_to_code = {c: k for k, c in self.code_to_char.items()}
        self.char_to_code[" "] = 0xFF
        self.gap, self.space = gap, space
        self.width = [0] * 256
        self.mask: list[list[int]] = [
            [0] * 10 for _ in range(256)
        ]  # mascara por fila (8 + 2 de desborde), recortada a la izquierda
        self.bitmap: list[list[list[int]]] = [
            [] for _ in range(256)
        ]  # filas de 'ink' recortadas (lista de listas 0/1)
        self.dropped_loss: list[str] = []
        self._load_glyphs(_load_tiles(png_path))
        overrides = dict(overrides or {})
        self._apply_drop(overrides.pop("_drop", {}))
        self.width[0xFF] = space
        for k, v in overrides.items():
            code = int(k, 16) if str(k).lower().startswith("0x") else ord(k)
            self.width[code] = v

        # TTF cache: key = (line_pitch, font_data_hash), value = ttf_bytes
        self._ttf_cache: dict[tuple[int, str], bytes] = {}

    def _load_glyphs(self, tiles) -> None:
        """Fill width/mask/bitmap from the 256 tiles: ink is trimmed horizontally."""
        bg = tiles[0xFF][0][0]
        text = set(self.code_to_char)
        for code, rows in enumerate(tiles):
            cols = [x for r in rows for x, p in enumerate(r) if p != bg]
            if not cols:
                self.width[code] = self.space
                self.bitmap[code] = [[] for _ in range(8)]
                continue
            left, right = min(cols), max(cols)
            bm = [[1 if p != bg else 0 for p in r][left : right + 1] for r in rows]
            self.bitmap[code] = bm
            for r, row in enumerate(bm):
                m = 0
                for x, v in enumerate(row):
                    if v:
                        m |= 1 << (7 - x)
                self.mask[code][r] = m
            ink = right - left + 1
            self.width[code] = ink + self.gap if code in text else 8

    def _apply_drop(self, drops: dict) -> None:
        """Lower descender glyphs (j p q g y...) by `dy` rows; the game only has 2 spare rows."""
        for chars, dy in drops.items():
            for ch in chars:
                code = self.char_to_code.get(ch)
                if code is None or not self.bitmap[code]:
                    continue
                if dy < 0 or dy > 2:
                    self.dropped_loss.append(ch)
                    logger.warning(
                        f"Glyph '{ch}' (U+{ord(ch):04X}) dropped: _drop value {dy} exceeds limit (max 2)"
                    )
                    continue
                bm = self.bitmap[code]
                w = max((len(r) for r in bm), default=0)
                self.bitmap[code] = [[0] * w for _ in range(dy)] + bm  # 8 + dy filas: no se pierde tinta
                self.mask[code] = ([0] * dy + self.mask[code])[:10]

    # ── medicion ──────────────────────────────────────────────────────────────

    def adv(self, ch: str) -> int:
        code = self.char_to_code.get(ch)
        return self.width[code] if code is not None else 8

    def _plain_width(self, text: str) -> int:
        """Pixels of text with codes and braces removed (they take no room)."""
        s = ASCII_CODE.sub("", text).replace("{", "").replace("}", "")
        return sum(self.adv(c) for c in s)

    def name_slot_width(self) -> int:
        """Worst-case width of a character name: the player may rename a character to any
        NAME_MAX_CHARS characters, so we reserve NAME_MAX_CHARS of the widest letter."""
        return self._plain_width(NAME_WORST_CHAR * NAME_MAX_CHARS)

    def measure(self, text: str) -> int:
        """Width in game pixels of an editor line.
        Codes take no room.  {Name} and \\charNN are measured at least as wide as the
        worst-case name (see name_slot_width), so a line that fits with "Cid" still fits
        when the player types "WWWWWW"."""
        slot = self.name_slot_width()
        total = pos = 0
        for m in NAME_SLOT.finditer(text):
            total += self._plain_width(text[pos : m.start()])
            name = m.group(1)
            total += max(self._plain_width(name), slot) if name is not None else slot
            pos = m.end()
        return total + self._plain_width(text[pos:])

    # ── fuente TrueType en memoria ────────────────────────────────────────────

    def ttf_bytes(self, line_pitch: int = 16) -> bytes:
        """TrueType in memory. ascent = line_pitch px, descent 0, so one text line is exactly
        `line_pitch` game pixels tall with the glyph at the bottom (8 px spacer row above).
        Cached by (line_pitch, font_data_hash)."""
        cache_key = (line_pitch, self._compute_font_hash())
        if cache_key in self._ttf_cache:
            return self._ttf_cache[cache_key]

        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen

        order, cmap, extras = self._glyph_plan()
        fb = FontBuilder(8 * UNIT, isTTF=True)
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap(cmap)

        glyphs, metrics = {}, {}
        for nm in order:
            pen = TTGlyphPen(None)
            adv = self._draw_glyph(pen, nm, extras)
            glyphs[nm] = pen.glyph()
            metrics[nm] = (adv * UNIT, 0)
        fb.setupGlyf(glyphs)
        fb.setupHorizontalMetrics(metrics)
        fb.setupHorizontalHeader(ascent=line_pitch * UNIT, descent=0)
        fb.setupNameTable({"familyName": FAMILY, "styleName": "Regular"})
        fb.setupOS2(
            sTypoAscender=line_pitch * UNIT,
            sTypoDescender=0,
            sTypoLineGap=0,
            usWinAscent=line_pitch * UNIT,
            usWinDescent=0,
            fsType=0,
        )
        fb.setupPost()
        buf = io.BytesIO()
        fb.save(buf)
        ttf_data = buf.getvalue()
        self._ttf_cache[cache_key] = ttf_data
        return ttf_data

    def _glyph_plan(self):
        """(glyph order, cmap, extra glyph bitmaps) for the generated font."""
        order = [".notdef"]
        cmap = {}
        seen = set()
        for ch, code in sorted(self.char_to_code.items(), key=lambda kv: kv[1]):
            nm = f"g{code:02X}"
            if nm not in seen:
                seen.add(nm)
                order.append(nm)
            cmap[ord(ch)] = nm
        for ch in "{}\u2500":  # llaves y rayas de separador: sin ancho
            cmap[ord(ch)] = "zero"
        order.append("zero")
        # caracteres que el juego no imprime: glifo propio para que Qt no cambie de fuente
        extras = {}
        chars = (
            [chr(c) for c in range(0x21, 0x7F)]
            + [chr(c) for c in range(0xA0, 0x100)]
            + list("\u201c\u201d\u2018\u2019\u2013\u2014")
        )
        for ch in chars:
            if ord(ch) in cmap:
                continue
            nm = f"x{ord(ch):04X}"
            extras[nm] = _EXTRA.get(ch, _TOFU)
            cmap[ord(ch)] = nm
            order.append(nm)
        return order, cmap, extras

    def _draw_glyph(self, pen, name: str, extras: dict) -> int:
        """Draw glyph `name` into `pen`; returns its advance in game pixels."""
        if name == "zero":
            return 0
        if name in extras:
            _draw_rows(pen, [[c == "#" for c in row] for row in extras[name]], top=6)
            return 8
        if name == ".notdef":
            for x0, y0, x1, y1 in ((0, 0, 7, 1), (0, 7, 7, 8), (0, 1, 1, 7), (6, 1, 7, 7)):
                _rect(pen, x0, y0, x1, y1)
            return 8
        code = int(name[1:], 16)
        _draw_rows(pen, self.bitmap[code], top=7)
        return self.width[code]

    def _compute_font_hash(self) -> str:
        """Hash of everything that affects the generated TTF (cache key)."""
        parts = [str(self.gap), str(self.space), *map(str, self.width)]
        parts += ["".join(map(str, row)) for rows in self.bitmap for row in rows]
        parts += [f"{ch}:{code}" for ch, code in sorted(self.char_to_code.items())]
        return hashlib.md5("|".join(parts).encode(), usedforsecurity=False).hexdigest()[:16]
