from ff4_editor.model.encoding import build_dte_set, encode_size

DTE = {"AB", "BA"}


def test_plain_chars():
    assert encode_size("xyz", set()) == 4  # 3 + terminador
    assert encode_size("xyz", set(), add_terminator=False) == 3


def test_dte_pairs_cost_one_byte():
    assert encode_size("ABBA", DTE) == 3  # 2 DTE + terminador
    assert encode_size("ABA", DTE) == 3  # AB + A + terminador


def test_control_codes():
    assert encode_size(r"a\nb", set()) == 4  # a, \n, b, term
    assert encode_size(r"\char03", set()) == 3  # \charNN = 2 bytes
    assert encode_size(r"\wait[2x4]", set()) == 3  # con parámetro = 2 bytes


def test_build_dte_set():
    d = {"charTable": {"dte": {"char": {"0x01": "AB", "0x02": "BA"}}}}
    assert build_dte_set(d) == DTE
    assert build_dte_set({}) == set()


# ── shared array storage (ROMEncoder.findSubarray) ────────────────────────────
def test_shared_size_stores_equal_items_once():
    from ff4_editor.model.encoding import shared_size

    assert shared_size(["hello", "hello"], set()) == 6  # 5 bytes + terminator, once
    assert shared_size(["hello", "world"], set()) == 12


def test_shared_size_reuses_bytes_inside_longer_items():
    from ff4_editor.model.encoding import shared_size

    # "lo" + terminator is the tail of "hello" + terminator: no new bytes
    assert shared_size(["hello", "lo"], set()) == 6
    # but a prefix is not followed by the terminator, so it is stored separately
    assert shared_size(["hello", "hel"], set()) == 10


def test_shared_size_respects_dte_and_codes():
    from ff4_editor.model.encoding import encode_size, shared_size

    dte = {"AB"}
    assert shared_size(["ABAB"], dte) == encode_size("ABAB", dte) == 3
    assert shared_size([r"\char03", r"\char03"], set()) == 3  # 2 bytes + terminator, once
