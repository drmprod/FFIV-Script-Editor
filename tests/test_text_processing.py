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
    assert tp.visible_len(r"\char00x") == 7  # \charNN counts as a worst-case name


def test_visible_len_name_tokens():
    assert tp.visible_len("{Cecil}") == 6  # aproximación por defecto
    assert tp.visible_len("{Cecil}", measure=lambda s: 3) == 3  # con medidor
    assert tp.visible_len("{Cid}") == 6  # nombre corto: peor caso de todos modos


# ── reflow ─────────────────────────────────────────────────────────────────────
def test_reflow_line_fits():
    assert tp.reflow_line("hola mundo", 28) == ["hola mundo"]


def test_reflow_line_wraps_on_words():
    out = tp.reflow_line("uno dos tres cuatro", 9)
    assert out == ["uno dos", "tres", "cuatro"]
    assert all(len(ln) <= 9 for ln in out)


def test_reflow_line_hard_cut_long_word():
    out = tp.reflow_line("x" * 40, 10)
    assert all(len(ln) <= 10 for ln in out)
    assert "".join(ln.rstrip("-") for ln in out) == "x" * 40


def test_reflow_line_with_measure_in_pixels():
    def measure(s):
        return 6 * len(s)  # 6 px por carácter

    out = tp.reflow_line("aaa bbb ccc", 36, measure)  # 6 caracteres por línea
    assert out == ["aaa", "bbb", "ccc"]
    assert all(measure(ln) <= 36 for ln in out)


def test_line_in_the_middle_of_a_row_is_kept_literal():
    d = tp.json_to_display(r"a\line b")
    assert d == r"a\line b" and BLANK_LINE_DISPLAY not in d


def test_ambiguous_names_stay_as_codes():
    tp.set_char_names({0: "Same", 1: "Same", 2: "Other"})
    assert tp.json_to_display(r"\char00 \char02") == r"\char00 {Other}"
    assert tp.display_to_json("{Other} {Same}") == r"\char02 {Same}"  # no adivina


# ── Reflow: palabras largas y códigos ─────────────────────────────────────────
def test_reflow_cuts_a_long_word_even_after_other_text():
    out = tp.reflow_line("Hola supercalifragilistico a", 12)
    assert all(tp.visible_len(ln) <= 12 for ln in out)
    assert "".join(ln.rstrip("-") for ln in out).replace(" ", "") == "Holasupercalifragilisticoa"


def test_reflow_never_splits_codes_or_names():
    line = "xxxxxxxx\\char03yyyyyyyy{Kain}zzzzzzzz\\wait[2x4]"
    for limit in (6, 8, 12):
        out = tp.reflow_line(line, limit)
        for ln in out:
            assert ln.count("{") == ln.count("}")
            assert "\\char03" in ln or "\\char" not in ln.replace("\\char03", "")
            assert "\\wait[2x4]" in ln or "\\wait" not in ln.replace("\\wait[2x4]", "")
        assert "".join(out).replace("-", "") == line


def test_reflow_is_idempotent():
    import random

    rnd = random.Random(7)
    words = ["Hola", "mundo", "supercalifragilistico", "x" * 30, "\\char00", "{Cecil}", "a"]
    for _ in range(300):
        line = " ".join(rnd.choice(words) for _ in range(rnd.randint(1, 10)))
        out = tp.reflow_line(line, 20)
        assert [x for ln in out for x in tp.reflow_line(ln, 20)] == out
