"""Semantic colours that follow the platform palette (readable on light and dark themes).

The game-styled VWF card keeps its fixed colours (`constants.VWF_*`); this is for the widgets that
use the application palette: the mono editor highlighting and the status-bar warnings."""

from __future__ import annotations

from PySide6.QtGui import QColor, QGuiApplication, QPalette


def is_dark(pal: QPalette | None = None) -> bool:
    pal = pal or QGuiApplication.palette()
    return pal.color(QPalette.ColorRole.Base).lightness() < 128


def command_color(pal: QPalette | None = None) -> QColor:
    """`\\wait`, `\\song[..]`... : teal, lightened on dark backgrounds, darkened on light ones."""
    return QColor("#6fa8a0") if is_dark(pal) else QColor("#2d7a6f")


def error_color(pal: QPalette | None = None) -> QColor:
    return QColor("#e8685a") if is_dark(pal) else QColor("#c0392b")


def warning_color(pal: QPalette | None = None) -> QColor:
    return QColor("#e0a83c") if is_dark(pal) else QColor("#b9770e")


def css_color(color: QColor) -> str:
    return f"color: {color.name()};"
