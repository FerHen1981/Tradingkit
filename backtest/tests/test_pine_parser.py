"""Pine expression-parser tests (D-101 increment 3, core).

Covers the real expression forms the fleet uses (calls with named args, member access,
history refs, nested ternary, operator precedence) and the hard-fail contract on anything
unparseable.
"""
from __future__ import annotations

import pytest

from backtest.pineinterp import parse_expression, PineParseError
from backtest.pineinterp.parser import (Num, Str, Name, Bool, Na, Unary, Binary,
                                         Ternary, Member, Index, Call)


def test_number_string_bool_na():
    assert isinstance(parse_expression("1.25"), Num) and parse_expression("1.25").value == 1.25
    assert isinstance(parse_expression('"hi"'), Str)
    assert parse_expression("true").value is True
    assert isinstance(parse_expression("na"), Na)


def test_member_access_and_call():
    n = parse_expression("ta.ema(close, emaLen)")
    assert isinstance(n, Call) and isinstance(n.func, Member)
    assert n.func.obj.ident == "ta" and n.func.attr == "ema"
    assert len(n.args) == 2 and n.args[0].name is None


def test_named_and_positional_args():
    n = parse_expression('input.float(150, "DLL $", minval=0, step=10, group=GROUP_RG)')
    assert isinstance(n, Call)
    assert [a.name for a in n.args] == [None, None, "minval", "step", "group"]
    assert isinstance(n.args[2].value, Num) and n.args[2].value.value == 0


def test_history_reference():
    n = parse_expression("close[1]")
    assert isinstance(n, Index) and isinstance(n.obj, Name) and n.obj.ident == "close"
    assert isinstance(n.index, Num) and n.index.value == 1


def test_precedence_mul_over_add():
    # 2 * _dev / _basis  ->  (2 * _dev) / _basis  (left-assoc, * and / same prec)
    n = parse_expression("2 * _dev / _basis")
    assert isinstance(n, Binary) and n.op == "/"
    assert isinstance(n.left, Binary) and n.left.op == "*"


def test_precedence_comparison_and_logical():
    # bbwpVal >= bbwpMin and bbwpVal <= bbwpMax  ->  (>=) and (<=)
    n = parse_expression("bbwpVal >= bbwpMin and bbwpVal <= bbwpMax")
    assert isinstance(n, Binary) and n.op == "and"
    assert n.left.op == ">=" and n.right.op == "<="


def test_unary_not_call():
    n = parse_expression("not na(bbwpVal)")
    assert isinstance(n, Unary) and n.op == "not" and isinstance(n.operand, Call)


def test_nested_ternary_right_assoc():
    # the real f_bbwpMa body
    n = parse_expression('_type == "SMA" ? ta.sma(_src, _len) : _type == "EMA" ? ta.ema(_src, _len) : ta.vwma(_src, _len)')
    assert isinstance(n, Ternary)
    assert isinstance(n.cond, Binary) and n.cond.op == "=="
    assert isinstance(n.otherwise, Ternary)          # right-assoc chain


def test_paren_grouping_overrides_precedence():
    n = parse_expression("(a + b) * c")
    assert isinstance(n, Binary) and n.op == "*" and isinstance(n.left, Binary) and n.left.op == "+"


def test_hard_fail_on_incomplete_expression():
    with pytest.raises(PineParseError):
        parse_expression("1 +")


def test_hard_fail_on_trailing_tokens():
    with pytest.raises(PineParseError, match="trailing"):
        parse_expression("a b")


def test_hard_fail_on_broken_ternary():
    with pytest.raises(PineParseError, match="ternary"):
        parse_expression("c ? 1")
