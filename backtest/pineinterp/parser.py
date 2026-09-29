"""Pine expression parser — increment 3 (core) of the interpreter (D-101).

Precedence-climbing (Pratt) parser over the lexer's tokens, building a small AST for the
expression grammar the fleet uses. Like every layer here it HARD-FAILS (PineParseError,
with line+col) on anything it cannot parse — a parser that guessed past an unfamiliar form
would seed a plausible, wrong backtest.

Scope of THIS module: expressions — literals, names, `na`, calls with positional AND named
args (`input.int(9, "len", minval=1)`), member access (`ta.ema`, `strategy.position_size`),
history refs (`close[1]`), unary `-`/`not`, the binary operators with Pine precedence, and
the ternary `?:`. Statements (typed declarations, `:=`, `if/for/switch` blocks, `f(...) =>`
function definitions with indented bodies) are increment 3b; the evaluator is increment 4.

Pine operator precedence, low to high (Pine reference):
    ?:            (ternary, right-assoc)
    or
    and
    == != < > <= >=
    + -
    * / %
    unary  - + not
    postfix  call()  member.  history[]
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lexer import Tok, TokType, tokenize


class PineParseError(SyntaxError):
    """A token sequence the parser does not accept. Never guessed past — see docstring."""


# --- AST ---------------------------------------------------------------------
@dataclass
class Node:
    line: int = field(default=0, kw_only=True)


@dataclass
class Num(Node):
    value: float


@dataclass
class Str(Node):
    value: str


@dataclass
class Color(Node):
    value: str


@dataclass
class Bool(Node):
    value: bool


@dataclass
class Na(Node):
    pass


@dataclass
class Name(Node):
    ident: str


@dataclass
class Unary(Node):
    op: str
    operand: Node


@dataclass
class Binary(Node):
    op: str
    left: Node
    right: Node


@dataclass
class Ternary(Node):
    cond: Node
    then: Node
    otherwise: Node


@dataclass
class Member(Node):
    obj: Node
    attr: str


@dataclass
class Index(Node):          # history reference:  expr[n]
    obj: Node
    index: Node


@dataclass
class Arg:
    value: Node
    name: str | None = None      # named argument (kwarg) or None for positional


@dataclass
class Call(Node):
    func: Node
    args: list[Arg]


# --- precedence tables -------------------------------------------------------
_BINARY_PREC = {
    "or": 1, "and": 2,
    "==": 3, "!=": 3, "<": 3, ">": 3, "<=": 3, ">=": 3,
    "+": 4, "-": 4,
    "*": 5, "/": 5, "%": 5,
}
_MAX_PREC = 5


class _Parser:
    def __init__(self, toks: list[Tok], name: str):
        # expression parsing ignores NEWLINE (statement layer handles line structure);
        # inside an expression a NEWLINE only appears within brackets, where it is noise.
        self.toks = [t for t in toks if t.type != TokType.NEWLINE]
        self.name = name
        self.i = 0

    def _peek(self) -> Tok:
        return self.toks[self.i]

    def _next(self) -> Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def _err(self, t: Tok, msg: str):
        raise PineParseError(f"{self.name}:{t.line}:{t.col}: {msg} (got {t.type.name} {t.value!r})")

    def _expect(self, tt: TokType) -> Tok:
        t = self._peek()
        if t.type != tt:
            self._err(t, f"expected {tt.name}")
        return self._next()

    # expression = ternary
    def parse_expr(self) -> Node:
        return self._ternary()

    def _ternary(self) -> Node:
        cond = self._binary(1)
        t = self._peek()
        if t.type == TokType.OP and t.value == "?":
            self._next()
            then = self._ternary()
            c = self._peek()
            if not (c.type == TokType.OP and c.value == ":"):
                self._err(c, "expected ':' in ternary")
            self._next()
            otherwise = self._ternary()
            return Ternary(cond, then, otherwise, line=cond.line)
        return cond

    def _binary(self, min_prec: int) -> Node:
        left = self._unary()
        while True:
            t = self._peek()
            op = t.value if t.type in (TokType.OP, TokType.KEYWORD) else None
            prec = _BINARY_PREC.get(op) if op else None
            if prec is None or prec < min_prec:
                return left
            self._next()
            right = self._binary(prec + 1)         # left-assoc
            left = Binary(op, left, right, line=left.line)

    def _unary(self) -> Node:
        t = self._peek()
        if (t.type == TokType.OP and t.value in ("-", "+")) or (t.type == TokType.KEYWORD and t.value == "not"):
            self._next()
            return Unary(t.value, self._unary(), line=t.line)
        return self._postfix()

    def _postfix(self) -> Node:
        node = self._primary()
        while True:
            t = self._peek()
            if t.type == TokType.LPAREN:            # call
                self._next()
                args = self._arg_list()
                self._expect(TokType.RPAREN)
                node = Call(node, args, line=node.line)
            elif t.type == TokType.DOT:             # member
                self._next()
                attr = self._expect(TokType.IDENT)
                node = Member(node, attr.value, line=node.line)
            elif t.type == TokType.LSQUARE:         # history ref
                self._next()
                idx = self.parse_expr()
                self._expect(TokType.RSQUARE)
                node = Index(node, idx, line=node.line)
            else:
                return node

    def _arg_list(self) -> list[Arg]:
        args: list[Arg] = []
        if self._peek().type == TokType.RPAREN:
            return args
        while True:
            # named arg?  IDENT '=' expr   (but '==' is comparison, so only single '=')
            if (self._peek().type == TokType.IDENT and self.i + 1 < len(self.toks)
                    and self.toks[self.i + 1].type == TokType.OP
                    and self.toks[self.i + 1].value == "="):
                nm = self._next().value
                self._next()                        # '='
                args.append(Arg(self.parse_expr(), name=nm))
            else:
                args.append(Arg(self.parse_expr()))
            if self._peek().type == TokType.COMMA:
                self._next()
                continue
            return args

    def _primary(self) -> Node:
        t = self._next()
        if t.type == TokType.NUMBER:
            return Num(float(t.value), line=t.line)
        if t.type == TokType.STRING:
            return Str(t.value, line=t.line)
        if t.type == TokType.COLOR:
            return Color(t.value, line=t.line)
        if t.type == TokType.KEYWORD:
            if t.value in ("true", "false"):
                return Bool(t.value == "true", line=t.line)
            if t.value == "na":
                return Na(line=t.line)
            self._err(t, "unexpected keyword in expression")
        if t.type == TokType.IDENT:
            return Name(t.value, line=t.line)
        if t.type == TokType.LPAREN:
            inner = self.parse_expr()
            self._expect(TokType.RPAREN)
            return inner
        self._err(t, "expected an expression")


def parse_expression(src: str, name: str = "<expr>") -> Node:
    """Parse a single Pine expression into an AST. Raises PineParseError (or PineLexError)
    on anything unparseable. Trailing tokens after a complete expression are an error —
    the caller asked for one expression."""
    p = _Parser(tokenize(src, name=name), name)
    node = p.parse_expr()
    if p._peek().type != TokType.EOF:
        p._err(p._peek(), "unexpected trailing tokens after expression")
    return node
