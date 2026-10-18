"""
ff4_editor/game_font.py
Locating font.png and building the game's variable-width font from it.
The only Qt dependency is registering the generated TrueType font with Qt.
"""

import json
import os

from PySide6.QtGui import QFontDatabase

from .errors import FF4Error, logger
from .i18n import tr
from .util.vwf_font import VWFFont, text_codes_from_json


class GameFontError(FF4Error):
    """font.png could not be turned into a usable font."""


def find_font_png(configured: str, json_path: str | None) -> str | None:
    """font.png: the configured path, next to the JSON (also gfx/, tools/ or the parent
    directory), or next to the package."""
    candidates = [configured] if configured else []
    if json_path:
        d = os.path.dirname(os.path.abspath(json_path))
        candidates += [
            os.path.join(d, "font.png"),
            os.path.join(d, "gfx", "font.png"),
            os.path.join(d, "tools", "font.png"),
            os.path.join(os.path.dirname(d), "font.png"),
        ]
    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(package_parent, "font.png"))
    return next((p for p in candidates if os.path.isfile(p)), None)


def load_overrides(png_path: str) -> dict:
    """Optional vwf_overrides.json next to font.png (glyph widths / descender drops)."""
    path = os.path.join(os.path.dirname(png_path), "vwf_overrides.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise GameFontError(tr("No se pudo leer {path}: {error}").format(path=path, error=e)) from e
    if not isinstance(data, dict):
        raise GameFontError(tr("{path}: se esperaba un objeto JSON").format(path=path))
    return data


def build_game_font(
    png_path: str, char_table_text: dict, gap: int, space: int, line_pitch: int
) -> tuple[VWFFont, int]:
    """Build the font and register it with Qt. Returns (font, Qt application-font id).
    Raises GameFontError with a readable message."""
    try:
        font = VWFFont(png_path, text_codes_from_json(char_table_text), gap, space, load_overrides(png_path))
        font_id = QFontDatabase.addApplicationFontFromData(font.ttf_bytes(line_pitch))
    except GameFontError:
        raise
    except Exception as e:  # noqa: BLE001 - PIL and fontTools raise many unrelated types
        logger.warning("Game font could not be built", exc_info=True)
        raise GameFontError(str(e)) from e
    if font_id < 0:
        raise GameFontError(tr("Qt rechazó la fuente generada"))
    return font, font_id


def release_game_font(font_id: int | None) -> None:
    if font_id is not None:
        QFontDatabase.removeApplicationFont(font_id)
