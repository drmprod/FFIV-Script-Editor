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

import io
import re

from ..errors import logger

PALETTE = [(12, 10, 26), (80, 80, 80), (255, 255, 255), (180, 180, 180)]
FAMILY = 'FF4 VWF'
UNIT = 8        # unidades de fuente por pixel del juego (FreeType exige unitsPerEm >= 16)

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
DEFAULT_TEXT[0xFF] = ' '


# Glyphs for characters the game cannot print (editor syntax such as \\wait[2x4]).  They
# exist only so that Qt never falls back to another font (which would change the line
# height); 5x7 pixels, advance 8.
_EXTRA = {
    '\\': ["#....", ".#...", ".#...", "..#..", "..#..", "...#.", "...#."],
    '[':  ["###..", "#....", "#....", "#....", "#....", "#....", "###.."],
    ']':  ["..###", "....#", "....#", "....#", "....#", "....#", "..###"],
    '(':  ["..#..", ".#...", "#....", "#....", "#....", ".#...", "..#.."],
    ')':  ["..#..", "...#.", "....#", "....#", "....#", "...#.", "..#.."],
    '"':  ["#.#..", "#.#..", ".....", ".....", ".....", ".....", "....."],
    ';':  [".....", "..#..", ".....", ".....", "..#..", "..#..", ".#..."],
    '+':  [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
    '=':  [".....", ".....", "#####", ".....", "#####", ".....", "....."],
    '*':  [".....", "#.#.#", ".###.", "#####", ".###.", "#.#.#", "....."],
    '<':  ["...#.", "..#..", ".#...", "#....", ".#...", "..#..", "...#."],
    '>':  [".#...", "..#..", "...#.", "....#", "...#.", "..#..", ".#..."],
    '_':  [".....", ".....", ".....", ".....", ".....", ".....", "#####"],
    '#':  [".#.#.", "#####", ".#.#.", ".#.#.", "#####", ".#.#.", "....."],
    '&':  [".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"],
    '@':  [".###.", "#...#", "#.###", "#.#.#", "#.###", "#....", ".###."],
    '|':  ["..#..", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    '~':  [".....", ".....", ".##.#", "#.##.", ".....", ".....", "....."],
    '^':  ["..#..", ".#.#.", "#...#", ".....", ".....", ".....", "....."],
    '`':  [".#...", "..#..", ".....", ".....", ".....", ".....", "....."],
    '$':  ["..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."],
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
    m[0xFF] = ' '
    return m


def _load_tiles(png_path):
    from PIL import Image
    img = Image.open(png_path).convert('RGB')
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
                row.append(min(range(4), key=lambda i: sum((a - b) ** 2 for a, b in zip(px, PALETTE[i]))))
            rows.append(row)
        tiles.append(rows)
    return tiles


class VWFFont:
    """Anchos y glifos del juego.  `code_to_char` = {codigo: caracter} del charTable de texto."""

    def __init__(self, png_path, code_to_char=None, gap=1, space=4, overrides=None):
        self.code_to_char = dict(code_to_char) if code_to_char else dict(DEFAULT_TEXT)
        self.char_to_code = {c: k for k, c in self.code_to_char.items()}
        self.char_to_code[' '] = 0xFF
        self.gap, self.space = gap, space
        tiles = _load_tiles(png_path)
        bg = tiles[0xFF][0][0]
        self.width = [0] * 256
        self.mask = [[0] * 10 for _ in range(256)]       # mascara por fila (8 + 2 de desborde), recortada a la izquierda
        self.bitmap = [None] * 256                       # filas de 'ink' recortadas (lista de listas 0/1)
        text = set(self.code_to_char)
        for code, rows in enumerate(tiles):
            cols = [x for r in rows for x, p in enumerate(r) if p != bg]
            if not cols:
                self.width[code] = space
                self.bitmap[code] = [[0] * 0 for _ in range(8)]
                continue
            left, right = min(cols), max(cols)
            bm = [[1 if p != bg else 0 for p in r][left:right + 1] for r in rows]
            self.bitmap[code] = bm
            for r, row in enumerate(bm):
                m = 0
                for x, v in enumerate(row):
                    if v:
                        m |= 1 << (7 - x)
                self.mask[code][r] = m
            ink = right - left + 1
            self.width[code] = ink + gap if code in text else 8
        overrides = dict(overrides or {})
        self.dropped_loss = []
        for chars, dy in overrides.pop('_drop', {}).items():     # bajar glifos (j p q g y...)
            for ch in chars:
                code = self.char_to_code.get(ch)
                if code is None or not self.bitmap[code]:
                    continue
                bm = self.bitmap[code]
                w = max((len(r) for r in bm), default=0)
                if dy < 0 or dy > 2:
                    self.dropped_loss.append(ch)     # el juego solo tiene 2 filas de desborde
                    logger.warning(f"Glyph '{ch}' (U+{ord(ch):04X}) dropped: _drop value {dy} exceeds limit (max 2)")
                    continue
                self.bitmap[code] = [[0] * w for _ in range(dy)] + bm        # 8 + dy filas: no se pierde tinta
                self.mask[code] = ([0] * dy + self.mask[code])[:10]
        self.width[0xFF] = space
        for k, v in overrides.items():
            code = int(k, 16) if str(k).lower().startswith('0x') else ord(k)
            self.width[code] = v

        # TTF cache: key = (line_pitch, font_data_hash), value = ttf_bytes
        self._ttf_cache: dict[tuple[int, str], bytes] = {}

    # ── medicion ──────────────────────────────────────────────────────────────

    def adv(self, ch: str) -> int:
        code = self.char_to_code.get(ch)
        return self.width[code] if code is not None else 8

    def measure(self, text: str) -> int:
        """Ancho en pixeles del juego de una linea del editor.
        {Nombre} -> se mide el nombre; las llaves y las secuencias \\xxx no ocupan lugar."""
        s = re.sub(r'\\[a-zA-Z0-9]+(?:\[.*?\])?', '', text)
        s = s.replace('{', '').replace('}', '')
        return sum(self.adv(c) for c in s)

    # ── fuente TrueType en memoria ────────────────────────────────────────────

    def ttf_bytes(self, line_pitch: int = 16) -> bytes:
        """TrueType in memory. ascent = line_pitch px, descent 0, so one text line is exactly
        `line_pitch` game pixels tall with the glyph at the bottom (8 px spacer row above).
        Cached by (line_pitch, font_data_hash)."""
        # Compute a hash of the font data that affects the TTF output
        font_data_hash = self._compute_font_hash()
        cache_key = (line_pitch, font_data_hash)
        
        if cache_key in self._ttf_cache:
            return self._ttf_cache[cache_key]

        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen

        names = {}
        order = ['.notdef']
        cmap = {}
        for ch, code in sorted(self.char_to_code.items(), key=lambda kv: kv[1]):
            nm = 'g%02X' % code
            if nm not in names.values():
                order.append(nm)
            names[ch] = nm
            cmap[ord(ch)] = nm
        # llaves y rayas de separador: sin ancho
        for ch in '{}\u2500':
            cmap[ord(ch)] = 'zero'
        order.append('zero')
        # caracteres que el juego no imprime: glifo propio para que Qt no cambie de fuente
        extras = {}
        chars = [chr(c) for c in range(0x21, 0x7F)] + [chr(c) for c in range(0xA0, 0x100)] \
                + list('\u201c\u201d\u2018\u2019\u2013\u2014')
        for ch in chars:
            if ord(ch) in cmap:
                continue
            nm = 'x%04X' % ord(ch)
            extras[nm] = _EXTRA.get(ch, _TOFU)
            cmap[ord(ch)] = nm
            order.append(nm)

        fb = FontBuilder(8 * UNIT, isTTF=True)
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap(cmap)

        glyphs, metrics = {}, {}
        for nm in order:
            pen = TTGlyphPen(None)
            adv = 0
            if nm == 'zero':
                adv = 0
            elif nm in extras:
                adv = 8
                for r, row in enumerate(extras[nm]):
                    y0, y1 = (6 - r) * UNIT, (7 - r) * UNIT
                    x = 0
                    while x < len(row):
                        if row[x] == '#':
                            st = x
                            while x < len(row) and row[x] == '#':
                                x += 1
                            pen.moveTo((st * UNIT, y0)); pen.lineTo((st * UNIT, y1)); pen.lineTo((x * UNIT, y1)); pen.lineTo((x * UNIT, y0)); pen.closePath()
                        else:
                            x += 1
            elif nm == '.notdef':
                adv = 8
                for (x0, y0, x1, y1) in ((0, 0, 7, 1), (0, 7, 7, 8), (0, 1, 1, 7), (6, 1, 7, 7)):
                    x0, y0, x1, y1 = x0 * UNIT, y0 * UNIT, x1 * UNIT, y1 * UNIT
                    pen.moveTo((x0, y0)); pen.lineTo((x0, y1)); pen.lineTo((x1, y1)); pen.lineTo((x1, y0)); pen.closePath()
            else:
                code = int(nm[1:], 16)
                adv = self.width[code]
                for r, row in enumerate(self.bitmap[code]):
                    y0, y1 = (7 - r) * UNIT, (8 - r) * UNIT
                    x = 0
                    while x < len(row):
                        if row[x]:
                            s = x
                            while x < len(row) and row[x]:
                                x += 1
                            pen.moveTo((s * UNIT, y0)); pen.lineTo((s * UNIT, y1)); pen.lineTo((x * UNIT, y1)); pen.lineTo((x * UNIT, y0)); pen.closePath()
                        else:
                            x += 1
            glyphs[nm] = pen.glyph()
            metrics[nm] = (adv * UNIT, 0)
        fb.setupGlyf(glyphs)
        fb.setupHorizontalMetrics(metrics)
        fb.setupHorizontalHeader(ascent=line_pitch * UNIT, descent=0)
        fb.setupNameTable({'familyName': FAMILY, 'styleName': 'Regular'})
        fb.setupOS2(sTypoAscender=line_pitch * UNIT, sTypoDescender=0, sTypoLineGap=0,
                    usWinAscent=line_pitch * UNIT, usWinDescent=0, fsType=0)
        fb.setupPost()
        buf = io.BytesIO()
        fb.save(buf)
        ttf_data = buf.getvalue()
        self._ttf_cache[cache_key] = ttf_data
        return ttf_data

    def _compute_font_hash(self) -> str:
        """Compute a hash of the font data that affects TTF output."""
        import hashlib
        # Hash the relevant font data: widths, bitmaps, character mappings
        data = []
        data.append(str(self.gap))
        data.append(str(self.space))
        # Include widths for all codes
        for code in range(256):
            data.append(str(self.width[code]))
        # Include bitmap data for all codes
        for code in range(256):
            if self.bitmap[code]:
                for row in self.bitmap[code]:
                    data.append(''.join(str(v) for v in row))
        # Include character mappings
        for ch, code in sorted(self.char_to_code.items()):
            data.append(f"{ch}:{code}")
        # Create hash
        full_data = '|'.join(data)
        return hashlib.md5(full_data.encode()).hexdigest()[:16]
