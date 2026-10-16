from ff4_editor.model.encoding import build_dte_set, encode_size

DTE = {"AB", "BA"}


def test_plain_chars():
    assert encode_size("xyz", set()) == 4                 # 3 + terminador
    assert encode_size("xyz", set(), add_terminator=False) == 3


def test_dte_pairs_cost_one_byte():
    assert encode_size("ABBA", DTE) == 3                  # 2 DTE + terminador
    assert encode_size("ABA", DTE) == 3                   # AB + A + terminador


def test_control_codes():
    assert encode_size(r"a\nb", set()) == 4               # a, \n, b, term
    assert encode_size(r"\char03", set()) == 3            # \charNN = 2 bytes
    assert encode_size(r"\wait[2x4]", set()) == 3         # con parámetro = 2 bytes


def test_build_dte_set():
    d = {"charTable": {"dte": {"char": {"0x01": "AB", "0x02": "BA"}}}}
    assert build_dte_set(d) == DTE
    assert build_dte_set({}) == set()
