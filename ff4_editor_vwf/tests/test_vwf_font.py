import pytest

from ff4_editor.util.vwf_font import VWFFont

CODES = {0x42: "A", 0x43: "B", 0x44: "C", 0xFF: " "}


@pytest.fixture
def font(font_png):
    return VWFFont(font_png, CODES, gap=1, space=4)


def test_advances(font):
    assert font.adv("A") == 6      # 5 de tinta + gap
    assert font.adv("B") == 4
    assert font.adv("C") == 8
    assert font.adv(" ") == 4      # space


def test_measure_sums_advances(font):
    assert font.measure("AB") == 10
    assert font.measure("A B") == 14


def test_measure_ignores_control_codes_and_braces(font):
    assert font.measure(r"A\wait[2x4]B") == font.measure("AB")
    assert font.measure("{A}") == font.adv("A")


def test_unknown_char_advances_8(font):
    assert font.adv("ñ") == 8


def test_gap_and_space_params(font_png):
    f = VWFFont(font_png, CODES, gap=2, space=6)
    assert f.adv("A") == 7 and f.adv(" ") == 6


def test_drop_over_limit_is_reported(font_png):
    f = VWFFont(font_png, CODES, overrides={"_drop": {"A": 5}})
    assert "A" in f.dropped_loss


def test_ttf_bytes_valid_and_cached(font):
    a = font.ttf_bytes(16)
    assert a[:4] in (b"\x00\x01\x00\x00", b"true") and len(a) > 100
    assert font.ttf_bytes(16) is a or font.ttf_bytes(16) == a
