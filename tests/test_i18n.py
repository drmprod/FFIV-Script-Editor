"""Interface translations: the English catalogue is complete and consistent with the sources."""

import os
import re
import xml.etree.ElementTree as ET

import pytest

from ff4_editor import i18n

TS = os.path.join(i18n.TRANSLATIONS_DIR, "ff4_en.ts")


def _messages():
    root = ET.parse(TS).getroot()
    return [(m.findtext("source") or "", m.find("translation")) for m in root.iter("message")]


def test_catalogue_is_complete():
    msgs = _messages()
    assert msgs, "ff4_en.ts has no messages (run `make i18n`)"
    for src, tr_el in msgs:
        assert tr_el is not None and (tr_el.text or "").strip(), f"sin traducir: {src!r}"
        assert tr_el.get("type") != "unfinished", f"inconclusa: {src!r}"


def test_placeholders_and_mnemonics_match():
    field = re.compile(r"\{[^{}]*\}")
    for src, tr_el in _messages():
        text = tr_el.text or ""
        assert sorted(field.findall(src)) == sorted(field.findall(text)), src
        assert ("&" in src) == ("&" in text) or "<" in src, src  # menu mnemonics survive (HTML excepted)


@pytest.fixture
def english(qapp):
    i18n.install_language("en")
    yield
    i18n.install_language("es")


def test_install_language_switches_and_restores(qapp):
    assert i18n.tr("&Guardar") == "&Guardar"
    assert i18n.install_language("en") == "en"
    try:
        assert i18n.tr("&Guardar") == "&Save"
        assert i18n.tr("Excede por {n} bytes").format(n=3) == "Over by 3 bytes"
    finally:
        i18n.install_language("es")
    assert i18n.tr("&Guardar") == "&Guardar"


def test_unknown_language_falls_back_to_source(qapp):
    assert i18n.install_language("xx") == "es"
    assert i18n.resolve_language("auto") in i18n.LANGUAGES
