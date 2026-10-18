"""
ff4_editor/i18n.py
Interface translations.  The source language of every user-visible string is Spanish; other
languages are Qt translation files (ff4_<lang>.qm, built from ff4_<lang>.ts by `make i18n`).

Use `tr("texto")` for any text the user sees.  Variable parts use str.format placeholders
(`tr("Excede por {n} bytes").format(n=n)`), never f-strings, so the sentence stays one unit.
"""

import os

from PySide6.QtCore import QCoreApplication, QLocale, QTranslator

SOURCE_LANGUAGE = "es"
LANGUAGES = {"es": "Español", "en": "English"}
TRANSLATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translations")

_translators: list[QTranslator] = []


def tr(text: str) -> str:
    """Translate a Spanish source string (context-free; lupdate collects it as is)."""
    return QCoreApplication.translate("", text)


def resolve_language(setting: str) -> str:
    """'auto' follows the system locale; unknown languages fall back to the source language."""
    lang = QLocale.system().name().split("_")[0] if setting in ("", "auto") else setting
    return lang if lang in LANGUAGES else SOURCE_LANGUAGE


def install_language(setting: str) -> str:
    """Load the translation for `setting` ('auto', 'es', 'en', ...) and return the language in use."""
    app = QCoreApplication.instance()
    for t in _translators:
        if app is not None:
            app.removeTranslator(t)
    _translators.clear()
    lang = resolve_language(setting)
    if lang != SOURCE_LANGUAGE and app is not None:
        t = QTranslator()
        if t.load(f"ff4_{lang}", TRANSLATIONS_DIR):
            app.installTranslator(t)
            _translators.append(t)
        else:
            lang = SOURCE_LANGUAGE
    return lang
