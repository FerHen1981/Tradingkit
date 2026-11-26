"""Pine lexer tests (D-101 increment 1).

Two things matter: (1) it tokenizes the real fleet — the whole lexical surface the 13
live scripts use — and (2) it HARD-FAILS on anything it does not recognise, never
swallows it. The second is the D-101 contract; a lexer that skipped the unknown would
be the first crack in a plausible-but-wrong backtest.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backtest.pineinterp import tokenize, TokType, PineLexError
from backtest.pineinterp.lexer import Tok

PINE_DIR = Path(__file__).resolve().parent.parent.parent / "pine"
SCRIPTS = sorted(PINE_DIR.glob("*.pine"))


@pytest.mark.skipif(not SCRIPTS, reason="pine/*.pine not present")
@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name.replace("MEX_", "").replace("_v1_0_0.pine", ""))
def test_tokenizes_every_live_script(path):
    """The whole fleet lexes without a single unrecognised character."""
    toks = tokenize(path.read_text(encoding="utf-8"), name=path.name)
    assert toks and toks[-1].type == TokType.EOF
    assert len(toks) > 500                      # these are large scripts; sanity


def _types(src):
    return [(t.type, t.value) for t in tokenize(src) if t.type != TokType.NEWLINE][:-1]  # drop EOF


def test_assign_and_arrow_and_ternary():
    assert (TokType.OP, ":=") in _types("x := 1")
    assert (TokType.OP, "=>") in _types("f(a) => a + 1")
    t = _types("x = c ? 1 : 2")
    assert (TokType.OP, "?") in t and (TokType.OP, ":") in t


def test_member_access_vs_decimal():
    # ta.ema -> IDENT DOT IDENT ; 1.25 -> single NUMBER
    assert _types("ta.ema") == [(TokType.IDENT, "ta"), (TokType.DOT, "."), (TokType.IDENT, "ema")]
    assert _types("1.25") == [(TokType.NUMBER, "1.25")]
    assert _types(".5") == [(TokType.NUMBER, ".5")]


def test_history_ref_and_calls():
    t = _types("close[1]")
    assert (TokType.LSQUARE, "[") in t and (TokType.NUMBER, "1") in t and (TokType.RSQUARE, "]") in t


def test_color_literal():
    assert _types("#ff0000") == [(TokType.COLOR, "#ff0000")]
    assert _types("#AABBCCDD") == [(TokType.COLOR, "#AABBCCDD")]


def test_string_with_escaped_quote():
    (tt, val), = _types(r'"a\"b"')
    assert tt == TokType.STRING and val == 'a"b'


def test_comment_and_version_annotation_are_skipped():
    assert _types("//@version=6\nx = 1") == [(TokType.IDENT, "x"), (TokType.OP, "="), (TokType.NUMBER, "1")]


def test_keywords_vs_idents():
    assert (TokType.KEYWORD, "if") in _types("if x")
    assert (TokType.KEYWORD, "and") in _types("a and b")
    # type words stay IDENT (they double as namespaces like color.new)
    assert (TokType.IDENT, "color") in _types("color.new")


def test_hard_fail_on_unknown_character():
    with pytest.raises(PineLexError, match="unrecognised character"):
        tokenize("x = 1 $ 2")


def test_hard_fail_on_unterminated_string():
    with pytest.raises(PineLexError, match="unterminated string"):
        tokenize('x = "abc')


def test_hard_fail_on_bad_color():
    with pytest.raises(PineLexError, match="invalid color"):
        tokenize("c = #12345")            # 5 hex digits — not 6 or 8


def test_line_and_col_tracking():
    toks = tokenize("a = 1\nbb = 2")
    b = [t for t in toks if t.value == "bb"][0]
    assert b.line == 2 and b.col == 1
