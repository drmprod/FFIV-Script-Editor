"""TextCodec reproduces romtools/text-codec.js: longest match, DTE, codes with parameters."""

import pytest

from ff4_editor.model.textcodec import DEFAULT_ENCODINGS, TextCodec, shared_bytes

TABLES = {
    "text": {
        "char": {
            "0x41": "A",
            "0x42": "B",
            "0x43": "C",
            "0xFF": " ",
            "0x01": "\\n",
            "0x03": "\\song[",
            "0x05": "\\wait[",
            "0x09": "\\line",
            "0x0400": "\\char00",
            "0x0403": "\\char03",
            "0x20": "\\item",
        }
    },
    "dte": {"char": {"0x9B": "AB", "0x9C": "BA", "0x9D": "ABC"}},
    "nullTerminated": {"char": {"0x00": "\\0"}},
    "fixedLength": {"char": {"0xFE": "\\pad"}},
}


@pytest.fixture
def dialog():
    return TextCodec(DEFAULT_ENCODINGS["dialog"], TABLES)


@pytest.fixture
def fixed():
    return TextCodec(DEFAULT_ENCODINGS["fixedLength"], TABLES)


def test_plain_text_and_terminator(dialog, fixed):
    assert dialog.encode("A C") == bytes([0x41, 0xFF, 0x43, 0x00])
    assert fixed.encode("A C") == bytes([0x41, 0xFF, 0x43])  # fixedLength tables have no \0
    assert fixed.pad == 0xFE


def test_longest_match_wins_over_dte_pairs(dialog):
    assert dialog.encode("ABC") == bytes([0x9D, 0x00])  # the 3-char key beats "AB" + "C"
    assert dialog.encode("ABAB") == bytes([0x9B, 0x9B, 0x00])
    assert dialog.encode("ABA") == bytes([0x9B, 0x41, 0x00])


def test_codes_and_parameters(dialog):
    assert dialog.encode("A\\nB") == bytes([0x41, 0x01, 0x42, 0x00])
    assert dialog.encode("\\char03") == bytes([0x04, 0x03, 0x00])  # 2-byte value
    assert dialog.encode("\\wait[0x28]") == bytes([0x05, 0x28, 0x00])  # 1-byte parameter
    assert dialog.encode("\\song[0x2D]A") == bytes([0x03, 0x2D, 0x41, 0x00])


def test_no_word_boundaries_like_the_real_encoder(dialog):
    # "\item" is a key, so it matches as a prefix of "\items"; "\char" alone is not a key
    assert dialog.encode("\\items") == bytes([0x20, 0x00])  # 's' is not in the table: skipped
    assert dialog.encode("\\charge") == bytes([0x00])  # nothing matches, everything is skipped


def test_unknown_characters_are_skipped_and_raw_bytes_work(dialog):
    assert dialog.encode("A¿B") == bytes([0x41, 0x42, 0x00])
    assert dialog.encode("A\\x7FB") == bytes([0x41, 0x7F, 0x42, 0x00])


def test_explicit_terminator_ends_the_string(dialog):
    assert dialog.encode("A\\0B") == bytes([0x41, 0x00])


def test_empty_string_is_just_the_terminator(dialog, fixed):
    assert dialog.encode("") == b"\x00"
    assert fixed.encode("") == b""


def test_bad_parameter_does_not_consume_text(dialog):
    # n = 0 and nothing consumed, as in the JS fallback: "\wait[" + 0 then the rest is parsed
    assert dialog.encode("\\wait[zz]")[:2] == bytes([0x05, 0x00])


def test_later_charTables_override_earlier_ones():
    tables = {"a": {"char": {"0x01": "X"}}, "b": {"char": {"0x02": "X"}}}
    assert TextCodec({"charTable": ["a", "b"]}, tables).encode("X") == b"\x02"


def test_shared_bytes_stores_equal_items_once_and_reuses_tails():
    assert shared_bytes([b"hello\x00", b"hello\x00"]) == 6
    assert shared_bytes([b"hello\x00", b"lo\x00"]) == 6  # tail of the first item
    assert shared_bytes([b"hello\x00", b"hel\x00"]) == 10
