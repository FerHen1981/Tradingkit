"""Pine v6 lexer — increment 1 of the interpreter (D-101).

Turns Pine source into a flat token stream. It recognises exactly the lexical surface
Pine uses; any character that cannot start a valid token raises PineLexError with the
line and column, rather than being skipped. That refusal is the whole point (D-101): a
tokenizer that swallowed the unknown would let a wrong backtest look right.

The lexer does NOT decide grammar (indentation blocks, statement continuation inside
parens, member access vs decimal point beyond the digit rule). It records each token's
line and column so the parser can. NEWLINE tokens are always emitted; the parser drops
the ones inside an open bracket, which is where Pine allows a statement to continue.
"""
from __future__ import annotations

import enum
from typing import NamedTuple


class TokType(enum.Enum):
    NUMBER = "NUMBER"
    STRING = "STRING"
    COLOR = "COLOR"        # #RRGGBB / #RRGGBBAA literal
    IDENT = "IDENT"
    KEYWORD = "KEYWORD"
    OP = "OP"              # := == != <= >= => < > = + - * / % ? :
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    LSQUARE = "LSQUARE"
    RSQUARE = "RSQUARE"
    COMMA = "COMMA"
    DOT = "DOT"
    NEWLINE = "NEWLINE"
    EOF = "EOF"


class Tok(NamedTuple):
    type: TokType
    value: str
    line: int
    col: int


class PineLexError(SyntaxError):
    """A character the lexer does not recognise. Never swallowed — see module docstring."""


# Control-flow / literal / logical words. Type words (int/float/bool/string/color) are
# deliberately left as IDENT: they double as namespaces (color.new) and the parser, not
# the lexer, is the place to tell those apart.
KEYWORDS = frozenset({
    "if", "else", "for", "to", "by", "while", "switch", "var", "varip",
    "and", "or", "not", "true", "false", "na", "import", "export", "method",
    "type", "continue", "break",
})

# Multi-char operators, longest first so ':=' is not read as ':' then '='.
_OPS3 = ()
_OPS2 = (":=", "==", "!=", "<=", ">=", "=>")
_OPS1 = ("=", "<", ">", "+", "-", "*", "/", "%", "?", ":")

_ID_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_ID_CONT = _ID_START | set("0123456789")
_DIGIT = set("0123456789")
_HEX = set("0123456789abcdefABCDEF")


def tokenize(src: str, name: str = "<pine>") -> list[Tok]:
    """Full token list ending in EOF. Raises PineLexError on an unrecognised character."""
    toks: list[Tok] = []
    i, n = 0, len(src)
    line, line_start = 1, 0

    def col(pos: int) -> int:
        return pos - line_start + 1

    def err(pos: int, msg: str):
        raise PineLexError(f"{name}:{line}:{col(pos)}: {msg}")

    while i < n:
        c = src[i]

        # newline
        if c == "\n":
            toks.append(Tok(TokType.NEWLINE, "\\n", line, col(i)))
            i += 1
            line += 1
            line_start = i
            continue
        # horizontal whitespace
        if c in " \t\r":
            i += 1
            continue
        # line comment (incl. //@version=6 and other annotations)
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        # string
        if c == '"':
            start = i
            i += 1
            buf = []
            while i < n and src[i] != '"':
                if src[i] == "\\" and i + 1 < n:      # escape: keep the escaped char
                    buf.append(src[i + 1])
                    i += 2
                    continue
                if src[i] == "\n":
                    err(start, "unterminated string literal")
                buf.append(src[i])
                i += 1
            if i >= n:
                err(start, "unterminated string literal")
            i += 1                                     # closing quote
            toks.append(Tok(TokType.STRING, "".join(buf), line, col(start)))
            continue
        # color literal  #RRGGBB or #RRGGBBAA
        if c == "#":
            start = i
            j = i + 1
            while j < n and src[j] in _HEX:
                j += 1
            hexlen = j - (i + 1)
            if hexlen not in (6, 8):
                err(start, f"invalid color literal (expected #RRGGBB or #RRGGBBAA)")
            toks.append(Tok(TokType.COLOR, src[i:j], line, col(start)))
            i = j
            continue
        # number:  digits [. digits] [e[+-]digits]  |  . digits
        if c in _DIGIT or (c == "." and i + 1 < n and src[i + 1] in _DIGIT):
            start = i
            while i < n and src[i] in _DIGIT:
                i += 1
            if i < n and src[i] == ".":
                i += 1
                while i < n and src[i] in _DIGIT:
                    i += 1
            if i < n and src[i] in "eE":
                k = i + 1
                if k < n and src[k] in "+-":
                    k += 1
                if k < n and src[k] in _DIGIT:
                    i = k
                    while i < n and src[i] in _DIGIT:
                        i += 1
            toks.append(Tok(TokType.NUMBER, src[start:i], line, col(start)))
            continue
        # identifier / keyword
        if c in _ID_START:
            start = i
            while i < n and src[i] in _ID_CONT:
                i += 1
            word = src[start:i]
            tt = TokType.KEYWORD if word in KEYWORDS else TokType.IDENT
            toks.append(Tok(tt, word, line, col(start)))
            continue
        # structural single chars
        simple = {"(": TokType.LPAREN, ")": TokType.RPAREN, "[": TokType.LSQUARE,
                  "]": TokType.RSQUARE, ",": TokType.COMMA}
        if c in simple:
            toks.append(Tok(simple[c], c, line, col(i)))
            i += 1
            continue
        if c == ".":
            toks.append(Tok(TokType.DOT, ".", line, col(i)))
            i += 1
            continue
        # operators, longest match first
        two = src[i:i + 2]
        if two in _OPS2:
            toks.append(Tok(TokType.OP, two, line, col(i)))
            i += 2
            continue
        if c in _OPS1:
            toks.append(Tok(TokType.OP, c, line, col(i)))
            i += 1
            continue
        # anything else is refused, loudly
        err(i, f"unrecognised character {c!r} (0x{ord(c):02x})")

    toks.append(Tok(TokType.EOF, "", line, col(i)))
    return toks
