
from ff4_editor.constants import BLANK_LINE_DISPLAY
from ff4_editor.util import text_processing as tp


def test_roundtrip_simple():
    for s in ["hola", r"a\nb", r"a\nb\nc", r"a\n\line b", r"x\n\ny", ""]:
        assert tp.display_to_json(tp.json_to_display(s)) == s, s


def test_blank_line_marker():
    d = tp.json_to_display("a\\n\\linez")
    assert BLANK_LINE_DISPLAY in d.split("\n")


def test_char_names_both_ways():
    tp.set_char_names({0: "Cecil", 3: "Rosa"})
    assert tp.json_to_display(r"\char00 y \char03") == "{Cecil} y {Rosa}"
    assert tp.display_to_json("{Cecil} y {Rosa}") == r"\char00 y \char03"


def test_unknown_char_code_is_kept():
    assert tp.json_to_display(r"\char09") == r"\char09"


def test_duplicate_char_names_do_not_rewrite_untouched_codes():
    tp.set_char_names({0: "Same", 1: "Same"})
    assert tp.display_to_json(tp.json_to_display(r"\char00 \char01")) == r"\char00 \char01"


def test_roundtrip_text_before_line():
    s = r"a\line b"
    assert tp.display_to_json(tp.json_to_display(s)) == s


def test_roundtrip_space_between_n_and_line():
    s = r"there.\n \line There"
    assert tp.display_to_json(tp.json_to_display(s)) == s


def test_visible_len_ignores_codes():
    assert tp.visible_len(r"ab\wait[2x4]cd") == 4
    assert tp.visible_len(r"\char00x") == 1


def test_visible_len_name_tokens():
    assert tp.visible_len("{Cecil}") == 6                       # aproximación por defecto
    assert tp.visible_len("{Cecil}", measure=lambda s: 3) == 3  # con medidor


# ── reflow ─────────────────────────────────────────────────────────────────────
def test_reflow_line_fits():
    assert tp.reflow_line("hola mundo", 28) == ["hola mundo"]


def test_reflow_line_wraps_on_words():
    out = tp.reflow_line("uno dos tres cuatro", 9)
    assert out == ["uno dos", "tres", "cuatro"]
    assert all(len(l) <= 9 for l in out)


def test_reflow_line_hard_cut_long_word():
    out = tp.reflow_line("x" * 40, 10)
    assert all(len(l) <= 10 for l in out)
    assert "".join(l.rstrip("-") for l in out) == "x" * 40


def test_reflow_line_with_measure_in_pixels():
    measure = lambda s: 6 * len(s)           # 6 px por carácter
    out = tp.reflow_line("aaa bbb ccc", 36, measure)   # 6 caracteres por línea
    assert out == ["aaa", "bbb", "ccc"]
    assert all(measure(l) <= 36 for l in out)





def test_line_in_the_middle_of_a_row_is_kept_literal():
    d = tp.json_to_display(r"a\line b")
    assert d == r"a\line b" and BLANK_LINE_DISPLAY not in d


def test_ambiguous_names_stay_as_codes():
    tp.set_char_names({0: "Same", 1: "Same", 2: "Other"})
    assert tp.json_to_display(r"\char00 \char02") == r"\char00 {Other}"
    assert tp.display_to_json("{Other} {Same}") == r"\char02 {Same}"      # no adivina