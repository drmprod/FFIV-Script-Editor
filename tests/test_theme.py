from PySide6.QtGui import QColor, QPalette

from ff4_editor import theme


def _pal(base: str) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Base, QColor(base))
    return p


def test_colors_follow_palette_lightness(qapp):
    dark, light = _pal("#202020"), _pal("#ffffff")
    assert theme.is_dark(dark) and not theme.is_dark(light)
    for fn in (theme.command_color, theme.error_color, theme.warning_color):
        assert fn(dark).lightness() > fn(light).lightness()
